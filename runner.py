#!/usr/bin/env python3
import asyncio, html, json, os, random, re, sys, time
from argparse import ArgumentParser
import aiohttp

UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]
RX_T = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
RX_M = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?([\w-]+)""", re.I)
RX_C = re.compile(r"charset=([\w-]+)", re.I)
RETRY = ("eof", "reset", "refused", "disconnect", "closed", "aborted")

try:
    from charset_normalizer import from_bytes as _sniff
except Exception:
    _sniff = None


def dec(raw, ct):
    e = None
    if ct:
        m = RX_C.search(ct)
        if m:
            e = m.group(1)
    if not e:
        m = RX_M.search(raw[:4096])
        if m:
            e = m.group(1).decode("ascii", "ignore")
    if not e and _sniff:
        try:
            b = _sniff(raw[:16384]).best()
            if b and b.encoding:
                e = b.encoding
        except Exception:
            pass
    try:
        return raw.decode(e or "utf-8", "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def norm(s, n=200):
    if not s:
        return ""
    s = re.sub(r"\s+", " ", html.unescape(s)).strip()
    return s[:n] + "\u2026" if len(s) > n else s


def err(e):
    s = (str(e) or e.__class__.__name__).lower()
    if "dns" in s or "resolve" in s or "nodename" in s or "getaddrinfo" in s:
        return "d1"
    if "timeout" in s or "timed out" in s:
        return "t1"
    if "ssl" in s or "certificate" in s:
        return "s1"
    if "refused" in s:
        return "r1"
    if "reset" in s:
        return "r2"
    if "disconnect" in s or "closed" in s or "eof" in s:
        return "e1"
    return "x1"


async def head(resp, cap):
    ct = resp.headers.get("Content-Type", "")
    if ct and not any(k in ct.lower() for k in ("html", "xml", "text/plain")):
        return ""
    buf = bytearray()
    try:
        async for ch in resp.content.iter_chunked(8192):
            buf.extend(ch)
            if b"</title>" in bytes(buf[-8192:]).lower() or len(buf) >= cap:
                break
    except Exception:
        pass
    if not buf:
        return ""
    m = RX_T.search(dec(bytes(buf), ct))
    return norm(m.group(1)) if m else ""


async def one(sess, tgt, o, sem):
    row = {"i": tgt, "u": tgt, "s": 0, "e": "", "ms": 0}
    t0 = time.perf_counter()
    cands = [tgt] if "://" in tgt else ["https://" + tgt, "http://" + tgt]
    for i, url in enumerate(cands):
        if i and time.perf_counter() - t0 > o.timeout:
            break
        row["u"] = url
        att = 0
        while True:
            try:
                async with sem:
                    async with sess.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=o.timeout),
                        allow_redirects=True,
                        max_redirects=10,
                        headers={"User-Agent": random.choice(UA) if o.rotate else UA[0]},
                    ) as r:
                        row["s"] = r.status
                        row["f"] = str(r.url)
                        row["t"] = "" if o.skip else await head(r, o.cap)
                row["e"] = ""
                row["ms"] = int((time.perf_counter() - t0) * 1000)
                return row
            except Exception as ex:
                k = err(ex)
                if att < o.retry and any(m in str(ex).lower() for m in RETRY):
                    att += 1
                    await asyncio.sleep(0.5 * att)
                    continue
                row["e"] = k
                row["s"] = 0
                row["ms"] = int((time.perf_counter() - t0) * 1000)
                break
        if row["s"]:
            break
    return row


async def main(o):
    tg = []
    for f in o.list:
        with open(f, encoding="utf-8", errors="replace") as fh:
            tg += [x.strip() for x in fh]
    tg = [x for x in tg if x and not x.startswith("#")]
    if o.dedup:
        tg = list(dict.fromkeys(tg))
    if not tg:
        print("no targets")
        return 2

    try:
        res = aiohttp.ThreadedResolver()
    except Exception:
        res = None
    kw = dict(limit=o.conc * 2, limit_per_host=8, ttl_dns_cache=300)
    if res:
        kw["resolver"] = res
    conn = aiohttp.TCPConnector(**kw)
    sem = asyncio.Semaphore(o.conc)
    out = []

    async with aiohttp.ClientSession(connector=conn) as sess:
        async def w(t):
            r = await one(sess, t, o, sem)
            out.append(r)
            if o.verbose:
                print(json.dumps(r, ensure_ascii=False), flush=True)

        t0 = time.time()
        await asyncio.gather(*[asyncio.create_task(w(t)) for t in tg])

    ok = [r for r in out if r["s"]]
    bad = len(out) - len(ok)
    print("total %d ok %d fail %d sec %.1f" % (len(out), len(ok), bad, time.time() - t0))

    if o.out:
        with open(o.out, "w", encoding="utf-8", newline="") as fh:
            for r in out:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    else:
        for r in sorted(out, key=lambda x: -x["s"]):
            print(r["s"], r["u"], r.get("t", "") or r["e"])
    return 0


if __name__ == "__main__":
    p = ArgumentParser()
    p.add_argument("-l", "--list", action="append", default=[])
    p.add_argument("-o", "--out", default=None)
    p.add_argument("-c", "--conc", type=int, default=int(os.environ.get("C", "200")))
    p.add_argument("-t", "--timeout", type=float, default=15.0)
    p.add_argument("-r", "--retry", type=int, default=2)
    p.add_argument("--cap", type=int, default=131072)
    p.add_argument("--skip", action="store_true")
    p.add_argument("--dedup", action="store_true")
    p.add_argument("--rotate", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    sys.exit(asyncio.run(main(p.parse_args())))

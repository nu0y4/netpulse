#!/usr/bin/env python3
import argparse, asyncio, json, os, re, sys, time
from playwright.async_api import async_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

DEFAULT = {
    "limit": 200,
    "codes": "2xx",
    "width": 1440,
    "height": 900,
    "quality": 80,
    "full_page": False,
    "concurrency": 4,
    "wait_ms": 800,
    "timeout": 25000,
    "scale": 1,
}


def slug(u):
    s = re.sub(r"^[a-z]+://", "", u or "")
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
    return (s[:56].strip("_") or "page")


def want(code, spec):
    if not spec or spec == "all":
        return True
    for tok in str(spec).split(","):
        tok = tok.strip().lower()
        if not tok:
            continue
        if tok.endswith("xx") and len(tok) == 3 and tok[0].isdigit():
            lo = int(tok[0]) * 100
            if lo <= code <= lo + 99:
                return True
        elif tok.isdigit() and int(tok) == code:
            return True
    return False


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--in", dest="inp", required=True)
    ap.add_argument("-d", "--dir", dest="dir", default="shots")
    ap.add_argument("-o", "--out", dest="out", default="shots.json")
    ap.add_argument("--opt", dest="opt", default=None)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    cfg = dict(DEFAULT)
    if a.opt and os.path.exists(a.opt):
        try:
            cfg.update(json.load(open(a.opt, encoding="utf-8")))
        except Exception as e:
            print("bad opt.json:", e)

    rows = []
    for line in open(a.inp, encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))

    picked = [r for r in rows if r.get("s") and want(int(r["s"]), cfg["codes"])]
    if len(picked) > cfg["limit"]:
        picked = picked[:cfg["limit"]]
    print("probed=%d picked=%d limit=%d" % (len(rows), len(picked), cfg["limit"]))
    if not picked:
        json.dump([], open(a.out, "w", encoding="utf-8"))
        return 0

    os.makedirs(a.dir, exist_ok=True)
    sem = asyncio.Semaphore(max(1, int(cfg["concurrency"])))
    out = []
    t0 = time.time()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                  "--hide-scrollbars", "--mute-audio"],
        )
        ctx = await browser.new_context(
            viewport={"width": int(cfg["width"]), "height": int(cfg["height"])},
            device_scale_factor=float(cfg.get("scale", 1)),
            ignore_https_errors=True,
            user_agent=UA,
        )

        async def one(idx, row):
            async with sem:
                name = "%04d_%s.jpg" % (idx, slug(row.get("u")))
                path = os.path.join(a.dir, name)
                rec = {
                    "seq": idx, "url": row.get("u"), "status": row.get("s"),
                    "title": row.get("t", ""), "file": name,
                    "ok": False, "ms": 0, "bytes": 0, "error": "",
                }
                page = None
                ts = time.perf_counter()
                try:
                    page = await ctx.new_page()
                    await page.goto(row["u"], wait_until="domcontentloaded",
                                    timeout=int(cfg["timeout"]))
                    if cfg.get("wait_ms"):
                        await page.wait_for_timeout(int(cfg["wait_ms"]))
                    await page.screenshot(
                        path=path, full_page=bool(cfg.get("full_page")),
                        type="jpeg", quality=int(cfg["quality"]),
                    )
                    rec["ok"] = True
                    rec["bytes"] = os.path.getsize(path)
                except Exception as e:
                    rec["error"] = str(e)[:160]
                finally:
                    if page is not None:
                        try:
                            await page.close()
                        except Exception:
                            pass
                rec["ms"] = int((time.perf_counter() - ts) * 1000)
                out.append(rec)
                if a.verbose or not rec["ok"]:
                    print("  %-5s %-58s %s" % (rec["status"], (rec["url"] or "")[:58],
                                               "ok %.0fKB" % (rec["bytes"]/1024) if rec["ok"] else "FAIL " + rec["error"][:60]))
                return rec

        await asyncio.gather(*[asyncio.create_task(one(i + 1, r)) for i, r in enumerate(picked)])
        await ctx.close()
        await browser.close()

    out.sort(key=lambda x: x["seq"])
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    good = sum(1 for x in out if x["ok"])
    total = sum(x["bytes"] for x in out)
    print("done shots=%d ok=%d failed=%d size=%.1fMB sec=%.1f" %
          (len(out), good, len(out) - good, total/1024/1024, time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

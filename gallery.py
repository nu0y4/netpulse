#!/usr/bin/env python3
"""把截图结果生成一个可以直接双击打开的画廊页。"""
import argparse, html, json, os, sys, time

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#0f1218;color:#e6e9ef;
 font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif}
header{padding:20px 26px 14px;border-bottom:1px solid #232936;position:sticky;top:0;
 background:rgba(15,18,24,.92);backdrop-filter:blur(8px);z-index:5}
h1{margin:0 0 6px;font-size:17px;font-weight:650}
.stat{font-size:12.5px;color:#8b94a7}
.stat b{color:#4ade80}
.stat i{color:#f87171;font-style:normal}
.bar{padding:12px 26px;display:flex;gap:10px;flex-wrap:wrap;align-items:center;
 border-bottom:1px solid #232936;position:sticky;top:74px;background:rgba(15,18,24,.92);z-index:4}
.bar input{background:#181d27;border:1px solid #2a3140;color:#e6e9ef;border-radius:7px;
 padding:7px 11px;font-size:13px;width:260px;outline:none}
.bar input:focus{border-color:#3b82f6}
.bar button{background:#181d27;border:1px solid #2a3140;color:#c3cad8;border-radius:7px;
 padding:7px 13px;font-size:12.5px;cursor:pointer}
.bar button:hover{border-color:#3b82f6;color:#fff}
.bar button.on{background:#3b82f6;border-color:#3b82f6;color:#fff}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px;padding:20px 26px 60px}
.card{background:#161b24;border:1px solid #232936;border-radius:11px;overflow:hidden;
 text-decoration:none;color:inherit;display:flex;flex-direction:column;transition:.16s}
.card:hover{border-color:#3b82f6;transform:translateY(-2px)}
.thumb{width:100%;aspect-ratio:16/10;object-fit:cover;object-position:top;background:#0b0e13;display:block}
.meta{padding:10px 12px 12px}
.row1{display:flex;gap:7px;align-items:center;margin-bottom:5px}
.code{font-family:Consolas,monospace;font-weight:700;font-size:12px;padding:1px 7px;border-radius:5px}
.c2{color:#4ade80;background:rgba(74,222,128,.13)}
.c3{color:#60a5fa;background:rgba(96,165,250,.13)}
.c4{color:#fbbf24;background:rgba(251,191,36,.13)}
.c5{color:#f87171;background:rgba(248,113,113,.13)}
.c0{color:#94a3b8;background:rgba(148,163,184,.13)}
.url{font-size:11.5px;color:#93a0b5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
 font-family:Consolas,monospace;flex:1}
.title{font-size:12.5px;color:#d5dbe6;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fail{padding:26px 14px;text-align:center;color:#f87171;font-size:12.5px;background:#1a1216}
.empty{padding:70px;text-align:center;color:#6b7488}
#lb{position:fixed;inset:0;background:rgba(5,7,10,.96);display:none;z-index:50;
 align-items:center;justify-content:center;flex-direction:column;padding:26px}
#lb.on{display:flex}
#lb img{max-width:100%;max-height:calc(100vh - 110px);border-radius:8px;box-shadow:0 20px 60px rgba(0,0,0,.6)}
#lb .cap{margin-top:14px;font-size:13px;color:#c3cad8;max-width:90vw;text-align:center;word-break:break-all}
#lb .nav{position:absolute;top:50%;transform:translateY(-50%);font-size:40px;color:#5b6577;
 cursor:pointer;padding:14px;user-select:none;line-height:1}
#lb .nav:hover{color:#fff}
#prev{left:14px}#next{right:14px}
#close{position:absolute;top:16px;right:22px;font-size:30px;color:#5b6577;cursor:pointer;line-height:1}
#close:hover{color:#fff}
"""

JS = """
var cards=[].slice.call(document.querySelectorAll('.card[data-img]'));
var cur=-1, lb=document.getElementById('lb'), im=document.getElementById('lbi'), cp=document.getElementById('lbc');
function show(i){ if(i<0||i>=cards.length) return; cur=i;
  var c=cards[i]; im.src=c.getAttribute('data-img');
  cp.textContent=c.getAttribute('data-cap')||''; lb.classList.add('on'); }
function hide(){ lb.classList.remove('on'); im.src=''; cur=-1; }
cards.forEach(function(c,i){ c.addEventListener('click',function(e){ e.preventDefault(); show(i); }); });
document.getElementById('next').addEventListener('click',function(e){ e.stopPropagation(); show(cur+1); });
document.getElementById('prev').addEventListener('click',function(e){ e.stopPropagation(); show(cur-1); });
document.getElementById('close').addEventListener('click',hide);
lb.addEventListener('click',function(e){ if(e.target===lb) hide(); });
document.addEventListener('keydown',function(e){
  if(e.key==='Escape') hide();
  else if(e.key==='ArrowRight'&&cur>=0) show(cur+1);
  else if(e.key==='ArrowLeft'&&cur>=0) show(cur-1);
});
var q=document.getElementById('q');
q.addEventListener('input',function(){
  var v=q.value.toLowerCase(), n=0;
  cards.forEach(function(c){
    var hit=!v||c.getAttribute('data-key').indexOf(v)>=0;
    c.style.display=hit?'':'none'; if(hit) n++;
  });
  document.getElementById('shown').textContent=n;
});
var fo=document.getElementById('fo'); fo.addEventListener('click',function(){
  var on=fo.classList.toggle('on'); fo.textContent=on?'只看成功':'全部';
  cards.forEach(function(c){ c.style.display=(on&&c.getAttribute('data-ok')!=='1')?'none':''; });
});
"""


def cls(code):
    c = int(code or 0)
    if not c:
        return "c0"
    if c < 300:
        return "c2"
    if c < 400:
        return "c3"
    if c < 500:
        return "c4"
    return "c5"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--in", dest="inp", required=True)
    ap.add_argument("-o", "--out", dest="out", default="gallery.html")
    ap.add_argument("-t", "--title", dest="title", default="页面截图")
    a = ap.parse_args()

    rows = json.load(open(a.inp, encoding="utf-8"))
    rows.sort(key=lambda r: (not r.get("ok"), r.get("seq", 0)))
    ok = sum(1 for r in rows if r.get("ok"))
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")

    parts = []
    parts.append("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>")
    parts.append("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    parts.append("<title>" + html.escape(a.title) + "</title>")
    parts.append("<style>" + CSS + "</style></head><body>")
    parts.append("<header><h1>" + html.escape(a.title) + "</h1>")
    parts.append("<div class='stat'>共 " + str(len(rows)) + " 张，成功 <b>" + str(ok) +
                 "</b>，失败 <i>" + str(len(rows) - ok) + "</i> · 生成于 " + stamp + "</div></header>")
    parts.append("<div class='bar'><input id='q' placeholder='搜索 URL / 标题'>")
    parts.append("<button id='fo'>全部</button>")
    parts.append("<span class='stat'>显示 <b id='shown'>" + str(len(rows)) + "</b> / " + str(len(rows)) + "</span></div>")

    if not rows:
        parts.append("<div class='empty'>没有截图。可能是没有存活目标，或全部被过滤掉了。</div>")
    else:
        parts.append("<div class='grid'>")
        for r in rows:
            url = r.get("url") or ""
            title = r.get("title") or ""
            code = r.get("status") or 0
            f = r.get("file") or ""
            cap = str(code) + "  " + url + ("  |  " + title if title else "")
            key = (url + " " + title).lower().replace("'", "")
            if r.get("ok"):
                parts.append(
                    "<a class='card' href='shots/" + html.escape(f) + "' data-img='shots/" +
                    html.escape(f) + "' data-cap=\"" + html.escape(cap).replace('"', "&quot;") +
                    "\" data-key=\"" + html.escape(key).replace('"', "&quot;") + "\" data-ok='1'>")
                parts.append("<img class='thumb' loading='lazy' src='shots/" + html.escape(f) + "' alt=''>")
            else:
                parts.append("<div class='card' data-key=\"" + html.escape(key).replace('"', "&quot;") + "\" data-ok='0'>")
                parts.append("<div class='fail'>截图失败<br>" + html.escape((r.get("error") or "")[:120]) + "</div>")
            parts.append("<div class='meta'><div class='row1'><span class='code " + cls(code) + "'>" +
                         (str(code) if code else "ERR") + "</span>")
            parts.append("<span class='url'>" + html.escape(url) + "</span></div>")
            if title:
                parts.append("<div class='title'>" + html.escape(title) + "</div>")
            parts.append("</div>")
            parts.append("</a>" if r.get("ok") else "</div>")
        parts.append("</div>")

    parts.append("<div id='lb'><span id='close'>&times;</span><span class='nav' id='prev'>&#8249;</span>")
    parts.append("<img id='lbi' alt=''><div class='cap' id='lbc'></div>")
    parts.append("<span class='nav' id='next'>&#8250;</span></div>")
    parts.append("<script>" + JS + "</script></body></html>")

    open(a.out, "w", encoding="utf-8").write("\n".join(parts))
    print("gallery written: %s (%d items, %d ok)" % (a.out, len(rows), ok))
    return 0


if __name__ == "__main__":
    sys.exit(main())

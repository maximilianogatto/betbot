"""Capture a competition page + an event page, logging ALL requests.

Run: ./betbot/bin/python sandbox/betsson/capture_v2.py <url-path>
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "captures_v2"
OUT.mkdir(parents=True, exist_ok=True)
PATH = sys.argv[1] if len(sys.argv) > 1 else "apuestas-deportivas/futbol/mundial/copa-del-mundo"
START = f"https://cba.betsson.bet.ar/{PATH}"
SKIP = re.compile(r"\.(png|jpg|jpeg|gif|svg|woff2?|ttf|css|js|ico)(\?|$)", re.I)

def safe(url, idx):
    return f"body_{idx:03d}_" + re.sub(r"[^a-zA-Z0-9]+","_",url.split("?")[0])[-46:] + ".txt"

def main():
    reqs=[]; bodies=[]; idx=0
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True)
        ctx=b.new_context(user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Chrome/124",
            viewport={"width":414,"height":896},is_mobile=True,locale="es-AR")
        pg=ctx.new_page()
        pg.on("request", lambda r: reqs.append(r.url) if "betsson.bet.ar" in r.url and not SKIP.search(r.url) else None)
        def on_resp(resp):
            nonlocal idx
            try:
                url=resp.url; ct=(resp.headers or {}).get("content-type","")
                if "betsson.bet.ar" not in url or SKIP.search(url): return
                if "json" not in ct and resp.request.resource_type not in ("xhr","fetch"): return
                idx+=1; fn=safe(url,idx)
                try: body=resp.text()
                except: body=""
                (OUT/fn).write_text(body[:3_000_000],encoding="utf-8")
                bodies.append({"idx":idx,"url":url,"status":resp.status,"len":len(body),"file":fn,"req_headers":dict(resp.request.headers or {})})
                print(f"[{idx:03d}] {resp.status} {url[:120]}")
            except Exception as e: print("err",e)
        pg.on("response", on_resp)
        print("== goto", START)
        pg.goto(START, wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(6000)
        pg.screenshot(path=str(OUT/"comp.png"), full_page=False)
        # try clicking first event row to load an event page
        for sel in ["[class*=event-row]","[class*=EventRow]","[href*='/apuestas-deportivas/futbol/']","[class*=participant]"]:
            try:
                loc=pg.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=3000); print("clicked",sel)
                    pg.wait_for_timeout(6000)
                    pg.screenshot(path=str(OUT/"event.png"),full_page=False)
                    break
            except Exception: pass
        b.close()
    (OUT/"index.json").write_text(json.dumps(bodies,indent=2))
    (OUT/"all_requests.json").write_text(json.dumps(sorted(set(reqs)),indent=2))
    print(f"\n{len(bodies)} bodies, {len(set(reqs))} distinct request urls")
    from collections import Counter
    c=Counter(u.split("?")[0].replace("https://cba.betsson.bet.ar","") for u in reqs)
    for u,n in c.most_common(40): print(f"  {n:3d} {u}")

if __name__=="__main__": main()

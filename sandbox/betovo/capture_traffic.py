"""Deep network capture for betovo848425.com (unknown sportsbook platform).

Loads the mobile site, records every XHR/fetch response, drives the UI a bit
(open sports / a league), and dumps interesting bodies for analysis.

Outputs:
  captures/index.json       -> [{idx,url,method,status,ctype,len,body_file}]
  captures/body_NNN_*.txt   -> raw response bodies (truncated if huge)

Run:  ./betbot/bin/python sandbox/bz/capture_traffic.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(parents=True, exist_ok=True)

START_URL = "https://www.betovo848425.com/"

SKIP_CTYPE = re.compile(r"(image/|font/|text/css|javascript)", re.IGNORECASE)
SKIP_URL = re.compile(r"\.(png|jpg|jpeg|gif|svg|woff2?|ttf|css|js)(\?|$)", re.IGNORECASE)


def _safe_name(url: str, idx: int) -> str:
    tail = re.sub(r"[^a-zA-Z0-9]+", "_", url.split("?")[0])[-60:]
    return f"body_{idx:03d}_{tail}.txt"


def main() -> None:
    records: list[dict] = []
    idx = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Chrome/124"
            ),
            viewport={"width": 414, "height": 896},
            is_mobile=True,
            locale="en-US",
        )
        page = ctx.new_page()

        def on_response(resp):
            nonlocal idx
            try:
                url = resp.url
                ctype = (resp.headers or {}).get("content-type", "")
                if SKIP_URL.search(url) or SKIP_CTYPE.search(ctype):
                    return
                if "json" not in ctype and resp.request.resource_type not in ("xhr", "fetch"):
                    return
                idx += 1
                body_file = _safe_name(url, idx)
                try:
                    body = resp.text()
                except Exception:
                    body = ""
                if len(body) > 2_000_000:
                    body = body[:2_000_000] + "\n...[TRUNCATED]"
                (OUT / body_file).write_text(body, encoding="utf-8")
                records.append(
                    {
                        "idx": idx,
                        "url": url,
                        "method": resp.request.method,
                        "status": resp.status,
                        "ctype": ctype,
                        "len": len(body),
                        "body_file": body_file,
                    }
                )
                print(f"[{idx:03d}] {resp.status} {resp.request.method} {url[:120]}")
            except Exception as exc:  # noqa: BLE001
                print("listener error:", exc)

        page.on("response", on_response)

        print("== loading", START_URL, "==")
        page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(9000)

        # Try to navigate into sports / a league. Best-effort selectors.
        for sel in [
            "text=/sports?/i",
            "text=/f[uú]tbol|soccer|football/i",
            "[class*=sport]",
            "[class*=league]",
            "[class*=match]",
        ]:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=2500)
                    print("clicked", sel)
                    page.wait_for_timeout(4000)
            except Exception:
                pass

        page.wait_for_timeout(4000)
        browser.close()

    (OUT / "index.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"\n== DONE: {len(records)} JSON/XHR responses captured -> {OUT}")
    hosts: dict[str, int] = {}
    for r in records:
        base = r["url"].split("?")[0]
        hosts[base] = hosts.get(base, 0) + 1
    print("\nDistinct endpoints:")
    for base, c in sorted(hosts.items(), key=lambda kv: -kv[1]):
        print(f"  {c:3d}x  {base}")


if __name__ == "__main__":
    main()

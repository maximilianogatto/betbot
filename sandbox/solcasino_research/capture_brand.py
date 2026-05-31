"""Discover Rainbet's Betby/sptpub brand id + api host via Playwright.

Rainbet runs the Betby sportsbook (sptpub.com feed). Each casino has its OWN
brand id + api host; the goal here is to capture them by loading the live
sportsbook and watching the network for sptpub/betby calls.

Outputs:
  captures/brand_requests.json  -> every sptpub/betby request seen (url, status)
  captures/brand_config.json    -> inferred {api_host, brand_id, language, feed}

Run:  ./betbot/bin/python sandbox/rainbet/capture_brand.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(parents=True, exist_ok=True)

# Candidate entry points (Rainbet may redirect / use a bt-path widget).
START_URLS = [
    "https://rainbet.com/sports",
    "https://rainbet.com/sports?bt-path=%2Fsoccer",
    "https://rainbet.com/",
]

BETBY_RE = re.compile(r"(sptpub\.com|betby\.com|betby\.io)", re.IGNORECASE)
# .../api/v4/<feed>/brand/<brand_id>/<lang>/<version>
FEED_RE = re.compile(
    r"https://([^/]+)/api/v\d+/(prematch|live)/brand/(\d+)/([a-z]{2})/(\d+)",
    re.IGNORECASE,
)


def main() -> None:
    seen: list[dict] = []
    configs: dict[str, dict] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/136.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
            locale="en-US",
        )
        page = ctx.new_page()

        def on_request(req):
            url = req.url
            if not BETBY_RE.search(url):
                return
            seen.append({"url": url, "method": req.method, "resource": req.resource_type})
            m = FEED_RE.match(url)
            if m:
                api_host, feed, brand_id, lang, version = m.groups()
                key = f"{api_host}|{brand_id}"
                configs[key] = {
                    "api_host": api_host,
                    "brand_id": brand_id,
                    "language": lang,
                    "feed": feed,
                }
                print(f"  >> FEED  host={api_host} brand={brand_id} feed={feed} lang={lang} v={version}")
            else:
                print(f"  .. betby {req.method} {url[:120]}")

        page.on("request", on_request)

        for url in START_URLS:
            print(f"== loading {url} ==")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:  # noqa: BLE001
                print("  goto error:", exc)
                continue
            page.wait_for_timeout(9000)
            # try clicking into a soccer/league area to force feed loads
            for sel in ["text=/soccer/i", "text=/f[uú]tbol/i", "[class*=sport]", "[class*=league]"]:
                try:
                    loc = page.locator(sel).first
                    if loc.count() and loc.is_visible():
                        loc.click(timeout=2500)
                        page.wait_for_timeout(3500)
                except Exception:
                    pass
            if configs:
                break  # got what we need

        browser.close()

    (OUT / "brand_requests.json").write_text(json.dumps(seen, indent=2), encoding="utf-8")
    (OUT / "brand_config.json").write_text(json.dumps(list(configs.values()), indent=2), encoding="utf-8")
    print(f"\n== DONE: {len(seen)} betby requests, {len(configs)} feed config(s) ==")
    for cfg in configs.values():
        print("  CONFIG:", cfg)
    if not configs:
        print("  (no feed config captured — page may be geo/CF-blocked; inspect brand_requests.json)")


if __name__ == "__main__":
    main()

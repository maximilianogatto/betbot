"""Deep network capture for mystake.bet prematch.

Loads the prematch SPA, attaches a response listener that records every
XHR/fetch the site makes, then drives the UI a little (open the league
directory, click into a couple of leagues) so we can see the full set of
endpoints the front-end actually uses.

Outputs:
  research/captures/index.json        -> list of {url, status, ctype, body_file}
  research/captures/body_NNN_*.json   -> raw response bodies (truncated if huge)

Run:  ./betbot/bin/python sandbox/mystake/research/capture_traffic.py
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "captures"
OUT.mkdir(parents=True, exist_ok=True)

PREMATCH_URL = "https://mystake.bet/as/sportsbook/prematch#/prematch/selection"

# Only keep bodies for endpoints that look like data (skip fonts/images/css/js bundles)
INTERESTING = re.compile(
    r"(prematch|directory|getAll|cache/get|getprematch|topgames|gameall|champ|tournament|league|sport|menu|tree|category)",
    re.IGNORECASE,
)
SKIP_CTYPE = re.compile(r"(image/|font/|text/css|javascript|text/html)", re.IGNORECASE)


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
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
            locale="en-US",
        )
        page = ctx.new_page()

        def on_response(resp):
            nonlocal idx
            try:
                url = resp.url
                ctype = (resp.headers or {}).get("content-type", "")
                if SKIP_CTYPE.search(ctype):
                    return
                if not INTERESTING.search(url):
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
                print(f"[{idx:03d}] {resp.status} {resp.request.method} {url[:110]}")
            except Exception as exc:  # noqa: BLE001
                print("listener error:", exc)

        page.on("response", on_response)

        print("== Loading prematch page ==")
        page.goto(PREMATCH_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)  # let initial XHRs fire

        # Try to open the "all leagues / directory" panel and click a few leagues.
        # Selectors are best-effort; failures are non-fatal — the listener already
        # captured the bootstrap traffic.
        clicks = [
            "text=/all leagues/i",
            "text=/todas las ligas/i",
            "text=/leagues/i",
            "[class*=league]",
            "[class*=tournament]",
            "[class*=category]",
        ]
        for sel in clicks:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=3000)
                    print(f"clicked {sel}")
                    page.wait_for_timeout(4000)
            except Exception:
                pass

        # Click into the sport / soccer tree items, then individual leagues.
        for sel in ["[class*=sport]", "[class*=region]", "[class*=country]"]:
            try:
                items = page.locator(sel)
                n = min(items.count(), 6)
                for i in range(n):
                    try:
                        it = items.nth(i)
                        if it.is_visible():
                            it.click(timeout=2000)
                            page.wait_for_timeout(2500)
                    except Exception:
                        pass
            except Exception:
                pass

        page.wait_for_timeout(4000)
        browser.close()

    (OUT / "index.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"\n== DONE: {len(records)} interesting responses captured -> {OUT}")
    # Quick summary of distinct endpoints
    hosts = {}
    for r in records:
        base = r["url"].split("?")[0]
        hosts[base] = hosts.get(base, 0) + 1
    print("\nDistinct endpoints:")
    for base, c in sorted(hosts.items(), key=lambda kv: -kv[1]):
        print(f"  {c:3d}x  {base}")


if __name__ == "__main__":
    main()

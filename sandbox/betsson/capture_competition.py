"""Navigate to a specific football competition page and capture the
fixtures/coupon endpoint (events list per competition).

Run: ./betbot/bin/python sandbox/betsson/capture_competition.py <slug>
e.g. sandbox/betsson/capture_competition.py futbol/mundial/copa-del-mundo
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "captures_comp"
OUT.mkdir(parents=True, exist_ok=True)

SLUG = sys.argv[1] if len(sys.argv) > 1 else "futbol/mundial/copa-del-mundo"
START_URL = f"https://cba.betsson.bet.ar/apuestas-deportivas/{SLUG}"

SKIP_URL = re.compile(r"\.(png|jpg|jpeg|gif|svg|woff2?|ttf|css|js)(\?|$)", re.IGNORECASE)


def _safe_name(url: str, idx: int) -> str:
    tail = re.sub(r"[^a-zA-Z0-9]+", "_", url.split("?")[0])[-50:]
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
            locale="es-AR",
        )
        page = ctx.new_page()

        def on_response(resp):
            nonlocal idx
            try:
                url = resp.url
                ctype = (resp.headers or {}).get("content-type", "")
                if SKIP_URL.search(url):
                    return
                if "json" not in ctype and resp.request.resource_type not in ("xhr", "fetch"):
                    return
                if "betsson.bet.ar" not in url:
                    return
                idx += 1
                body_file = _safe_name(url, idx)
                try:
                    body = resp.text()
                except Exception:
                    body = ""
                if len(body) > 3_000_000:
                    body = body[:3_000_000] + "\n...[TRUNCATED]"
                (OUT / body_file).write_text(body, encoding="utf-8")
                records.append({
                    "idx": idx, "url": url, "method": resp.request.method,
                    "status": resp.status, "ctype": ctype, "len": len(body),
                    "body_file": body_file,
                    "req_headers": dict(resp.request.headers or {}),
                })
                print(f"[{idx:03d}] {resp.status} {resp.request.method} {url[:130]}")
            except Exception as exc:  # noqa: BLE001
                print("listener error:", exc)

        page.on("response", on_response)
        print("== loading", START_URL, "==")
        page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(12000)
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(5000)
        browser.close()

    (OUT / "index.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"\n== DONE: {len(records)} responses -> {OUT}")
    hosts: dict[str, int] = {}
    for r in records:
        base = r["url"].split("?")[0]
        hosts[base] = hosts.get(base, 0) + 1
    for base, c in sorted(hosts.items(), key=lambda kv: -kv[1]):
        print(f"  {c:3d}x  {base.replace('https://cba.betsson.bet.ar','')}")


if __name__ == "__main__":
    main()

import asyncio
import json
from playwright.async_api import async_playwright

URL = "https://solcasino.io/sports?bt-path=%2Fsoccer%2Fitaly%2Fserie-a-1669819042829045760"
TOURNAMENT_ID = "1669819042829045760"
OUT = f"solca_{TOURNAMENT_ID}_merged.json"

def deep_merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst

def has_target(data):
    txt = json.dumps(data, ensure_ascii=False)
    return TOURNAMENT_ID in txt

async def main():
    merged = {
        "sports": {},
        "categories": {},
        "tournaments": {},
        "events": {},
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1600, "height": 1000})
        page = await context.new_page()

        async def on_response(response):
            url = response.url
            if "/api/v4/prematch/" not in url:
                return

            ctype = response.headers.get("content-type", "").lower()
            if "json" not in ctype:
                return

            try:
                data = await response.json()
            except Exception:
                return

            if not has_target(data):
                return

            deep_merge(merged, data)

            count = sum(
                1
                for e in merged.get("events", {}).values()
                if (e.get("desc") or {}).get("type") == "match"
                and str((e.get("desc") or {}).get("tournament")) == TOURNAMENT_ID
            )
            print(f"→ merge {len(merged['events'])} eventos totales | Serie A matches: {count}")

        page.on("response", on_response)

        print("Abriendo:", URL)
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        print("Esperando responses. Hacé scroll hasta el final si hace falta...")
        await page.wait_for_timeout(30000)

        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

        print("Guardado:", OUT)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
import asyncio
import json
from playwright.async_api import async_playwright

# URL = "https://solcasino.io/sports?bt-path=%2Fsoccer%2Fitaly%2Fserie-a-1669819042829045760"
URL = "https://solcasino.io/sports?bt-path=%2Fsoccer%2Fitaly%2Fserie-a-1669819042829045760"
TARGET_TOURNAMENT_ID = "1669819042829045760"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        async def on_response(response):
            ctype = response.headers.get("content-type", "").lower()
            if "json" not in ctype:
                return

            try:
                data = await response.json()
            except Exception:
                return

            text = json.dumps(data, ensure_ascii=False)

            if TARGET_TOURNAMENT_ID not in text:
                return

            filename = f"rainbet_{TARGET_TOURNAMENT_ID}.json"

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print("\nMATCH REAL")
            print("URL:", response.url)
            print("STATUS:", response.status)
            print("Archivo:", filename)
            print("events:", len(data.get("events", {})))
            print("tournament:", data.get("tournaments", {}).get(TARGET_TOURNAMENT_ID))

        page.on("response", on_response)

        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        print("Esperando. Scroll o recargá si hace falta.")
        await page.wait_for_timeout(120_000)

if __name__ == "__main__":
    asyncio.run(main())
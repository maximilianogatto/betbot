import asyncio
import json
import os
from playwright.async_api import async_playwright

# Setup responses directory
RESPONSES_DIR = "sandbox/palloliitto/responses"
os.makedirs(RESPONSES_DIR, exist_ok=True)

async def capture_endpoint(page, name, endpoint_url):
    print(f"Fetching {name} via browser context: {endpoint_url}...")
    try:
        # We execute fetch inside the browser context to bypass Cloudflare seamlessly
        js_code = f"""
        async () => {{
            const response = await fetch("{endpoint_url}");
            if (!response.ok) {{
                throw new Error("HTTP " + response.status + ": " + await response.text());
            }}
            return await response.json();
        }}
        """
        data = await page.evaluate(js_code)
        
        # Save response
        out_path = os.path.join(RESPONSES_DIR, f"{name}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        print(f"Successfully saved {name}.json ({len(str(data))} chars)")
        return data
    except Exception as e:
        print(f"Error fetching {name}: {e}")
        return None

async def main():
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        # We set a normal desktop user agent to avoid bot detection during page load
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print("Navigating to home page to establish Cloudflare session...")
        await page.goto("https://tulospalvelu.palloliitto.fi/", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(5)  # Wait for any cloudflare challenges / loads to settle
        
        # 1. Fetch Categories to see all leagues
        categories_url = "https://spl.torneopal.net/taso/rest/getCategories?season_id=2025-26,2026"
        categories_data = await capture_endpoint(page, "getCategories", categories_url)
        
        # 2. Fetch getSite
        await capture_endpoint(page, "getSite", "https://spl.torneopal.net/taso/rest/getSite")
        
        # 3. Fetch getChampions
        await capture_endpoint(page, "getChampions", "https://spl.torneopal.net/taso/rest/getChampions")
        
        # 4. Fetch getMatches for today
        import datetime
        today_str = datetime.date.today().isoformat()
        await capture_endpoint(page, f"getMatches_{today_str}", f"https://spl.torneopal.net/taso/rest/getMatches?date={today_str}")
        
        # If we successfully parsed categories, let's explore some categories
        if categories_data:
            # Let's see what is the structure of category
            # We print a few to inspect
            if isinstance(categories_data, list):
                print(f"Found {len(categories_data)} categories.")
                # We can find some major categories. Finnish top men's league is Veikkausliiga. Let's see if we can find it.
                # Let's filter some interesting categories to probe
                veikkausliiga_cats = [c for c in categories_data if "Veikkausliiga" in str(c.get("name", ""))]
                ykkosliiga_cats = [c for c in categories_data if "Ykkösliiga" in str(c.get("name", ""))]
                
                print("Sample Veikkausliiga categories:", veikkausliiga_cats[:2])
                print("Sample Ykkösliiga categories:", ykkosliiga_cats[:2])
                
                # Let's pick the first 3 categories to probe standings and matches
                for cat in categories_data[:5]:
                    cat_id = cat.get("category_id")
                    cat_name = cat.get("name", "Unknown").replace(" ", "_").replace("/", "_")
                    if cat_id:
                        # Fetch Standing for this category
                        await capture_endpoint(
                            page, 
                            f"getStanding_{cat_id}_{cat_name}", 
                            f"https://spl.torneopal.net/taso/rest/getStanding?category_id={cat_id}"
                        )
                        # Fetch Matches for this category
                        await capture_endpoint(
                            page, 
                            f"getCategoryMatches_{cat_id}_{cat_name}", 
                            f"https://spl.torneopal.net/taso/rest/getMatches?category_id={cat_id}"
                        )
            elif isinstance(categories_data, dict):
                print("Categories data is a dict. Keys:", list(categories_data.keys()))
        
        await browser.close()
        print("Done capturing network responses.")

if __name__ == "__main__":
    asyncio.run(main())

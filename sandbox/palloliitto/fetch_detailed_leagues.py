import asyncio
import json
import os
from playwright.async_api import async_playwright

RESPONSES_DIR = "sandbox/palloliitto/responses"
os.makedirs(RESPONSES_DIR, exist_ok=True)

async def capture_endpoint(page, name, endpoint_url):
    print(f"Fetching {name} from: {endpoint_url}...")
    try:
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
    # Read categories from getCategories.json
    cat_path = os.path.join(RESPONSES_DIR, "getCategories.json")
    if not os.path.exists(cat_path):
        print("getCategories.json not found! Please run capture_responses.py first.")
        return
        
    with open(cat_path, "r", encoding="utf-8") as f:
        categories_data = json.load(f)
        
    categories = categories_data.get("categories", [])
    print(f"Loaded {len(categories)} categories from getCategories.json")
    
    # We want to fetch for major men's and women's adult categories:
    # VL: Veikkausliiga, M1L: Ykkösliiga, M1: Ykkönen, M2: Kakkonen, NL: Kansallinen Liiga
    target_cats = ["VL", "M1L", "M1", "M2", "NL"]
    
    selected_cats = []
    for cat in categories:
        cat_id = cat.get("category_id")
        season_id = cat.get("season_id")
        if cat_id in target_cats and season_id == "2026":
            selected_cats.append(cat)
            
    print(f"Selected {len(selected_cats)} target categories for detailed probing:")
    for sc in selected_cats:
        print(f" - {sc.get('category_id')}: {sc.get('category_name')} ({sc.get('competition_id')})")
        
    async with async_playwright() as p:
        print("\nLaunching browser...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print("Navigating to home page...")
        await page.goto("https://tulospalvelu.palloliitto.fi/", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)
        
        # 1. Fetch Standing and Matches for each selected category
        for sc in selected_cats:
            cat_id = sc.get("category_id")
            name = sc.get("category_name").replace(" ", "_")
            
            # Fetch standing
            standing_url = f"https://spl.torneopal.net/taso/rest/getStanding?category_id={cat_id}"
            await capture_endpoint(page, f"getStanding_{cat_id}", standing_url)
            
            # Fetch matches (fixtures and results)
            matches_url = f"https://spl.torneopal.net/taso/rest/getMatches?category_id={cat_id}"
            await capture_endpoint(page, f"getMatches_{cat_id}", matches_url)
            
            # Torneopal has stats endpoints: getScorers, getStatistics, or getGroupDetails?
            # Let's try getScorers and see if it works!
            scorers_url = f"https://spl.torneopal.net/taso/rest/getScorers?category_id={cat_id}"
            await capture_endpoint(page, f"getScorers_{cat_id}", scorers_url)
            
        # 2. Let's try some generic or other parameters.
        # What if we fetch a specific match? We can find a match_id from the today matches.
        # Let's load getMatches_2026-06-01.json (or today matches) to find a match_id
        matches_today_files = [f for f in os.listdir(RESPONSES_DIR) if f.startswith("getMatches_")]
        if matches_today_files:
            today_path = os.path.join(RESPONSES_DIR, matches_today_files[0])
            with open(today_path, "r", encoding="utf-8") as f:
                today_data = json.load(f)
            matches_list = today_data.get("matches", [])
            print(f"\nFound {len(matches_list)} matches in today's matches.")
            # find a couple of matches to probe their details
            valid_matches = [m for m in matches_list if m.get("match_id")]
            if valid_matches:
                print(f"Sample match ID to probe: {valid_matches[0].get('match_id')}")
                for m in valid_matches[:3]:
                    m_id = m.get("match_id")
                    h_team = m.get("home_team_name", "Home")
                    a_team = m.get("away_team_name", "Away")
                    clean_name = f"{h_team}_vs_{a_team}".replace(" ", "_").replace("/", "_")
                    
                    # Fetch match details
                    match_url = f"https://spl.torneopal.net/taso/rest/getMatch?match_id={m_id}"
                    await capture_endpoint(page, f"getMatch_{m_id}_{clean_name}", match_url)
                    
        await browser.close()
        print("\nAll target category/match details captured.")

if __name__ == "__main__":
    asyncio.run(main())

import json
import os

RESPONSES_DIR = "sandbox/palloliitto/responses"

def analyze_categories():
    path = os.path.join(RESPONSES_DIR, "getCategories.json")
    if not os.path.exists(path):
        print("getCategories.json does not exist.")
        return
        
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    print("getCategories JSON type:", type(data).__name__)
    if isinstance(data, dict):
        print("Keys:", list(data.keys()))
        categories = data.get("categories", [])
        print("Number of categories:", len(categories))
        
        if categories:
            print("\nSample Category Structure:")
            print(json.dumps(categories[0], indent=2, ensure_ascii=False))
            
            # Let's see some categories
            print("\nFirst 20 categories:")
            for cat in categories[:20]:
                print(f"ID: {cat.get('category_id')}, Name: {cat.get('name')}, Club ID: {cat.get('club_id')}, Sex: {cat.get('sex')}, Age Category: {cat.get('age_category')}")
                
            # Filter some interesting ones (Men's adult categories usually have sex='M' and age_category='adult' or age_category=None)
            print("\nFiltered Adult Men's or prominent Categories (e.g. Veikkausliiga, Ykkösliiga, Cup):")
            prominent = []
            for cat in categories:
                name = cat.get("name", "")
                cat_id = cat.get("category_id")
                # Look for adult leagues or main levels
                if "liiga" in name.lower() or "cup" in name.lower() or "kakkonen" in name.lower() or "ykkönen" in name.lower() or "kolmonen" in name.lower():
                    prominent.append(cat)
                    
            print(f"Found {len(prominent)} prominent leagues.")
            for p in prominent[:30]:
                print(f"ID: {p.get('category_id')}, Name: {p.get('name')}, Sex: {p.get('sex')}, Season: {p.get('season_id')}")
                
            # Let's save a full list of categories to sandbox/palloliitto/categories_list.txt
            with open("sandbox/palloliitto/categories_list.txt", "w", encoding="utf-8") as out:
                out.write("CATEGORY_ID | NAME | SEX | AGE_CATEGORY | SEASON_ID\n")
                out.write("-" * 80 + "\n")
                for cat in categories:
                    out.write(f"{cat.get('category_id')} | {cat.get('name')} | {cat.get('sex')} | {cat.get('age_category')} | {cat.get('season_id')}\n")
            print("Saved full list to sandbox/palloliitto/categories_list.txt")

def analyze_matches():
    # Find any match file
    files = [f for f in os.listdir(RESPONSES_DIR) if f.startswith("getMatches")]
    if not files:
        print("No getMatches response file found.")
        return
        
    path = os.path.join(RESPONSES_DIR, files[0])
    print(f"\nAnalyzing match file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    print("getMatches JSON type:", type(data).__name__)
    if isinstance(data, dict):
        print("Keys:", list(data.keys()))
        matches = data.get("matches", [])
        print("Number of matches in file:", len(matches))
        if matches:
            print("\nSample Match Structure:")
            # find first match with some data
            sample_match = matches[0]
            for m in matches:
                if m.get("home_team_name") and m.get("away_team_name"):
                    sample_match = m
                    break
            print(json.dumps(sample_match, indent=2, ensure_ascii=False))

def analyze_site():
    path = os.path.join(RESPONSES_DIR, "getSite.json")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print("\ngetSite Keys:", list(data.keys()) if isinstance(data, dict) else "not dict")
    if isinstance(data, dict):
        print("Sample site configuration:")
        print(json.dumps(data.get("site", {}) if "site" in data else data, indent=2)[:500])

if __name__ == "__main__":
    analyze_categories()
    analyze_matches()
    analyze_site()

import json
import os
from curl_cffi import requests

def probe_endpoint(name, url):
    print(f"\nProbing {name} ({url})...")
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://tulospalvelu.palloliitto.fi",
        "Referer": "https://tulospalvelu.palloliitto.fi/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, impersonate="chrome", timeout=20.0)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            try:
                j = r.json()
                print("Type:", type(j).__name__)
                if isinstance(j, list):
                    print("Length:", len(j))
                    if j:
                        print("Sample item keys:", list(j[0].keys()) if hasattr(j[0], 'keys') else "not dict")
                        print("Sample item:", json.dumps(j[0], indent=2)[:500])
                elif isinstance(j, dict):
                    print("Keys:", list(j.keys()))
                    print("Sample:", json.dumps(j, indent=2)[:800])
                
                os.makedirs("sandbox/palloliitto/responses", exist_ok=True)
                with open(f"sandbox/palloliitto/responses/{name}.json", "w") as f:
                    json.dump(j, f, indent=2)
            except Exception as parse_err:
                print("JSON parsing failed, response text starts with:")
                print(r.text[:500])
        else:
            print("Error text:", r.text[:200])
    except Exception as e:
        print("Failed:", e)

def main():
    endpoints = {
        "getCategories": "https://spl.torneopal.net/taso/rest/getCategories?season_id=2025-26,2026",
        "getSite": "https://spl.torneopal.net/taso/rest/getSite",
        "getClubs": "https://spl.torneopal.net/taso/rest/getClubs",
        "getMatchesToday": "https://spl.torneopal.net/taso/rest/getMatches?date=2026-06-01",
        "getChampions": "https://spl.torneopal.net/taso/rest/getChampions",
    }
    
    for name, url in endpoints.items():
        probe_endpoint(name, url)

if __name__ == "__main__":
    main()

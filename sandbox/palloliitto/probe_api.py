import httpx
import json
import os

async def probe_endpoint(name, url):
    print(f"\nProbing {name} ({url})...")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url)
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
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
                
                # Save first 50 lines to a file for review
                os.makedirs("sandbox/palloliitto/responses", exist_ok=True)
                with open(f"sandbox/palloliitto/responses/{name}.json", "w") as f:
                    json.dump(j, f, indent=2)
            else:
                print("Error text:", r.text[:200])
    except Exception as e:
        print("Failed:", e)

import asyncio

async def main():
    # We will probe the main captured REST endpoints
    endpoints = {
        "getCategories": "https://spl.torneopal.net/taso/rest/getCategories?season_id=2025-26,2026",
        "getSite": "https://spl.torneopal.net/taso/rest/getSite",
        "getClubs": "https://spl.torneopal.net/taso/rest/getClubs",
        "getMatchesToday": "https://spl.torneopal.net/taso/rest/getMatches?date=2026-06-01",
        "getChampions": "https://spl.torneopal.net/taso/rest/getChampions",
    }
    
    for name, url in endpoints.items():
        await probe_endpoint(name, url)

if __name__ == "__main__":
    asyncio.run(main())

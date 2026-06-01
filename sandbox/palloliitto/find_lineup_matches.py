import json
import os
import httpx

RESPONSES_DIR = "sandbox/palloliitto/responses"
HEADERS = {
    "accept": "json/4h7dznqdxwtp3hsfdyf5r793uahfxy7x",
    "referer": "https://tulospalvelu.palloliitto.fi/",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
}

def main():
    m_id = "4036852"
    print(f"\nFetching match {m_id}: FC Inter vs VPS")
    
    url = f"https://spl.torneopal.net/taso/rest/getMatch?match_id={m_id}"
    r = httpx.get(url, headers=HEADERS, timeout=10.0)
    if r.status_code == 200:
        m_data = r.json()
        match_obj = m_data.get("match", {})
        lineups = match_obj.get("lineups", [])
        print("Lineups type:", type(lineups).__name__)
        if isinstance(lineups, list):
            print(f"Lineups list length: {len(lineups)}")
            if lineups:
                print("First lineup item keys:", list(lineups[0].keys()) if isinstance(lineups[0], dict) else "not dict")
                print("First lineup item sample:")
                print(json.dumps(lineups[0], indent=2, ensure_ascii=False))
                
                # Check for starting player flags
                # Check team key (is there a team_id or home_away or club_id?)
                team_ids = set(item.get("team_id") for item in lineups if isinstance(item, dict))
                print(f"Unique team IDs in lineups: {team_ids}")
        elif isinstance(lineups, dict):
            print("Lineups is a dict. Keys:", list(lineups.keys()))
    else:
        print("Failed to fetch:", r.status_code)


if __name__ == "__main__":
    main()


import json
import httpx

HEADERS = {
    "accept": "json/4h7dznqdxwtp3hsfdyf5r793uahfxy7x",
    "referer": "https://tulospalvelu.palloliitto.fi/",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
}

def query_and_save(name, endpoint_url):
    print(f"\nQuerying {name} ({endpoint_url})...")
    try:
        r = httpx.get(endpoint_url, headers=HEADERS, timeout=15.0)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print("Type:", type(data).__name__)
            if isinstance(data, dict):
                print("Keys:", list(data.keys()))
                # Save a sample to show schema
                import os
                os.makedirs("sandbox/palloliitto/responses_http", exist_ok=True)
                with open(f"sandbox/palloliitto/responses_http/{name}.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"Saved to responses_http/{name}.json")
                return data
            else:
                print("Response is not a dict.")
        else:
            print("Error text:", r.text[:200])
    except Exception as e:
        print("Failed:", e)
    return None

def main():
    # 1. Fetch Veikkausliiga Standing
    standing = query_and_save("standing_VL", "https://spl.torneopal.net/taso/rest/getStanding?category_id=VL")
    if standing:
        # Inspect structure of standing
        groups = standing.get("groups", [])
        print(f"Found {len(groups)} groups in standing.")
        if groups:
            first_group = groups[0]
            print("Group keys:", list(first_group.keys()))
            standings_list = first_group.get("standings", [])
            print(f"Standings count: {len(standings_list)}")
            if standings_list:
                print("Sample Standing entry:")
                print(json.dumps(standings_list[0], indent=2, ensure_ascii=False)[:600])

    # 2. Fetch Veikkausliiga Matches
    matches = query_and_save("matches_VL", "https://spl.torneopal.net/taso/rest/getMatches?category_id=VL")
    match_id = None
    if matches:
        matches_list = matches.get("matches", [])
        print(f"Found {len(matches_list)} matches.")
        if matches_list:
            print("Sample Match entry:")
            print(json.dumps(matches_list[0], indent=2, ensure_ascii=False)[:600])
            for m in matches_list:
                if m.get("match_id"):
                    match_id = m.get("match_id")
                    break

    # 3. Fetch Veikkausliiga Scorers
    scorers = query_and_save("scorers_VL", "https://spl.torneopal.net/taso/rest/getScorers?category_id=VL")
    if scorers:
        scorers_list = scorers.get("scorers", [])
        print(f"Found {len(scorers_list)} scorers.")
        if scorers_list:
            print("Sample Scorer entry:")
            print(json.dumps(scorers_list[0], indent=2, ensure_ascii=False)[:600])

    # 4. Fetch specific match detail if match_id was found
    if match_id:
        match_detail = query_and_save(f"match_{match_id}", f"https://spl.torneopal.net/taso/rest/getMatch?match_id={match_id}")
        if match_detail:
            print("Match keys:", list(match_detail.keys()))
            m_info = match_detail.get("match", {})
            print(f"Match: {m_info.get('home_team_name')} vs {m_info.get('away_team_name')} on {m_info.get('date')}")
            # print if there are events / stats
            print("Has lineups:", "lineups" in match_detail)
            print("Has events:", "events" in match_detail)
            if "events" in match_detail:
                events = match_detail.get("events", [])
                print(f"Events count: {len(events)}")
                if events:
                    print("Sample event:", json.dumps(events[0], indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()

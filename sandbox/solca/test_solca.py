import json

def extract_rainbet_football_matches(data: dict, tournament_id: str) -> list[dict]:
    tournament = data.get("tournaments", {}).get(tournament_id, {})
    events = data.get("events", {})

    matches = []

    for event_id, event in events.items():
        desc = event.get("desc") or {}
        markets = event.get("markets") or {}

        if desc.get("type") != "match":
            continue

        if str(desc.get("tournament")) != str(tournament_id):
            continue

        competitors = desc.get("competitors") or []
        if len(competitors) < 2:
            continue

        market_1x2 = ((markets.get("1") or {}).get("") or {})

        odds_1x2 = {
            "1": float(market_1x2["1"]["k"]) if "1" in market_1x2 else None,
            "X": float(market_1x2["2"]["k"]) if "2" in market_1x2 else None,
            "2": float(market_1x2["3"]["k"]) if "3" in market_1x2 else None,
        }

        matches.append({
            "home": competitors[0]["name"],
            "away": competitors[1]["name"],
            "odds": odds_1x2,
        })

    return matches


# 👇 MAIN
if __name__ == "__main__":
    # with open("rainbet_1669819042829045760.json") as f:
    #     data = json.load(f)
    with open("solca_1669819042829045760_merged.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    tournament_id = "1669819042829045760"  # Serie A

    matches = extract_rainbet_football_matches(data, tournament_id)

    for m in matches:
        print(m)
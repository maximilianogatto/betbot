import json
from datetime import datetime

# TOURNAMENT_ID = "1669819042829045760"  # Serie A real
TOURNAMENT_ID = "1669819042829045760"  # Serie A 

def to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

def extract_1x2(markets):
    market = (markets or {}).get("1", {}).get("", {})
    return {
        "1": to_float(market.get("1", {}).get("k")),
        "X": to_float(market.get("2", {}).get("k")),
        "2": to_float(market.get("3", {}).get("k")),
    }

with open("rainbet_candidate.json", "r", encoding="utf-8") as f:
    data = json.load(f)
    # print(data)

tournament = data.get("tournaments", {}).get(TOURNAMENT_ID, {})
events = data.get("events", {})

print("Torneo:", tournament.get("name"))


matches = []

for event_id, event in events.items():
    desc = event.get("desc") or {}
    markets = event.get("markets") or {}

    if str(desc.get("tournament")) != TOURNAMENT_ID:
        continue

    competitors = desc.get("competitors") or []
    if len(competitors) < 2:
        continue

    scheduled = desc.get("scheduled")

    matches.append({
        "event_id": event_id,
        "league": tournament.get("name"),
        "home": competitors[0].get("name", "").strip(),
        "away": competitors[1].get("name", "").strip(),
        "scheduled_raw": scheduled,
        "scheduled": (
            datetime.fromtimestamp(scheduled).strftime("%Y-%m-%d %H:%M:%S")
            if scheduled else None
        ),
        "odds_1x2": extract_1x2(markets),
    })

print(json.dumps(matches, ensure_ascii=False, indent=2))
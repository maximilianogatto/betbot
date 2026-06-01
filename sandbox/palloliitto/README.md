# Finnish Football Leagues API Research (`tulospalvelu.palloliitto.fi`)

This directory contains the reverse-engineered specification and HTTP-only Python client for the Finnish Football Association (Suomen Palloliitto) results service.

---

## 1. Backend Architecture & Authentication Bypass

The frontend website `https://tulospalvelu.palloliitto.fi/` uses a REST API hosted at:
`https://spl.torneopal.net/taso/rest/`

### The Security Token (CORS / Cloudflare Bypass)
Standard HTTP requests directly to `spl.torneopal.net` return a `403 Forbidden` from Cloudflare due to browser checks and CORS configurations. 

Through header interception, we discovered a **custom Accept header** acting as a static API Key / Security Token:
```http
accept: json/4h7dznqdxwtp3hsfdyf5r793uahfxy7x
referer: https://tulospalvelu.palloliitto.fi/
```
Sending this exact accept header with a realistic `User-Agent` allows any standard HTTP client (e.g. `httpx`, `requests`, `urllib`) to access Torneopal endpoints directly, at high speeds and without running a headless browser.

---

## 2. Finnish Football Pyramid Tiers (Escalafón)

The website contains all levels of Finnish football and futsal. The adult national pyramid uses a structured category system. Below is the official tier hierarchy mapped inside the client:

### Men's Football Pyramid
| Tier | League Code | Official Name | Level |
|------|-------------|---------------|-------|
| 1    | `VL`        | Veikkausliiga | Professional Top Tier |
| 2    | `M1L`       | Ykkösliiga    | Professional Second Tier |
| 3    | `M1`        | Ykkönen       | Professional Third Tier |
| 4    | `M2`        | Kakkonen      | Semi-Pro Fourth Tier |
| 5    | `M3`        | Kolmonen      | Fifth Tier (Regional) |
| 6    | `M4`        | Nelonen       | Sixth Tier (Regional) |
| 7    | `M5`        | Vitonen       | Seventh Tier (Regional) |
| 8    | `M6`        | Kutonen       | Eighth Tier (Regional) |
| 9    | `M7`        | Seiska        | Ninth Tier (Regional) |

### Women's Football Pyramid
| Tier | League Code | Official Name | Level |
|------|-------------|---------------|-------|
| 1    | `NL`        | Kansallinen Liiga | Top Tier |
| 2    | `N1`        | Naisten Ykkönen   | Second Tier |
| 3    | `N2`        | Naisten Kakkonen  | Third Tier |
| 4    | `N3`        | Naisten Kolmonen  | Fourth Tier |
| 5    | `N4`        | Naisten Nelonen   | Fifth Tier |
| 6    | `N5`        | Naisten Vitonen   | Sixth Tier |

### Cups & Futsal
- **Cups**: `MSC` (Miesten Suomen Cup), `NSC` (Naisten Suomen Cup), `LC` (Liigacup).
- **Futsal Men**: `FML` (Futsal-Liiga - Tier 1), `FM1` (Futsal-Ykkönen - Tier 2), `FM2` (Futsal-Kakkonen - Tier 3).
- **Futsal Women**: `FNL` (Naisten Futsal-Liiga - Tier 1), `FN1` (Naisten Futsal-Ykkönen - Tier 2).

---

## 3. Discovered REST Endpoints & Parameters

All endpoints require the security headers outlined in Section 1.

### A. Get Categories (Leagues list)
Returns a flat dictionary list of all categories for the selected season.
- **URL**: `/getCategories?season_id=2026`
- **Output JSON Key**: `categories`

### B. Get Daily Matches / Live Fixtures
Fetches matches played on a specific date (used to detect live games).
- **URL**: `/getMatches?date=YYYY-MM-DD`
- **Example**: `/getMatches?date=2026-06-01`
- **Output JSON Key**: `matches`

### C. Get Fixtures by League
Retrieves the full list of fixtures (past and upcoming) for a particular category.
- **URL**: `/getMatches?competition_id={competition_id}&category_id={category_id}`
- **Example**: `/getMatches?competition_id=spljp26&category_id=VL` (Veikkausliiga 2026)
- **Output JSON Key**: `matches`

### D. Get Standings / Table
Returns standings and ranking stats for a group inside a league category.
- **URL**: `/getGroup?competition_id={competition_id}&category_id={category_id}&group_id={group_id}`
- **Example**: `/getGroup?competition_id=spljp26&category_id=VL&group_id=1`
- **Output JSON Key**: `group.live_standings`

### E. Get Match Details & Stats
Fetches full details for a match: rosters/lineups, goals, cards (yellow/red), substitution details, events timeline, referees, and stadium information.
- **URL**: `/getMatch?match_id={match_id}`
- **Example**: `/getMatch?match_id=4066662`
- **Output JSON Key**: `match`

### F. Get Team Details
Returns team information, crest image, club websites, jersey patterns, and city.
- **URL**: `/getTeam?team_id={team_id}`
- **Output JSON Key**: `team`

---

## 4. Python API Client Usage

A complete, standard library + `httpx` based client is available at [api_client.py](file:///Users/maximilianogatto/Library/CloudStorage/OneDrive-Personal/Apuestas/BetBot/sandbox/palloliitto/api_client.py).

### How to use:
```python
from api_client import PalloliittoAPI

with PalloliittoAPI() as api:
    # 1. Fetch Veikkausliiga (VL) standings
    standings = api.get_standings(competition_id="spljp26", category_id="VL", group_id="1")
    for team in standings:
        print(f"#{team['current_standing']}: {team['team_name']} | {team['points']} pts")

    # 2. Fetch Veikkausliiga upcoming fixtures
    fixtures = api.get_matches_by_league(competition_id="spljp26", category_id="VL")
    for match in fixtures[:5]:
        print(f"{match['date']}: {match['team_A_name']} vs {match['team_B_name']}")
```

You can execute the verification script to see a live demonstration of these requests:
```bash
./betbot/bin/python sandbox/palloliitto/verify_client.py
```

---

## 5. Summary of Findings

1. **HTTP-only connection**: Successful! Cloudflare bypass is achieved using the static `accept` header string `json/4h7dznqdxwtp3hsfdyf5r793uahfxy7x`. Standard python clients can request all stats natively without any browser overhead.
2. **Escalafón (Hierarchy)**: Completed and documented. Categories are categorized dynamically by tier in `api_client.py`.
3. **Data Availability**: Very rich! The API provides real-time goals, cards (bookings), match lineups, regional standings, and flat fixtures for all leagues in Finland, covering both professional tiers and lower division amateur football that conventional sites fail to cover.

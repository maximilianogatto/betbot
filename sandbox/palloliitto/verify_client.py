import datetime
from api_client import PalloliittoAPI

def main():
    print("=============================================================")
    # 1. Initialize API client
    api = PalloliittoAPI()
    print("Successfully initialized PalloliittoAPI client!")
    
    # 2. Get and print the League Escalafón (ranking)
    print("\n--- Finnish Football & Futsal League Hierarchy (Escalafón) ---")
    leagues = api.get_league_ranking_list()
    print(f"{'SPORT':<10} | {'LEAGUE NAME':<25} | {'CODE':<6} | {'GENDER':<6} | {'TIER':<4}")
    print("-" * 65)
    for l in leagues:
        print(f"{l['sport']:<10} | {l['name']:<25} | {l['category_id']:<6} | {l['gender']:<6} | Tier {l['tier']}")

    # 3. Fetch Categories list (limit to 10 for display)
    print("\n--- Fetching Categories ---")
    try:
        categories = api.get_categories(season="2026")
        print(f"Total categories fetched: {len(categories)}")
        classified = [c for c in categories if c.get("hierarchy_level") != 99]
        print(f"Recognized classified leagues: {len(classified)}")
        print("\nSample Classified Categories:")
        for cat in classified[:5]:
            print(f" - {cat.get('category_name')} (ID: {cat.get('category_id')}) - Tier {cat.get('hierarchy_level')} {cat.get('sport_type').upper()}")
    except Exception as e:
        print("Failed to fetch categories:", e)

    # 4. Fetch Matches for Today
    today_str = datetime.date.today().isoformat()
    print(f"\n--- Fetching Matches for Today ({today_str}) ---")
    try:
        matches_today = api.get_matches_by_date(today_str)
        print(f"Total matches scheduled today: {len(matches_today)}")
        if matches_today:
            # Print first 5 matches
            print("\nSample Today Matches:")
            for m in matches_today[:5]:
                home = m.get("home_team_name") or m.get("club_A_name") or "Home"
                away = m.get("away_team_name") or m.get("club_B_name") or "Away"
                cat_name = m.get("category_name") or "League"
                m_id = m.get("match_id")
                score = f"{m.get('fs_A', '')}-{m.get('fs_B', '')}" if m.get('fs_A') is not None else "vs"
                print(f" - [{cat_name}] {home} {score} {away} (Match ID: {m_id})")
    except Exception as e:
        print("Failed to fetch matches today:", e)

    # 5. Fetch Veikkausliiga Fixtures/Matches (VL)
    print("\n--- Fetching Veikkausliiga Fixtures/Matches (VL) ---")
    try:
        vl_matches = api.get_matches_by_league(competition_id="spljp26", category_id="VL")
        print(f"Total matches found in Veikkausliiga: {len(vl_matches)}")
        if vl_matches:
            # Print first 5
            print("\nVeikkausliiga Sample Fixtures:")
            for m in vl_matches[:5]:
                home = m.get("team_A_name") or m.get("club_A_name")
                away = m.get("team_B_name") or m.get("club_B_name")
                date = m.get("date")
                score = f"{m.get('fs_A')}-{m.get('fs_B')}" if m.get('status') == "Finished" else "vs"
                print(f" - {date}: {home} {score} {away} (ID: {m.get('match_id')})")
    except Exception as e:
        print("Failed to fetch Veikkausliiga fixtures:", e)

    # 6. Fetch Veikkausliiga Standings (VL, Group 1)
    print("\n--- Fetching Veikkausliiga Standings (VL, Group 1) ---")
    try:
        vl_standings = api.get_standings(competition_id="spljp26", category_id="VL", group_id="1")
        print(f"Total teams in standings: {len(vl_standings)}")
        if vl_standings:
            print(f"\n{'POS':<3} | {'TEAM NAME':<25} | {'GP':<3} | {'W':<3} | {'D':<3} | {'L':<3} | {'GD':<5} | {'PTS':<3}")
            print("-" * 65)
            for t in vl_standings:
                print(f"{t.get('current_standing', 0):<3} | {t.get('team_name', 'Unknown'):<25} | {t.get('matches_played', 0):<3} | {t.get('matches_won', 0):<3} | {t.get('matches_tied', 0):<3} | {t.get('matches_lost', 0):<3} | {t.get('goals_diff', 0):<5} | {t.get('points', 0):<3}")
    except Exception as e:
        print("Failed to fetch Veikkausliiga standings:", e)

    # 7. Fetch specific match details for a match (e.g. first match ID from today's list or a known one)
    match_id = None
    if 'matches_today' in locals() and matches_today:
        for m in matches_today:
            if m.get("match_id"):
                match_id = m.get("match_id")
                break
    if not match_id and 'vl_matches' in locals() and vl_matches:
        for m in vl_matches:
            if m.get("match_id"):
                match_id = m.get("match_id")
                break
                
    if match_id:
        print(f"\n--- Fetching Match Details for Match ID: {match_id} ---")
        try:
            m_details = api.get_match_details(match_id)
            print(f"Teams: {m_details.get('club_A_name')} vs {m_details.get('club_B_name')}")
            print(f"Date: {m_details.get('date')} {m_details.get('time')}")
            print(f"Venue: {m_details.get('venue_name') or 'N/A'}, Attendance: {m_details.get('attendance', 0)}")
            print(f"Status: {m_details.get('status')}")
            
            # Print goals / events if available
            goals = m_details.get("goals", [])
            print(f"Goals scored: {len(goals)}")
            for g in goals:
                scorer = g.get("player_name") or "Player"
                team = "Home" if g.get("team_id") == m_details.get("team_A_id") else "Away"
                minute = g.get("minute") or "N/A"
                print(f" - Goal ({team}): {scorer} at {minute}'")
                
            bookings = m_details.get("bookings", [])
            print(f"Cards shown: {len(bookings)}")
            for b in bookings:
                player = b.get("player_name") or "Player"
                team = "Home" if b.get("team_id") == m_details.get("team_A_id") else "Away"
                card = b.get("card_type") or "Yellow"
                minute = b.get("minute") or "N/A"
                print(f" - {card} Card ({team}): {player} at {minute}'")
                
            lineups = m_details.get("lineups", {})
            has_lineups = "A" in lineups or "B" in lineups
            print(f"Has lineup configuration: {has_lineups}")
            
        except Exception as e:
            print(f"Failed to fetch match details for {match_id}:", e)
            
    print("\n=============================================================")
    api.close()

if __name__ == "__main__":
    main()

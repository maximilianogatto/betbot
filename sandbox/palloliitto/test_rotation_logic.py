import json
import httpx
from api_client import PalloliittoAPI

def analyze_team_rotation(api: PalloliittoAPI, target_match_id: str):
    print(f"\nAnalyzing lineups and rotation for match ID: {target_match_id}...")
    
    # 1. Fetch target match details
    match = api.get_match_details(target_match_id)
    if not match:
        print("Match not found.")
        return
        
    home_name = match.get("club_A_name") or match.get("team_A_name")
    away_name = match.get("club_B_name") or match.get("team_B_name")
    home_id = match.get("team_A_id")
    away_id = match.get("team_B_id")
    home_primary_cat = match.get("team_A_primary_category_id") or match.get("category_id")
    away_primary_cat = match.get("team_B_primary_category_id") or match.get("category_id")
    competition_id = match.get("competition_id")
    
    print(f"Match: {home_name} vs {away_name}")
    print(f"Primary categories - Home: {home_primary_cat}, Away: {away_primary_cat}")
    
    # Get current starting 11 for both teams
    lineups_list = match.get("lineups", [])
    if not lineups_list:
        print("No lineups filled for this match yet.")
        return
        
    home_starters = [p for p in lineups_list if p.get("team_id") == home_id and p.get("start") == "1"]
    away_starters = [p for p in lineups_list if p.get("team_id") == away_id and p.get("start") == "1"]
    
    print(f"Current starters - Home: {len(home_starters)}, Away: {len(away_starters)}")
    
    # Let's perform the rotation check for Home team
    print(f"\n--- ROTATION ANALYSIS FOR HOME TEAM ({home_name}) ---")
    perform_team_analysis(api, home_name, home_id, home_primary_cat, competition_id, home_starters, target_match_id)
    
    # Let's perform the rotation check for Away team
    print(f"\n--- ROTATION ANALYSIS FOR AWAY TEAM ({away_name}) ---")
    perform_team_analysis(api, away_name, away_id, away_primary_cat, competition_id, away_starters, target_match_id)

def perform_team_analysis(api: PalloliittoAPI, team_name, team_id, primary_category_id, competition_id, current_starters, target_match_id):
    if not current_starters:
        print("No current starters available to compare.")
        return
        
    # Get recent league matches for this category
    # (Usually getMatches?competition_id=...&category_id=... contains all league matches)
    try:
        league_matches = api.get_matches_by_league(competition_id, primary_category_id)
    except Exception as e:
        print(f"Could not load league matches: {e}")
        return
        
    # Find recent finished matches for this team (exclude today's match itself)
    # We want up to 3 recent matches
    recent_matches = []
    for m in league_matches:
        m_id = m.get("match_id")
        if m_id == target_match_id:
            continue
        if m.get("status") in ["Finished", "Played"] and m.get("walkover") != 1:
            if m.get("team_A_id") == team_id or m.get("team_B_id") == team_id:
                recent_matches.append(m)
                
    # Sort matches by date descending (latest first)
    recent_matches.sort(key=lambda x: x.get("date", ""), reverse=True)
    recent_matches = recent_matches[:3]
    
    print(f"Found {len(recent_matches)} recent league matches to calculate starting frequency:")
    for rm in recent_matches:
        print(f" - {rm.get('date')}: {rm.get('team_A_name')} {rm.get('fs_A')}-{rm.get('fs_B')} {rm.get('team_B_name')} (ID: {rm.get('match_id')})")
        
    if not recent_matches:
        print("No recent matches found to compare. Assuming regular starting lineup.")
        return
        
    # Count how many times each player started in these recent matches
    starter_counts = {}  # player_id -> count
    player_names = {}    # player_id -> player_name
    
    for rm in recent_matches:
        rm_id = rm.get("match_id")
        details = api.get_match_details(rm_id)
        if details:
            rm_lineup = details.get("lineups", [])
            for p in rm_lineup:
                if p.get("team_id") == team_id and p.get("start") == "1":
                    p_id = p.get("player_id")
                    starter_counts[p_id] = starter_counts.get(p_id, 0) + 1
                    player_names[p_id] = p.get("player_name")
                    
    # A regular starter is a player who started in at least 50% of the recent games (i.e. >= 2 out of 3, or >= 1 out of 1 or 2)
    min_starts = max(1, len(recent_matches) // 2 + (1 if len(recent_matches) % 2 != 0 else 0))
    regular_starter_ids = {p_id for p_id, count in starter_counts.items() if count >= min_starts}
    
    print(f"Total unique starters in recent games: {len(starter_counts)}")
    print(f"Regular starters identified (started in >= {min_starts} of recent games): {len(regular_starter_ids)}")
    
    # Compare current starters with regular starters
    current_starter_ids = {p.get("player_id") for p in current_starters}
    matching_starters = current_starter_ids & regular_starter_ids
    
    regularity_ratio = len(matching_starters) / 11 if len(matching_starters) <= 11 else len(matching_starters) / len(current_starters)
    
    print(f"Starters today who are regulars: {len(matching_starters)} / {len(current_starters)}")
    print(f"Lineup regularity: {regularity_ratio:.0%}")
    
    if regularity_ratio >= 0.70:
        print("✅ ALINEACIÓN PRINCIPAL: El equipo está jugando con sus titulares habituales de liga.")
    elif regularity_ratio >= 0.45:
        print("⚠️ ROTACIÓN PARCIAL: Hay rotación intermedia. Varios titulares descansan hoy.")
    else:
        print("🚨 ROTACIÓN MASIVA / SUPLENTES: ¡El equipo está jugando con suplentes o reservistas! Alta probabilidad de B-Team.")
        # Print non-regular starters
        non_regulars = [p for p in current_starters if p.get("player_id") not in regular_starter_ids]
        print("Suplentes/Nuevos titulares hoy:")
        for nr in non_regulars[:5]:
            print(f" - #{nr.get('shirt_number')} {nr.get('player_name')} ({nr.get('position_en')})")

def main():
    api = PalloliittoAPI()
    # Let's analyze FC Inter vs VPS (match 4036852)
    analyze_team_rotation(api, "4036852")
    api.close()

if __name__ == "__main__":
    main()

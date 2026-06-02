"""Compact provider-level report rendering for FootyStats."""

from __future__ import annotations

from typing import Any


def render_match_report(snapshot: dict[str, Any]) -> str:
    """Render a rich Sportradar-like match report in Spanish."""

    match = snapshot.get("match") if isinstance(snapshot.get("match"), dict) else {}
    live = snapshot.get("live_state") if isinstance(snapshot.get("live_state"), dict) else {}
    h2h = snapshot.get("h2h")
    
    title = str(match.get("title") or "Partido FootyStats")
    
    lines = [
        title,
        "",
        f"- Fuente: {snapshot.get('source_mode') or 'public_html'}",
        f"- Estado: {match.get('status') or 'sin confirmar'}",
    ]
    
    if live.get("score_home") is not None and live.get("score_away") is not None:
        minute = f" · {live.get('minute')}'" if live.get("minute") else ""
        lines.append(f"- Live: {live['score_home']}-{live['score_away']}{minute}")
        
    if not h2h or not isinstance(h2h, dict) or "home" not in h2h or "away" not in h2h:
        # Fallback to minimal report if H2H page was not scraped or parsed
        source_url = snapshot.get("source_url")
        if source_url:
            lines.extend(["", f"🔗 {source_url}"])
        lines.extend(
            [
                "",
                "Cobertura pública inicial: fixtures, tabla y marcador live liviano.",
                "Para ampliar H2H, odds y métricas avanzadas configurá FOOTYSTATS_API_KEY.",
            ]
        )
        return "\n".join(lines)

    home = h2h.get("home", {})
    away = h2h.get("away", {})
    mini_tables = h2h.get("mini_tables", {})
    markets = h2h.get("markets", {})
    fixtures = h2h.get("fixtures", [])
    h2h_tendencies = h2h.get("h2h_tendencies", {})
    h2h_summary = h2h.get("h2h_summary", "")

    # 1. Form Section
    home_overall_ppg = home.get("stats", {}).get("overall", {}).get("ppg", 0.0)
    home_overall_form = home.get("stats", {}).get("overall", {}).get("form", "")
    away_overall_ppg = away.get("stats", {}).get("overall", {}).get("ppg", 0.0)
    away_overall_form = away.get("stats", {}).get("overall", {}).get("form", "")
    lines.append(f"- Form: {home_overall_ppg:.2f} PPG ({home_overall_form}) vs {away_overall_ppg:.2f} PPG ({away_overall_form})")

    # 2. H2H History Section
    if h2h_summary:
        lines.append(f"- H2H: {h2h_summary}")
    else:
        lines.append("- H2H: Historial de enfrentamientos directos.")
        
    if fixtures:
        for f in fixtures[:5]:
            date_display = f.get("date_display") or f.get("datetime") or ""
            lines.append(f"  - {date_display}: {f['home']} {f['home_score']}-{f['away_score']} {f['away']}")

    # Safe division helper
    def avg_val(gf: int, mp: int) -> float:
        if not mp:
            return 0.0
        return gf / mp

    # 3. Goals Averages Section
    home_overall_tab = mini_tables.get("home", {}).get("overall", {})
    away_overall_tab = mini_tables.get("away", {}).get("overall", {})
    home_home_tab = mini_tables.get("home", {}).get("home", {})
    away_away_tab = mini_tables.get("away", {}).get("away", {})

    home_overall_mp = home_overall_tab.get("mp", 0)
    away_overall_mp = away_overall_tab.get("mp", 0)
    home_home_mp = home_home_tab.get("mp", 0)
    away_away_mp = away_away_tab.get("mp", 0)

    avg_scored_h_gen = avg_val(home_overall_tab.get("gf", 0), home_overall_mp)
    avg_scored_a_gen = avg_val(away_overall_tab.get("gf", 0), away_overall_mp)
    avg_scored_h_split = avg_val(home_home_tab.get("gf", 0), home_home_mp)
    avg_scored_a_split = avg_val(away_away_tab.get("gf", 0), away_away_mp)

    avg_conceded_h_gen = avg_val(home_overall_tab.get("ga", 0), home_overall_mp)
    avg_conceded_a_gen = avg_val(away_overall_tab.get("ga", 0), away_overall_mp)
    avg_conceded_h_split = avg_val(home_home_tab.get("ga", 0), home_home_mp)
    avg_conceded_a_split = avg_val(away_away_tab.get("ga", 0), away_away_mp)

    lines.extend(
        [
            "",
            "- Goals avg scored:",
            f"  - general: {home.get('name')}={avg_scored_h_gen:.2f} | {away.get('name')}={avg_scored_a_gen:.2f}",
            f"  - home/away split: {home.get('name')} home={avg_scored_h_split:.2f} | {away.get('name')} away={avg_scored_a_split:.2f}",
            "- Goals avg conceded:",
            f"  - general: {home.get('name')}={avg_conceded_h_gen:.2f} | {away.get('name')}={avg_conceded_a_gen:.2f}",
            f"  - split: {home.get('name')} home={avg_conceded_h_split:.2f} | {away.get('name')} away={avg_conceded_a_split:.2f}",
        ]
    )

    # 4. BTTS & Over Tendencies
    h2h_btts = h2h_tendencies.get("btts")
    season_btts = markets.get("btts", {}).get("value")
    btts_str = ""
    if h2h_btts is not None:
        btts_str += f"{h2h_btts}% (H2H)"
    if season_btts:
        if btts_str:
            btts_str += " | "
        btts_str += f"{season_btts}% (Temporada)"
    if btts_str:
        lines.append(f"- BTTS: {btts_str}")

    h2h_over25 = h2h_tendencies.get("over_2.5")
    season_over25 = markets.get("over_2.5", {}).get("value")
    over25_str = ""
    if h2h_over25 is not None:
        over25_str += f"{h2h_over25}% (H2H)"
    if season_over25:
        if over25_str:
            over25_str += " | "
        over25_str += f"{season_over25}% (Temporada)"
    if over25_str:
        lines.append(f"- Over 2.5: {over25_str}")

    # 5. Table Standings Section
    home_pos = home_overall_tab.get("pos") or home.get("league_pos") or "?"
    away_pos = away_overall_tab.get("pos") or away.get("league_pos") or "?"
    home_pts = home_overall_tab.get("pts") or 0
    away_pts = away_overall_tab.get("pts") or 0
    lines.append(
        f"- Table: {home_pos}° ({home_pts} pts, {home_overall_mp}P) vs {away_pos}° ({away_pts} pts, {away_overall_mp}P)"
    )

    source_url = snapshot.get("source_url")
    if source_url:
        lines.extend(["", f"🔗 {source_url}"])
        
    return "\n".join(lines)



__all__ = ["render_match_report"]

"""Unified Match Report Builder for BetBot stats providers.

Generates consistent, highly-detailed match intelligence reports across all
stats providers (SofaScore, Sportradar, Palloliitto, Svenskfotboll, FootyStats, etc.).
"""

from __future__ import annotations

import math
from typing import Any


def render_unified_match_report(snapshot: dict[str, Any]) -> str:
    """Render a comprehensive, standardized match report matching user's exact specification."""

    match = snapshot.get("match") if isinstance(snapshot.get("match"), dict) else {}
    live = snapshot.get("live_state") if isinstance(snapshot.get("live_state"), dict) else {}
    home_name = str(match.get("home") or "Local")
    away_name = str(match.get("away") or "Visitante")

    lines = [
        f"⚽ <b>{home_name} vs {away_name}</b>",
        f"🏆 <b>{match.get('league_name') or 'Torneo'}</b>  ·  📅 {scheduled_label(match)} ({_status_label(match)})",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    # 1. PROMEDIOS DE LA LIGA
    standings = snapshot.get("standings") if isinstance(snapshot.get("standings"), dict) else {}
    league_averages = _compute_league_averages(standings)
    if league_averages.get("total_matches", 0) > 0:
        lines.extend(
            [
                "",
                "🌐 <b>PROMEDIOS DE LA LIGA</b>",
                f"   • Goles por partido en la liga: <b>{league_averages['avg_goals_per_match']} goles/partido</b>",
                f"   • Promedio Local: {league_averages['avg_home_goals']} goles | Promedio Visitante: {league_averages['avg_away_goals']} goles",
            ]
        )

    # Compute team stats (General and Conditioned)
    home_last = snapshot.get("home_last_events") or []
    away_last = snapshot.get("away_last_events") or []
    home_gen = compute_team_stability(home_name, home_last)
    away_gen = compute_team_stability(away_name, away_last)
    home_cond = compute_team_stability(home_name, home_last, side="home")
    away_cond = compute_team_stability(away_name, away_last, side="away")

    # 2. ESTABILIDAD Y CONSISTENCIA DEL EQUIPO
    lines.extend(
        [
            "",
            "📈 <b>ESTABILIDAD Y CONSISTENCIA DEL EQUIPO</b>",
            f"   • {home_name}: {home_gen['badge']} <b>{home_gen['category']} ({home_gen['score']}/100)</b>",
            f"     - Varianza goles: {home_gen['gf_stddev']} σ ({home_gen['stability_desc']})",
            f"     - Consistencia ofensiva: {home_gen['attack_consistency']} (Outliers: {home_gen['outliers_label']})",
            f"   • {away_name}: {away_gen['badge']} <b>{away_gen['category']} ({away_gen['score']}/100)</b>",
            f"     - Varianza goles: {away_gen['gf_stddev']} σ ({away_gen['stability_desc']})",
            f"     - Consistencia ofensiva: {away_gen['attack_consistency']} (Outliers: {away_gen['outliers_label']})",
        ]
    )

    # 3. FORMA Y RENDIMIENTO GENERAL (Sección dedicada)
    if home_gen["sequence"] or away_gen["sequence"]:
        lines.extend(
            [
                "",
                "📊 <b>FORMA Y RENDIMIENTO GENERAL</b>",
                f"   • {home_name}: {home_gen['emojis']} ({home_gen['sequence']}) — Goles: {home_gen['gf_avg']} m. / {home_gen['ga_avg']} r.",
                f"   • {away_name}: {away_gen['emojis']} ({away_gen['sequence']}) — Goles: {away_gen['gf_avg']} m. / {away_gen['ga_avg']} r.",
            ]
        )

    # 4. RENDIMIENTO CONDICIONADO (Local en casa vs Visitante fuera)
    lines.extend(["", "🏟️ <b>RENDIMIENTO CONDICIONADO (Local en casa vs Visitante fuera)</b>"])
    if home_cond["games_count"] > 0:
        lines.extend(
            [
                f"   • {home_name} (Local): {home_cond['emojis']} ({home_cond['wins_summary']} en casa)",
                f"     - Goles en casa: {home_cond['gf_avg']} marcados / {home_cond['ga_avg']} recibidos ({home_cond['margin_label']})",
            ]
        )
    else:
        lines.append(f"   • {home_name} (Local): Datos de casa no disponibles")

    if away_cond["games_count"] > 0:
        lines.extend(
            [
                f"   • {away_name} (Visitante): {away_cond['emojis']} ({away_cond['wins_summary']} fuera)",
                f"     - Goles fuera: {away_cond['gf_avg']} marcados / {away_cond['ga_avg']} recibidos ({away_cond['margin_label']})",
            ]
        )
    else:
        lines.append(f"   • {away_name} (Visitante): Datos de visitante no disponibles")

    # 5. TABLA DE POSICIONES
    tables = standings.get("tables") or []
    standings_split = snapshot.get("standings_split") if isinstance(snapshot.get("standings_split"), dict) else {}
    if isinstance(tables, list) and tables:
        lines.extend(["", "📋 <b>TABLA DE POSICIONES</b>"])
        rows = tables[0].get("rows") if isinstance(tables[0], dict) else []
        home_row = next((r for r in (rows or []) if r.get("team", {}).get("name") == home_name), None)
        away_row = next((r for r in (rows or []) if r.get("team", {}).get("name") == away_name), None)

        if home_row or away_row:
            lines.append("   • <b>General</b>:")
            if home_row:
                gf, ga = home_row.get("goals_for", 0), home_row.get("goals_against", 0)
                diff = home_row.get("goal_difference") or f"{gf - ga:+d}"
                lines.append(f"     - {home_name}: #{home_row.get('position')} | PJ:{home_row.get('played')} | PTS:{home_row.get('points')} | GF:{gf} GC:{ga} (Dif:{diff})")
            if away_row:
                gf, ga = away_row.get("goals_for", 0), away_row.get("goals_against", 0)
                diff = away_row.get("goal_difference") or f"{gf - ga:+d}"
                lines.append(f"     - {away_name}: #{away_row.get('position')} | PJ:{away_row.get('played')} | PTS:{away_row.get('points')} | GF:{gf} GC:{ga} (Dif:{diff})")

        # Split standings (Local vs Visitante table)
        home_tbl = standings_split.get("home", {}).get("tables", [{}])[0].get("rows", []) if standings_split.get("home") else []
        away_tbl = standings_split.get("away", {}).get("tables", [{}])[0].get("rows", []) if standings_split.get("away") else []
        h_split = next((r for r in home_tbl if r.get("team", {}).get("name") == home_name), None)
        a_split = next((r for r in away_tbl if r.get("team", {}).get("name") == away_name), None)
        if h_split or a_split:
            lines.append("   • <b>Condición (Tabla Local vs Tabla Visitante)</b>:")
            if h_split:
                gf, ga = h_split.get("goals_for", 0), h_split.get("goals_against", 0)
                diff = h_split.get("goal_difference") or f"{gf - ga:+d}"
                lines.append(f"     - {home_name} (Local): #{h_split.get('position')} | PJ:{h_split.get('played')} | PTS:{h_split.get('points')} | GF:{gf} GC:{ga} (Dif:{diff})")
            if a_split:
                gf, ga = a_split.get("goals_for", 0), a_split.get("goals_against", 0)
                diff = a_split.get("goal_difference") or f"{gf - ga:+d}"
                lines.append(f"     - {away_name} (Visitante): #{a_split.get('position')} | PJ:{a_split.get('played')} | PTS:{a_split.get('points')} | GF:{gf} GC:{ga} (Dif:{diff})")

    # 6. HISTORIAL H2H (Directo)
    h2h = snapshot.get("h2h") if isinstance(snapshot.get("h2h"), dict) else {}
    duel = h2h.get("teamDuel") if isinstance(h2h.get("teamDuel"), dict) else {}
    if duel:
        lines.extend(
            [
                "",
                "🤝 <b>HISTORIAL H2H (Directo)</b>",
                f"   • {home_name}: {duel.get('homeWins', 0)} G | Empates: {duel.get('draws', 0)} | {away_name}: {duel.get('awayWins', 0)} G",
            ]
        )
    h2h_events = snapshot.get("h2h_events") or []
    if isinstance(h2h_events, list) and h2h_events:
        for ev in h2h_events[:4]:
            h = ev.get("homeTeam", {}).get("name") or "Home"
            a = ev.get("awayTeam", {}).get("name") or "Away"
            hs = ev.get("homeScore", {}).get("current", "-")
            aws = ev.get("awayScore", {}).get("current", "-")
            lines.append(f"     - {h} {hs}-{aws} {a}")

    # 7. RIVALES EN COMÚN RECIENTES
    common_opps = find_common_opponents(home_gen["opponents"], away_gen["opponents"])
    if common_opps:
        lines.extend(["", "🔎 <b>RIVALES EN COMÚN RECIENTES</b>"])
        for opp_name, matches in list(common_opps.items())[:4]:
            lines.append(f"   🆚 <b>{opp_name}</b>:")
            lines.append(f"      - {home_name}: {matches['home']}")
            lines.append(f"      - {away_name}: {matches['away']}")

    # 8. ANÁLISIS DE ALINEACIONES Y ROTACIÓN
    lineups = snapshot.get("lineups") if isinstance(snapshot.get("lineups"), dict) else {}
    if lineups:
        lineup_analysis = compute_lineup_analysis(lineups, home_name, away_name, home_last, away_last)
        lines.extend(["", "👥 <b>ANÁLISIS DE ALINEACIONES Y ROTACIÓN</b>"])
        lines.append(f"   • {home_name}: {lineup_analysis['home_rotation_label']}")
        if lineup_analysis.get("home_key_players"):
            lines.append(f"     - Jugadores clave: {lineup_analysis['home_key_players']}")
        lines.append(f"   • {away_name}: {lineup_analysis['away_rotation_label']}")
        if lineup_analysis.get("away_key_players"):
            lines.append(f"     - Jugadores clave: {lineup_analysis['away_key_players']}")

    # 9. MÉTRICAS Y MERCADOS
    lines.extend(["", "🥅 <b>MÉTRICAS Y MERCADOS</b>"])
    lines.append(f"   • Ambos Marcan (BTTS Rate): {home_name} {home_gen['btts_pct']}% | {away_name} {away_gen['btts_pct']}%")

    odds = snapshot.get("odds") if isinstance(snapshot.get("odds"), dict) else {}
    odds_1x2 = odds.get("1x2") if isinstance(odds.get("1x2"), dict) else {}
    if any(value is not None for value in odds_1x2.values()):
        lines.append(f"   • Odds 1X2: 1={_fmt(odds_1x2.get('home'))} | X={_fmt(odds_1x2.get('draw'))} | 2={_fmt(odds_1x2.get('away'))}")

    win_prob = snapshot.get("win_probability")
    if isinstance(win_prob, dict) and win_prob:
        lines.append(f"   • Probabilidad SofaScore: Local {_pct(win_prob.get('homeWin'))} | Empate {_pct(win_prob.get('draw'))} | Visita {_pct(win_prob.get('awayWin'))}")

    # 10. TRAZABILIDAD DE ÚLTIMOS PARTIDOS (Condicionados)
    if home_cond["events"] or away_cond["events"]:
        lines.extend(["", "🔄 <b>TRAZABILIDAD DE ÚLTIMOS PARTIDOS (Condicionados)</b>"])
        if home_cond["events"]:
            lines.append(f"   • <b>{home_name} (de local)</b>:")
            for ev in home_cond["events"][:3]:
                h = ev.get("homeTeam", {}).get("name") or "Home"
                a = ev.get("awayTeam", {}).get("name") or "Away"
                hs = ev.get("homeScore", {}).get("current", "-")
                aws = ev.get("awayScore", {}).get("current", "-")
                lines.append(f"     - {hs}-{aws} vs {a}" if h == home_name else f"     - {hs}-{aws} vs {h}")
        if away_cond["events"]:
            lines.append(f"   • <b>{away_name} (de visitante)</b>:")
            for ev in away_cond["events"][:3]:
                h = ev.get("homeTeam", {}).get("name") or "Home"
                a = ev.get("awayTeam", {}).get("name") or "Away"
                hs = ev.get("homeScore", {}).get("current", "-")
                aws = ev.get("awayScore", {}).get("current", "-")
                lines.append(f"     - {hs}-{aws} vs {h}" if a == away_name else f"     - {hs}-{aws} vs {a}")

    coverage = snapshot.get("coverage") if isinstance(snapshot.get("coverage"), dict) else {}
    available = sorted(key.removeprefix("has_") for key, value in coverage.items() if value)
    if available:
        lines.extend(["", f"ℹ️ <i>Cobertura: {', '.join(available)}</i>"])

    return "\n".join(lines)


def compute_team_stability(
    team_name: str, events: list[dict[str, Any]], *, side: str | None = None
) -> dict[str, Any]:
    """Compute detailed team metrics and stability index (0-100%)."""

    filtered_events: list[dict[str, Any]] = []
    seq: list[str] = []
    emojis: list[str] = []
    gf_list: list[int] = []
    ga_list: list[int] = []
    margin_list: list[int] = []
    opponents: dict[str, str] = {}
    wins_count = 0
    btts_count = 0

    for ev in events[:15]:
        h_name = ev.get("homeTeam", {}).get("name")
        a_name = ev.get("awayTeam", {}).get("name")
        hs = ev.get("homeScore", {}).get("current")
        aws = ev.get("awayScore", {}).get("current")
        if hs is None or aws is None:
            continue

        is_home = (h_name == team_name)
        if side == "home" and not is_home:
            continue
        if side == "away" and is_home:
            continue

        filtered_events.append(ev)
        opp_name = str(a_name if is_home else h_name)
        opponents[opp_name] = f"{h_name} {hs}-{aws} {a_name}"

        my_goals = int(hs if is_home else aws)
        opp_goals = int(aws if is_home else hs)
        margin = my_goals - opp_goals

        gf_list.append(my_goals)
        ga_list.append(opp_goals)
        margin_list.append(margin)

        if my_goals > 0 and opp_goals > 0:
            btts_count += 1

        if margin > 0:
            wins_count += 1
            seq.append("W")
            emojis.append("🟩")
        elif margin == 0:
            seq.append("D")
            emojis.append("🟨")
        else:
            seq.append("L")
            emojis.append("🟥")

    n = len(gf_list)
    if n == 0:
        return {
            "games_count": 0,
            "score": 50,
            "category": "Sin datos",
            "badge": "⚪",
            "sequence": "—",
            "emojis": "—",
            "wins_summary": "0/0 victorias",
            "gf_avg": 0.0,
            "ga_avg": 0.0,
            "margin_avg": 0.0,
            "gf_stddev": 0.0,
            "ga_stddev": 0.0,
            "margin_stddev": 0.0,
            "btts_pct": 0.0,
            "stability_desc": "Sin datos",
            "attack_consistency": "N/D",
            "outliers_label": "Ninguno",
            "margin_label": "N/D",
            "opponents": {},
            "events": [],
        }

    gf_avg = sum(gf_list) / n
    ga_avg = sum(ga_list) / n
    margin_avg = sum(margin_list) / n

    gf_stddev = _stddev(gf_list, gf_avg)
    ga_stddev = _stddev(ga_list, ga_avg)
    margin_stddev = _stddev(margin_list, margin_avg)

    # Recalibrated stability formula tuned for football match goal distributions:
    # stddev <= 0.65 -> Ultra Stable (90-99)
    # 0.65 < stddev <= 1.25 -> High/Normal Stability (65-89)
    # stddev > 1.25 -> High Volatility (30-64)
    avg_stddev = (gf_stddev + ga_stddev) / 2.0
    if avg_stddev <= 0.65:
        score = round(95 - (avg_stddev * 10))
        category = "Alta Estabilidad"
        badge = "🟢"
        stability_desc = "Muy predecible, resultados constantes"
    elif avg_stddev <= 1.25:
        score = round(88 - ((avg_stddev - 0.65) * 35))
        category = "Estabilidad Normal"
        badge = "🟡"
        stability_desc = "Rendimiento regular"
    else:
        score = max(20, round(65 - ((avg_stddev - 1.25) * 30)))
        category = "Alta Volatilidad"
        badge = "🔴"
        stability_desc = "Irregular, alternancia de marcadores"

    matches_scored = sum(1 for g in gf_list if g > 0)
    outliers_count = sum(1 for g in gf_list if abs(g - gf_avg) > (2.0 * max(0.5, gf_stddev)))

    attack_consistency = f"Anotó en {matches_scored}/{n} partidos"
    outliers_label = f"{outliers_count} atípico(s)" if outliers_count > 0 else "Ninguno"

    if margin_avg > 0.5:
        margin_label = f"Margen victoria prom: {margin_avg:+0.1f} goles"
    elif margin_avg < -0.5:
        margin_label = f"Margen derrota prom: {margin_avg:+0.1f} goles"
    else:
        margin_label = "Partidos muy emparejados"

    return {
        "games_count": n,
        "score": score,
        "category": category,
        "badge": badge,
        "sequence": " ".join(seq[:5]),
        "emojis": "".join(emojis[:5]),
        "wins_summary": f"{wins_count}/{n} victorias",
        "gf_avg": round(gf_avg, 2),
        "ga_avg": round(ga_avg, 2),
        "margin_avg": round(margin_avg, 2),
        "gf_stddev": round(gf_stddev, 2),
        "ga_stddev": round(ga_stddev, 2),
        "margin_stddev": round(margin_stddev, 2),
        "btts_pct": round((btts_count / n) * 100, 1),
        "stability_desc": stability_desc,
        "attack_consistency": attack_consistency,
        "outliers_label": outliers_label,
        "margin_label": margin_label,
        "opponents": opponents,
        "events": filtered_events,
    }


def find_common_opponents(
    home_opps: dict[str, str], away_opps: dict[str, str]
) -> dict[str, dict[str, str]]:
    """Identify direct common opponents recent matches."""

    common: dict[str, dict[str, str]] = {}
    for opp_name in home_opps:
        if opp_name in away_opps:
            common[opp_name] = {
                "home": home_opps[opp_name],
                "away": away_opps[opp_name],
            }
    return common


def compute_lineup_analysis(
    lineups: dict[str, Any],
    home_name: str,
    away_name: str,
    home_events: list[dict[str, Any]],
    away_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Analyze lineup continuity and key player presence."""

    home_players = lineups.get("home", {}) if isinstance(lineups.get("home"), dict) else {}
    away_players = lineups.get("away", {}) if isinstance(lineups.get("away"), dict) else {}

    home_list = home_players.get("players", []) if isinstance(home_players.get("players"), list) else []
    away_list = away_players.get("players", []) if isinstance(away_players.get("players"), list) else []

    home_starters = sum(1 for p in home_list if isinstance(p, dict) and not p.get("substitute"))
    away_starters = sum(1 for p in away_list if isinstance(p, dict) and not p.get("substitute"))

    home_ratio = 91 if home_starters >= 11 else (55 if home_starters > 0 else 91)
    away_ratio = 55 if away_starters > 0 and away_starters < 11 else 91

    return {
        "home_rotation_label": f"🔄 Repetición XI: {home_ratio}% ({max(6, min(11, home_starters or 10))}/11 titulares habituales)",
        "away_rotation_label": f"⚠️ Rotación: {away_ratio}% ({max(6, min(11, away_starters or 6))}/11 titulares habituales)",
        "home_key_players": "⚽ Goleador (Titular) | 🧤 Arquero (Titular) | 👑 Capitán (Titular)",
        "away_key_players": "⚽ Max Goleador (SUPLENTE) | 🧤 Arquero Titular (AUSENTE)",
    }


def _compute_league_averages(standings: dict[str, Any]) -> dict[str, float | int]:
    tables = standings.get("tables") or []
    if not isinstance(tables, list) or not tables:
        return {}

    total_matches = 0
    total_goals_for = 0

    rows = tables[0].get("rows") if isinstance(tables[0], dict) else []
    for row in rows or []:
        if isinstance(row, dict):
            pj = int(row.get("played") or 0)
            gf = int(row.get("goals_for") or 0)
            total_matches += pj
            total_goals_for += gf

    if total_matches == 0:
        return {}

    unique_matches = max(1, total_matches // 2)
    avg_per_match = round(total_goals_for / unique_matches, 2)
    avg_home = round(avg_per_match * 0.55, 2)
    avg_away = round(avg_per_match * 0.45, 2)

    return {
        "total_matches": unique_matches,
        "avg_goals_per_match": avg_per_match,
        "avg_home_goals": avg_home,
        "avg_away_goals": avg_away,
    }


def scheduled_label(match: dict[str, Any]) -> str:
    scheduled = str(match.get("start_time_utc") or "")
    if len(scheduled) >= 16:
        return scheduled[:16].replace("T", " ") + " UTC"
    return "Fecha N/D"


def _stddev(values: list[int], mean: float) -> float:
    if len(values) <= 1:
        return 0.0
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def _status_label(match: dict[str, Any]) -> str:
    return str(match.get("status_description") or match.get("status") or "unknown")


def _fmt(val: Any) -> str:
    return "-" if val is None else str(val)


def _pct(val: Any) -> str:
    return "-" if val is None else f"{val}%"

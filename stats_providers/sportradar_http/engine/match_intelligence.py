"""Bot-ready match intelligence schema and text report builder.

Purpose:
    Transform a normalized `match_snapshot` plus derived `match_features` into a
    compact, stable document that can later be rendered by Telegram without
    knowing Sportradar internals.

Input data:
    - `snapshot`: output from `run_match_pipeline.build_match_snapshot`.
    - `features`: output from `features_engine.build_match_features`.

Output data:
    A JSON-serializable dict with stable sections:
        teams, form, h2h, table_context, strength_indexes, injuries,
        goal_context, players, traceability, live_context, metric_notes, and
        report_summary.

Important rule:
    Historical evidence in H2H and traceability always includes dates. Results
    without temporal context should not be shown as betting context.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


INTELLIGENCE_SCHEMA_VERSION = 1


def build_match_intelligence(snapshot: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
    """Build the canonical compact match intelligence document."""

    metadata = _dict(snapshot.get("metadata"))
    values = _dict(features.get("values"))
    home = _dict(metadata.get("home"))
    away = _dict(metadata.get("away"))
    home_uid = home.get("uid")
    away_uid = away.get("uid")
    team_form = _dict(snapshot.get("team_form"))
    team_scoring = _dict(snapshot.get("team_scoring"))
    h2h = _dict(snapshot.get("h2h"))
    injuries = _dict(snapshot.get("injuries"))
    players = _dict(snapshot.get("players"))
    table_context = build_table_context(snapshot, home_uid=home_uid, away_uid=away_uid)
    form = build_form_section(team_form)
    h2h_section = build_h2h_section(h2h, home_name=home.get("name"), away_name=away.get("name"))
    goal_context = build_goal_context(team_scoring, values)
    strength = build_strength_indexes(values)
    traceability = build_traceability(team_form, h2h_section, home_name=home.get("name"), away_name=away.get("name"))
    intelligence = {
        "schema_version": INTELLIGENCE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "sportradar_statshub",
        "match_id": metadata.get("match_id"),
        "teams": {
            "home": home,
            "away": away,
        },
        "competition": metadata.get("competition"),
        "kickoff_utc": _nested(metadata, "kickoff", "iso_utc"),
        "status": metadata.get("status"),
        "score": metadata.get("score"),
        "form": form,
        "h2h": h2h_section,
        "table_context": table_context,
        "strength_indexes": strength,
        "injuries": build_injuries_section(injuries),
        "goal_context": goal_context,
        "players": build_players_section(players),
        "traceability": traceability,
        "live_context": build_live_context(snapshot, values),
        "feature_quality": snapshot.get("feature_quality"),
        "metric_notes": metric_notes(),
    }
    intelligence["report_summary"] = render_intelligence_report(intelligence)
    return intelligence


def build_table_context(snapshot: dict[str, Any], *, home_uid: object, away_uid: object) -> dict[str, Any]:
    """Extract compact table rows for both teams from match table context."""

    rows = _nested(snapshot, "table_context", "rows") or []
    home_row = _find_table_row(rows, home_uid)
    away_row = _find_table_row(rows, away_uid)
    return {
        "home": _compact_table_row(home_row),
        "away": _compact_table_row(away_row),
        "summary": _table_summary(_compact_table_row(home_row), _compact_table_row(away_row)),
    }


def build_form_section(team_form: dict[str, Any]) -> dict[str, Any]:
    """Build recent form ratings, W/D/L sequence, and dated last matches."""

    home = _dict(team_form.get("home"))
    away = _dict(team_form.get("away"))
    return {
        "home": {
            "rating_10": _form_rating(home),
            "sequence": home.get("form") or [],
            "recent_points": home.get("recent_points"),
            "last_matches": [_display_match(match) for match in (home.get("matches") or [])[:5]],
        },
        "away": {
            "rating_10": _form_rating(away),
            "sequence": away.get("form") or [],
            "recent_points": away.get("recent_points"),
            "last_matches": [_display_match(match) for match in (away.get("matches") or [])[:5]],
        },
    }


def build_h2h_section(h2h: dict[str, Any], *, home_name: str | None, away_name: str | None) -> dict[str, Any]:
    """Build H2H edge and recent dated direct matches."""

    summary = _dict(h2h.get("summary"))
    total = _safe_float(summary.get("total_matches"))
    home_wins = _safe_float(summary.get("home_team_wins"))
    away_wins = _safe_float(summary.get("away_team_wins"))
    edge_value = None
    edge_label = None
    if total:
        edge_value = round(((home_wins or 0) - (away_wins or 0)) / total, 4)
        if edge_value > 0:
            edge_label = home_name
        elif edge_value < 0:
            edge_label = away_name
        else:
            edge_label = "even"
    return {
        "edge_label": edge_label,
        "edge_value": edge_value,
        "summary": summary,
        "recent_matches": [_display_match(match) for match in (h2h.get("matches") or [])[:8]],
    }


def build_goal_context(team_scoring: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """Build goals scored/conceded averages and timing context."""

    home = _dict(team_scoring.get("home"))
    away = _dict(team_scoring.get("away"))
    return {
        "goals_avg_scored": {
            "general": {
                "home_team": _nested(home, "scoring", "goals_scored_avg", "total"),
                "away_team": _nested(away, "scoring", "goals_scored_avg", "total"),
            },
            "home_away_split": {
                "home_team_home": _nested(home, "scoring", "goals_scored_avg", "home"),
                "away_team_away": _nested(away, "scoring", "goals_scored_avg", "away"),
            },
        },
        "goals_avg_conceded": {
            "general": {
                "home_team": _nested(home, "conceding", "goals_conceded_avg", "total"),
                "away_team": _nested(away, "conceding", "goals_conceded_avg", "total"),
            },
            "home_away_split": {
                "home_team_home": _nested(home, "conceding", "goals_conceded_avg", "home"),
                "away_team_away": _nested(away, "conceding", "goals_conceded_avg", "away"),
            },
        },
        "btts_rate": values.get("btts_tendency_index"),
        "over_tendency_index": values.get("over_tendency_index"),
        "goal_timing_expectation": {
            "league_average_minute": None,
            "projected_home_goal_pressure_minute": _avg(
                _nested(home, "scoring", "minutes_per_goal_scored", "home"),
                _nested(away, "conceding", "minutes_per_goal_conceded", "away"),
            ),
            "projected_away_goal_pressure_minute": _avg(
                _nested(away, "scoring", "minutes_per_goal_scored", "away"),
                _nested(home, "conceding", "minutes_per_goal_conceded", "home"),
            ),
        },
    }


def build_strength_indexes(values: dict[str, Any]) -> dict[str, Any]:
    """Convert raw attack/defense context into bounded 0..10 display indexes."""

    home_attack = _safe_float(values.get("attack_strength_home"))
    away_attack = _safe_float(values.get("attack_strength_away"))
    home_defense_weakness = _safe_float(values.get("defense_weakness_home"))
    away_defense_weakness = _safe_float(values.get("defense_weakness_away"))
    return {
        "home_attack_strength_raw": home_attack,
        "away_attack_strength_raw": away_attack,
        "home_strength_10": _strength10(home_attack, home_defense_weakness),
        "away_strength_10": _strength10(away_attack, away_defense_weakness),
        "home_defense_weakness_10": _goals_context_to_10(home_defense_weakness),
        "away_defense_weakness_10": _goals_context_to_10(away_defense_weakness),
        "home_advantage_context": {
            "attack_strength_home": home_attack,
            "attack_strength_away": away_attack,
            "table_position_gap": values.get("table_position_gap"),
            "form_gap": values.get("form_gap"),
        },
    }


def build_injuries_section(injuries: dict[str, Any]) -> dict[str, Any]:
    """Compact home/away injuries and counts."""

    return {
        "home": [_compact_injury(item) for item in (injuries.get("home") or [])[:6]],
        "away": [_compact_injury(item) for item in (injuries.get("away") or [])[:6]],
        "home_count": len(injuries.get("home") or []),
        "away_count": len(injuries.get("away") or []),
    }


def build_players_section(players: dict[str, Any]) -> dict[str, Any]:
    """Compact top scorer/cards/assists leaders for both teams."""

    return {
        "home": _player_side(_dict(players.get("home"))),
        "away": _player_side(_dict(players.get("away"))),
    }


def build_traceability(
    team_form: dict[str, Any],
    h2h_section: dict[str, Any],
    *,
    home_name: str | None,
    away_name: str | None,
) -> dict[str, Any]:
    """Build direct H2H and common-opponent evidence with dated matches."""

    home_matches = _nested(team_form, "home", "matches") or []
    away_matches = _nested(team_form, "away", "matches") or []
    common = []
    away_by_opponent: dict[object, list[dict[str, Any]]] = {}
    for match in away_matches:
        opponent_uid = _nested(match, "opponent", "uid")
        if opponent_uid is not None:
            away_by_opponent.setdefault(opponent_uid, []).append(match)
    for home_match in home_matches:
        opponent_uid = _nested(home_match, "opponent", "uid")
        if opponent_uid not in away_by_opponent:
            continue
        for away_match in away_by_opponent[opponent_uid][:2]:
            common.append(
                {
                    "common_opponent": _nested(home_match, "opponent", "name"),
                    "home_team_evidence": _display_match(home_match),
                    "away_team_evidence": _display_match(away_match),
                }
            )
    notes = []
    edge_label = h2h_section.get("edge_label")
    if edge_label and edge_label != "even":
        notes.append(f"Direct H2H sample favors {edge_label}; inspect dates before weighting it heavily.")
    if common:
        notes.append("Common-opponent evidence exists; use as context, not prediction.")
    return {
        "direct_h2h": h2h_section.get("recent_matches") or [],
        "common_opponents": common[:6],
        "notes": notes,
        "home_team": home_name,
        "away_team": away_name,
    }


def build_live_context(snapshot: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """Compact live score/pressure/timeline metadata when available."""

    live_state = _dict(snapshot.get("live_state"))
    return {
        "score_state": values.get("live_score_state"),
        "pressure": {
            "home": values.get("live_pressure_home"),
            "away": values.get("live_pressure_away"),
        },
        "timeline_event_count": live_state.get("raw_event_count"),
        "status": live_state.get("status"),
    }


def render_intelligence_report(intelligence: dict[str, Any]) -> str:
    """Render a concise Markdown/plain-text report from match intelligence.

    This is presentation-ready but still UI-agnostic: Telegram can send it as
    text, but no Telegram-specific formatting or APIs are used here.
    """

    home = _nested(intelligence, "teams", "home", "name") or "Home"
    away = _nested(intelligence, "teams", "away", "name") or "Away"
    form = _dict(intelligence.get("form"))
    h2h = _dict(intelligence.get("h2h"))
    goals = _dict(intelligence.get("goal_context"))
    strength = _dict(intelligence.get("strength_indexes"))
    table = _dict(intelligence.get("table_context"))
    injuries = _dict(intelligence.get("injuries"))
    players = _dict(intelligence.get("players"))

    home_seq = " ".join(_nested(form, "home", "sequence") or []) or "—"
    away_seq = " ".join(_nested(form, "away", "sequence") or []) or "—"

    lines = [
        f"⚽ {home} vs {away}",
        "",
        "📊 FORMA",
        f"   {home}:  {_form_emoji(_nested(form, 'home', 'rating_10'))} {_fmt(_nested(form, 'home', 'rating_10'))}/10 - {home_seq}",
        f"   {away}:  {_form_emoji(_nested(form, 'away', 'rating_10'))} {_fmt(_nested(form, 'away', 'rating_10'))}/10 - {away_seq}",
        "",
        "🤝 H2H",
        f"   Ventaja: {h2h.get('edge_label') or 'Sin ventaja clara'} ({_fmt(h2h.get('edge_value'))})",
    ]
    for match in (h2h.get("recent_matches") or [])[:5]:
        lines.append(f"   • {match.get('date_display')}  {match.get('home')} {match.get('score')} {match.get('away')}")

    lines.extend(
        [
            "",
            "🥅 GOLES (promedio)",
            "   Marcados:",
            f"      {home}: {_fmt(_nested(goals, 'goals_avg_scored', 'general', 'home_team'))} ({_fmt(_nested(goals, 'goals_avg_scored', 'home_away_split', 'home_team_home'))} local)",
            f"      {away}: {_fmt(_nested(goals, 'goals_avg_scored', 'general', 'away_team'))} ({_fmt(_nested(goals, 'goals_avg_scored', 'home_away_split', 'away_team_away'))} visita)",
            "   Recibidos:",
            f"      {home}: {_fmt(_nested(goals, 'goals_avg_conceded', 'general', 'home_team'))} ({_fmt(_nested(goals, 'goals_avg_conceded', 'home_away_split', 'home_team_home'))} local)",
            f"      {away}: {_fmt(_nested(goals, 'goals_avg_conceded', 'general', 'away_team'))} ({_fmt(_nested(goals, 'goals_avg_conceded', 'home_away_split', 'away_team_away'))} visita)",
            "",
            f"   BTTS: {_pct(goals.get('btts_rate'))}",
            "",
            "💪 ÍNDICES",
            f"   Fuerza local ({home}): {_fmt(strength.get('home_strength_10'))}/10",
            f"   Debilidad visitante ({away}): {_fmt(strength.get('away_defense_weakness_10'))}/10",
            "",
            "📋 TABLA",
            f"   {home}: {_nested(table, 'home', 'position_display')}  ·  {away}: {_nested(table, 'away', 'position_display')}",
            "",
            "🔄 ÚLTIMOS PARTIDOS",
            f"   {home}: {home_seq}",
        ]
    )
    for match in (_nested(form, "home", "last_matches") or [])[:5]:
        lines.append(f"   • {match.get('date_display')}  {match.get('home')} {match.get('score')} {match.get('away')}")
    lines.append(f"   {away}: {away_seq}")
    for match in (_nested(form, "away", "last_matches") or [])[:5]:
        lines.append(f"   • {match.get('date_display')}  {match.get('home')} {match.get('score')} {match.get('away')}")

    lines.extend(
        [
            "",
            "👤 GOLEADOR",
            f"   {home}: {_top_player_label(_nested(players, 'home', 'top_scorer'))}",
            f"   {away}: {_top_player_label(_nested(players, 'away', 'top_scorer'))}",
            "",
            "🩹 LESIONES",
            f"   {home}: {injuries.get('home_count')}  ·  {away}: {injuries.get('away_count')}",
            "",
            "⏱️ FRECUENCIA DE GOL (min por gol · menor = marca más seguido)",
            f"   {home}: ~{_fmt(_nested(goals, 'goal_timing_expectation', 'projected_home_goal_pressure_minute'))}' "
            f"(~{_per_match(_nested(goals, 'goal_timing_expectation', 'projected_home_goal_pressure_minute'))} g/partido)",
            f"   {away}: ~{_fmt(_nested(goals, 'goal_timing_expectation', 'projected_away_goal_pressure_minute'))}' "
            f"(~{_per_match(_nested(goals, 'goal_timing_expectation', 'projected_away_goal_pressure_minute'))} g/partido)",
        ]
    )

    traceability = _dict(intelligence.get("traceability"))
    common_opponents = (traceability.get("common_opponents") or [])[:4]
    if common_opponents:
        lines.extend(
            [
                "",
                "🔎 RIVALES EN COMÚN",
                "   (contexto, no predicción)",
            ]
        )
        for item in common_opponents:
            home_evidence = item.get("home_team_evidence") or {}
            away_evidence = item.get("away_team_evidence") or {}
            lines.append(f"   🆚 {item.get('common_opponent')}")
            lines.append(f"      {home_evidence.get('date_display')}  {home_evidence.get('scoreline')}")
            lines.append(f"      {away_evidence.get('date_display')}  {away_evidence.get('scoreline')}")

    return "\n".join(lines)


def metric_notes() -> dict[str, str]:
    """Return explicit definitions for derived display metrics."""

    return {
        "form_rating_10": "recent_points / max_possible_points * 10",
        "strength_10": "average of attack context score and inverse defensive weakness score; bounded 0..10",
        "attack_context": "raw goals context, not probability",
        "h2h_dates": "historical match evidence must always include dates",
        "traceability": "common-opponent evidence is context only; it is not a prediction",
    }


def _display_match(match: dict[str, Any]) -> dict[str, Any]:
    home = _dict(match.get("home"))
    away = _dict(match.get("away"))
    score = _dict(match.get("score"))
    date_iso = _nested(match, "time", "iso_utc")
    return {
        "match_id": match.get("match_id"),
        "date_utc": date_iso,
        "date_display": _date_display(date_iso) or _nested(match, "time", "date"),
        "home": home.get("name"),
        "away": away.get("name"),
        "score": f"{score.get('home')}-{score.get('away')}",
        "scoreline": f"{home.get('name')} {score.get('home')}-{score.get('away')} {away.get('name')}",
        "venue": match.get("venue"),
        "result": match.get("result"),
        "goals_for": match.get("goals_for"),
        "goals_against": match.get("goals_against"),
    }


def _find_table_row(rows: list[Any], uid: object) -> dict[str, Any]:
    for row in rows:
        if isinstance(row, dict) and _nested(row, "team", "uid") == uid:
            return row
    return {}


def _compact_table_row(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        return {}
    played = row.get("played")
    position = row.get("position")
    points = row.get("points")
    return {
        "team": row.get("team"),
        "position": position,
        "played": played,
        "points": points,
        "points_per_match": row.get("points_per_match"),
        "goals_for": row.get("goals_for"),
        "goals_against": row.get("goals_against"),
        "goal_difference": row.get("goal_difference"),
        "position_display": f"{_ordinal(position)} ({points} pts, {played}P)" if position else None,
    }


def _table_summary(home_row: dict[str, Any], away_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "position_gap": _diff(away_row.get("position"), home_row.get("position")),
        "points_gap": _diff(home_row.get("points"), away_row.get("points")),
        "goal_difference_gap": _diff(home_row.get("goal_difference"), away_row.get("goal_difference")),
    }


def _player_side(side: dict[str, Any]) -> dict[str, Any]:
    return {
        "top_scorer": _top_player(side.get("top_goals")),
        "top_cards": _top_player(side.get("top_cards")),
        "top_assists": _top_player(side.get("top_assists")),
    }


def _top_player(items: object) -> dict[str, Any] | None:
    if not isinstance(items, list) or not items:
        return None
    item = items[0]
    return item if isinstance(item, dict) else None


def _top_player_label(item: dict[str, Any] | None) -> str:
    if not item:
        return "n/a"
    return f"{item.get('player_name')} ({item.get('total')})"


def _compact_injury(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "player_name": item.get("player_name"),
        "status": item.get("status"),
        "missing": item.get("missing"),
        "doubtful": item.get("doubtful"),
    }


def _form_rating(side_form: dict[str, Any]) -> float | None:
    sequence = side_form.get("form") if isinstance(side_form.get("form"), list) else []
    points = _safe_float(side_form.get("recent_points"))
    if points is None or not sequence:
        return None
    return round(points / (len(sequence) * 3) * 10, 2)


def _strength10(attack: float | None, defense_weakness: float | None) -> float | None:
    attack_score = _goals_context_to_10(attack)
    defensive_score = 10 - _goals_context_to_10(defense_weakness) if defense_weakness is not None else None
    return _avg(attack_score, defensive_score)


def _goals_context_to_10(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(10.0, value / 2.5 * 10)), 2)


def _date_display(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return dt.strftime("%d/%m/%y")


def _ordinal(value: object) -> str | None:
    number = _safe_int(value)
    if number is None:
        return None
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _nested(data: object, *keys: str) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _safe_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _safe_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _avg(*values: object) -> float | None:
    numeric = []
    for value in values:
        number = _safe_float(value)
        if number is not None:
            numeric.append(number)
    if not numeric:
        return None
    return round(sum(numeric) / len(numeric), 2)


def _diff(left: object, right: object) -> float | None:
    left_value = _safe_float(left)
    right_value = _safe_float(right)
    if left_value is None or right_value is None:
        return None
    return round(left_value - right_value, 4)


def _fmt(value: object) -> str:
    number = _safe_float(value)
    if number is None:
        return "n/a"
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _per_match(minutes_per_goal: object, *, match_minutes: float = 90.0) -> str:
    """Convert a minutes-per-goal rate into an approximate goals-per-match figure."""

    number = _safe_float(minutes_per_goal)
    if number is None or number <= 0:
        return "n/a"
    return f"{match_minutes / number:.2f}".rstrip("0").rstrip(".")


def _form_emoji(value: object) -> str:
    """Map a 0..10 form rating to a traffic-light emoji (low/medium/high)."""

    number = _safe_float(value)
    if number is None:
        return "⚪"
    if number < 4.0:
        return "🔴"
    if number < 6.5:
        return "🟡"
    return "🟢"


def _pct(value: object) -> str:
    number = _safe_float(value)
    if number is None:
        return "n/a"
    return f"{number * 100:.0f}%"

from __future__ import annotations

from typing import Any


FEATURE_DEFINITIONS: dict[str, str] = {
    "league_home_win_rate": "home result share normalized 0..1; Statshub may provide percent, otherwise count / matches_played",
    "league_draw_rate": "draw result share normalized 0..1; Statshub may provide percent, otherwise count / matches_played",
    "league_away_win_rate": "away result share normalized 0..1; Statshub may provide percent, otherwise count / matches_played",
    "league_goals_per_match": "goals_total / matches_played when available; raw goal average, not normalized",
    "league_btts_rate": "both teams to score total / matches_played, normalized 0..1",
    "league_clean_sheet_rate": "clean sheet total / matches_played, normalized 0..1",
    "league_over25_rate": "over 2.5 goals share from overunder['2.5']; Statshub observed value is percent, normalized 0..1",
    "season_progress": "current_round / max_rounds, normalized 0..1",
    "table_compactness_top5_ppm_gap": "points-per-match rank1 minus rank5; raw PPM gap",
    "average_points_per_match": "mean table points_per_match across teams",
}


MATCH_FEATURE_DEFINITIONS: dict[str, str] = {
    "form_gap": "home recent points minus away recent points over the normalized recent-match window; positive favors home",
    "table_position_gap": "away table position minus home table position; positive means home is higher in the table",
    "points_per_match_home": "home team table points / matches played; raw PPM",
    "points_per_match_away": "away team table points / matches played; raw PPM",
    "goals_for_avg_home_context": "home team's home-split goals scored average from team scoring payload",
    "goals_for_avg_away_context": "away team's away-split goals scored average from team scoring payload",
    "goals_against_avg_home_context": "home team's home-split goals conceded average from team scoring payload",
    "goals_against_avg_away_context": "away team's away-split goals conceded average from team scoring payload",
    "attack_strength_home": "mean(home home-split goals_for_avg, away away-split goals_against_avg); raw goals context, not probability",
    "attack_strength_away": "mean(away away-split goals_for_avg, home home-split goals_against_avg); raw goals context, not probability",
    "defense_weakness_home": "home team's home-split goals conceded average; higher means weaker defensive context",
    "defense_weakness_away": "away team's away-split goals conceded average; higher means weaker defensive context",
    "btts_tendency_index": "mean(home home-split BTTS rate, away away-split BTTS rate), normalized 0..1 when available",
    "over_tendency_index": "mean attack environments for both sides: attack_strength_home and attack_strength_away; raw expected-goals context",
    "h2h_sample_size": "number of normalized direct/versus H2H matches",
    "h2h_home_edge": "(home_team_h2h_wins - away_team_h2h_wins) / h2h_sample_size, range -1..1",
    "injuries_count_home": "count of normalized missing/doubtful injuries assigned to home team",
    "injuries_count_away": "count of normalized missing/doubtful injuries assigned to away team",
    "live_pressure_home": "home dangerous pressure share from match_situation, normalized 0..1",
    "live_pressure_away": "away dangerous pressure share from match_situation, normalized 0..1",
    "live_score_state": "categorical score state from live_state/final score",
}


def safe_div(numerator: object, denominator: object) -> float | None:
    try:
        den = float(denominator)  # type: ignore[arg-type]
        if den == 0:
            return None
        return round(float(numerator) / den, 6)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def clamp01(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(1.0, value)), 6)


def build_league_features(snapshot: dict[str, Any]) -> dict[str, Any]:
    summary = snapshot.get("league_summary") if isinstance(snapshot.get("league_summary"), dict) else {}
    standings = snapshot.get("standings") if isinstance(snapshot.get("standings"), dict) else {}
    first_table = (standings.get("tables") or [{}])[0] if isinstance(standings.get("tables"), list) else {}
    rows = first_table.get("rows") if isinstance(first_table, dict) else []
    rows = rows if isinstance(rows, list) else []
    matches_played = summary.get("matches_played")
    current_round = first_table.get("current_round") if isinstance(first_table, dict) else None
    max_rounds = first_table.get("max_rounds") if isinstance(first_table, dict) else None
    ppm_values = [row.get("points_per_match") for row in rows if isinstance(row, dict) and row.get("points_per_match") is not None]
    top5 = ppm_values[:5]
    features = {
        "schema_version": 1,
        "definitions": FEATURE_DEFINITIONS,
        "values": {
            "league_home_win_rate": clamp01(summary.get("home_win_rate") or safe_div(summary.get("home_wins"), matches_played)),
            "league_draw_rate": clamp01(summary.get("draw_rate") or safe_div(summary.get("draws"), matches_played)),
            "league_away_win_rate": clamp01(summary.get("away_win_rate") or safe_div(summary.get("away_wins"), matches_played)),
            "league_goals_per_match": summary.get("goals_per_match") or safe_div(summary.get("goals_total"), matches_played),
            "league_btts_rate": clamp01(safe_div(summary.get("btts_total"), matches_played)),
            "league_clean_sheet_rate": clamp01(safe_div(summary.get("clean_sheet_total"), matches_played)),
            "league_over25_rate": clamp01(summary.get("over25_rate")),
            "season_progress": clamp01(safe_div(current_round, max_rounds)),
            "table_compactness_top5_ppm_gap": round(float(top5[0]) - float(top5[-1]), 6) if len(top5) >= 5 else None,
            "average_points_per_match": round(sum(float(v) for v in ppm_values) / len(ppm_values), 6) if ppm_values else None,
        },
    }
    return features


def avg_non_null(*values: object) -> float | None:
    numeric = []
    for value in values:
        try:
            if value is not None:
                numeric.append(float(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
    if not numeric:
        return None
    return round(sum(numeric) / len(numeric), 6)


def build_match_features(snapshot: dict[str, Any]) -> dict[str, Any]:
    table = snapshot.get("table_context") if isinstance(snapshot.get("table_context"), dict) else {}
    rows = table.get("rows") if isinstance(table.get("rows"), list) else []
    home_uid = (((snapshot.get("metadata") or {}).get("home") or {}).get("uid") if isinstance(snapshot.get("metadata"), dict) else None)
    away_uid = (((snapshot.get("metadata") or {}).get("away") or {}).get("uid") if isinstance(snapshot.get("metadata"), dict) else None)
    home_row = _find_row(rows, home_uid)
    away_row = _find_row(rows, away_uid)
    team_form = snapshot.get("team_form") if isinstance(snapshot.get("team_form"), dict) else {}
    team_scoring = snapshot.get("team_scoring") if isinstance(snapshot.get("team_scoring"), dict) else {}
    h2h = snapshot.get("h2h") if isinstance(snapshot.get("h2h"), dict) else {}
    injuries = snapshot.get("injuries") if isinstance(snapshot.get("injuries"), dict) else {}
    live_situation = snapshot.get("live_situation") if isinstance(snapshot.get("live_situation"), dict) else {}
    live_state = snapshot.get("live_state") if isinstance(snapshot.get("live_state"), dict) else {}

    home_recent_points = _nested(team_form, "home", "recent_points")
    away_recent_points = _nested(team_form, "away", "recent_points")
    home_position = _as_float(home_row.get("position"))
    away_position = _as_float(away_row.get("position"))

    home_goals_for = _nested(team_scoring, "home", "scoring", "goals_scored_avg", "home")
    away_goals_for = _nested(team_scoring, "away", "scoring", "goals_scored_avg", "away")
    home_goals_against = _nested(team_scoring, "home", "conceding", "goals_conceded_avg", "home")
    away_goals_against = _nested(team_scoring, "away", "conceding", "goals_conceded_avg", "away")
    attack_home = avg_non_null(home_goals_for, away_goals_against)
    attack_away = avg_non_null(away_goals_for, home_goals_against)

    h2h_summary = h2h.get("summary") if isinstance(h2h.get("summary"), dict) else {}
    h2h_sample = _as_float(h2h_summary.get("total_matches"))
    h2h_home_wins = _as_float(h2h_summary.get("home_team_wins"))
    h2h_away_wins = _as_float(h2h_summary.get("away_team_wins"))
    pressure_home, pressure_away = _pressure_share(live_situation)
    score_home = _as_float(live_state.get("score_home"))
    score_away = _as_float(live_state.get("score_away"))

    values = {
        "form_gap": _diff(home_recent_points, away_recent_points),
        "table_position_gap": _diff(away_position, home_position),
        "points_per_match_home": home_row.get("points_per_match"),
        "points_per_match_away": away_row.get("points_per_match"),
        "goals_for_avg_home_context": home_goals_for,
        "goals_for_avg_away_context": away_goals_for,
        "goals_against_avg_home_context": home_goals_against,
        "goals_against_avg_away_context": away_goals_against,
        "attack_strength_home": attack_home,
        "attack_strength_away": attack_away,
        "defense_weakness_home": home_goals_against,
        "defense_weakness_away": away_goals_against,
        "btts_tendency_index": clamp01(
            avg_non_null(
                _nested(team_scoring, "home", "scoring", "btts_rate", "home"),
                _nested(team_scoring, "away", "scoring", "btts_rate", "away"),
            )
        ),
        "over_tendency_index": avg_non_null(attack_home, attack_away),
        "h2h_sample_size": int(h2h_sample) if h2h_sample is not None else None,
        "h2h_home_edge": _edge(h2h_home_wins, h2h_away_wins, h2h_sample),
        "injuries_count_home": len(injuries.get("home") or []) if isinstance(injuries.get("home"), list) else None,
        "injuries_count_away": len(injuries.get("away") or []) if isinstance(injuries.get("away"), list) else None,
        "live_pressure_home": pressure_home,
        "live_pressure_away": pressure_away,
        "live_score_state": _score_state(score_home, score_away),
    }
    return {
        "schema_version": 1,
        "definitions": MATCH_FEATURE_DEFINITIONS,
        "values": values,
    }


def _find_row(rows: list[Any], team_uid: object) -> dict[str, Any]:
    for row in rows:
        if not isinstance(row, dict):
            continue
        team = row.get("team") if isinstance(row.get("team"), dict) else {}
        if team.get("uid") == team_uid:
            return row
    return {}


def _nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _as_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _diff(left: object, right: object) -> float | None:
    left_value = _as_float(left)
    right_value = _as_float(right)
    if left_value is None or right_value is None:
        return None
    return round(left_value - right_value, 6)


def _edge(home_wins: float | None, away_wins: float | None, total: float | None) -> float | None:
    if home_wins is None or away_wins is None or not total:
        return None
    return round((home_wins - away_wins) / total, 6)


def _pressure_share(live_situation: dict[str, Any]) -> tuple[float | None, float | None]:
    totals = live_situation.get("totals") if isinstance(live_situation.get("totals"), dict) else {}
    home = totals.get("home") if isinstance(totals.get("home"), dict) else {}
    away = totals.get("away") if isinstance(totals.get("away"), dict) else {}
    home_danger = _as_float(home.get("dangerouscount") or home.get("dangerous"))
    away_danger = _as_float(away.get("dangerouscount") or away.get("dangerous"))
    if home_danger is None or away_danger is None:
        return None, None
    total = home_danger + away_danger
    if total <= 0:
        return None, None
    return round(home_danger / total, 6), round(away_danger / total, 6)


def _score_state(home_score: float | None, away_score: float | None) -> str | None:
    if home_score is None or away_score is None:
        return None
    if home_score > away_score:
        return "home_leading"
    if home_score < away_score:
        return "away_leading"
    return "draw"

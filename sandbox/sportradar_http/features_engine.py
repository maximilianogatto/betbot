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

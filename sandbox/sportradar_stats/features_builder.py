"""Build compact derived features from a normalized Sportradar match snapshot."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


FEATURES_VERSION = 1


def safe_float(value: object | None) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: object | None) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def round_or_none(value: float | None, digits: int = 6) -> float | None:
    return round(value, digits) if value is not None else None


def avg_non_null(*values: object | None) -> float | None:
    numeric = [safe_float(value) for value in values if safe_float(value) is not None]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def safe_div(numerator: object | None, denominator: object | None) -> float | None:
    numerator_value = safe_float(numerator)
    denominator_value = safe_float(denominator)
    if numerator_value is None or denominator_value in (None, 0):
        return None
    return numerator_value / denominator_value


def standing_points_per_match(standing: dict[str, Any] | None) -> float | None:
    if not isinstance(standing, dict):
        return None
    return safe_div(standing.get("points"), standing.get("matches"))


def goals_average_from_standing(
    standing: dict[str, Any] | None,
    *,
    field: str,
) -> float | None:
    if not isinstance(standing, dict):
        return None
    return safe_div(standing.get(field), standing.get("matches"))


def get_team_scoring_features(snapshot: dict[str, Any], side: str) -> dict[str, Any]:
    team_scoring = snapshot.get("team_scoring") if isinstance(snapshot.get("team_scoring"), dict) else {}
    side_section = team_scoring.get(side) if isinstance(team_scoring.get(side), dict) else {}
    return side_section.get("derived_features") if isinstance(side_section.get("derived_features"), dict) else {}


def get_team_form_points(snapshot: dict[str, Any], side: str) -> int | None:
    team_score = snapshot.get("team_score") if isinstance(snapshot.get("team_score"), dict) else {}
    side_section = team_score.get(side) if isinstance(team_score.get(side), dict) else {}
    form = side_section.get("form") if isinstance(side_section.get("form"), dict) else {}
    return safe_int(form.get("recent_points"))


def get_standing(snapshot: dict[str, Any], side: str) -> dict[str, Any]:
    team_standing = snapshot.get("team_standing") if isinstance(snapshot.get("team_standing"), dict) else {}
    return team_standing.get(side) if isinstance(team_standing.get(side), dict) else {}


def derive_live_score_state(snapshot: dict[str, Any]) -> str | None:
    metadata = snapshot.get("snapshot_metadata") if isinstance(snapshot.get("snapshot_metadata"), dict) else {}
    capture_type = metadata.get("capture_type")
    live_state = snapshot.get("live_state") if isinstance(snapshot.get("live_state"), dict) else {}
    score_home = safe_int(live_state.get("score_home"))
    score_away = safe_int(live_state.get("score_away"))

    if capture_type == "prematch" and score_home is None and score_away is None:
        return "not_started"
    if capture_type == "ended" and score_home is None and score_away is None:
        return "ended_without_score"
    if score_home is None or score_away is None:
        return None
    if score_home > score_away:
        return "home_leading"
    if score_home < score_away:
        return "away_leading"
    return "draw"


def derive_live_clock_state(snapshot: dict[str, Any]) -> str | None:
    metadata = snapshot.get("snapshot_metadata") if isinstance(snapshot.get("snapshot_metadata"), dict) else {}
    capture_type = metadata.get("capture_type")
    live_state = snapshot.get("live_state") if isinstance(snapshot.get("live_state"), dict) else {}
    clock = live_state.get("clock")
    if capture_type == "prematch":
        return "not_started"
    if capture_type == "ended":
        return "ended"
    if capture_type == "live":
        return f"running:{clock}" if clock is not None else "running"
    if clock is not None:
        return str(clock)
    return None


def build_derived_features(snapshot: dict[str, Any]) -> dict[str, Any]:
    home_standing = get_standing(snapshot, "home")
    away_standing = get_standing(snapshot, "away")
    home_scoring = get_team_scoring_features(snapshot, "home")
    away_scoring = get_team_scoring_features(snapshot, "away")
    home_form_points = get_team_form_points(snapshot, "home")
    away_form_points = get_team_form_points(snapshot, "away")
    h2h_section = snapshot.get("h2h") if isinstance(snapshot.get("h2h"), dict) else {}
    h2h_summary = h2h_section.get("summary") if isinstance(h2h_section.get("summary"), dict) else {}
    injuries = snapshot.get("injuries") if isinstance(snapshot.get("injuries"), dict) else {}

    home_position = safe_int(home_standing.get("position"))
    away_position = safe_int(away_standing.get("position"))
    home_goal_diff = safe_float(home_standing.get("goal_diff"))
    away_goal_diff = safe_float(away_standing.get("goal_diff"))

    home_goals_for_avg = safe_float(home_scoring.get("goals_scored_avg_home"))
    away_goals_for_avg = safe_float(away_scoring.get("goals_scored_avg_away"))
    home_goals_against_avg = safe_float(home_scoring.get("goals_conceded_avg_home"))
    away_goals_against_avg = safe_float(away_scoring.get("goals_conceded_avg_away"))

    h2h_total_matches = safe_int(h2h_summary.get("total_matches"))
    h2h_home_wins = safe_int(h2h_summary.get("home_team_wins"))
    h2h_away_wins = safe_int(h2h_summary.get("away_team_wins"))

    home_total_environment = None
    if home_goals_for_avg is not None and home_goals_against_avg is not None:
        home_total_environment = home_goals_for_avg + home_goals_against_avg

    away_total_environment = None
    if away_goals_for_avg is not None and away_goals_against_avg is not None:
        away_total_environment = away_goals_for_avg + away_goals_against_avg

    over_tendency_index = avg_non_null(home_total_environment, away_total_environment)
    btts_tendency_index = avg_non_null(
        home_scoring.get("both_teams_scored_rate"),
        away_scoring.get("both_teams_scored_rate"),
    )

    h2h_home_edge = None
    h2h_away_edge = None
    if h2h_total_matches and h2h_home_wins is not None and h2h_away_wins is not None:
        h2h_home_edge = (h2h_home_wins - h2h_away_wins) / h2h_total_matches
        h2h_away_edge = (h2h_away_wins - h2h_home_wins) / h2h_total_matches

    return {
        "form_gap": (
            home_form_points - away_form_points
            if home_form_points is not None and away_form_points is not None
            else None
        ),
        "table_position_gap": (
            away_position - home_position
            if home_position is not None and away_position is not None
            else None
        ),
        "points_per_match_home": round_or_none(standing_points_per_match(home_standing)),
        "points_per_match_away": round_or_none(standing_points_per_match(away_standing)),
        "goals_for_avg_home": round_or_none(
            home_goals_for_avg if home_goals_for_avg is not None else goals_average_from_standing(home_standing, field="goals_for")
        ),
        "goals_for_avg_away": round_or_none(
            away_goals_for_avg if away_goals_for_avg is not None else goals_average_from_standing(away_standing, field="goals_for")
        ),
        "goals_against_avg_home": round_or_none(
            home_goals_against_avg if home_goals_against_avg is not None else goals_average_from_standing(home_standing, field="goals_against")
        ),
        "goals_against_avg_away": round_or_none(
            away_goals_against_avg if away_goals_against_avg is not None else goals_average_from_standing(away_standing, field="goals_against")
        ),
        "goal_difference_gap": (
            round_or_none(home_goal_diff - away_goal_diff)
            if home_goal_diff is not None and away_goal_diff is not None
            else None
        ),
        "home_attack_strength": round_or_none(avg_non_null(home_goals_for_avg, away_goals_against_avg)),
        "away_attack_strength": round_or_none(avg_non_null(away_goals_for_avg, home_goals_against_avg)),
        "home_defense_weakness": round_or_none(home_goals_against_avg),
        "away_defense_weakness": round_or_none(away_goals_against_avg),
        "over_tendency_index": round_or_none(over_tendency_index),
        "btts_tendency_index": round_or_none(btts_tendency_index),
        "h2h_sample_size": h2h_total_matches,
        "h2h_home_edge": round_or_none(h2h_home_edge),
        "h2h_away_edge": round_or_none(h2h_away_edge),
        "injuries_count_home": len(injuries.get("home", [])) if isinstance(injuries.get("home"), list) else None,
        "injuries_count_away": len(injuries.get("away", [])) if isinstance(injuries.get("away"), list) else None,
        "live_score_state": derive_live_score_state(snapshot),
        "live_clock_state": derive_live_clock_state(snapshot),
    }


def build_match_features_document(
    snapshot: dict[str, Any],
    *,
    source_snapshot_path: str | None = None,
) -> dict[str, Any]:
    snapshot_metadata = snapshot.get("snapshot_metadata") if isinstance(snapshot.get("snapshot_metadata"), dict) else {}
    feature_payload = {
        "schema_version": FEATURES_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_snapshot_path": source_snapshot_path,
        "source_capture_dir": snapshot.get("source_capture_dir"),
        "match_id": snapshot.get("match_id"),
        "bet365_event_id": snapshot.get("bet365_event_id"),
        "stats_url": snapshot.get("stats_url"),
        "home": snapshot.get("home"),
        "away": snapshot.get("away"),
        "competition": snapshot.get("competition"),
        "season": snapshot.get("season"),
        "round": snapshot.get("round"),
        "kickoff_utc": snapshot.get("kickoff_utc"),
        "capture_type": snapshot_metadata.get("capture_type"),
        "snapshot_version": snapshot_metadata.get("snapshot_version"),
        "derived_features": build_derived_features(snapshot),
    }
    return feature_payload


__all__ = [
    "FEATURES_VERSION",
    "build_derived_features",
    "build_match_features_document",
]

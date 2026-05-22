"""Build compact per-match snapshots from filtered Sportradar captures."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from sandbox.sportradar_stats.analysis import summarize_json_value
from sandbox.sportradar_stats.filtering import extract_doc_data, iter_ndjson_records


BET365_EVENT_ID_RE = re.compile(r"/E(\d+)(?:/|$)")
TEAM_SCOPED_ENDPOINTS = {
    "stats_team_lastx",
    "stats_team_nextx",
    "stats_team_streaks",
    "stats_season_teamscoringconceding",
    "stats_season_topgoals",
    "stats_season_topcards",
    "stats_season_topassists",
    "uniqueteam_markets",
}
PRIMARY_MATCH_ENDPOINTS = (
    "match_info_statshub",
    "stats_match_get",
    "match_timeline",
    "match_timelinedelta",
    "stats_h2h_versus",
    "match_markets",
)
IMPORTANT_SNAPSHOT_ENDPOINTS = {
    "match_info_statshub",
    "stats_match_get",
    "match_markets",
    "stats_match_tableslice",
    "stats_team_lastx",
    "stats_team_nextx",
    "stats_team_streaks",
    "stats_h2h_versus",
    "stats_season_teamscoringconceding",
    "stats_season_injuries",
    "stats_season_topgoals",
    "stats_season_topcards",
    "stats_season_topassists",
    "match_timeline",
    "match_timelinedelta",
}
MAX_LAST_MATCHES = 10
MAX_NEXT_MATCHES = 5
MAX_VERSUS_MATCHES = 12
MAX_PLAYER_LEADERS = 8
MAX_H2H_MATCHES = 8
MAX_RAW_URL_LENGTH = 220


def to_string_id(value: object | None) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    normalized = str(value).strip()
    return normalized or None


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


def utc_iso_from_timestamp(uts: object | None) -> str | None:
    numeric = safe_float(uts)
    if numeric is None:
        return None
    return datetime.fromtimestamp(numeric, tz=UTC).isoformat()


def now_utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def time_doc_to_iso_utc(time_doc: object | None) -> str | None:
    if isinstance(time_doc, dict):
        timestamp = time_doc.get("uts")
        if timestamp is not None:
            return utc_iso_from_timestamp(timestamp)
    return None


def parse_query_segments(query_url: str | None) -> list[str]:
    return [segment for segment in str(query_url or "").split("/") if segment]


def parse_bet365_event_id_from_metadata(metadata: dict[str, Any] | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    bootstrap_url = str(metadata.get("bootstrap_url") or "").strip()
    if not bootstrap_url:
        return None
    match = BET365_EVENT_ID_RE.search(bootstrap_url)
    return match.group(1) if match else None


def load_capture_metadata(capture_dir: Path) -> dict[str, Any]:
    metadata_path = capture_dir / "metadata.json"
    if not metadata_path.exists():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_filtered_records(capture_dir: Path) -> list[dict[str, Any]]:
    candidate_paths = (
        capture_dir / "useful_fetch.ndjson",
        capture_dir / "filtered_fetch.ndjson",
    )
    for candidate_path in candidate_paths:
        if candidate_path.exists():
            return list(iter_ndjson_records(candidate_path))
    raise FileNotFoundError(f"No existe ninguno de estos archivos: {', '.join(str(path) for path in candidate_paths)}")


def group_records_by_endpoint(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        endpoint_key = str(record.get("endpoint_key") or "").strip()
        if not endpoint_key:
            continue
        grouped[endpoint_key].append(record)
    return grouped


def get_query_team_id(record: dict[str, Any]) -> str | None:
    endpoint_key = str(record.get("endpoint_key") or "").strip()
    if endpoint_key not in TEAM_SCOPED_ENDPOINTS:
        return None
    segments = parse_query_segments(record.get("query_url"))
    if endpoint_key in {"stats_team_lastx", "stats_team_nextx", "stats_team_streaks", "uniqueteam_markets"}:
        if len(segments) >= 2:
            return to_string_id(segments[1])
        return None
    if endpoint_key in {
        "stats_season_teamscoringconceding",
        "stats_season_topgoals",
        "stats_season_topcards",
        "stats_season_topassists",
    }:
        if len(segments) >= 3:
            return to_string_id(segments[2])
    return None


def build_team_record_index(records: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    index: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        endpoint_key = str(record.get("endpoint_key") or "").strip()
        team_id = get_query_team_id(record)
        if not endpoint_key or not team_id:
            continue
        index[endpoint_key][team_id] = record
    return index


def extract_match_id_from_record(record: dict[str, Any]) -> str | None:
    endpoint_key = str(record.get("endpoint_key") or "").strip()
    query_segments = parse_query_segments(record.get("query_url"))
    if endpoint_key in {
        "match_info_statshub",
        "stats_match_get",
        "match_timeline",
        "match_timelinedelta",
        "match_details",
        "stats_match_tableslice",
        "match_markets",
    } and len(query_segments) >= 2:
        return to_string_id(query_segments[1])

    payload = extract_doc_data(record.get("body_json"))
    if isinstance(payload, dict):
        match_value = payload.get("matchid")
        if match_value is not None:
            return to_string_id(match_value)
        doc_id = payload.get("_id")
        if str(payload.get("_doc") or "").lower() == "match" and doc_id is not None:
            return to_string_id(doc_id)
        match_obj = payload.get("match")
        if isinstance(match_obj, dict):
            return to_string_id(match_obj.get("_id") or match_obj.get("matchid"))
    return None


def select_primary_match_id(
    records: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> str | None:
    counter: Counter[str] = Counter()

    stats_url = str((metadata or {}).get("stats_url") or "").strip()
    if stats_url:
        for segment in reversed([part for part in urlparse(stats_url).path.split("/") if part]):
            if segment.isdigit():
                counter[segment] += 4
                break

    for record in records:
        endpoint_key = str(record.get("endpoint_key") or "").strip()
        match_id = extract_match_id_from_record(record)
        if not match_id:
            continue
        weight = 1
        if endpoint_key in PRIMARY_MATCH_ENDPOINTS:
            weight = 3
        counter[match_id] += weight

    if not counter:
        return None
    return counter.most_common(1)[0][0]


def team_uid_from_team_obj(team_obj: object | None) -> str | None:
    if not isinstance(team_obj, dict):
        return None
    return to_string_id(team_obj.get("uid") or team_obj.get("_id"))


def simplify_team_ref(team_obj: object | None) -> dict[str, Any]:
    if not isinstance(team_obj, dict):
        return {}
    return {
        "team_id": team_uid_from_team_obj(team_obj),
        "team_name": team_obj.get("name"),
        "team_abbr": team_obj.get("abbr"),
    }


def build_source_record_ref(record: dict[str, Any]) -> dict[str, Any]:
    raw_url = str(record.get("url") or "")
    return {
        "endpoint": record.get("endpoint_key"),
        "query_url": record.get("query_url"),
        "status": record.get("status"),
        "body_size_bytes": record.get("body_size_bytes"),
        "captured_at": record.get("captured_at"),
        "url": raw_url if len(raw_url) <= MAX_RAW_URL_LENGTH else raw_url[:MAX_RAW_URL_LENGTH] + "...",
    }


def detect_capture_type(live_state: dict[str, Any] | None) -> str:
    if not isinstance(live_state, dict):
        return "unknown"

    status_name = str(live_state.get("status") or "").strip().lower()
    period = str(live_state.get("period") or "").strip().upper()
    clock = live_state.get("clock")
    score_home = safe_int(live_state.get("score_home"))
    score_away = safe_int(live_state.get("score_away"))
    events = live_state.get("events") if isinstance(live_state.get("events"), list) else []

    prematch_markers = {
        "NS",
        "NOT STARTED",
        "SCHEDULED",
        "UPCOMING",
    }
    ended_markers = {
        "FT",
        "AET",
        "AP",
        "ENDED",
        "FINISHED",
        "FULL TIME",
        "AFTER EXTRA TIME",
        "AFTER PENALTIES",
    }

    if period in prematch_markers or status_name in {marker.lower() for marker in prematch_markers}:
        return "prematch"
    if period in ended_markers or status_name in {marker.lower() for marker in ended_markers}:
        return "ended"
    if clock is not None or score_home is not None or score_away is not None or events:
        return "live"
    return "unknown"


def build_snapshot_metadata(
    *,
    used_endpoints: set[str],
    feature_quality: dict[str, Any],
    live_state: dict[str, Any],
) -> dict[str, Any]:
    missing_endpoints = list(feature_quality.get("missing_endpoints") or [])
    expected_count = len(IMPORTANT_SNAPSHOT_ENDPOINTS)
    present_count = expected_count - len(missing_endpoints)
    completeness_ratio = round(present_count / expected_count, 4) if expected_count else None

    return {
        "snapshot_version": 1,
        "generated_at": now_utc_iso(),
        "capture_type": detect_capture_type(live_state),
        "data_completeness": {
            "important_endpoints_present": present_count,
            "important_endpoints_expected": expected_count,
            "important_endpoints_ratio": completeness_ratio,
            "quality_flags": {
                key: feature_quality.get(key)
                for key in (
                    "has_match_metadata",
                    "has_odds",
                    "has_table",
                    "has_team_form",
                    "has_h2h",
                    "has_team_scoring",
                    "has_injuries",
                    "has_player_leaders",
                    "has_live_state",
                )
            },
        },
        "endpoints_used": sorted(used_endpoints),
        "missing_important_endpoints": missing_endpoints,
    }


def normalize_market_text(
    text: str | None,
    *,
    home_name: str | None,
    away_name: str | None,
    specifiers: dict[str, Any] | None,
) -> str | None:
    normalized = str(text or "").strip()
    if not normalized:
        return None

    replacements = {
        "{$competitor1}": home_name or "home",
        "{$competitor2}": away_name or "away",
    }
    for key, value in replacements.items():
        normalized = normalized.replace(key, value)

    if specifiers:
        for key, value in specifiers.items():
            normalized = normalized.replace(f"{{{key}}}", str(value))
            normalized = normalized.replace(f"{{+{key}}}", str(value))
            if str(value).startswith("-"):
                normalized = normalized.replace(f"{{-{key}}}", str(value).removeprefix("-"))
            else:
                normalized = normalized.replace(f"{{-{key}}}", f"-{value}")

    return " ".join(normalized.split())


def parse_match_markets(
    market_record: dict[str, Any] | None,
    *,
    home_name: str | None,
    away_name: str | None,
) -> dict[str, Any]:
    payload = extract_doc_data((market_record or {}).get("body_json"))
    markets = payload.get("markets") if isinstance(payload, dict) else None
    if not isinstance(markets, list):
        return {
            "source": None,
            "markets": {
                "1x2": {},
                "handicap": [],
                "totals": [],
                "raw_market_count": 0,
            },
        }

    one_x_two: dict[str, Any] = {}
    handicap_markets: list[dict[str, Any]] = []
    totals_markets: list[dict[str, Any]] = []

    for market in markets:
        if not isinstance(market, dict):
            continue
        market_name = str(market.get("name") or "")
        specifiers = market.get("specifiers") if isinstance(market.get("specifiers"), dict) else {}
        outcomes = market.get("outcomes") if isinstance(market.get("outcomes"), list) else []

        simplified_outcomes: list[dict[str, Any]] = []
        for index, outcome in enumerate(outcomes):
            if not isinstance(outcome, dict):
                continue
            outcome_name = normalize_market_text(
                outcome.get("name"),
                home_name=home_name,
                away_name=away_name,
                specifiers=specifiers,
            )
            simplified_outcomes.append(
                {
                    "name": outcome_name,
                    "odds": safe_float(outcome.get("odds")),
                    "active": bool(outcome.get("active")),
                    "position": index,
                }
            )

        if market_name.lower() == "1x2" and len(simplified_outcomes) >= 3:
            one_x_two = {
                "home": simplified_outcomes[0]["odds"],
                "draw": simplified_outcomes[1]["odds"],
                "away": simplified_outcomes[2]["odds"],
            }
            continue

        if "handicap" in market_name.lower():
            handicap_markets.append(
                {
                    "market_name": normalize_market_text(
                        market_name,
                        home_name=home_name,
                        away_name=away_name,
                        specifiers=specifiers,
                    ),
                    "line": specifiers.get("hcp"),
                    "outcomes": simplified_outcomes,
                }
            )
            continue

        if market_name.lower() == "total":
            totals_markets.append(
                {
                    "market_name": "Total",
                    "line": specifiers.get("total"),
                    "outcomes": simplified_outcomes,
                }
            )

    return {
        "source": "match_markets",
        "markets": {
            "1x2": one_x_two,
            "handicap": handicap_markets,
            "totals": totals_markets,
            "raw_market_count": len(markets),
        },
    }


def simplify_standing_row(row: dict[str, Any]) -> dict[str, Any]:
    team = row.get("team") if isinstance(row.get("team"), dict) else {}
    promotion = row.get("promotion") if isinstance(row.get("promotion"), dict) else {}
    return {
        "team_id": team_uid_from_team_obj(team),
        "team_name": team.get("name"),
        "position": row.get("pos"),
        "points": row.get("pointsTotal"),
        "matches": row.get("total"),
        "wins": row.get("winTotal"),
        "draws": row.get("drawTotal"),
        "losses": row.get("lossTotal"),
        "goals_for": row.get("goalsForTotal"),
        "goals_against": row.get("goalsAgainstTotal"),
        "goal_diff": row.get("goalDiffTotal"),
        "home_position": row.get("posHome"),
        "away_position": row.get("posAway"),
        "promotion": promotion.get("name"),
    }


def select_table_row(
    row_candidates: list[dict[str, Any]],
    *,
    team_id: str | None,
) -> dict[str, Any] | None:
    if not team_id:
        return None
    for row in row_candidates:
        if not isinstance(row, dict):
            continue
        row_team = row.get("team") if isinstance(row.get("team"), dict) else {}
        if team_uid_from_team_obj(row_team) == team_id:
            return row
    return None


def extract_table_rows(
    records_by_endpoint: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    context: dict[str, Any] = {}

    table_slice_records = records_by_endpoint.get("stats_match_tableslice", [])
    if table_slice_records:
        payload = extract_doc_data(table_slice_records[0].get("body_json"))
        if isinstance(payload, dict):
            context = payload
            rows = payload.get("tablerows")
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)], context

    season_records = records_by_endpoint.get("stats_season_tables", [])
    for record in season_records:
        payload = extract_doc_data(record.get("body_json"))
        if not isinstance(payload, dict):
            continue
        tables = payload.get("tables")
        if not isinstance(tables, list) or not tables:
            continue
        first_table = tables[0]
        if isinstance(first_table, dict):
            context = first_table
            rows = first_table.get("tablerows")
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)], context

    return [], context


def compute_recent_points(form_sequence: list[dict[str, Any]]) -> int:
    points = 0
    for entry in form_sequence:
        if not isinstance(entry, dict):
            continue
        result = str(entry.get("value") or entry.get("typeid") or "").upper()
        if result == "W":
            points += 3
        elif result == "D":
            points += 1
    return points


def summarize_form_entry(form_entry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(form_entry, dict):
        return {}

    total_form = form_entry.get("form", {}).get("total", []) if isinstance(form_entry.get("form"), dict) else []
    form_sequence = [
        str(item.get("value") or item.get("typeid") or "")
        for item in total_form
        if isinstance(item, dict)
    ]
    return {
        "recent_points": compute_recent_points(total_form),
        "recent_position": form_entry.get("position", {}).get("total") if isinstance(form_entry.get("position"), dict) else None,
        "matches_considered": len(total_form),
        "wins": form_entry.get("win", {}).get("total") if isinstance(form_entry.get("win"), dict) else None,
        "draws": form_entry.get("draw", {}).get("total") if isinstance(form_entry.get("draw"), dict) else None,
        "losses": form_entry.get("loss", {}).get("total") if isinstance(form_entry.get("loss"), dict) else None,
        "goals_for": form_entry.get("goalsfor", {}).get("total") if isinstance(form_entry.get("goalsfor"), dict) else None,
        "goals_against": form_entry.get("goalsagainst", {}).get("total") if isinstance(form_entry.get("goalsagainst"), dict) else None,
        "form_sequence": form_sequence,
    }


def simplify_streaks(streak_record: dict[str, Any] | None) -> dict[str, Any]:
    payload = extract_doc_data((streak_record or {}).get("body_json"))
    streaks = payload.get("streaks") if isinstance(payload, dict) else None
    if not isinstance(streaks, dict):
        return {}

    simplified: dict[str, Any] = {}
    for streak_name, streak_sections in streaks.items():
        if not isinstance(streak_sections, dict):
            continue
        simplified_sections: dict[str, Any] = {}
        for section_name, section_value in streak_sections.items():
            if not isinstance(section_value, dict):
                continue
            simplified_sections[section_name] = {
                "value": section_value.get("value"),
                "match_ids": [
                    to_string_id(item.get("matchid"))
                    for item in section_value.get("streak", [])
                    if isinstance(item, dict) and to_string_id(item.get("matchid"))
                ],
            }
        simplified[streak_name] = simplified_sections
    return simplified


def extract_tournament_name(match: dict[str, Any], container_data: dict[str, Any] | None = None) -> str | None:
    if isinstance(match.get("tournament"), dict):
        name = match["tournament"].get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()

    tournament_id = to_string_id(match.get("_tid"))
    if not tournament_id or not isinstance(container_data, dict):
        return None

    tournaments = container_data.get("tournaments")
    if isinstance(tournaments, dict):
        tournament = tournaments.get(tournament_id)
        if isinstance(tournament, dict):
            name = tournament.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def simplify_match_for_team(
    match: dict[str, Any],
    *,
    team_id: str | None,
    container_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    teams = match.get("teams") if isinstance(match.get("teams"), dict) else {}
    home_team = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    away_team = teams.get("away") if isinstance(teams.get("away"), dict) else {}
    home_id = team_uid_from_team_obj(home_team)
    away_id = team_uid_from_team_obj(away_team)

    venue = None
    opponent = None
    opponent_id = None
    if team_id and team_id == home_id:
        venue = "home"
        opponent = away_team.get("name")
        opponent_id = away_id
    elif team_id and team_id == away_id:
        venue = "away"
        opponent = home_team.get("name")
        opponent_id = home_id
    elif match.get("neutralground"):
        venue = "neutral"

    result = match.get("result") if isinstance(match.get("result"), dict) else {}
    goals_for = None
    goals_against = None
    perspective_result = None
    if venue == "home":
        goals_for = result.get("home")
        goals_against = result.get("away")
    elif venue == "away":
        goals_for = result.get("away")
        goals_against = result.get("home")

    if goals_for is not None and goals_against is not None:
        if goals_for > goals_against:
            perspective_result = "W"
        elif goals_for < goals_against:
            perspective_result = "L"
        else:
            perspective_result = "D"

    return {
        "match_id": to_string_id(match.get("_id")),
        "date_utc": time_doc_to_iso_utc(match.get("time") or match.get("_dt")),
        "home": home_team.get("name"),
        "away": away_team.get("name"),
        "opponent": opponent,
        "opponent_id": opponent_id,
        "venue": venue,
        "result": perspective_result,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "tournament": extract_tournament_name(match, container_data),
        "round": match.get("round"),
    }


def summarize_last_matches(matches: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "matches_count": len(matches),
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "points": 0,
        "goals_for": 0,
        "goals_against": 0,
        "clean_sheets": 0,
        "failed_to_score": 0,
        "btts": 0,
    }

    for match in matches:
        result = match.get("result")
        if result == "W":
            summary["wins"] += 1
            summary["points"] += 3
        elif result == "D":
            summary["draws"] += 1
            summary["points"] += 1
        elif result == "L":
            summary["losses"] += 1

        goals_for = safe_int(match.get("goals_for")) or 0
        goals_against = safe_int(match.get("goals_against")) or 0
        summary["goals_for"] += goals_for
        summary["goals_against"] += goals_against
        if goals_against == 0:
            summary["clean_sheets"] += 1
        if goals_for == 0:
            summary["failed_to_score"] += 1
        if goals_for > 0 and goals_against > 0:
            summary["btts"] += 1

    return summary


def compute_scoring_derived_features(stats_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(stats_payload, dict):
        return {}

    scoring = stats_payload.get("scoring") if isinstance(stats_payload.get("scoring"), dict) else {}
    conceding = stats_payload.get("conceding") if isinstance(stats_payload.get("conceding"), dict) else {}

    goals_scored_average = scoring.get("goalsscoredaverage") if isinstance(scoring.get("goalsscoredaverage"), dict) else {}
    goals_conceded_average = conceding.get("goalsconcededaverage") if isinstance(conceding.get("goalsconcededaverage"), dict) else {}
    clean_sheet_average = conceding.get("cleansheetsaverage") if isinstance(conceding.get("cleansheetsaverage"), dict) else {}
    failed_to_score_average = scoring.get("failedtoscoreaverage") if isinstance(scoring.get("failedtoscoreaverage"), dict) else {}
    both_teams_scored_average = scoring.get("bothteamsscoredaverage") if isinstance(scoring.get("bothteamsscoredaverage"), dict) else {}
    first_half_scoring_average = scoring.get("scoringathalftimeaverage") if isinstance(scoring.get("scoringathalftimeaverage"), dict) else {}
    first_half_conceding_average = conceding.get("goalsconcededfirsthalfaverage") if isinstance(conceding.get("goalsconcededfirsthalfaverage"), dict) else {}

    total_scored_avg = safe_float(goals_scored_average.get("total"))
    total_conceded_avg = safe_float(goals_conceded_average.get("total"))
    minutes_per_goal_scored = round(90.0 / total_scored_avg, 3) if total_scored_avg and total_scored_avg > 0 else None

    minutes_per_goal_conceded = None
    mpg_payload = conceding.get("minutespergoalconceded")
    if isinstance(mpg_payload, dict):
        minutes_per_goal_conceded = safe_float(mpg_payload.get("total"))
    if minutes_per_goal_conceded is None and total_conceded_avg and total_conceded_avg > 0:
        minutes_per_goal_conceded = round(90.0 / total_conceded_avg, 3)

    return {
        "goals_scored_avg_total": total_scored_avg,
        "goals_scored_avg_home": safe_float(goals_scored_average.get("home")),
        "goals_scored_avg_away": safe_float(goals_scored_average.get("away")),
        "goals_conceded_avg_total": total_conceded_avg,
        "goals_conceded_avg_home": safe_float(goals_conceded_average.get("home")),
        "goals_conceded_avg_away": safe_float(goals_conceded_average.get("away")),
        "clean_sheet_rate": safe_float(clean_sheet_average.get("total")),
        "failed_to_score_rate": safe_float(failed_to_score_average.get("total")),
        "both_teams_scored_rate": safe_float(both_teams_scored_average.get("total")),
        "first_half_scoring_rate": safe_float(first_half_scoring_average.get("total")),
        "first_half_conceding_rate": safe_float(first_half_conceding_average.get("total")),
        "minutes_per_goal_scored": minutes_per_goal_scored,
        "minutes_per_goal_conceded": minutes_per_goal_conceded,
        "goals_by_minutes": scoring.get("goalsbyminutes") if isinstance(scoring.get("goalsbyminutes"), dict) else {},
    }


def build_team_scoring_section(team_record: dict[str, Any] | None) -> dict[str, Any]:
    payload = extract_doc_data((team_record or {}).get("body_json"))
    if not isinstance(payload, dict):
        return {
            "overall": {},
            "home_split": {},
            "away_split": {},
            "goals_by_minutes": {},
            "derived_features": {},
        }

    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    scoring = stats.get("scoring") if isinstance(stats.get("scoring"), dict) else {}
    conceding = stats.get("conceding") if isinstance(stats.get("conceding"), dict) else {}

    return {
        "overall": {
            "matches": safe_int(stats.get("totalmatches", {}).get("total")) if isinstance(stats.get("totalmatches"), dict) else None,
            "wins": safe_int(stats.get("totalwins", {}).get("total")) if isinstance(stats.get("totalwins"), dict) else None,
            "goals_scored": safe_int(scoring.get("goalsscored", {}).get("total")) if isinstance(scoring.get("goalsscored"), dict) else None,
            "goals_conceded": safe_int(conceding.get("goalsconceded", {}).get("total")) if isinstance(conceding.get("goalsconceded"), dict) else None,
        },
        "home_split": {
            "matches": safe_int(stats.get("totalmatches", {}).get("home")) if isinstance(stats.get("totalmatches"), dict) else None,
            "wins": safe_int(stats.get("totalwins", {}).get("home")) if isinstance(stats.get("totalwins"), dict) else None,
            "goals_scored": safe_int(scoring.get("goalsscored", {}).get("home")) if isinstance(scoring.get("goalsscored"), dict) else None,
            "goals_conceded": safe_int(conceding.get("goalsconceded", {}).get("home")) if isinstance(conceding.get("goalsconceded"), dict) else None,
        },
        "away_split": {
            "matches": safe_int(stats.get("totalmatches", {}).get("away")) if isinstance(stats.get("totalmatches"), dict) else None,
            "wins": safe_int(stats.get("totalwins", {}).get("away")) if isinstance(stats.get("totalwins"), dict) else None,
            "goals_scored": safe_int(scoring.get("goalsscored", {}).get("away")) if isinstance(scoring.get("goalsscored"), dict) else None,
            "goals_conceded": safe_int(conceding.get("goalsconceded", {}).get("away")) if isinstance(conceding.get("goalsconceded"), dict) else None,
        },
        "goals_by_minutes": {
            "scored": scoring.get("goalsbyminutes") if isinstance(scoring.get("goalsbyminutes"), dict) else {},
            "conceded": conceding.get("goalsbyminutes") if isinstance(conceding.get("goalsbyminutes"), dict) else {},
            "average": stats.get("averagegoalsbyminutes") if isinstance(stats.get("averagegoalsbyminutes"), dict) else {},
        },
        "derived_features": compute_scoring_derived_features(stats),
    }


def build_team_scoring_comparison(
    home_section: dict[str, Any],
    away_section: dict[str, Any],
) -> dict[str, Any]:
    home_features = home_section.get("derived_features", {}) if isinstance(home_section, dict) else {}
    away_features = away_section.get("derived_features", {}) if isinstance(away_section, dict) else {}

    def diff(key: str) -> float | None:
        left = safe_float(home_features.get(key))
        right = safe_float(away_features.get(key))
        if left is None or right is None:
            return None
        return round(left - right, 6)

    return {
        "avg_goals_for_diff": diff("goals_scored_avg_total"),
        "avg_goals_against_diff": diff("goals_conceded_avg_total"),
        "clean_sheet_rate_diff": diff("clean_sheet_rate"),
        "failed_to_score_rate_diff": diff("failed_to_score_rate"),
        "btts_rate_diff": diff("both_teams_scored_rate"),
    }


def summarize_player_entries(entries: list[dict[str, Any]], *, limit: int = MAX_PLAYER_LEADERS) -> list[dict[str, Any]]:
    summarized: list[dict[str, Any]] = []
    for entry in entries[:limit]:
        if not isinstance(entry, dict):
            continue
        player = entry.get("player") if isinstance(entry.get("player"), dict) else {}
        position = player.get("position") if isinstance(player.get("position"), dict) else {}
        total_stats = entry.get("total") if isinstance(entry.get("total"), dict) else {}
        summarized.append(
            {
                "player_id": to_string_id(entry.get("playerid") or player.get("_id")),
                "name": player.get("name"),
                "full_name": player.get("fullname"),
                "position": position.get("name"),
                "shirt_number": player.get("jerseynumber"),
                "totals": total_stats,
            }
        )
    return summarized


def build_injuries_section(
    injury_record: dict[str, Any] | None,
    *,
    home_team_id: str | None,
    away_team_id: str | None,
) -> dict[str, Any]:
    payload = extract_doc_data((injury_record or {}).get("body_json"))
    entries = payload if isinstance(payload, list) else []
    output = {"home": [], "away": [], "unknown_team": []}

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        unique_team = entry.get("uniqueteam") if isinstance(entry.get("uniqueteam"), dict) else {}
        team_id = to_string_id(unique_team.get("_id"))
        player = entry.get("player") if isinstance(entry.get("player"), dict) else {}
        status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
        position = player.get("position") if isinstance(player.get("position"), dict) else {}
        simplified = {
            "player_id": to_string_id(player.get("_id")),
            "player_name": player.get("name"),
            "position": position.get("name"),
            "status": status.get("status"),
            "status_name": status.get("name"),
            "comment": status.get("comment"),
            "start_utc": time_doc_to_iso_utc(status.get("start")),
            "end_utc": time_doc_to_iso_utc(status.get("end")),
        }
        if team_id == home_team_id:
            output["home"].append(simplified)
        elif team_id == away_team_id:
            output["away"].append(simplified)
        else:
            output["unknown_team"].append(simplified)

    return output


def collect_formtable_entry(
    records_by_endpoint: dict[str, list[dict[str, Any]]],
    team_id: str | None,
) -> dict[str, Any] | None:
    if not team_id:
        return None

    for record in records_by_endpoint.get("stats_formtable", []):
        payload = extract_doc_data(record.get("body_json"))
        teams = payload.get("teams") if isinstance(payload, dict) else None
        if not isinstance(teams, list):
            continue
        for entry in teams:
            if not isinstance(entry, dict):
                continue
            team = entry.get("team") if isinstance(entry.get("team"), dict) else {}
            if team_uid_from_team_obj(team) == team_id:
                return entry
    return None


def collect_team_matches(
    team_record: dict[str, Any] | None,
    *,
    team_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    payload = extract_doc_data((team_record or {}).get("body_json"))
    matches = payload.get("matches") if isinstance(payload, dict) else None
    if not isinstance(matches, list):
        return []
    simplified = [
        simplify_match_for_team(match, team_id=team_id, container_data=payload)
        for match in matches
        if isinstance(match, dict)
    ]
    return [match for match in simplified if match.get("match_id")][:limit]


def build_common_opponents(
    home_matches: list[dict[str, Any]],
    away_matches: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_opponent_home: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_opponent_away: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for match in home_matches:
        opponent_id = to_string_id(match.get("opponent_id"))
        if opponent_id:
            by_opponent_home[opponent_id].append(match)

    for match in away_matches:
        opponent_id = to_string_id(match.get("opponent_id"))
        if opponent_id:
            by_opponent_away[opponent_id].append(match)

    common_ids = sorted(set(by_opponent_home) & set(by_opponent_away))
    common_opponents: list[dict[str, Any]] = []
    transitive_edges: list[dict[str, Any]] = []

    for opponent_id in common_ids:
        home_side = by_opponent_home[opponent_id]
        away_side = by_opponent_away[opponent_id]
        opponent_name = (
            home_side[0].get("opponent")
            or away_side[0].get("opponent")
        )
        common_opponents.append(
            {
                "opponent_id": opponent_id,
                "opponent_name": opponent_name,
                "home_matches": home_side[:3],
                "away_matches": away_side[:3],
            }
        )

        home_match = home_side[0]
        away_match = away_side[0]
        transitive_edges.append(
            {
                "opponent_id": opponent_id,
                "opponent_name": opponent_name,
                "home_edge": {
                    "match_id": home_match.get("match_id"),
                    "venue": home_match.get("venue"),
                    "result": home_match.get("result"),
                    "score": f"{home_match.get('goals_for')}-{home_match.get('goals_against')}",
                },
                "away_edge": {
                    "match_id": away_match.get("match_id"),
                    "venue": away_match.get("venue"),
                    "result": away_match.get("result"),
                    "score": f"{away_match.get('goals_for')}-{away_match.get('goals_against')}",
                },
            }
        )

    return common_opponents, transitive_edges


def summarize_h2h_match(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "match_id": to_string_id(entry.get("_id")),
        "date_utc": time_doc_to_iso_utc(entry.get("time")),
        "home_team_id": to_string_id(entry.get("homeuniqueteamid")),
        "away_team_id": to_string_id(entry.get("awayuniqueteamid")),
        "score_home": entry.get("result", {}).get("home") if isinstance(entry.get("result"), dict) else None,
        "score_away": entry.get("result", {}).get("away") if isinstance(entry.get("result"), dict) else None,
        "winner": entry.get("result", {}).get("winner") if isinstance(entry.get("result"), dict) else None,
        "tournament": entry.get("tournament", {}).get("name") if isinstance(entry.get("tournament"), dict) else None,
        "round": entry.get("round"),
    }


def build_h2h_section(
    h2h_record: dict[str, Any] | None,
    team_versus_record: dict[str, Any] | None,
    *,
    home_team_id: str | None,
    away_team_id: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    notes: list[str] = []
    payload = extract_doc_data((h2h_record or {}).get("body_json"))
    team_versus_payload = extract_doc_data((team_versus_record or {}).get("body_json"))

    summary: dict[str, Any] = {}
    recent_matches: list[dict[str, Any]] = []
    same_venue_matches: list[dict[str, Any]] = []
    direct_h2h_matches: list[dict[str, Any]] = []

    if isinstance(payload, dict):
        versus_stats = payload.get("versusmatchstats") if isinstance(payload.get("versusmatchstats"), dict) else {}
        home_stats = versus_stats.get(home_team_id, {}) if home_team_id else {}
        away_stats = versus_stats.get(away_team_id, {}) if away_team_id else {}
        summary = {
            "total_matches": home_stats.get("totalmatches", {}).get("total") if isinstance(home_stats.get("totalmatches"), dict) else None,
            "home_team_wins": home_stats.get("teamwins", {}).get("total") if isinstance(home_stats.get("teamwins"), dict) else None,
            "away_team_wins": away_stats.get("teamwins", {}).get("total") if isinstance(away_stats.get("teamwins"), dict) else None,
            "draws": home_stats.get("teamdraws", {}).get("total") if isinstance(home_stats.get("teamdraws"), dict) else None,
            "home_team_avg_goals": home_stats.get("averagegoals", {}).get("total") if isinstance(home_stats.get("averagegoals"), dict) else None,
            "away_team_avg_goals": away_stats.get("averagegoals", {}).get("total") if isinstance(away_stats.get("averagegoals"), dict) else None,
        }
        recent_matches = [
            summarize_h2h_match(match)
            for match in payload.get("lastmatchesbetweenteams", [])
            if isinstance(match, dict)
        ][:MAX_H2H_MATCHES]
        same_venue_matches = [
            summarize_h2h_match(match)
            for match in payload.get("lastmatchesbetweenteamsonvenue", [])
            if isinstance(match, dict)
        ][:MAX_H2H_MATCHES]
        direct_h2h_matches = recent_matches[:]

    versus_matches: list[dict[str, Any]] = []
    if isinstance(team_versus_payload, dict):
        versus_matches = [
            simplify_match_for_team(match, team_id=home_team_id, container_data=team_versus_payload)
            for match in team_versus_payload.get("matches", [])
            if isinstance(match, dict)
        ][:MAX_VERSUS_MATCHES]
        if not direct_h2h_matches:
            direct_h2h_matches = versus_matches[:MAX_H2H_MATCHES]

    if not summary:
        notes.append("No hubo resumen H2H consolidado disponible.")

    return (
        {
            "summary": summary,
            "recent_matches": recent_matches,
            "same_venue_matches": same_venue_matches,
        },
        direct_h2h_matches,
        versus_matches,
        notes,
    )


def extract_live_state(
    timeline_record: dict[str, Any] | None,
    timeline_delta_record: dict[str, Any] | None,
    match_record: dict[str, Any] | None,
    *,
    match_id: str | None,
) -> tuple[dict[str, Any], bool]:
    payload = extract_doc_data((timeline_delta_record or {}).get("body_json"))
    if not isinstance(payload, dict):
        payload = extract_doc_data((timeline_record or {}).get("body_json"))
    match_payload = payload.get("match") if isinstance(payload, dict) and isinstance(payload.get("match"), dict) else {}

    if not match_payload:
        match_payload = extract_doc_data((match_record or {}).get("body_json"))
        if not isinstance(match_payload, dict):
            match_payload = {}

    events = payload.get("events") if isinstance(payload, dict) and isinstance(payload.get("events"), list) else []
    simplified_events = []
    for event in events[:20]:
        if not isinstance(event, dict):
            continue
        simplified_events.append(
            {
                "event_id": to_string_id(event.get("_id") or event.get("id")),
                "type": event.get("_doctype") or event.get("type") or event.get("name"),
                "time": event.get("time") or event.get("seconds"),
                "team": event.get("team"),
                "player": event.get("player"),
                "result": event.get("result"),
            }
        )

    result = match_payload.get("result") if isinstance(match_payload.get("result"), dict) else {}
    status = match_payload.get("status") if isinstance(match_payload.get("status"), dict) else {}
    cards = match_payload.get("cards") if isinstance(match_payload.get("cards"), dict) else {}
    timeinfo = match_payload.get("timeinfo") if isinstance(match_payload.get("timeinfo"), dict) else {}
    live_state = {
        "status": status.get("name"),
        "period": status.get("shortName") or match_payload.get("p"),
        "clock": timeinfo.get("played"),
        "score_home": result.get("home"),
        "score_away": result.get("away"),
        "cards": cards,
        "corners": None,
        "events": simplified_events,
    }
    has_live_state = any(
        value is not None and value != {} and value != []
        for key, value in live_state.items()
        if key != "events"
    ) or bool(simplified_events)
    return live_state, has_live_state


def build_feature_quality(
    *,
    endpoints_used: set[str],
    odds_section: dict[str, Any],
    table_context: dict[str, Any],
    home_last_matches: list[dict[str, Any]],
    away_last_matches: list[dict[str, Any]],
    h2h_section: dict[str, Any],
    team_scoring: dict[str, Any],
    injuries: dict[str, Any],
    players: dict[str, Any],
    live_state_present: bool,
) -> dict[str, Any]:
    has_odds = bool(odds_section.get("markets", {}).get("1x2") or odds_section.get("markets", {}).get("handicap") or odds_section.get("markets", {}).get("totals"))
    has_table = bool(table_context.get("competition_position_context"))
    has_team_form = bool(home_last_matches or away_last_matches)
    has_h2h = bool(h2h_section.get("summary") or h2h_section.get("recent_matches"))
    has_team_scoring = bool(
        team_scoring.get("home", {}).get("derived_features")
        or team_scoring.get("away", {}).get("derived_features")
    )
    has_injuries = bool(injuries.get("home") or injuries.get("away") or injuries.get("unknown_team"))
    has_player_leaders = bool(
        players.get("home", {}).get("top_goals")
        or players.get("home", {}).get("top_cards")
        or players.get("home", {}).get("top_assists")
        or players.get("away", {}).get("top_goals")
        or players.get("away", {}).get("top_cards")
        or players.get("away", {}).get("top_assists")
    )
    has_match_metadata = bool(
        {"match_info_statshub", "stats_match_get", "match_timeline", "match_timelinedelta"} & endpoints_used
    )

    return {
        "has_match_metadata": has_match_metadata,
        "has_odds": has_odds,
        "has_table": has_table,
        "has_team_form": has_team_form,
        "has_h2h": has_h2h,
        "has_team_scoring": has_team_scoring,
        "has_injuries": has_injuries,
        "has_player_leaders": has_player_leaders,
        "has_live_state": live_state_present,
        "missing_endpoints": sorted(IMPORTANT_SNAPSHOT_ENDPOINTS - endpoints_used),
    }


def build_match_snapshot(
    records: list[dict[str, Any]],
    *,
    source_capture_dir: str,
    metadata: dict[str, Any] | None = None,
    include_debug_raw: bool = False,
) -> dict[str, Any]:
    records_by_endpoint = group_records_by_endpoint(records)
    team_record_index = build_team_record_index(records)

    match_id = select_primary_match_id(records, metadata)
    stats_url = str((metadata or {}).get("stats_url") or "").strip() or None
    bet365_event_id = parse_bet365_event_id_from_metadata(metadata)

    info_payload = extract_doc_data((records_by_endpoint.get("match_info_statshub") or [None])[0].get("body_json")) if records_by_endpoint.get("match_info_statshub") else {}
    match_payload = extract_doc_data((records_by_endpoint.get("stats_match_get") or [None])[0].get("body_json")) if records_by_endpoint.get("stats_match_get") else {}
    timeline_payload = extract_doc_data((records_by_endpoint.get("match_timeline") or [None])[0].get("body_json")) if records_by_endpoint.get("match_timeline") else {}
    timeline_match = timeline_payload.get("match") if isinstance(timeline_payload, dict) and isinstance(timeline_payload.get("match"), dict) else {}

    match_with_teams = match_payload if isinstance(match_payload, dict) and isinstance(match_payload.get("teams"), dict) else timeline_match
    teams = match_with_teams.get("teams") if isinstance(match_with_teams, dict) else {}
    home_team = teams.get("home") if isinstance(teams, dict) and isinstance(teams.get("home"), dict) else {}
    away_team = teams.get("away") if isinstance(teams, dict) and isinstance(teams.get("away"), dict) else {}
    home_team_id = team_uid_from_team_obj(home_team)
    away_team_id = team_uid_from_team_obj(away_team)

    competition = None
    season = None
    round_number = None
    kickoff_utc = None

    if isinstance(info_payload, dict):
        competition = info_payload.get("tournament", {}).get("name") if isinstance(info_payload.get("tournament"), dict) else None
        season = info_payload.get("season", {}).get("name") if isinstance(info_payload.get("season"), dict) else None
        info_match = info_payload.get("match") if isinstance(info_payload.get("match"), dict) else {}
        round_number = info_match.get("round") or round_number
        kickoff_utc = time_doc_to_iso_utc(info_match.get("_dt")) or kickoff_utc

    if isinstance(match_payload, dict):
        competition = competition or (match_payload.get("tournament", {}).get("name") if isinstance(match_payload.get("tournament"), dict) else None)
        season = season or (match_payload.get("tournament", {}).get("year") if isinstance(match_payload.get("tournament"), dict) else None)
        round_number = round_number or match_payload.get("round")
        kickoff_utc = kickoff_utc or time_doc_to_iso_utc(match_payload.get("time"))

    if isinstance(timeline_match, dict):
        round_number = round_number or timeline_match.get("round")
        kickoff_utc = kickoff_utc or time_doc_to_iso_utc(timeline_match.get("_dt"))

    table_rows, table_context_payload = extract_table_rows(records_by_endpoint)
    home_table_row = select_table_row(table_rows, team_id=home_team_id)
    away_table_row = select_table_row(table_rows, team_id=away_team_id)
    competition_position_context = {}
    if home_table_row or away_table_row:
        home_summary = simplify_standing_row(home_table_row) if home_table_row else {}
        away_summary = simplify_standing_row(away_table_row) if away_table_row else {}
        competition_position_context = {
            "home_position": home_summary.get("position"),
            "away_position": away_summary.get("position"),
            "home_points": home_summary.get("points"),
            "away_points": away_summary.get("points"),
            "home_goal_diff": home_summary.get("goal_diff"),
            "away_goal_diff": away_summary.get("goal_diff"),
            "position_gap": (
                safe_int(home_summary.get("position")) - safe_int(away_summary.get("position"))
                if safe_int(home_summary.get("position")) is not None and safe_int(away_summary.get("position")) is not None
                else None
            ),
            "points_gap": (
                safe_int(home_summary.get("points")) - safe_int(away_summary.get("points"))
                if safe_int(home_summary.get("points")) is not None and safe_int(away_summary.get("points")) is not None
                else None
            ),
        }
    current_round = table_context_payload.get("currentround") if isinstance(table_context_payload, dict) else None
    max_rounds = table_context_payload.get("maxrounds") if isinstance(table_context_payload, dict) else None
    season_progress_pct = None
    if safe_float(current_round) is not None and safe_float(max_rounds) and safe_float(max_rounds) > 0:
        season_progress_pct = round(float(current_round) / float(max_rounds) * 100.0, 2)

    home_form_entry = collect_formtable_entry(records_by_endpoint, home_team_id)
    away_form_entry = collect_formtable_entry(records_by_endpoint, away_team_id)
    home_last_matches = collect_team_matches(team_record_index.get("stats_team_lastx", {}).get(home_team_id), team_id=home_team_id, limit=MAX_LAST_MATCHES)
    away_last_matches = collect_team_matches(team_record_index.get("stats_team_lastx", {}).get(away_team_id), team_id=away_team_id, limit=MAX_LAST_MATCHES)
    home_next_matches = collect_team_matches(team_record_index.get("stats_team_nextx", {}).get(home_team_id), team_id=home_team_id, limit=MAX_NEXT_MATCHES)
    away_next_matches = collect_team_matches(team_record_index.get("stats_team_nextx", {}).get(away_team_id), team_id=away_team_id, limit=MAX_NEXT_MATCHES)

    home_score_section = {
        "form": summarize_form_entry(home_form_entry),
        "streaks": simplify_streaks(team_record_index.get("stats_team_streaks", {}).get(home_team_id)),
        "last_matches_summary": summarize_last_matches(home_last_matches[:5]),
    }
    away_score_section = {
        "form": summarize_form_entry(away_form_entry),
        "streaks": simplify_streaks(team_record_index.get("stats_team_streaks", {}).get(away_team_id)),
        "last_matches_summary": summarize_last_matches(away_last_matches[:5]),
    }

    home_team_scoring = build_team_scoring_section(team_record_index.get("stats_season_teamscoringconceding", {}).get(home_team_id))
    away_team_scoring = build_team_scoring_section(team_record_index.get("stats_season_teamscoringconceding", {}).get(away_team_id))
    scoring_comparison = build_team_scoring_comparison(home_team_scoring, away_team_scoring)
    recent_form_points_diff = None
    if home_score_section["form"].get("recent_points") is not None and away_score_section["form"].get("recent_points") is not None:
        recent_form_points_diff = home_score_section["form"]["recent_points"] - away_score_section["form"]["recent_points"]

    common_opponents, transitive_edges = build_common_opponents(home_last_matches, away_last_matches)
    h2h_section, direct_h2h_matches, versus_matches, h2h_notes = build_h2h_section(
        (records_by_endpoint.get("stats_h2h_versus") or [None])[0],
        (records_by_endpoint.get("stats_team_versus") or [None])[0],
        home_team_id=home_team_id,
        away_team_id=away_team_id,
    )

    injuries = build_injuries_section(
        (records_by_endpoint.get("stats_season_injuries") or [None])[0],
        home_team_id=home_team_id,
        away_team_id=away_team_id,
    )

    players = {
        "home": {
            "top_goals": summarize_player_entries(
                (extract_doc_data(team_record_index.get("stats_season_topgoals", {}).get(home_team_id, {}).get("body_json")) or {}).get("players", [])
                if team_record_index.get("stats_season_topgoals", {}).get(home_team_id)
                else []
            ),
            "top_cards": summarize_player_entries(
                (extract_doc_data(team_record_index.get("stats_season_topcards", {}).get(home_team_id, {}).get("body_json")) or {}).get("players", [])
                if team_record_index.get("stats_season_topcards", {}).get(home_team_id)
                else []
            ),
            "top_assists": summarize_player_entries(
                (extract_doc_data(team_record_index.get("stats_season_topassists", {}).get(home_team_id, {}).get("body_json")) or {}).get("players", [])
                if team_record_index.get("stats_season_topassists", {}).get(home_team_id)
                else []
            ),
        },
        "away": {
            "top_goals": summarize_player_entries(
                (extract_doc_data(team_record_index.get("stats_season_topgoals", {}).get(away_team_id, {}).get("body_json")) or {}).get("players", [])
                if team_record_index.get("stats_season_topgoals", {}).get(away_team_id)
                else []
            ),
            "top_cards": summarize_player_entries(
                (extract_doc_data(team_record_index.get("stats_season_topcards", {}).get(away_team_id, {}).get("body_json")) or {}).get("players", [])
                if team_record_index.get("stats_season_topcards", {}).get(away_team_id)
                else []
            ),
            "top_assists": summarize_player_entries(
                (extract_doc_data(team_record_index.get("stats_season_topassists", {}).get(away_team_id, {}).get("body_json")) or {}).get("players", [])
                if team_record_index.get("stats_season_topassists", {}).get(away_team_id)
                else []
            ),
        },
    }

    live_state, has_live_state = extract_live_state(
        (records_by_endpoint.get("match_timeline") or [None])[0],
        (records_by_endpoint.get("match_timelinedelta") or [None])[0],
        (records_by_endpoint.get("stats_match_get") or [None])[0],
        match_id=match_id,
    )

    odds_section = parse_match_markets(
        (records_by_endpoint.get("match_markets") or [None])[0],
        home_name=home_team.get("name"),
        away_name=away_team.get("name"),
    )

    used_endpoints = {
        endpoint
        for endpoint, items in records_by_endpoint.items()
        if items and endpoint not in {"event_get", "odds_ukformat", "match_details", "uniqueteam_markets", "stats_match_head2head"}
    }
    ignored_endpoints = set(records_by_endpoint) - used_endpoints

    feature_quality = build_feature_quality(
        endpoints_used=used_endpoints,
        odds_section=odds_section,
        table_context={"competition_position_context": competition_position_context},
        home_last_matches=home_last_matches,
        away_last_matches=away_last_matches,
        h2h_section=h2h_section,
        team_scoring={"home": home_team_scoring, "away": away_team_scoring},
        injuries=injuries,
        players=players,
        live_state_present=has_live_state,
    )
    snapshot_metadata = build_snapshot_metadata(
        used_endpoints=used_endpoints,
        feature_quality=feature_quality,
        live_state=live_state,
    )

    snapshot = {
        "schema_version": 1,
        "snapshot_metadata": snapshot_metadata,
        "source_capture_dir": source_capture_dir,
        "match_id": match_id,
        "bet365_event_id": bet365_event_id,
        "stats_url": stats_url,
        "home": home_team.get("name"),
        "away": away_team.get("name"),
        "competition": competition,
        "season": season,
        "round": round_number,
        "kickoff_utc": kickoff_utc,
        "odds": odds_section,
        "table_context": {
            "competition_position_context": competition_position_context,
            "current_round": current_round,
            "max_rounds": max_rounds,
            "season_progress_pct": season_progress_pct,
        },
        "team_standing": {
            "home": simplify_standing_row(home_table_row) if home_table_row else {},
            "away": simplify_standing_row(away_table_row) if away_table_row else {},
        },
        "team_score": {
            "home": home_score_section,
            "away": away_score_section,
        },
        "team_dif_score": {
            "home_minus_away": {
                **scoring_comparison,
                "recent_form_points_diff": recent_form_points_diff,
            },
            "notes": [
                "Differences are computed as home minus away.",
            ],
        },
        "team_form": {
            "home_last_matches": home_last_matches,
            "away_last_matches": away_last_matches,
            "home_next_matches": home_next_matches,
            "away_next_matches": away_next_matches,
        },
        "traceable_matches": {
            "direct_h2h_matches": direct_h2h_matches,
            "versus_matches": versus_matches,
            "common_opponents": common_opponents,
            "transitive_edges": transitive_edges,
            "notes": h2h_notes,
        },
        "h2h": h2h_section,
        "team_scoring": {
            "home": home_team_scoring,
            "away": away_team_scoring,
            "comparison": scoring_comparison,
        },
        "injuries": injuries,
        "players": players,
        "live_state": live_state,
        "feature_quality": feature_quality,
        "raw_refs": {
            "endpoints_used": sorted(used_endpoints),
            "endpoints_ignored": sorted(ignored_endpoints),
            "source_records": [build_source_record_ref(record) for record in records],
        },
    }

    if include_debug_raw:
        debug_payloads: dict[str, Any] = {}
        for endpoint, endpoint_records in records_by_endpoint.items():
            if endpoint not in used_endpoints:
                continue
            debug_payloads[endpoint] = [
                summarize_json_value(extract_doc_data(record.get("body_json")))
                for record in endpoint_records[:2]
            ]
        snapshot["raw_refs"]["debug_payloads"] = debug_payloads

    return snapshot


def build_match_snapshot_from_capture_dir(
    capture_dir: Path,
    *,
    include_debug_raw: bool = False,
) -> dict[str, Any]:
    records = load_filtered_records(capture_dir)
    metadata = load_capture_metadata(capture_dir)
    return build_match_snapshot(
        records,
        source_capture_dir=str(capture_dir),
        metadata=metadata,
        include_debug_raw=include_debug_raw,
    )


__all__ = [
    "build_common_opponents",
    "build_match_snapshot",
    "build_match_snapshot_from_capture_dir",
    "build_team_scoring_comparison",
    "build_team_scoring_section",
    "compute_recent_points",
    "compute_scoring_derived_features",
    "parse_match_markets",
    "simplify_match_for_team",
    "summarize_last_matches",
]

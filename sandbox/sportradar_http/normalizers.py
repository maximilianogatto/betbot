from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def doc_data(payload: dict[str, Any] | None) -> object | None:
    if not isinstance(payload, dict):
        return None
    doc = payload.get("doc")
    if not isinstance(doc, list) or not doc or not isinstance(doc[0], dict):
        return None
    return doc[0].get("data")


def as_int(value: object, default: int | None = None) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def as_float(value: object, default: float | None = None) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def compact_time(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    uts = as_int(value.get("uts"))
    return {
        "date": value.get("date"),
        "time": value.get("time"),
        "tz": value.get("tz"),
        "uts": uts,
        "iso_utc": datetime.fromtimestamp(uts, tz=UTC).isoformat() if uts else None,
    }


def compact_team(team: object) -> dict[str, Any]:
    if not isinstance(team, dict):
        return {"id": None, "uid": None, "name": None}
    return {
        "id": as_int(team.get("_id")),
        "uid": as_int(team.get("uid")) or as_int(team.get("_id")),
        "name": team.get("name"),
        "medium_name": team.get("mediumname"),
        "abbr": team.get("abbr"),
        "country": ((team.get("countrycode") or {}).get("name") if isinstance(team.get("countrycode"), dict) else None),
    }


def normalize_league_summary(payload: dict[str, Any]) -> dict[str, Any]:
    data = doc_data(payload)
    if not isinstance(data, dict):
        return {}
    matches = data.get("matches") if isinstance(data.get("matches"), dict) else {}
    goals = data.get("goals") if isinstance(data.get("goals"), dict) else {}
    clean_sheet = data.get("clean_sheet") if isinstance(data.get("clean_sheet"), dict) else {}
    btts = data.get("both_teams_to_score") if isinstance(data.get("both_teams_to_score"), dict) else {}
    overunder = data.get("overunder") if isinstance(data.get("overunder"), dict) else {}
    played = as_int(matches.get("played")) or 0
    home_raw = as_float(matches.get("home_wins"))
    draw_raw = as_float(matches.get("draws"))
    away_raw = as_float(matches.get("away_wins"))
    outcome_sum = sum(value for value in (home_raw, draw_raw, away_raw) if value is not None)
    outcome_is_percent = 99.0 <= outcome_sum <= 101.0
    home_rate = _percent_or_count_to_rate(home_raw, played, outcome_is_percent=outcome_is_percent)
    draw_rate = _percent_or_count_to_rate(draw_raw, played, outcome_is_percent=outcome_is_percent)
    away_rate = _percent_or_count_to_rate(away_raw, played, outcome_is_percent=outcome_is_percent)
    return {
        "matches_played": played,
        "match_outcome_unit": "percent" if outcome_is_percent else "count",
        "home_wins_raw": home_raw,
        "away_wins_raw": away_raw,
        "draws_raw": draw_raw,
        "home_win_rate": home_rate,
        "away_win_rate": away_rate,
        "draw_rate": draw_rate,
        "home_wins_estimated": round(home_rate * played) if home_rate is not None and played else None,
        "away_wins_estimated": round(away_rate * played) if away_rate is not None and played else None,
        "draws_estimated": round(draw_rate * played) if draw_rate is not None and played else None,
        "goals_total": as_int(goals.get("total")) or 0,
        "goals_per_match": as_float(goals.get("pr_match")),
        "goals_per_match_home": as_float(goals.get("pr_match_home")),
        "goals_per_match_away": as_float(goals.get("pr_match_away")),
        "clean_sheet_total": as_int(clean_sheet.get("total")),
        "clean_sheet_per_match": as_float(clean_sheet.get("pr_match")),
        "btts_total": as_int(btts.get("total")),
        "btts_per_match": as_float(btts.get("pr_match")),
        "over25_rate": _percent_or_count_to_rate(as_float(overunder.get("2.5")), played, outcome_is_percent=True),
        "over_under": overunder,
    }


def _percent_or_count_to_rate(value: float | None, played: int, *, outcome_is_percent: bool) -> float | None:
    if value is None:
        return None
    if outcome_is_percent:
        return round(value / 100.0, 6)
    if played:
        return round(value / played, 6)
    if 0 <= value <= 1:
        return value
    return None


def normalize_teams(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = doc_data(payload)
    teams = data.get("teams") if isinstance(data, dict) else []
    return [compact_team(team) for team in teams or []]


def normalize_standings(payload: dict[str, Any]) -> dict[str, Any]:
    data = doc_data(payload)
    if not isinstance(data, dict):
        return {"tables": []}
    tables = []
    for table in data.get("tables") or []:
        if not isinstance(table, dict):
            continue
        rows = []
        for row in table.get("tablerows") or []:
            if not isinstance(row, dict):
                continue
            played = as_int(row.get("total")) or 0
            points = as_int(row.get("pointsTotal")) or 0
            rows.append(
                {
                    "position": as_int(row.get("pos")),
                    "team": compact_team(row.get("team")),
                    "played": played,
                    "points": points,
                    "points_per_match": round(points / played, 4) if played else None,
                    "wins": as_int(row.get("winTotal")) or 0,
                    "draws": as_int(row.get("drawTotal")) or 0,
                    "losses": as_int(row.get("lossTotal")) or 0,
                    "goals_for": as_int(row.get("goalsForTotal")) or 0,
                    "goals_against": as_int(row.get("goalsAgainstTotal")) or 0,
                    "goal_difference": as_int(row.get("goalDiffTotal")) or 0,
                    "home": {
                        "played": as_int(row.get("home")) or 0,
                        "points": as_int(row.get("pointsHome")) or 0,
                        "goals_for": as_int(row.get("goalsForHome")) or 0,
                        "goals_against": as_int(row.get("goalsAgainstHome")) or 0,
                    },
                    "away": {
                        "played": as_int(row.get("away")) or 0,
                        "points": as_int(row.get("pointsAway")) or 0,
                        "goals_for": as_int(row.get("goalsForAway")) or 0,
                        "goals_against": as_int(row.get("goalsAgainstAway")) or 0,
                    },
                }
            )
        tables.append(
            {
                "id": as_int(table.get("_id")),
                "name": table.get("name"),
                "current_round": as_int(table.get("currentround")),
                "max_rounds": as_int(table.get("maxrounds")),
                "rows": rows,
            }
        )
    return {
        "season": {
            "id": as_int(data.get("_id")),
            "unique_tournament_id": as_int(data.get("_utid")),
            "name": data.get("name"),
            "year": data.get("year"),
        },
        "tables": tables,
    }


def normalize_formtable(payload: dict[str, Any]) -> dict[str, Any]:
    data = doc_data(payload)
    if not isinstance(data, dict):
        return {"teams": []}
    teams = []
    for item in data.get("teams") or []:
        if not isinstance(item, dict):
            continue
        form = item.get("form") if isinstance(item.get("form"), dict) else {}
        teams.append(
            {
                "team": compact_team(item.get("team")),
                "position": item.get("position"),
                "played": item.get("played"),
                "points": item.get("points"),
                "goals_for": item.get("goalsfor"),
                "goals_against": item.get("goalsagainst"),
                "goal_difference": item.get("goaldifference"),
                "form_total": [entry.get("value") for entry in form.get("total") or [] if isinstance(entry, dict)],
                "form_home": [entry.get("value") for entry in form.get("home") or [] if isinstance(entry, dict)],
                "form_away": [entry.get("value") for entry in form.get("away") or [] if isinstance(entry, dict)],
            }
        )
    return {
        "current_round": as_int(data.get("currentround")),
        "winpoints": as_int(data.get("winpoints")),
        "losspoints": as_int(data.get("losspoints")),
        "teams": teams,
    }


def normalize_fixtures(payload: dict[str, Any], *, max_items: int | None = None) -> list[dict[str, Any]]:
    data = doc_data(payload)
    if not isinstance(data, dict):
        return []
    matches = data.get("matches") or []
    normalized = []
    for match in matches[:max_items] if max_items else matches:
        if not isinstance(match, dict):
            continue
        teams = match.get("teams") if isinstance(match.get("teams"), dict) else {}
        result = match.get("result") if isinstance(match.get("result"), dict) else {}
        normalized.append(
            {
                "match_id": as_int(match.get("_id")),
                "round": as_int(match.get("round")),
                "round_name": ((match.get("roundname") or {}).get("name") if isinstance(match.get("roundname"), dict) else None),
                "time": compact_time(match.get("time")),
                "home": compact_team(teams.get("home") if isinstance(teams, dict) else None),
                "away": compact_team(teams.get("away") if isinstance(teams, dict) else None),
                "result": {
                    "home": as_int(result.get("home")),
                    "away": as_int(result.get("away")),
                    "winner": result.get("winner"),
                    "period": result.get("period"),
                },
                "status": {
                    "postponed": bool(match.get("postponed")),
                    "canceled": bool(match.get("canceled")),
                    "in_livescore": bool(match.get("inlivescore")),
                    "neutral_ground": bool(match.get("neutralground")),
                },
            }
        )
    return normalized


def normalize_player_leaders(payload: dict[str, Any], *, value_key: str = "total", max_items: int = 20) -> list[dict[str, Any]]:
    data = doc_data(payload)
    if not isinstance(data, dict):
        return []
    players = data.get("players") or []
    leaders = []
    for item in players[:max_items]:
        if not isinstance(item, dict):
            continue
        player = item.get("player") if isinstance(item.get("player"), dict) else {}
        leaders.append(
            {
                "player_id": as_int(item.get("playerid")) or as_int(player.get("_id")),
                "player_name": player.get("name") or player.get("fullname"),
                "total": as_int(item.get(value_key)) or 0,
                "home": as_int(item.get("home")),
                "away": as_int(item.get("away")),
                "teams": item.get("teams"),
            }
        )
    return leaders


def normalize_injuries(payload: dict[str, Any], *, max_items: int = 50) -> list[dict[str, Any]]:
    data = doc_data(payload)
    injuries = data if isinstance(data, list) else []
    normalized = []
    for item in injuries[:max_items]:
        if not isinstance(item, dict):
            continue
        player = item.get("player") if isinstance(item.get("player"), dict) else {}
        status = item.get("status") if isinstance(item.get("status"), dict) else {}
        team = item.get("uniqueteam") if isinstance(item.get("uniqueteam"), dict) else {}
        normalized.append(
            {
                "player_id": as_int(item.get("_playerid")) or as_int(player.get("_id")),
                "player_name": player.get("name") or player.get("fullname"),
                "team": compact_team(team),
                "status": status.get("name") or status.get("status"),
                "missing": bool(status.get("missing")),
                "doubtful": bool(status.get("doubtful")),
                "start": compact_time(status.get("start")),
            }
        )
    return normalized


def normalize_venues(payload: dict[str, Any], *, max_items: int = 50) -> list[dict[str, Any]]:
    data = doc_data(payload)
    venues = data.get("venues") if isinstance(data, dict) else []
    normalized = []
    for venue in (venues or [])[:max_items]:
        if not isinstance(venue, dict):
            continue
        normalized.append(
            {
                "id": as_int(venue.get("_id")),
                "name": venue.get("name"),
                "city": venue.get("city"),
                "country": venue.get("country"),
                "capacity": as_int(venue.get("capacity")),
            }
        )
    return normalized


def make_raw_ref(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = doc_data(payload)
    encoded = str(payload).encode("utf-8")
    return {
        "endpoint": endpoint,
        "queryUrl": payload.get("queryUrl"),
        "body_size_estimate_bytes": len(encoded),
        "data_type": type(data).__name__,
        "data_keys": sorted(data.keys())[:30] if isinstance(data, dict) else None,
        "data_count": len(data) if isinstance(data, list) else None,
    }

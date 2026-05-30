"""Normalization helpers for raw Statshub gismo payloads.

Purpose:
    Convert large, inconsistent Statshub JSON responses into compact dictionaries
    with stable keys for downstream feature generation and reporting.

Input convention:
    Most gismo responses have the shape `{"doc": [{"data": ...}], "queryUrl": ...}`.
    `doc_data()` extracts that common `data` node. Every normalizer is defensive:
    missing or malformed payload sections return empty/default structures instead
    of raising whenever possible.

Output convention:
    Normalized values are plain JSON-serializable dicts/lists. IDs are converted
    to `int` when safe, datetimes include `iso_utc`, and full raw payloads are not
    embedded. Use `make_raw_ref()` for traceability metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any


def doc_data(payload: dict[str, Any] | None) -> object | None:
    """Extract `doc[0].data` from a gismo payload."""

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
    """Normalize Statshub time objects into date/time/tz/uts/iso_utc fields."""

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
    """Normalize team identity fields used across fixtures, tables and matches."""

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


def compact_match(match: object, *, perspective_team_uid: int | None = None) -> dict[str, Any]:
    """Normalize a match row with optional team-perspective result fields.

    Args:
        match: Raw match dict from fixtures/lastx/H2H payloads.
        perspective_team_uid: When provided, adds `venue`, `opponent`,
            `goals_for`, `goals_against`, and result `W/D/L` from that team's
            point of view.
    """

    if not isinstance(match, dict):
        return {}
    teams = match.get("teams") if isinstance(match.get("teams"), dict) else {}
    result = match.get("result") if isinstance(match.get("result"), dict) else {}
    home = compact_team(teams.get("home") if isinstance(teams, dict) else None)
    away = compact_team(teams.get("away") if isinstance(teams, dict) else None)
    home_score = as_int(result.get("home"))
    away_score = as_int(result.get("away"))
    venue = None
    goals_for = None
    goals_against = None
    result_label = None
    opponent = None
    if perspective_team_uid is not None:
        if home.get("uid") == perspective_team_uid:
            venue = "home"
            opponent = away
            goals_for = home_score
            goals_against = away_score
        elif away.get("uid") == perspective_team_uid:
            venue = "away"
            opponent = home
            goals_for = away_score
            goals_against = home_score
        if goals_for is not None and goals_against is not None:
            result_label = "W" if goals_for > goals_against else "L" if goals_for < goals_against else "D"
    return {
        "match_id": as_int(match.get("_id")),
        "season_id": as_int(match.get("_seasonid")),
        "tournament_id": as_int(match.get("_utid")),
        "round": as_int(match.get("round")),
        "round_name": ((match.get("roundname") or {}).get("name") if isinstance(match.get("roundname"), dict) else None),
        "time": compact_time(match.get("time") or match.get("_dt")),
        "home": home,
        "away": away,
        "score": {"home": home_score, "away": away_score, "winner": result.get("winner")},
        "venue": venue,
        "opponent": opponent,
        "result": result_label,
        "goals_for": goals_for,
        "goals_against": goals_against,
    }


def normalize_league_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize season-level scoring/result summary metrics."""

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


def normalize_match_metadata(
    info_payload: dict[str, Any] | None,
    snapshot_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize match identity, teams, kickoff, score, competition and coverage."""

    info_data = doc_data(info_payload)
    snapshot_data = doc_data(snapshot_payload)
    info_data = info_data if isinstance(info_data, dict) else {}
    snapshot_data = snapshot_data if isinstance(snapshot_data, dict) else {}
    match = info_data.get("match") if isinstance(info_data.get("match"), dict) else snapshot_data
    teams = match.get("teams") if isinstance(match.get("teams"), dict) else {}
    result = match.get("result") if isinstance(match.get("result"), dict) else {}
    status = match.get("status") if isinstance(match.get("status"), dict) else {}
    tournament = info_data.get("tournament") if isinstance(info_data.get("tournament"), dict) else snapshot_data.get("tournament")
    tournament = tournament if isinstance(tournament, dict) else {}
    unique_tournament = (
        info_data.get("uniquetournament")
        if isinstance(info_data.get("uniquetournament"), dict)
        else snapshot_data.get("uniquetournament")
    )
    unique_tournament = unique_tournament if isinstance(unique_tournament, dict) else {}
    season = info_data.get("season") if isinstance(info_data.get("season"), dict) else snapshot_data.get("season")
    season = season if isinstance(season, dict) else {}
    realcategory = info_data.get("realcategory") if isinstance(info_data.get("realcategory"), dict) else snapshot_data.get("realcategory")
    realcategory = realcategory if isinstance(realcategory, dict) else {}
    stadium = info_data.get("stadium") if isinstance(info_data.get("stadium"), dict) else snapshot_data.get("stadium")
    stadium = stadium if isinstance(stadium, dict) else {}
    timeinfo = match.get("timeinfo") if isinstance(match.get("timeinfo"), dict) else {}
    return {
        "match_id": as_int(match.get("_id")),
        "sport_id": as_int(match.get("_sid")),
        "season_id": as_int(match.get("_seasonid")) or as_int(season.get("_id")),
        "tournament_id": as_int(match.get("_tid")),
        "unique_tournament_id": as_int(match.get("_utid")) or as_int(unique_tournament.get("_id")),
        "round": as_int(match.get("round")),
        "round_name": ((match.get("roundname") or {}).get("name") if isinstance(match.get("roundname"), dict) else None),
        "kickoff": compact_time(match.get("_dt") or match.get("time")),
        "home": compact_team(teams.get("home") if isinstance(teams, dict) else None),
        "away": compact_team(teams.get("away") if isinstance(teams, dict) else None),
        "score": {
            "home": as_int(result.get("home")),
            "away": as_int(result.get("away")),
            "winner": result.get("winner"),
        },
        "status": {
            "id": as_int(status.get("_id")),
            "name": status.get("name"),
            "short_name": status.get("shortName"),
            "matchstatus": match.get("matchstatus"),
            "in_livescore": bool(match.get("inlivescore")),
            "postponed": bool(match.get("postponed")),
            "cancelled": bool(match.get("cancelled") or match.get("canceled")),
            "running": _bool_or_none(timeinfo.get("running")),
            "played_seconds": as_int(timeinfo.get("played")),
        },
        "competition": {
            "name": tournament.get("name") or unique_tournament.get("name"),
            "tournament_name": tournament.get("name"),
            "unique_tournament_name": unique_tournament.get("name"),
            "country": realcategory.get("name"),
            "season_name": season.get("name"),
            "season_year": season.get("year") or tournament.get("year"),
        },
        "venue": {
            "id": as_int(stadium.get("_id")),
            "name": stadium.get("name"),
            "city": stadium.get("city"),
            "country": stadium.get("country"),
            "capacity": as_int(stadium.get("capacity")),
        },
        "attendance": as_int(info_data.get("attendance") or snapshot_data.get("attendance")),
        "coverage": _compact_coverage(match.get("coverage") or info_data.get("statscoverage") or snapshot_data.get("statscoverage")),
    }


def _bool_or_none(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _compact_coverage(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    keys = (
        "liveodds",
        "hasstats",
        "inlivescore",
        "deepercoverage",
        "matchdetails",
        "lineups",
        "injuries",
        "headtohead",
        "formtable",
        "leaguetable",
        "overunder",
    )
    return {key: value.get(key) for key in keys if key in value}


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
    normalized = normalized.replace("{$competitor1}", home_name or "home")
    normalized = normalized.replace("{$competitor2}", away_name or "away")
    if specifiers:
        for key, value in specifiers.items():
            normalized = normalized.replace(f"{{{key}}}", str(value))
            normalized = normalized.replace(f"{{+{key}}}", str(value))
            if str(value).startswith("-"):
                normalized = normalized.replace(f"{{-{key}}}", str(value).removeprefix("-"))
            else:
                normalized = normalized.replace(f"{{-{key}}}", f"-{value}")
    return " ".join(normalized.split())


def normalize_match_markets(
    payload: dict[str, Any] | None,
    *,
    home_name: str | None,
    away_name: str | None,
    source: str = "match_markets",
) -> dict[str, Any]:
    """Normalize priced 1X2, handicap and totals markets when present."""

    data = doc_data(payload)
    markets = data.get("markets") if isinstance(data, dict) else None
    if not isinstance(markets, list):
        markets = []
    one_x_two: dict[str, Any] = {}
    handicap_markets: list[dict[str, Any]] = []
    totals_markets: list[dict[str, Any]] = []
    other_market_names: list[str] = []
    for market in markets:
        if not isinstance(market, dict):
            continue
        market_name = str(market.get("name") or "")
        specifiers = market.get("specifiers") if isinstance(market.get("specifiers"), dict) else {}
        outcomes = market.get("outcomes") if isinstance(market.get("outcomes"), list) else []
        simplified_outcomes = []
        for index, outcome in enumerate(outcomes):
            if not isinstance(outcome, dict):
                continue
            simplified_outcomes.append(
                {
                    "name": normalize_market_text(
                        outcome.get("name"),
                        home_name=home_name,
                        away_name=away_name,
                        specifiers=specifiers,
                    ),
                    "odds": as_float(outcome.get("odds")),
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
        elif "handicap" in market_name.lower():
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
        elif market_name.lower() == "total":
            totals_markets.append(
                {
                    "market_name": "Total",
                    "line": specifiers.get("total"),
                    "outcomes": simplified_outcomes,
                }
            )
        else:
            clean_name = normalize_market_text(
                market_name,
                home_name=home_name,
                away_name=away_name,
                specifiers=specifiers,
            )
            if clean_name:
                other_market_names.append(clean_name)
    return {
        "source": source if payload else None,
        "markets": {
            "1x2": one_x_two,
            "handicap": handicap_markets,
            "totals": totals_markets,
            "other_market_names": other_market_names[:20],
            "raw_market_count": len(markets),
        },
    }


def normalize_sport_match_markets(
    payload: dict[str, Any] | None,
    *,
    match_id: int,
    home_name: str | None,
    away_name: str | None,
) -> dict[str, Any]:
    """Normalize one match from `unified_sport_matches_markets`.

    The sport/date market endpoint stores matches as a mapping keyed by match id:

    `{matches: {"69340066": {"markets": [...]}}}`.

    This helper converts that shape into the same compact odds contract used by
    `normalize_match_markets`, so validation can compare the match-level market
    endpoint with the sport/date market endpoint without duplicating parser
    logic.
    """

    data = doc_data(payload)
    matches = data.get("matches") if isinstance(data, dict) else {}
    match_data = None
    if isinstance(matches, dict):
        match_data = matches.get(str(match_id)) or matches.get(match_id)
    if not isinstance(match_data, dict):
        return {
            "source": "unified_sport_matches_markets" if payload else None,
            "markets": {
                "1x2": {},
                "handicap": [],
                "totals": [],
                "other_market_names": [],
                "raw_market_count": 0,
            },
        }
    synthetic_payload = {
        "queryUrl": payload.get("queryUrl") if isinstance(payload, dict) else None,
        "doc": [{"data": {"markets": match_data.get("markets") or []}}],
    }
    return normalize_match_markets(
        synthetic_payload,
        home_name=home_name,
        away_name=away_name,
        source="unified_sport_matches_markets",
    )


def normalize_match_table_slice(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize compact table context for the two teams in one match."""

    data = doc_data(payload)
    if not isinstance(data, dict):
        return {"rows": []}
    rows = []
    for row in data.get("tablerows") or []:
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
                    "position": as_int(row.get("posHome")),
                    "played": as_int(row.get("home")) or 0,
                    "points": as_int(row.get("pointsHome")) or 0,
                    "goals_for": as_int(row.get("goalsForHome")) or 0,
                    "goals_against": as_int(row.get("goalsAgainstHome")) or 0,
                },
                "away": {
                    "position": as_int(row.get("posAway")),
                    "played": as_int(row.get("away")) or 0,
                    "points": as_int(row.get("pointsAway")) or 0,
                    "goals_for": as_int(row.get("goalsForAway")) or 0,
                    "goals_against": as_int(row.get("goalsAgainstAway")) or 0,
                },
            }
        )
    return {
        "table_id": as_int(data.get("_id")),
        "name": data.get("name"),
        "season_id": as_int(data.get("seasonid")),
        "current_round": as_int(data.get("currentround")),
        "max_rounds": as_int(data.get("maxrounds")),
        "rows": rows,
    }


def normalize_match_details(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize match details/stat rows such as possession, shots and cards."""

    data = doc_data(payload)
    if not isinstance(data, dict):
        return {"stats_by_key": {}, "key_stats": {}}
    values = data.get("values") if isinstance(data.get("values"), dict) else {}
    stats_by_key: dict[str, dict[str, Any]] = {}
    for item in values.values():
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        key = _slug_stat_name(name)
        value = item.get("value") if isinstance(item.get("value"), dict) else {}
        stats_by_key[key] = {
            "name": name,
            "home": as_float(value.get("home")),
            "away": as_float(value.get("away")),
        }
    key_aliases = {
        "ball_possession": "possession",
        "goal_attempts": "goal_attempts",
        "shots_on_target": "shots_on_target",
        "shots_off_target": "shots_off_target",
        "shots_blocked": "shots_blocked",
        "corner_kicks": "corners",
        "yellow_cards": "yellow_cards",
        "red_cards": "red_cards",
        "free_kicks": "free_kicks",
        "offsides": "offsides",
        "saves": "saves",
        "fouls": "fouls",
    }
    key_stats = {
        alias: stats_by_key[key]
        for key, alias in key_aliases.items()
        if key in stats_by_key
    }
    return {
        "teams": data.get("teams") if isinstance(data.get("teams"), dict) else {},
        "key_stats": key_stats,
        "stats_by_key": stats_by_key,
        "raw_stat_count": len(stats_by_key),
    }


def _slug_stat_name(name: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_")


def normalize_match_timeline(payload: dict[str, Any] | None, *, max_events: int = 120) -> dict[str, Any]:
    """Normalize full or delta timeline payloads into score/status/events."""

    data = doc_data(payload)
    if not isinstance(data, dict):
        return {"events": [], "event_counts": {}, "important_events": []}
    match = data.get("match") if isinstance(data.get("match"), dict) else {}
    result = match.get("result") if isinstance(match.get("result"), dict) else {}
    timeinfo = match.get("timeinfo") if isinstance(match.get("timeinfo"), dict) else {}
    status = match.get("status") if isinstance(match.get("status"), dict) else {}
    events = data.get("events") if isinstance(data.get("events"), list) else []
    compact_events = [_compact_timeline_event(event) for event in events if isinstance(event, dict)]
    event_counts: dict[str, dict[str, int]] = {}
    for event in compact_events:
        event_type = str(event.get("type") or "unknown")
        team = str(event.get("team") or "neutral")
        event_counts.setdefault(event_type, {}).setdefault(team, 0)
        event_counts[event_type][team] += 1
    important_events = [
        event
        for event in compact_events
        if any(token in str(event.get("type") or "").lower() for token in ("goal", "card", "penalty", "corner"))
        or any(token in str(event.get("name") or "").lower() for token in ("goal", "card", "penalty", "corner"))
    ]
    cards = match.get("cards") if isinstance(match.get("cards"), dict) else {}
    return {
        "status": status.get("name"),
        "period": match.get("p"),
        "clock": {
            "played_seconds": as_int(timeinfo.get("played")),
            "running": _bool_or_none(timeinfo.get("running")),
            "started_uts": as_int(timeinfo.get("started")),
            "ended_uts": as_int(timeinfo.get("ended")),
        },
        "score_home": as_int(result.get("home")),
        "score_away": as_int(result.get("away")),
        "cards": cards,
        "event_counts": event_counts,
        "important_events": important_events,
        "events": compact_events[-max_events:] if max_events else compact_events,
        "raw_event_count": len(compact_events),
    }


def _compact_timeline_event(event: dict[str, Any]) -> dict[str, Any]:
    player = event.get("player") if isinstance(event.get("player"), dict) else {}
    result = event.get("result") if isinstance(event.get("result"), dict) else {}
    return {
        "id": event.get("_id"),
        "type": event.get("type") or event.get("_doctype"),
        "name": event.get("name"),
        "time": as_int(event.get("time")),
        "seconds": as_int(event.get("seconds")),
        "injurytime": as_int(event.get("injurytime")),
        "team": event.get("team"),
        "player_id": as_int(player.get("_id")),
        "player_name": player.get("name"),
        "score": {
            "home": as_int(result.get("home")),
            "away": as_int(result.get("away")),
        },
        "x": as_float(event.get("X")),
        "y": as_float(event.get("Y")),
        "uts": as_int(event.get("uts")),
    }


def normalize_match_situation(payload: dict[str, Any] | None, *, max_samples: int = 20) -> dict[str, Any]:
    """Normalize live pressure/situation samples from `stats_match_situation`."""

    data = doc_data(payload)
    samples = data.get("data") if isinstance(data, dict) else []
    if not isinstance(samples, list):
        return {"samples": [], "totals": {}, "latest": None}
    totals = {
        "home": {"attack": 0, "dangerous": 0, "attackcount": 0, "dangerouscount": 0},
        "away": {"attack": 0, "dangerous": 0, "attackcount": 0, "dangerouscount": 0},
    }
    compact_samples = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        compact_sample = {"time": as_int(sample.get("time")), "home": {}, "away": {}}
        for side in ("home", "away"):
            side_data = sample.get(side) if isinstance(sample.get(side), dict) else {}
            compact_side = {
                "attack": as_int(side_data.get("attack")) or 0,
                "dangerous": as_int(side_data.get("dangerous")) or 0,
                "attackcount": as_int(side_data.get("attackcount")) or 0,
                "dangerouscount": as_int(side_data.get("dangerouscount")) or 0,
            }
            compact_sample[side] = compact_side
            for key, value in compact_side.items():
                totals[side][key] += value
        compact_samples.append(compact_sample)
    return {
        "samples": compact_samples[-max_samples:] if max_samples else compact_samples,
        "totals": totals,
        "latest": compact_samples[-1] if compact_samples else None,
        "raw_sample_count": len(compact_samples),
    }


def normalize_team_recent_payload(
    payload: dict[str, Any] | None,
    *,
    team_uid: int | None,
    max_matches: int = 10,
) -> dict[str, Any]:
    """Normalize `stats_team_lastx` or `stats_team_nextx` into compact matches."""

    data = doc_data(payload)
    if not isinstance(data, dict):
        return {"team": {}, "matches": [], "recent_points": None, "form": []}
    matches = [
        compact_match(match, perspective_team_uid=team_uid)
        for match in (data.get("matches") or [])[:max_matches]
        if isinstance(match, dict)
    ]
    form = [match.get("result") for match in matches if match.get("result")]
    points = sum(3 if item == "W" else 1 if item == "D" else 0 for item in form)
    return {
        "team": compact_team(data.get("team")),
        "matches": matches,
        "form": form,
        "recent_points": points if form else None,
    }


def normalize_team_streaks(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize team streak/form keys without embedding verbose raw sections."""

    data = doc_data(payload)
    if not isinstance(data, dict):
        return {"team": {}, "last_form": {}, "streak_keys": []}
    lastmatchesform = data.get("lastmatchesform") if isinstance(data.get("lastmatchesform"), dict) else {}
    streaks = data.get("streaks") if isinstance(data.get("streaks"), dict) else {}
    return {
        "team": compact_team(data.get("team")),
        "last_form": {
            key: [entry.get("value") for entry in value[:10] if isinstance(entry, dict)]
            for key, value in lastmatchesform.items()
            if isinstance(value, list)
        },
        "streak_keys": sorted(streaks.keys())[:30],
    }


def normalize_team_scoring(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize scoring/conceding split metrics for one team in one season."""

    data = doc_data(payload)
    if not isinstance(data, dict):
        return {"team": {}, "matches": {}, "scoring": {}, "conceding": {}}
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    scoring = stats.get("scoring") if isinstance(stats.get("scoring"), dict) else {}
    conceding = stats.get("conceding") if isinstance(stats.get("conceding"), dict) else {}
    return {
        "team": compact_team(data.get("team")),
        "matches": _split_values(stats.get("totalmatches")),
        "wins": _split_values(stats.get("totalwins")),
        "scoring": {
            "goals_scored": _split_values(scoring.get("goalsscored")),
            "goals_scored_avg": _split_values(scoring.get("goalsscoredaverage")),
            "failed_to_score_rate": _split_values(scoring.get("failedtoscoreaverage")),
            "btts_rate": _split_values(scoring.get("bothteamsscoredaverage")),
            "first_half_scoring_rate": _split_values(scoring.get("scoringathalftimeaverage")),
            "minutes_per_goal_scored": _split_values(scoring.get("minutespergoalscored")),
            "goals_by_minutes": scoring.get("goalsbyminutes") if isinstance(scoring.get("goalsbyminutes"), dict) else {},
        },
        "conceding": {
            "goals_conceded": _split_values(conceding.get("goalsconceded")),
            "goals_conceded_avg": _split_values(conceding.get("goalsconcededaverage")),
            "clean_sheet_rate": _split_values(conceding.get("cleansheetsaverage")),
            "first_half_conceding_rate": _split_values(conceding.get("goalsconcededfirsthalfaverage")),
            "minutes_per_goal_conceded": _split_values(conceding.get("minutespergoalconceded")),
            "goals_by_minutes": conceding.get("goalsbyminutes") if isinstance(conceding.get("goalsbyminutes"), dict) else {},
        },
    }


def _split_values(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"total": None, "home": None, "away": None}
    return {
        "total": as_float(value.get("total")),
        "home": as_float(value.get("home")),
        "away": as_float(value.get("away")),
    }


def normalize_h2h_payload(
    payload: dict[str, Any] | None,
    *,
    home_uid: int | None,
    away_uid: int | None,
    max_matches: int = 10,
) -> dict[str, Any]:
    """Normalize direct H2H matches and compute home/away win summary."""

    data = doc_data(payload)
    if not isinstance(data, dict):
        return {"matches": [], "summary": {}}
    matches = [
        compact_match(match)
        for match in (data.get("matches") or [])[:max_matches]
        if isinstance(match, dict)
    ]
    summary = {"total_matches": len(matches), "home_team_wins": 0, "away_team_wins": 0, "draws": 0}
    for match in matches:
        score = match.get("score") if isinstance(match.get("score"), dict) else {}
        home = match.get("home") if isinstance(match.get("home"), dict) else {}
        away = match.get("away") if isinstance(match.get("away"), dict) else {}
        home_score = as_int(score.get("home"))
        away_score = as_int(score.get("away"))
        if home_score is None or away_score is None:
            continue
        if home_score == away_score:
            summary["draws"] += 1
        elif home_score > away_score and home.get("uid") == home_uid:
            summary["home_team_wins"] += 1
        elif home_score < away_score and away.get("uid") == home_uid:
            summary["home_team_wins"] += 1
        elif home_score > away_score and home.get("uid") == away_uid:
            summary["away_team_wins"] += 1
        elif home_score < away_score and away.get("uid") == away_uid:
            summary["away_team_wins"] += 1
    return {"matches": matches, "summary": summary}


def normalize_teams(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize season teams."""

    data = doc_data(payload)
    teams = data.get("teams") if isinstance(data, dict) else []
    return [compact_team(team) for team in teams or []]


def normalize_standings(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize standings tables with total/home/away fields."""

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
    """Normalize form-table rows and recent W/D/L sequences."""

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
    """Normalize season fixtures into match_id, teams, time, result and status."""

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
    """Normalize top goals/cards/assists player leaderboard rows."""

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
    """Normalize season injury rows with player/team/status fields."""

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
    """Normalize season venue metadata."""

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
    """Create compact traceability metadata for a raw endpoint payload."""

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

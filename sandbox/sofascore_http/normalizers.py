"""Pure normalizers for compact SofaScore research snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def normalize_league_option(tournament: dict[str, Any]) -> dict[str, Any]:
    """Normalize one SofaScore unique-tournament record for future discovery."""

    category = tournament.get("category") if isinstance(tournament.get("category"), dict) else {}
    return {
        "league_id": _string_id(tournament.get("id")),
        "league_name": tournament.get("name"),
        "slug": tournament.get("slug"),
        "country_id": _string_id(category.get("id")),
        "country_name": category.get("name"),
        "sport": _nested_value(category, "sport", "slug"),
        "has_performance_graph": bool(tournament.get("hasPerformanceGraphFeature")),
        "has_player_statistics": bool(tournament.get("hasEventPlayerStatistics")),
    }


def normalize_fixture(event: dict[str, Any]) -> dict[str, Any]:
    """Normalize one scheduled/live SofaScore event."""

    tournament = event.get("tournament") if isinstance(event.get("tournament"), dict) else {}
    unique_tournament = (
        tournament.get("uniqueTournament")
        if isinstance(tournament.get("uniqueTournament"), dict)
        else {}
    )
    status = event.get("status") if isinstance(event.get("status"), dict) else {}
    return {
        "match_id": _string_id(event.get("id")),
        "custom_id": _string_id(event.get("customId")),
        "slug": event.get("slug"),
        "home": _nested_value(event, "homeTeam", "name"),
        "home_id": _string_id(_nested_value(event, "homeTeam", "id")),
        "away": _nested_value(event, "awayTeam", "name"),
        "away_id": _string_id(_nested_value(event, "awayTeam", "id")),
        "start_time_utc": _timestamp_iso(event.get("startTimestamp")),
        "status": status.get("type"),
        "status_description": status.get("description"),
        "league_id": _string_id(unique_tournament.get("id") or tournament.get("id")),
        "league_name": unique_tournament.get("name") or tournament.get("name"),
        "season_id": _string_id(_nested_value(event, "season", "id")),
        "score_home": _score(event.get("homeScore")),
        "score_away": _score(event.get("awayScore")),
    }


def normalize_1x2_odds(payload: dict[str, Any]) -> dict[str, float | None]:
    """Extract decimal 1X2 odds from SofaScore's provider-specific markets."""

    for market in payload.get("markets") or []:
        if not isinstance(market, dict):
            continue
        if market.get("marketGroup") != "1X2":
            continue
        choices = market.get("choices")
        if not isinstance(choices, list):
            continue
        normalized: dict[str, float | None] = {"home": None, "draw": None, "away": None}
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            name = str(choice.get("name") or choice.get("fractionalValue") or "").strip().lower()
            value = _decimal_odd(choice)
            if name in {"1", "home"}:
                normalized["home"] = value
            elif name in {"x", "draw"}:
                normalized["draw"] = value
            elif name in {"2", "away"}:
                normalized["away"] = value
        return normalized
    return {"home": None, "draw": None, "away": None}


def flatten_statistics(statistics: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Flatten the ALL-period statistics groups into a readable mapping."""

    for period in statistics:
        if period.get("period") != "ALL":
            continue
        flattened: dict[str, dict[str, Any]] = {}
        for group in period.get("groups") or []:
            if not isinstance(group, dict):
                continue
            for item in group.get("statisticsItems") or []:
                if not isinstance(item, dict) or not item.get("name"):
                    continue
                flattened[str(item["name"])] = {
                    "home": item.get("home"),
                    "away": item.get("away"),
                }
        return flattened
    return {}


def build_match_snapshot(
    *,
    event: dict[str, Any],
    statistics: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
    lineups: dict[str, Any],
    h2h: dict[str, Any],
    win_probability: dict[str, Any],
    odds: dict[str, Any],
) -> dict[str, Any]:
    """Build a compact event snapshot suitable for provider feasibility tests."""

    fixture = normalize_fixture(event)
    return {
        "schema_version": 1,
        "provider": "sofascore_http_research",
        "match": fixture,
        "live_state": {
            "status": fixture["status"],
            "description": fixture["status_description"],
            "score_home": fixture["score_home"],
            "score_away": fixture["score_away"],
            "clock": event.get("time") if isinstance(event.get("time"), dict) else {},
            "statistics": flatten_statistics(statistics),
            "incidents": [normalize_incident(item) for item in incidents],
        },
        "lineups": {
            "confirmed": bool(lineups.get("confirmed")),
            "home_count": _lineup_count(lineups, "home"),
            "away_count": _lineup_count(lineups, "away"),
        },
        "h2h": h2h,
        "win_probability": win_probability.get("winProbability") or {},
        "odds": {
            "source": "event_odds_provider_1",
            "market_count": len(odds.get("markets") or []),
            "1x2": normalize_1x2_odds(odds),
        },
        "coverage": {
            "has_event": bool(event),
            "has_statistics": bool(statistics),
            "has_incidents": bool(incidents),
            "has_lineups": bool(lineups),
            "has_h2h": bool(h2h),
            "has_win_probability": bool(win_probability),
            "has_odds": bool(odds.get("markets")),
        },
    }


def _nested_value(payload: dict[str, Any], key: str, nested_key: str) -> Any:
    value = payload.get(key)
    return value.get(nested_key) if isinstance(value, dict) else None


def _timestamp_iso(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(value, tz=UTC).isoformat()


def _score(value: Any) -> int | float | None:
    if not isinstance(value, dict):
        return None
    score = value.get("current")
    return score if isinstance(score, (int, float)) else None


def _lineup_count(lineups: dict[str, Any], side: str) -> int:
    value = lineups.get(side)
    return len(value.get("players") or []) if isinstance(value, dict) else 0


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _decimal_odd(choice: dict[str, Any]) -> float | None:
    """Read decimal odds directly or convert SofaScore fractional odds."""

    decimal = _float_or_none(choice.get("decimalValue"))
    if decimal is not None:
        return decimal
    fractional = str(choice.get("fractionalValue") or "").strip()
    if "/" not in fractional:
        return None
    numerator, denominator = fractional.split("/", maxsplit=1)
    try:
        denominator_value = float(denominator)
        if denominator_value == 0:
            return None
        return round(1.0 + (float(numerator) / denominator_value), 6)
    except ValueError:
        return None


def normalize_incident(incident: dict[str, Any]) -> dict[str, Any]:
    """Keep timeline evidence without embedding full player documents."""

    normalized = {
        key: incident.get(key)
        for key in (
            "id",
            "incidentType",
            "incidentClass",
            "time",
            "addedTime",
            "isHome",
            "isLive",
            "homeScore",
            "awayScore",
            "text",
        )
        if incident.get(key) is not None
    }
    for source_key, target_key in (
        ("player", "player"),
        ("playerIn", "player_in"),
        ("playerOut", "player_out"),
    ):
        player = incident.get(source_key)
        if isinstance(player, dict):
            normalized[target_key] = {
                "id": _string_id(player.get("id")),
                "name": player.get("name"),
            }
    return normalized


def _string_id(value: Any) -> str | None:
    return str(value) if value is not None else None


__all__ = [
    "build_match_snapshot",
    "flatten_statistics",
    "normalize_incident",
    "normalize_1x2_odds",
    "normalize_fixture",
    "normalize_league_option",
]

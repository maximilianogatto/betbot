"""Active market validation helpers for the Sportradar HTTP provider.

Purpose:
    Validate whether existing sport/date endpoints contain usable active odds
    without expanding endpoint coverage.

Inputs:
    - `unified_sport_matches/{sport_id}/{date}/0`
    - `unified_sport_matches_markets/{sport_id}/{date}/0`

Outputs:
    Compact JSON/report structures that show priced 1X2, handicap and totals
    coverage by real match id. This module is pure: it does not fetch network
    data and does not know about Playwright.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from stats_providers.sportradar_http.engine.normalizers import as_float, as_int, doc_data, normalize_sport_match_markets


def build_sport_match_index(overview_payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Build match_id -> compact fixture metadata from `unified_sport_matches`."""

    data = doc_data(overview_payload)
    sport = data.get("sport") if isinstance(data, dict) and isinstance(data.get("sport"), dict) else {}
    index: dict[int, dict[str, Any]] = {}
    for category in sport.get("realcategories") or []:
        if not isinstance(category, dict):
            continue
        country = category.get("name")
        for tournament in category.get("tournaments") or []:
            if not isinstance(tournament, dict):
                continue
            league = tournament.get("name")
            for match in tournament.get("matches") or []:
                if not isinstance(match, dict):
                    continue
                match_id = as_int(match.get("_id"))
                if match_id is None:
                    continue
                teams = match.get("teams") if isinstance(match.get("teams"), dict) else {}
                home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
                away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
                time_data = match.get("time") if isinstance(match.get("time"), dict) else {}
                status = match.get("status") if isinstance(match.get("status"), dict) else {}
                result = match.get("result") if isinstance(match.get("result"), dict) else {}
                index[match_id] = {
                    "match_id": match_id,
                    "country": country,
                    "league": league,
                    "home": home.get("name"),
                    "away": away.get("name"),
                    "kickoff_utc": _iso_from_uts(time_data.get("uts")),
                    "status": status.get("name"),
                    "result_period": result.get("period"),
                    "in_livescore": bool(match.get("inlivescore")),
                    "tournament_id": as_int(tournament.get("_utid")) or as_int(tournament.get("_tid")),
                    "season_id": as_int(tournament.get("seasonid")),
                }
    return index


def summarize_sport_markets(
    markets_payload: dict[str, Any],
    *,
    match_index: dict[int, dict[str, Any]] | None = None,
    sample_limit: int = 20,
) -> dict[str, Any]:
    """Summarize active priced markets by match id."""

    data = doc_data(markets_payload)
    matches = data.get("matches") if isinstance(data, dict) and isinstance(data.get("matches"), dict) else {}
    rows = []
    counts = {
        "matches_with_market_payload": 0,
        "matches_with_active_priced_market": 0,
        "matches_with_1x2": 0,
        "matches_with_handicap": 0,
        "matches_with_totals": 0,
        "live_like_matches": 0,
    }
    for raw_match_id, match_data in matches.items():
        if not isinstance(match_data, dict):
            continue
        match_id = as_int(raw_match_id)
        if match_id is None:
            continue
        fixture = (match_index or {}).get(match_id, {})
        normalized = normalize_sport_match_markets(
            markets_payload,
            match_id=match_id,
            home_name=fixture.get("home"),
            away_name=fixture.get("away"),
        )
        markets = normalized.get("markets") if isinstance(normalized.get("markets"), dict) else {}
        raw_markets = match_data.get("markets") if isinstance(match_data.get("markets"), list) else []
        active_market_count = sum(1 for market in raw_markets if _market_has_active_price(market))
        has_active = active_market_count > 0
        has_1x2 = bool(markets.get("1x2"))
        has_handicap = bool(markets.get("handicap"))
        has_totals = bool(markets.get("totals"))
        counts["matches_with_market_payload"] += 1
        counts["matches_with_active_priced_market"] += int(has_active)
        counts["matches_with_1x2"] += int(has_1x2)
        counts["matches_with_handicap"] += int(has_handicap)
        counts["matches_with_totals"] += int(has_totals)
        counts["live_like_matches"] += int(_looks_live(fixture))
        rows.append(
            {
                **fixture,
                "match_id": match_id,
                "has_active_priced_market": has_active,
                "has_1x2": has_1x2,
                "has_handicap": has_handicap,
                "has_totals": has_totals,
                "active_market_count": active_market_count,
                "raw_market_count": len(raw_markets),
                "odds": {
                    "1x2": markets.get("1x2") or {},
                    "handicap_count": len(markets.get("handicap") or []),
                    "totals_count": len(markets.get("totals") or []),
                },
            }
        )
    rows.sort(key=lambda item: (not item.get("has_active_priced_market"), item.get("kickoff_utc") or "", item.get("match_id") or 0))
    return {
        "queryUrl": markets_payload.get("queryUrl"),
        "counts": counts,
        "sample_matches": rows[:sample_limit],
        "total_matches_in_payload": len(rows),
    }


def build_market_validation_report(results: list[dict[str, Any]]) -> str:
    """Render active market validation as Markdown."""

    totals = {
        "dates": len(results),
        "matches_with_market_payload": sum((item.get("counts") or {}).get("matches_with_market_payload") or 0 for item in results),
        "matches_with_active_priced_market": sum((item.get("counts") or {}).get("matches_with_active_priced_market") or 0 for item in results),
        "matches_with_1x2": sum((item.get("counts") or {}).get("matches_with_1x2") or 0 for item in results),
        "matches_with_handicap": sum((item.get("counts") or {}).get("matches_with_handicap") or 0 for item in results),
        "matches_with_totals": sum((item.get("counts") or {}).get("matches_with_totals") or 0 for item in results),
    }
    lines = [
        "# Sportradar Active Market Validation",
        "",
        f"- Dates checked: `{totals['dates']}`",
        f"- Matches with market payload: `{totals['matches_with_market_payload']}`",
        f"- Matches with active priced market: `{totals['matches_with_active_priced_market']}`",
        f"- Matches with 1X2: `{totals['matches_with_1x2']}`",
        f"- Matches with handicap: `{totals['matches_with_handicap']}`",
        f"- Matches with totals: `{totals['matches_with_totals']}`",
        "",
        "## By Date",
        "",
        "| Date | Market payloads | Active priced | 1X2 | Handicap | Totals | Live-like |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in results:
        counts = item.get("counts") or {}
        lines.append(
            "| {date} | {payloads} | {active} | {one_x_two} | {handicap} | {totals_count} | {live} |".format(
                date=item.get("date"),
                payloads=counts.get("matches_with_market_payload"),
                active=counts.get("matches_with_active_priced_market"),
                one_x_two=counts.get("matches_with_1x2"),
                handicap=counts.get("matches_with_handicap"),
                totals_count=counts.get("matches_with_totals"),
                live=counts.get("live_like_matches"),
            )
        )
    lines.extend(["", "## Samples", ""])
    for item in results:
        lines.append(f"### {item.get('date')}")
        lines.append("")
        for match in item.get("sample_matches") or []:
            lines.append(
                "- `{match_id}` {country} / {league}: {home} vs {away} kickoff={kickoff} active_markets={active} 1X2={one_x_two} AH={handicap} totals={totals}".format(
                    match_id=match.get("match_id"),
                    country=match.get("country"),
                    league=match.get("league"),
                    home=match.get("home"),
                    away=match.get("away"),
                    kickoff=match.get("kickoff_utc"),
                    active=match.get("active_market_count"),
                    one_x_two=match.get("has_1x2"),
                    handicap=match.get("has_handicap"),
                    totals=match.get("has_totals"),
                )
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _market_has_active_price(market: Any) -> bool:
    if not isinstance(market, dict) or not market.get("active"):
        return False
    outcomes = market.get("outcomes") if isinstance(market.get("outcomes"), list) else []
    return any(isinstance(outcome, dict) and outcome.get("active") and as_float(outcome.get("odds")) is not None for outcome in outcomes)


def _looks_live(fixture: dict[str, Any]) -> bool:
    status = str(fixture.get("status") or "").lower()
    period = str(fixture.get("result_period") or "").lower()
    return status not in {"", "not started", "ended"} or period not in {"", "nt", "ft"}


def _iso_from_uts(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(value), tz=UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return None

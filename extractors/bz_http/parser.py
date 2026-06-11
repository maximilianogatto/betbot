"""Parse BZ (m.bz.com) search + odds payloads into generic domain models.

``match/search`` returns tournaments grouped with their matches (Sportradar ids
throughout). ``odds/v2/bz/all`` returns market tabs for one match; the Main tab
markets used here:
  * market ``"1"``  -> 1X2     (outcomeId 1=home, 2=Draw, 3=away; ``odds`` = decimal)
  * market ``"16"`` -> Handicap (Asian; spec ``hcp=<line>``; outcomeId 1714=home,
    1715=away; each outcome's ``displayName`` is that side's line, e.g. "+2.0")
  * market ``"18"`` -> Total    (spec ``total=<line>``; outcomeId 12=Over, 13=Under)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.models import (
    CompetitionExtraction,
    CompetitionKey,
    EventKey,
    EventSnapshot,
    LiveEventSnapshot,
    Odds1X2,
    utc_now_iso,
)

PLATFORM = "bz_http"


def live_events_from_search(search_data: list[dict[str, Any]]) -> list[LiveEventSnapshot]:
    """Map a BZ statusList=1 search (tournaments -> live matches) to live snapshots."""

    live: list[LiveEventSnapshot] = []
    for tournament in search_data or []:
        if not isinstance(tournament, dict):
            continue
        country = tournament.get("categoryName")
        league = tournament.get("name")
        external_id = _normalize_tournament_id(tournament.get("id"))
        for match in tournament.get("matches") or []:
            if not isinstance(match, dict):
                continue
            home = str(match.get("homeName") or "").strip()
            away = str(match.get("awayName") or "").strip()
            if not home or not away:
                continue
            ses = match.get("sportEventStatus") or {}
            live.append(
                LiveEventSnapshot(
                    platform=PLATFORM,
                    external_event_id=str(match.get("id")),
                    home=home,
                    away=away,
                    competition_name=f"{country} · {league}" if country and league and country.lower() not in league.lower() else (league or "Unknown"),
                    country_name=country,
                    minute=match.get("matchStatusName") or match.get("statusName"),
                    home_score=_int(ses.get("homeScore")) if isinstance(ses, dict) else None,
                    away_score=_int(ses.get("awayScore")) if isinstance(ses, dict) else None,
                    home_red_cards=_int(ses.get("homeRedCards")) if isinstance(ses, dict) else None,
                    away_red_cards=_int(ses.get("awayRedCards")) if isinstance(ses, dict) else None,
                    home_yellow_cards=_int(ses.get("homeYellowCards")) if isinstance(ses, dict) else None,
                    away_yellow_cards=_int(ses.get("awayYellowCards")) if isinstance(ses, dict) else None,
                    scheduled_at=_kickoff_iso(match.get("scheduledTime")),
                    source_url=f"bz:tournament:{external_id}",
                    is_soccer=True,
                    extracted_at=utc_now_iso(),
                    raw_payload={"sr_match_id": str(match.get("id")), "matchStatus": match.get("matchStatus")},
                )
            )
    return live


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _main_markets(odds_tabs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return {market_id: market} from the Main tab (falling back to the first tab)."""

    if not odds_tabs:
        return {}
    main = next((tab for tab in odds_tabs if str(tab.get("tabId")) == "MAIN"), odds_tabs[0])
    markets: dict[str, dict[str, Any]] = {}
    for market in main.get("markets") or []:
        if isinstance(market, dict) and market.get("marketId") is not None:
            markets[str(market["marketId"])] = market
    return markets


def _first_spec(market: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(market, dict):
        return []
    specs = market.get("marketSpecifierList") or []
    if not specs:
        return []
    return specs[0].get("outcomes") or []


def _odds_1x2(markets: dict[str, Any]) -> Odds1X2:
    outcomes = {str(o.get("outcomeId")): _coerce_float(o.get("odds")) for o in _first_spec(markets.get("1"))}
    return Odds1X2(home=outcomes.get("1"), draw=outcomes.get("2"), away=outcomes.get("3"))


def _format_line(text: Any) -> str:
    value = _coerce_float(text)
    if value is None:
        return str(text)
    sign = "+" if value > 0 else ""
    return f"{sign}{int(value)}" if float(value).is_integer() else f"{sign}{value:g}"


def _asian_handicap(markets: dict[str, Any], *, home: str, away: str) -> dict[str, Any] | None:
    """Map BZ market 16 to the bot's asian_handicap shape (📐 AH)."""

    market = markets.get("16")
    if not isinstance(market, dict):
        return None
    rows_home: list[tuple[float, str, float]] = []
    rows_away: list[tuple[float, str, float]] = []
    for spec in market.get("marketSpecifierList") or []:
        if not isinstance(spec, dict):
            continue
        for outcome in spec.get("outcomes") or []:
            odds = _coerce_float(outcome.get("odds"))
            line_value = _coerce_float(outcome.get("displayName"))
            if odds is None or line_value is None:
                continue
            outcome_id = str(outcome.get("outcomeId"))
            label = _format_line(outcome.get("displayName"))
            if outcome_id == "1714":
                rows_home.append((abs(line_value), label, odds))
            elif outcome_id == "1715":
                rows_away.append((abs(line_value), label, odds))
    if not (rows_home and rows_away):
        return None

    rows_home.sort(key=lambda item: item[0])
    rows_away.sort(key=lambda item: item[0])
    selections: list[dict[str, Any]] = []
    for _, label, odds in rows_home[:3]:
        selections.append({"selection": home, "line": label, "odds": odds})
    for _, label, odds in rows_away[:3]:
        selections.append({"selection": away, "line": label, "odds": odds})
    return {"market_id": "bz_handicap", "market_name": "Asian Handicap", "selections": selections}


def _goal_line(markets: dict[str, Any], *, target: float = 2.5) -> dict[str, Any] | None:
    """Map BZ market 18 to the bot's goal_line shape (📏 GL)."""

    market = markets.get("18")
    if not isinstance(market, dict):
        return None
    rows: list[tuple[float, float | None, float | None]] = []
    for spec in market.get("marketSpecifierList") or []:
        if not isinstance(spec, dict):
            continue
        line = None
        spec_text = str(spec.get("specifiers") or "")
        for part in spec_text.split("|"):
            name, _, raw = part.partition("=")
            if name == "total":
                line = _coerce_float(raw)
        over = under = None
        for outcome in spec.get("outcomes") or []:
            if str(outcome.get("outcomeId")) == "12":
                over = _coerce_float(outcome.get("odds"))
            elif str(outcome.get("outcomeId")) == "13":
                under = _coerce_float(outcome.get("odds"))
            if line is None:
                line = _coerce_float(outcome.get("displayName"))
        if line is None or (over is None and under is None):
            continue
        rows.append((line, over, under))
    if not rows:
        return None

    rows.sort(key=lambda item: abs(item[0] - target))
    selections: list[dict[str, Any]] = []
    for line, over, under in rows:
        label = _format_line(line).lstrip("+")
        if over is not None:
            selections.append({"selection": "Over", "line": label, "odds": over})
        if under is not None:
            selections.append({"selection": "Under", "line": label, "odds": under})
    if not selections:
        return None
    return {"market_id": "bz_total", "market_name": "Goal Line", "selections": selections}


def _kickoff_iso(raw_value: Any) -> str | None:
    try:
        millis = int(raw_value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).isoformat()


def event_snapshot_from_match(
    match: dict[str, Any],
    odds_tabs: list[dict[str, Any]],
    *,
    competition_external_id: str,
    competition_name: str,
    source_url: str | None,
) -> EventSnapshot | None:
    match_id = match.get("id")
    home = str(match.get("homeName") or "").strip()
    away = str(match.get("awayName") or "").strip()
    if not match_id or not home or not away:
        return None

    markets = _main_markets(odds_tabs)
    markets_payload: dict[str, Any] = {}
    asian_handicap = _asian_handicap(markets, home=home, away=away)
    if asian_handicap is not None:
        markets_payload["asian_handicap"] = asian_handicap
    goal_line = _goal_line(markets)
    if goal_line is not None:
        markets_payload["goal_line"] = goal_line

    return EventSnapshot(
        key=EventKey(
            platform=PLATFORM,
            competition_external_id=competition_external_id,
            external_event_id=str(match_id),
        ),
        competition_name=competition_name,
        home=home,
        away=away,
        scheduled_label_date=None,
        scheduled_label_time=None,
        scheduled_at=_kickoff_iso(match.get("scheduledTime")),
        source_url=source_url,
        odds_1x2=_odds_1x2(markets),
        extracted_at=utc_now_iso(),
        markets_payload=markets_payload or None,
        metadata={
            "sr_match_id": str(match_id),
            "sr_season_id": match.get("seasonId"),
            "home_id": match.get("homeId"),
            "away_id": match.get("awayId"),
        },
        raw_payload={"match": {k: match.get(k) for k in ("id", "name", "scheduledTime", "matchStatus")}},
    )


def find_tournament(search_data: list[dict[str, Any]], tournament_id: str) -> dict[str, Any] | None:
    target = _normalize_tournament_id(tournament_id)
    for tournament in search_data or []:
        if isinstance(tournament, dict) and _normalize_tournament_id(tournament.get("id")) == target:
            return tournament
    return None


def build_competition_extraction(
    *,
    tournament_id: str,
    tournament: dict[str, Any],
    odds_by_match: dict[str, list[dict[str, Any]]],
    source_url: str,
) -> CompetitionExtraction:
    """Build a competition extraction from one tournament + per-match odds."""

    external_id = _normalize_tournament_id(tournament_id)
    name = str(tournament.get("name") or f"BZ liga {external_id}")
    country = tournament.get("categoryName")
    display_name = f"{country} · {name}" if country else name

    events: list[EventSnapshot] = []
    for match in tournament.get("matches") or []:
        if not isinstance(match, dict):
            continue
        match_id = str(match.get("id"))
        snapshot = event_snapshot_from_match(
            match,
            odds_by_match.get(match_id, []),
            competition_external_id=external_id,
            competition_name=display_name,
            source_url=source_url,
        )
        if snapshot is not None:
            events.append(snapshot)

    events.sort(key=lambda item: item.scheduled_at or "")

    return CompetitionExtraction(
        competition=CompetitionKey(platform=PLATFORM, competition_external_id=external_id),
        competition_name=display_name,
        source_url=source_url,
        events=events,
        is_empty=not events,
        is_provisional_name=not tournament.get("name"),
        extracted_at=utc_now_iso(),
        metadata={
            "tournament_id": f"sr:tournament:{external_id}",
            "category": country,
            "sr_season_id": tournament.get("currentSeasonId"),
        },
        raw_payload={},
    )


def _normalize_tournament_id(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("sr:tournament:"):
        return text.split(":")[-1]
    return text

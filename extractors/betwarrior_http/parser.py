"""Parse BetWarrior (Kambi) listView + betoffer payloads into domain models.

Kambi quirks: ``odds`` and ``line`` are integers scaled by 1000 (1660 = 1.66,
-250 = -0.25). Soccer markets used (selected by betOfferType id + criterion):
  * betOfferType ``2`` + criterion englishLabel "Full Time" -> 1X2
    (outcome types OT_ONE=home, OT_CROSS=draw, OT_TWO=away)
  * betOfferType ``7`` + criterion englishLabel "Asian Handicap" -> Asian handicap
    (one bet offer per line; outcomes[0]=home, [1]=away; each has its own ``line``)
  * betOfferType ``6`` + criterion englishLabel "Total Goals" -> goal line
    (outcome types OT_OVER/OT_UNDER; ``line`` is the total)
Each event's ``path`` is sport -> country -> league.
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

PLATFORM = "betwarrior_http"


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def live_events_from_open(payload: dict[str, Any]) -> list[LiveEventSnapshot]:
    """Map Kambi ``event/live/open.json`` to live snapshots (soccer only)."""

    live: list[LiveEventSnapshot] = []
    for item in payload.get("liveEvents") or []:
        if not isinstance(item, dict):
            continue
        event = item.get("event") or {}
        path = event.get("path") or []
        if not (path and path[0].get("termKey") == "football"):
            continue
        home = str(event.get("homeName") or "").strip()
        away = str(event.get("awayName") or "").strip()
        if not home or not away:
            continue
        is_soccer = not any("esport" in str(p.get("termKey", "")).lower() for p in path)
        country = path[-2].get("name") if len(path) >= 2 else None
        live_data = item.get("liveData") or {}
        clock = live_data.get("matchClock") or {}
        score = live_data.get("score") or {}
        minute = None
        if clock.get("minute") is not None:
            minute = f"{clock.get('minute')}'"
            if clock.get("period"):
                minute = f"{clock.get('period')} {minute}"
        live.append(
            LiveEventSnapshot(
                platform=PLATFORM,
                external_event_id=str(event.get("id")),
                home=home,
                away=away,
                competition_name=event.get("group"),
                country_name=country,
                minute=minute,
                home_score=_int(score.get("home")),
                away_score=_int(score.get("away")),
                scheduled_at=_kickoff_iso(event.get("start")),
                source_url=f"betwarrior:group:{event.get('groupId')}",
                is_soccer=is_soccer,
                extracted_at=utc_now_iso(),
                raw_payload={"state": event.get("state")},
            )
        )
    return live


def _odds(value: Any) -> float | None:
    try:
        return round(int(value) / 1000, 4)
    except (TypeError, ValueError):
        return None


def _line(value: Any) -> float | None:
    try:
        return int(value) / 1000
    except (TypeError, ValueError):
        return None


def _format_line(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{int(value)}" if float(value).is_integer() else f"{sign}{value:g}"


def _is(bet_offer: dict[str, Any], type_id: int, english_label: str) -> bool:
    return (
        bet_offer.get("betOfferType", {}).get("id") == type_id
        and bet_offer.get("criterion", {}).get("englishLabel") == english_label
    )


def _odds_1x2(bet_offers: list[dict[str, Any]]) -> Odds1X2:
    offer = next((b for b in bet_offers if _is(b, 2, "Full Time")), None)
    if offer is None:
        return Odds1X2(home=None, draw=None, away=None)
    by_type = {o.get("type"): _odds(o.get("odds")) for o in offer.get("outcomes", [])}
    return Odds1X2(home=by_type.get("OT_ONE"), draw=by_type.get("OT_CROSS"), away=by_type.get("OT_TWO"))


def _asian_handicap(bet_offers: list[dict[str, Any]], *, home: str, away: str) -> dict[str, Any] | None:
    rows_home: list[tuple[float, str, float]] = []
    rows_away: list[tuple[float, str, float]] = []
    for offer in bet_offers:
        if not _is(offer, 7, "Asian Handicap"):
            continue
        outcomes = offer.get("outcomes") or []
        if len(outcomes) < 2:
            continue
        for index, side_rows, name in ((0, rows_home, home), (1, rows_away, away)):
            outcome = outcomes[index]
            price = _odds(outcome.get("odds"))
            line = _line(outcome.get("line"))
            if price is None or line is None:
                continue
            side_rows.append((abs(line), _format_line(line), price))
    if not (rows_home and rows_away):
        return None
    rows_home.sort(key=lambda item: item[0])
    rows_away.sort(key=lambda item: item[0])
    selections: list[dict[str, Any]] = []
    seen_lines: set[str] = set()
    for _, label, price in rows_home[:4]:
        if ("h", label) not in seen_lines:
            selections.append({"selection": home, "line": label, "odds": price})
            seen_lines.add(("h", label))
    seen_lines.clear()
    for _, label, price in rows_away[:4]:
        if ("a", label) not in seen_lines:
            selections.append({"selection": away, "line": label, "odds": price})
            seen_lines.add(("a", label))
    return {"market_id": "kambi_asian_handicap", "market_name": "Asian Handicap", "selections": selections}


def _goal_line(bet_offers: list[dict[str, Any]], *, target: float = 2.5) -> dict[str, Any] | None:
    lines: dict[float, dict[str, float]] = {}
    for offer in bet_offers:
        if not _is(offer, 6, "Total Goals"):
            continue
        for outcome in offer.get("outcomes") or []:
            price = _odds(outcome.get("odds"))
            line = _line(outcome.get("line"))
            if price is None or line is None:
                continue
            side = outcome.get("type")
            if side == "OT_OVER":
                lines.setdefault(line, {})["over"] = price
            elif side == "OT_UNDER":
                lines.setdefault(line, {})["under"] = price
    if not lines:
        return None
    selections: list[dict[str, Any]] = []
    for line in sorted(lines.keys(), key=lambda value: abs(value - target)):
        label = _format_line(line).lstrip("+")
        if "over" in lines[line]:
            selections.append({"selection": "Over", "line": label, "odds": lines[line]["over"]})
        if "under" in lines[line]:
            selections.append({"selection": "Under", "line": label, "odds": lines[line]["under"]})
    if not selections:
        return None
    return {"market_id": "kambi_goal_line", "market_name": "Goal Line", "selections": selections}


def _kickoff_iso(raw_value: Any) -> str | None:
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def event_snapshot_from_event(
    event: dict[str, Any],
    bet_offers: list[dict[str, Any]],
    *,
    competition_external_id: str,
    competition_name: str,
    source_url: str | None,
) -> EventSnapshot | None:
    event_id = event.get("id")
    home = str(event.get("homeName") or "").strip()
    away = str(event.get("awayName") or "").strip()
    if event_id is None or not home or not away:
        return None

    markets_payload: dict[str, Any] = {}
    asian_handicap = _asian_handicap(bet_offers, home=home, away=away)
    if asian_handicap is not None:
        markets_payload["asian_handicap"] = asian_handicap
    goal_line = _goal_line(bet_offers)
    if goal_line is not None:
        markets_payload["goal_line"] = goal_line

    return EventSnapshot(
        key=EventKey(
            platform=PLATFORM,
            competition_external_id=competition_external_id,
            external_event_id=str(event_id),
        ),
        competition_name=competition_name,
        home=home,
        away=away,
        scheduled_label_date=None,
        scheduled_label_time=None,
        scheduled_at=_kickoff_iso(event.get("start")),
        source_url=source_url,
        odds_1x2=_odds_1x2(bet_offers),
        extracted_at=utc_now_iso(),
        markets_payload=markets_payload or None,
        metadata={"kambi_event_id": str(event_id), "english_name": event.get("englishName")},
        raw_payload={"event": {k: event.get(k) for k in ("id", "name", "start", "group", "groupId")}},
    )


def _country_from_path(path: list[dict[str, Any]] | None) -> str | None:
    if not isinstance(path, list) or len(path) < 2:
        return None
    return path[-2].get("name") or path[-2].get("englishName")


def build_competition_extraction(
    *,
    group_id: str,
    group_payload: dict[str, Any],
    source_url: str,
) -> CompetitionExtraction:
    events = [e for e in group_payload.get("events") or [] if str(e.get("groupId")) == str(group_id)]
    if not events:  # fall back to whatever the group returned
        events = list(group_payload.get("events") or [])

    offers_by_event: dict[str, list[dict[str, Any]]] = {}
    for offer in group_payload.get("betOffers") or []:
        offers_by_event.setdefault(str(offer.get("eventId")), []).append(offer)

    league_name = str(events[0].get("group")) if events else f"BetWarrior liga {group_id}"
    country = _country_from_path(events[0].get("path")) if events else None
    display_name = f"{country} · {league_name}" if country else league_name

    snapshots: list[EventSnapshot] = []
    for event in events:
        snapshot = event_snapshot_from_event(
            event,
            offers_by_event.get(str(event.get("id")), []),
            competition_external_id=str(group_id),
            competition_name=display_name,
            source_url=source_url,
        )
        if snapshot is not None:
            snapshots.append(snapshot)

    snapshots.sort(key=lambda item: item.scheduled_at or "")

    return CompetitionExtraction(
        competition=CompetitionKey(platform=PLATFORM, competition_external_id=str(group_id)),
        competition_name=display_name,
        source_url=source_url,
        events=snapshots,
        is_empty=not snapshots,
        is_provisional_name=not events,
        extracted_at=utc_now_iso(),
        metadata={"group_id": str(group_id), "country": country, "provider": "kambi"},
        raw_payload={},
    )

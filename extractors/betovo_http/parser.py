"""Parse Betovo (Altenar) GetEvents + GetEventDetails payloads into domain models.

GetEvents (normalized): ``events[]`` (id, name, champId, catId, startDate, extId,
competitorIds) plus lookup dicts ``champs`` (leagues), ``categories`` (countries),
``competitors``. GetEventDetails returns one event's full markets:
  * typeId ``1``  name "1x2"      -> odds named "1"/"X"/"2" (``price``)
  * typeId ``16`` name "Handicap" -> Asian handicap; odd name "<team> (<line>)",
    each odd carries ``competitorId``; market ``sv`` is the base line
  * typeId ``18`` name "Goal Line"/"Totals" -> odds named "Over <l>"/"Under <l>"

``extId`` looks like ``fp32_ar:match:554495`` -> the ``ar:match:554495`` part is the
Sportradar id, stored in metadata for direct stats linking.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
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

PLATFORM = "betovo_http"


def live_events_from_livenow(payload: dict[str, Any]) -> list[LiveEventSnapshot]:
    """Map Altenar ``GetLivenow`` to live snapshots (real-country soccer flagged)."""

    champs = _index_by_id(payload.get("champs"))
    categories = _index_by_id(payload.get("categories"))
    live: list[LiveEventSnapshot] = []
    for event in payload.get("events") or []:
        if not isinstance(event, dict):
            continue
        name = str(event.get("name") or "")
        home, _, away = name.partition(" vs. ")
        home, away = home.strip(), away.strip()
        if not home or not away:
            continue
        category = categories.get(event.get("catId")) or {}
        champ = champs.get(event.get("champId")) or {}
        score = event.get("score") if isinstance(event.get("score"), list) else [None, None]
        live.append(
            LiveEventSnapshot(
                platform=PLATFORM,
                external_event_id=str(event.get("id")),
                home=home,
                away=away,
                competition_name=champ.get("name"),
                country_name=category.get("name"),
                minute=event.get("liveTime") if event.get("liveTime") not in (None, "Not started") else event.get("ls"),
                home_score=_int(score[0]) if len(score) > 0 else None,
                away_score=_int(score[1]) if len(score) > 1 else None,
                home_red_cards=_side_count(event, "red", side=0),
                away_red_cards=_side_count(event, "red", side=1),
                home_yellow_cards=_side_count(event, "yellow", side=0),
                away_yellow_cards=_side_count(event, "yellow", side=1),
                scheduled_at=_kickoff_iso(event.get("startDate")),
                source_url=f"betovo:champ:{event.get('champId')}",
                is_soccer=bool(category.get("iso")),
                extracted_at=utc_now_iso(),
                raw_payload={"status": event.get("status"), "sr_match_id": _sr_id(event.get("extId"))},
            )
        )
    return live


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _side_count(event: dict[str, Any], color: str, *, side: int) -> int | None:
    """Best-effort card extraction from Altenar live events."""

    names = (
        ("redCards", "redcards", "reds") if color == "red" else ("yellowCards", "yellowcards", "yellows")
    )
    side_names = ("home", "away")
    for name in names:
        payload = event.get(name)
        if isinstance(payload, list) and len(payload) > side:
            return _int(payload[side])
        if isinstance(payload, dict):
            for key in (side_names[side], str(side), str(side + 1)):
                value = _int(payload.get(key))
                if value is not None:
                    return value
    return None

_LINE_IN_NAME_RE = re.compile(r"\(([+-]?\d+(?:\.\d+)?)\)")
_SR_ID_RE = re.compile(r"((?:sr|ar|od):match:\d+)", re.IGNORECASE)


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _index_by_id(items: Any) -> dict[Any, dict[str, Any]]:
    result: dict[Any, dict[str, Any]] = {}
    for item in items or []:
        if isinstance(item, dict) and "id" in item:
            result[item["id"]] = item
    return result


def _odd_ids(market: dict[str, Any]) -> list[int]:
    groups = market.get("desktopOddIds") or market.get("mobileOddIds") or []
    if groups and isinstance(groups[0], list):
        return [oid for grp in groups for oid in grp]
    # GetEvents-style flat list
    return list(market.get("oddIds") or [])


def _format_line(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{int(value)}" if float(value).is_integer() else f"{sign}{value:g}"


def _markets_by_type(detail: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    markets = detail.get("markets") or []
    odds = _index_by_id(detail.get("odds"))
    return markets, odds


def _odds_1x2(markets: list[dict[str, Any]], odds: dict[int, dict[str, Any]]) -> Odds1X2:
    market = next((m for m in markets if m.get("typeId") == 1 and m.get("name") == "1x2"), None)
    if market is None:
        market = next((m for m in markets if m.get("typeId") == 1), None)
    if market is None:
        return Odds1X2(home=None, draw=None, away=None)
    by_name: dict[str, float | None] = {}
    for oid in _odd_ids(market):
        odd = odds.get(oid)
        if odd:
            by_name[str(odd.get("name"))] = _coerce_float(odd.get("price"))
    return Odds1X2(home=by_name.get("1"), draw=by_name.get("X"), away=by_name.get("2"))


def _asian_handicap(
    markets: list[dict[str, Any]],
    odds: dict[int, dict[str, Any]],
    *,
    home_id: Any,
    away_id: Any,
    home: str,
    away: str,
) -> dict[str, Any] | None:
    market = next((m for m in markets if m.get("typeId") == 16 and m.get("name") == "Handicap"), None)
    if market is None:
        return None
    rows_home: list[tuple[float, str, float]] = []
    rows_away: list[tuple[float, str, float]] = []
    for oid in _odd_ids(market):
        odd = odds.get(oid)
        if not odd:
            continue
        price = _coerce_float(odd.get("price"))
        line_match = _LINE_IN_NAME_RE.search(str(odd.get("name") or ""))
        if price is None or not line_match:
            continue
        line = float(line_match.group(1))
        label = _format_line(line)
        if odd.get("competitorId") == home_id:
            rows_home.append((abs(line), label, price))
        elif odd.get("competitorId") == away_id:
            rows_away.append((abs(line), label, price))
    if not (rows_home and rows_away):
        return None
    rows_home.sort(key=lambda item: item[0])
    rows_away.sort(key=lambda item: item[0])
    selections: list[dict[str, Any]] = []
    for _, label, price in rows_home[:3]:
        selections.append({"selection": home, "line": label, "odds": price})
    for _, label, price in rows_away[:3]:
        selections.append({"selection": away, "line": label, "odds": price})
    return {"market_id": "betovo_handicap", "market_name": "Asian Handicap", "selections": selections}


def _goal_line(markets: list[dict[str, Any]], odds: dict[int, dict[str, Any]], *, target: float = 2.5) -> dict[str, Any] | None:
    market = next((m for m in markets if m.get("typeId") == 18 and m.get("name") in ("Goal Line", "Totals")), None)
    if market is None:
        market = next((m for m in markets if m.get("typeId") == 18), None)
    if market is None:
        return None
    lines: dict[float, dict[str, float]] = {}
    for oid in _odd_ids(market):
        odd = odds.get(oid)
        if not odd:
            continue
        price = _coerce_float(odd.get("price"))
        name = str(odd.get("name") or "")
        parts = name.split()
        if len(parts) < 2 or price is None:
            continue
        side = parts[0].lower()
        line = _coerce_float(parts[-1])
        if line is None or side not in ("over", "under"):
            continue
        lines.setdefault(line, {})[side] = price
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
    return {"market_id": "betovo_goal_line", "market_name": "Goal Line", "selections": selections}


def _kickoff_iso(raw_value: Any) -> str | None:
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _sr_id(ext_id: Any) -> str | None:
    match = _SR_ID_RE.search(str(ext_id or ""))
    return match.group(1) if match else None


def event_snapshot_from_event(
    event: dict[str, Any],
    detail: dict[str, Any],
    *,
    competition_external_id: str,
    competition_name: str,
    source_url: str | None,
) -> EventSnapshot | None:
    event_id = event.get("id")
    if event_id is None:
        return None

    competitors = detail.get("competitors") or []
    if len(competitors) >= 2:
        home, away = str(competitors[0].get("name") or "").strip(), str(competitors[1].get("name") or "").strip()
        home_id, away_id = competitors[0].get("id"), competitors[1].get("id")
    else:
        name = str(event.get("name") or "")
        home, _, away = name.partition(" vs. ")
        home, away = home.strip(), away.strip()
        ids = event.get("competitorIds") or [None, None]
        home_id, away_id = (ids[0], ids[1]) if len(ids) >= 2 else (None, None)
    if not home or not away:
        return None

    markets, odds = _markets_by_type(detail)
    markets_payload: dict[str, Any] = {}
    asian_handicap = _asian_handicap(markets, odds, home_id=home_id, away_id=away_id, home=home, away=away)
    if asian_handicap is not None:
        markets_payload["asian_handicap"] = asian_handicap
    goal_line = _goal_line(markets, odds)
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
        scheduled_at=_kickoff_iso(event.get("startDate")),
        source_url=source_url,
        odds_1x2=_odds_1x2(markets, odds),
        extracted_at=utc_now_iso(),
        markets_payload=markets_payload or None,
        metadata={"sr_match_id": _sr_id(event.get("extId")), "ext_id": event.get("extId")},
        raw_payload={"event": {k: event.get(k) for k in ("id", "name", "startDate", "extId", "status")}},
    )


def build_competition_extraction(
    *,
    champ_id: str,
    events_payload: dict[str, Any],
    details_by_event: dict[str, dict[str, Any]],
    source_url: str,
) -> CompetitionExtraction:
    champs = _index_by_id(events_payload.get("champs"))
    categories = _index_by_id(events_payload.get("categories"))
    champ = champs.get(_coerce_int(champ_id), {})
    champ_name = str(champ.get("name") or f"Betovo liga {champ_id}")
    category = categories.get(champ.get("categoryId") if champ.get("categoryId") is not None else None)

    # category resolved from the event when champ lacks categoryId
    events = [e for e in events_payload.get("events") or [] if str(e.get("champId")) == str(champ_id)]
    country = None
    if category:
        country = category.get("name")
    elif events:
        cat = categories.get(events[0].get("catId"))
        country = (cat or {}).get("name")
    display_name = f"{country} · {champ_name}" if country else champ_name

    snapshots: list[EventSnapshot] = []
    for event in events:
        detail = details_by_event.get(str(event.get("id")), {})
        snapshot = event_snapshot_from_event(
            event,
            detail,
            competition_external_id=str(champ_id),
            competition_name=display_name,
            source_url=source_url,
        )
        if snapshot is not None:
            snapshots.append(snapshot)

    snapshots.sort(key=lambda item: item.scheduled_at or "")

    return CompetitionExtraction(
        competition=CompetitionKey(platform=PLATFORM, competition_external_id=str(champ_id)),
        competition_name=display_name,
        source_url=source_url,
        events=snapshots,
        is_empty=not snapshots,
        is_provisional_name=not champ.get("name"),
        extracted_at=utc_now_iso(),
        metadata={"champ_id": str(champ_id), "category": country, "provider": "altenar"},
        raw_payload={},
    )


def _coerce_int(value: Any) -> Any:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value

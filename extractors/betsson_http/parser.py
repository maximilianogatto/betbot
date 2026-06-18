"""Parse Betsson (OBG) events-table payloads into domain models.

OBG quirks: odds are plain decimals (no scaling). Football markets are picked by
``marketTemplateId`` + ``selectionTemplateId``:
  * ``MW3W`` -> 1X2 (selection templates HOME / DRAW / AWAY)
  * ``MTG2W*`` -> full-match total goals, 2-way (OVER / UNDER; ``lineValue`` = total)
  * ``BTTS`` -> both teams to score (YES / NO)
  * ``M3WHCP`` -> 3-way European handicap (HANDICAPHOME / DRAW / AWAY). The book
    has no Asian line, so the home/away legs ride the ``asian_handicap`` slot (with
    the draw kept aside) to reuse the bot's handicap rendering / change-detection.

Each event carries ``participants`` (``side`` 1 = home, 2 = away), ``competitionId``,
``regionName`` (country) and a ``scoreboards`` entry for live score/cards/clock.
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

PLATFORM = "betsson_http"

_GOAL_LINE_TARGET = 2.5


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_line(value: float) -> str:
    return f"{int(value)}" if float(value).is_integer() else f"{value:g}"


def _format_signed(value: float) -> str:
    body = _format_line(abs(value))
    sign = "-" if value < 0 else "+"
    return f"{sign}{body}"


def _kickoff_iso(raw_value: Any) -> str | None:
    if not raw_value:
        return None
    try:
        return (
            datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .isoformat()
        )
    except ValueError:
        return None


def _participants(event: dict[str, Any]) -> tuple[str, str, str | None, str | None]:
    """Return (home_label, away_label, home_id, away_id) from ``participants``."""

    home = away = ""
    home_id = away_id = None
    for participant in event.get("participants") or []:
        if not isinstance(participant, dict):
            continue
        side = participant.get("side")
        label = str(participant.get("label") or "").strip()
        if side == 1:
            home, home_id = label, str(participant.get("id")) if participant.get("id") is not None else None
        elif side == 2:
            away, away_id = label, str(participant.get("id")) if participant.get("id") is not None else None
    return home, away, home_id, away_id


def _index_selections(selections: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_market: dict[str, list[dict[str, Any]]] = {}
    for selection in selections or []:
        if isinstance(selection, dict) and selection.get("marketId"):
            by_market.setdefault(str(selection["marketId"]), []).append(selection)
    for rows in by_market.values():
        rows.sort(key=lambda item: item.get("sortOrder") or 0)
    return by_market


def _markets_by_event(markets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_event: dict[str, list[dict[str, Any]]] = {}
    for market in markets or []:
        if isinstance(market, dict) and market.get("eventId"):
            by_event.setdefault(str(market["eventId"]), []).append(market)
    return by_event


def _odds_1x2(
    markets: list[dict[str, Any]],
    sel_by_market: dict[str, list[dict[str, Any]]],
) -> Odds1X2:
    market = next((m for m in markets if m.get("marketTemplateId") == "MW3W"), None)
    if market is None:
        return Odds1X2(home=None, draw=None, away=None)
    by_template = {
        s.get("selectionTemplateId"): _float(s.get("odds"))
        for s in sel_by_market.get(str(market.get("id")), [])
    }
    return Odds1X2(
        home=by_template.get("HOME"),
        draw=by_template.get("DRAW"),
        away=by_template.get("AWAY"),
    )


def _goal_line(
    markets: list[dict[str, Any]],
    sel_by_market: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """Collect full-match 2-way totals (``MTG2W*``) across every offered line."""

    lines: dict[float, dict[str, float]] = {}
    for market in markets:
        template = str(market.get("marketTemplateId") or "")
        if not template.startswith("MTG2W"):  # excludes 1st-half totals + player props
            continue
        line = _float(market.get("lineValue"))
        if line is None:
            continue
        for selection in sel_by_market.get(str(market.get("id")), []):
            price = _float(selection.get("odds"))
            if price is None:
                continue
            side = selection.get("selectionTemplateId")
            if side == "OVER":
                lines.setdefault(line, {})["over"] = price
            elif side == "UNDER":
                lines.setdefault(line, {})["under"] = price
    if not lines:
        return None
    selections: list[dict[str, Any]] = []
    for line in sorted(lines.keys(), key=lambda value: abs(value - _GOAL_LINE_TARGET)):
        label = _format_line(line)
        if "over" in lines[line]:
            selections.append({"selection": "Over", "line": label, "odds": lines[line]["over"]})
        if "under" in lines[line]:
            selections.append({"selection": "Under", "line": label, "odds": lines[line]["under"]})
    if not selections:
        return None
    return {"market_id": "obg_total_goals", "market_name": "Total de goles", "selections": selections}


def _european_handicap(
    markets: list[dict[str, Any]],
    sel_by_market: dict[str, list[dict[str, Any]]],
    *,
    home: str,
    away: str,
) -> dict[str, Any] | None:
    """Map the 3-way European handicap (``M3WHCP``) into the 2-way handicap slot.

    The book offers no Asian line, only a European 3-way handicap (one market per
    line, ``lineValue`` = ``"<home_start> - <away_start>"``, outcomes
    HANDICAPHOME / HANDICAPDRAW / HANDICAPAWAY). We surface the home/away legs (the
    actionable handicap odds) through the ``asian_handicap`` slot so they flow
    through the bot's existing handicap rendering / change-detection. The draw leg
    is kept in ``draw`` for callers that want the full 3-way picture.
    """

    rows_home: list[tuple[float, str, float]] = []
    rows_away: list[tuple[float, str, float]] = []
    draws: list[dict[str, Any]] = []
    for market in markets:
        if str(market.get("marketTemplateId") or "") != "M3WHCP":
            continue
        home_start = _home_handicap(market.get("lineValue"))
        if home_start is None:
            continue
        by_template = {
            s.get("selectionTemplateId"): _float(s.get("odds"))
            for s in sel_by_market.get(str(market.get("id")), [])
        }
        home_odds = by_template.get("HANDICAPHOME")
        away_odds = by_template.get("HANDICAPAWAY")
        draw_odds = by_template.get("HANDICAPDRAW")
        if home_odds is not None:
            rows_home.append((abs(home_start), _format_signed(home_start), home_odds))
        if away_odds is not None:
            rows_away.append((abs(home_start), _format_signed(-home_start), away_odds))
        if draw_odds is not None:
            draws.append({"selection": "Empate", "line": _format_signed(-home_start), "odds": draw_odds})
    if not (rows_home and rows_away):
        return None
    rows_home.sort(key=lambda item: item[0])
    rows_away.sort(key=lambda item: item[0])
    selections: list[dict[str, Any]] = []
    for _, label, price in rows_home[:4]:
        selections.append({"selection": home, "line": label, "odds": price})
    for _, label, price in rows_away[:4]:
        selections.append({"selection": away, "line": label, "odds": price})
    market_payload: dict[str, Any] = {
        "market_id": "obg_handicap_3way",
        "market_name": "Hándicap Europeo",
        "selections": selections,
    }
    if draws:
        market_payload["draw"] = draws[:4]
    return market_payload


def _home_handicap(line_value: Any) -> float | None:
    """Return the signed home handicap from a ``"<home> - <away>"`` line value."""

    text = str(line_value or "").strip()
    if not text:
        return None
    parts = [p.strip() for p in text.split("-")]
    # "1 - 0" -> ["1", "0"]; "0 - 1" -> ["0", "1"]; a leading "-" means a negative
    # start, e.g. "-1 - 0", so fall back to a single-number parse when needed.
    if len(parts) == 2:
        first, second = _float_signed(parts[0]), _float_signed(parts[1])
        if first is not None and second is not None:
            return first - second
    single = _float_signed(text)
    return single


def _float_signed(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _both_teams_to_score(
    markets: list[dict[str, Any]],
    sel_by_market: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    market = next((m for m in markets if m.get("marketTemplateId") == "BTTS"), None)
    if market is None:
        return None
    selections: list[dict[str, Any]] = []
    for selection in sel_by_market.get(str(market.get("id")), []):
        price = _float(selection.get("odds"))
        if price is None:
            continue
        label = str(selection.get("label") or selection.get("participantLabel") or "").strip()
        if label:
            selections.append({"selection": label, "odds": price})
    if not selections:
        return None
    return {
        "market_id": "obg_btts",
        "market_name": "Ambos equipos anotan",
        "selections": selections,
    }


def _markets_payload(
    markets: list[dict[str, Any]],
    sel_by_market: dict[str, list[dict[str, Any]]],
    *,
    home: str,
    away: str,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    # The book has no Asian line; the European 3-way handicap rides the
    # ``asian_handicap`` slot so it renders + change-detects like a handicap.
    handicap = _european_handicap(markets, sel_by_market, home=home, away=away)
    if handicap is not None:
        payload["asian_handicap"] = handicap
    goal_line = _goal_line(markets, sel_by_market)
    if goal_line is not None:
        payload["goal_line"] = goal_line
    btts = _both_teams_to_score(markets, sel_by_market)
    if btts is not None:
        payload["both_teams_to_score"] = btts
    return payload or None


def _competition_display_name(event: dict[str, Any]) -> str:
    country = str(event.get("regionName") or "").strip()
    league = str(event.get("competitionName") or "").strip()
    if country and league and country.lower() not in league.lower():
        return f"{country} · {league}"
    return league or country or "Betsson"


def build_competition_extraction(
    *,
    competition_id: str,
    table_payload: dict[str, Any],
    source_url: str,
) -> CompetitionExtraction:
    events = [
        e
        for e in table_payload.get("events") or []
        if isinstance(e, dict) and e.get("eventType") == "Fixture"
    ]
    sel_by_market = _index_selections(table_payload.get("selections") or [])
    markets_by_event = _markets_by_event(table_payload.get("markets") or [])

    display_name = _competition_display_name(events[0]) if events else f"Betsson liga {competition_id}"
    country = str(events[0].get("regionName")) if events else None

    snapshots: list[EventSnapshot] = []
    for event in events:
        home, away, _, _ = _participants(event)
        event_id = str(event.get("id") or "")
        if not event_id or not home or not away:
            continue
        markets = markets_by_event.get(event_id, [])
        snapshots.append(
            EventSnapshot(
                key=EventKey(
                    platform=PLATFORM,
                    competition_external_id=str(competition_id),
                    external_event_id=event_id,
                ),
                competition_name=display_name,
                home=home,
                away=away,
                scheduled_label_date=None,
                scheduled_label_time=None,
                scheduled_at=_kickoff_iso(event.get("startDate")),
                source_url=source_url,
                odds_1x2=_odds_1x2(markets, sel_by_market),
                extracted_at=utc_now_iso(),
                markets_payload=_markets_payload(markets, sel_by_market, home=home, away=away),
                metadata={"slug": event.get("slug"), "phase": event.get("phase")},
                raw_payload={},
            )
        )

    snapshots.sort(key=lambda item: item.scheduled_at or "")

    return CompetitionExtraction(
        competition=CompetitionKey(platform=PLATFORM, competition_external_id=str(competition_id)),
        competition_name=display_name,
        source_url=source_url,
        events=snapshots,
        is_empty=not snapshots,
        is_provisional_name=not events,
        extracted_at=utc_now_iso(),
        metadata={"competition_id": str(competition_id), "country": country, "provider": "obg"},
        raw_payload={},
    )


def _scoreboards_by_event(scoreboards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(sb.get("eventId")): sb
        for sb in scoreboards or []
        if isinstance(sb, dict) and sb.get("eventId")
    }


def _minute_label(scoreboard: dict[str, Any]) -> str | None:
    clock = scoreboard.get("matchClock") or {}
    minutes = _int(clock.get("minutes"))
    phase = (scoreboard.get("currentPhase") or {}).get("label")
    if minutes is not None:
        return f"{phase} {minutes}'" if phase else f"{minutes}'"
    return str(phase) if phase else None


def _stat(scoreboard: dict[str, Any], participant_id: str | None, key: str) -> int | None:
    if not participant_id:
        return None
    stats = (scoreboard.get("statistics") or {}).get(str(participant_id)) or {}
    entry = stats.get(key)
    if isinstance(entry, dict):
        return _int(entry.get("value"))
    return _int(entry)


def _score(scoreboard: dict[str, Any], participant_id: str | None) -> int | None:
    if not participant_id:
        return None
    return _int((scoreboard.get("scorePerParticipant") or {}).get(str(participant_id)))


def _snapshots_from_table(
    payload: dict[str, Any],
    *,
    with_live_data: bool,
) -> list[LiveEventSnapshot]:
    scoreboards = _scoreboards_by_event(payload.get("scoreboards") or [])
    out: list[LiveEventSnapshot] = []
    for event in payload.get("events") or []:
        if not isinstance(event, dict) or event.get("eventType") != "Fixture":
            continue
        home, away, home_id, away_id = _participants(event)
        event_id = str(event.get("id") or "")
        if not event_id or not home or not away:
            continue
        scoreboard = scoreboards.get(event_id) or {}
        minute = home_score = away_score = None
        h_red = a_red = h_yellow = a_yellow = None
        if with_live_data and scoreboard:
            minute = _minute_label(scoreboard)
            home_score = _score(scoreboard, home_id)
            away_score = _score(scoreboard, away_id)
            h_red = _stat(scoreboard, home_id, "redCards")
            a_red = _stat(scoreboard, away_id, "redCards")
            h_yellow = _stat(scoreboard, home_id, "yellowCards")
            a_yellow = _stat(scoreboard, away_id, "yellowCards")
        out.append(
            LiveEventSnapshot(
                platform=PLATFORM,
                external_event_id=event_id,
                home=home,
                away=away,
                competition_name=_competition_display_name(event),
                country_name=str(event.get("regionName") or "") or None,
                minute=minute,
                home_score=home_score,
                away_score=away_score,
                home_red_cards=h_red,
                away_red_cards=a_red,
                home_yellow_cards=h_yellow,
                away_yellow_cards=a_yellow,
                scheduled_at=_kickoff_iso(event.get("startDate")),
                source_url=f"betsson:competition:{event.get('competitionId')}",
                is_soccer=True,
                extracted_at=utc_now_iso(),
                raw_payload={"phase": event.get("phase")},
            )
        )
    return out


def live_events_from_table(payload: dict[str, Any]) -> list[LiveEventSnapshot]:
    """Map a ``eventPhase=Live`` events-table to live snapshots (score/cards/clock)."""

    return _snapshots_from_table(payload, with_live_data=True)


def prematch_events_from_table(payload: dict[str, Any]) -> list[LiveEventSnapshot]:
    """Map a competition events-table to prematch snapshots (no live data)."""

    return _snapshots_from_table(payload, with_live_data=False)


def _split_label(label: Any) -> tuple[str, str] | None:
    """Split an event label ``"Home - Away"`` into (home, away)."""

    text = str(label or "").strip()
    if " - " not in text:
        return None
    home, _, away = text.partition(" - ")
    home, away = home.strip(), away.strip()
    if not home or not away:
        return None
    return home, away


def prematch_events_from_tree(
    tree: dict[str, Any], *, category_id: str
) -> list[LiveEventSnapshot]:
    """Build the prematch listing from the categories tree in a single call.

    The ``categories/v2`` tree carries every event node (label, eventType, phase,
    startDate) under each competition, so the whole prematch board can be listed
    without the heavy paginated events-table sweep. Only soccer fixtures (not
    outrights) in the prematch phase are returned; odds/score are not available
    here (that is what the per-league extract / live feed provide).
    """

    items = (((tree or {}).get("data") or {}).get("items") or {})
    category = (items.get("categories") or {}).get(str(category_id)) or {}
    regions = category.get("regions") or {}
    out: list[LiveEventSnapshot] = []
    for region_id, region in regions.items():
        if not isinstance(region, dict) or str(region_id) == "0":
            continue
        country = str(region.get("label") or region.get("trackingLabel") or "") or None
        for competition_id, competition in (region.get("competitions") or {}).items():
            if not isinstance(competition, dict) or str(competition_id) == "0":
                continue
            league = str(competition.get("label") or "")
            if country and league and country.lower() not in league.lower():
                comp_name = f"{country} · {league}"
            else:
                comp_name = league or country or "Betsson"
            for event_id, event in (competition.get("events") or {}).items():
                if not isinstance(event, dict):
                    continue
                if event.get("eventType") != "Fixture" or event.get("phase") == "Live":
                    continue
                names = _split_label(event.get("label"))
                if names is None:
                    continue
                home, away = names
                out.append(
                    LiveEventSnapshot(
                        platform=PLATFORM,
                        external_event_id=str(event_id),
                        home=home,
                        away=away,
                        competition_name=comp_name,
                        country_name=country,
                        scheduled_at=_kickoff_iso(event.get("startDate")),
                        source_url=f"betsson:competition:{competition_id}",
                        is_soccer=True,
                        extracted_at=utc_now_iso(),
                        raw_payload={"phase": event.get("phase")},
                    )
                )
    return out

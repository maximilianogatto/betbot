"""Parse a merged Betby (sptpub) snapshot into generic domain models.

Snapshot shape (after merging chunks)::

    {
      "sports":      {"<sport_id>": {"name": "Soccer", ...}},
      "categories":  {"<cat_id>":   {"name": "Brazil", ...}},          # category == country
      "tournaments": {"<tour_id>":  {"name": "Serie A", "category_id": "<cat_id>"}},
      "events":      {"<event_id>": {"desc": {...}, "markets": {...}, "state": {...}}}
    }

Each event ``desc`` has ``type`` ("match"), ``sport``, ``tournament``,
``competitors`` ([home, away]) and ``scheduled`` (unix seconds). Markets seen in
the broad prematch snapshot for soccer:
  * market ``"1"``  -> 1X2  (outcome 1=home, 2=draw, 3=away; ``k`` = decimal odd)
  * market ``"18"`` -> totals (spec ``total=<line>``; outcome 12=over, 13=under)
  * market ``"10"`` -> double chance (not rendered by the bot)
Asian handicap (``hcp=``) is NOT present in the broad snapshot — Betby gates it
behind a per-event endpoint we could not reach over plain HTTP, so it is omitted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.models import (
    CompetitionExtraction,
    CompetitionKey,
    EventKey,
    EventSnapshot,
    Odds1X2,
    utc_now_iso,
)

PLATFORM = "rainbet_http"


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _odds_1x2(markets: dict[str, Any]) -> Odds1X2:
    market = (markets.get("1") or {}).get("") or {}
    if not isinstance(market, dict):
        return Odds1X2(home=None, draw=None, away=None)
    return Odds1X2(
        home=_coerce_float((market.get("1") or {}).get("k")),
        draw=_coerce_float((market.get("2") or {}).get("k")),
        away=_coerce_float((market.get("3") or {}).get("k")),
    )


def _spec_line(spec: str, key: str = "total") -> float | None:
    for part in str(spec).split("|"):
        name, _, raw = part.partition("=")
        if name == key:
            return _coerce_float(raw)
    return None


def _format_line(value: float) -> str:
    return f"{int(value)}" if float(value).is_integer() else f"{value:g}"


def _goal_line(markets: dict[str, Any], *, target: float = 2.5) -> dict[str, Any] | None:
    """Map Betby totals (market 18; over=12, under=13) to the bot's goal_line shape."""

    rows: list[tuple[float, float | None, float | None]] = []
    for market in markets.values():
        if not isinstance(market, dict):
            continue
        for spec, outcomes in market.items():
            line = _spec_line(str(spec), "total")
            if line is None or not isinstance(outcomes, dict):
                continue
            over = _coerce_float((outcomes.get("12") or {}).get("k"))
            under = _coerce_float((outcomes.get("13") or {}).get("k"))
            if over is None and under is None:
                continue
            rows.append((line, over, under))
    if not rows:
        return None

    rows.sort(key=lambda item: abs(item[0] - target))
    selections: list[dict[str, Any]] = []
    for line, over, under in rows:
        label = _format_line(line)
        if over is not None:
            selections.append({"selection": "Over", "line": label, "odds": over})
        if under is not None:
            selections.append({"selection": "Under", "line": label, "odds": under})
    if not selections:
        return None
    return {"market_id": "betby_totals", "market_name": "Goal Line", "selections": selections}


def _kickoff_iso(raw_value: Any) -> str | None:
    try:
        unix_value = int(raw_value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(unix_value, tz=timezone.utc).isoformat()


def event_snapshot_from_event(
    event_id: str,
    event: dict[str, Any],
    *,
    competition_external_id: str,
    competition_name: str,
    source_url: str | None,
) -> EventSnapshot | None:
    desc = event.get("desc") or {}
    if not isinstance(desc, dict):
        return None
    competitors = desc.get("competitors") or []
    if len(competitors) < 2:
        return None
    home = str((competitors[0] or {}).get("name") or "").strip()
    away = str((competitors[1] or {}).get("name") or "").strip()
    if not home or not away:
        return None

    markets = event.get("markets") or {}
    if not isinstance(markets, dict):
        markets = {}

    markets_payload: dict[str, Any] = {}
    goal_line = _goal_line(markets)
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
        scheduled_at=_kickoff_iso(desc.get("scheduled")),
        source_url=source_url,
        odds_1x2=_odds_1x2(markets),
        extracted_at=utc_now_iso(),
        markets_payload=markets_payload or None,
        raw_payload={"desc": desc, "market_keys": sorted(str(key) for key in markets.keys())},
    )


def build_competition_extraction(
    *,
    tournament_id: str,
    snapshot: dict[str, Any],
    source_url: str,
    competition_name: str | None = None,
) -> CompetitionExtraction:
    """Filter a merged snapshot to one tournament (league) and normalize it."""

    tournaments = snapshot.get("tournaments") or {}
    tournament = tournaments.get(str(tournament_id)) if isinstance(tournaments, dict) else None
    tournament = tournament if isinstance(tournament, dict) else {}
    resolved_name = competition_name or tournament.get("name") or f"Rainbet liga {tournament_id}"

    events: list[EventSnapshot] = []
    for event_id, event in (snapshot.get("events") or {}).items():
        if not isinstance(event, dict):
            continue
        desc = event.get("desc") or {}
        if desc.get("type") != "match":
            continue
        if str(desc.get("tournament")) != str(tournament_id):
            continue
        snapshot_event = event_snapshot_from_event(
            event_id,
            event,
            competition_external_id=str(tournament_id),
            competition_name=resolved_name,
            source_url=source_url,
        )
        if snapshot_event is not None:
            events.append(snapshot_event)

    events.sort(key=lambda item: item.scheduled_at or "")

    return CompetitionExtraction(
        competition=CompetitionKey(platform=PLATFORM, competition_external_id=str(tournament_id)),
        competition_name=resolved_name,
        source_url=source_url,
        events=events,
        is_empty=not events,
        is_provisional_name=competition_name is None and not tournament.get("name"),
        extracted_at=utc_now_iso(),
        metadata={"tournament_id": str(tournament_id), "provider": "betby_sptpub"},
        raw_payload={},
    )

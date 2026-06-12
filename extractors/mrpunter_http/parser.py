"""Parse MrPunter (FSB) positional-array payloads into domain models.

gameOdds / live events are positional arrays (not objects). Indices used:
  [0] eventId  [8] competitors [[id,{ES:name},"Home"],[id,{ES:name},"Away"]]
  [10] "Home vs Away"  [11] startISO  [12] score [s1,s2,null,{firstHalf...}]
  [15] clock {ClockRunning,...}  [19] markets (gameOdds only)  [31] MasterLeagueId
Each market: [marketId, name, name2, [typeCode,...], eventId, leagueId, sportId, [outcomes]].
Each outcome: [outcomeId, {ES:label}, {ES:short}, bool, PRICE(decimal), ...].

Markets are matched by NAME (robust to type-code drift):
  "Resultado del Partido"            -> 1X2 (labels: home / "Empate" / away)
  "Total de Goles Más/Menos"         -> goal line ("Más de X.X" / "Menos de X.X")
  name containing "Hándicap"/"Asiático" -> Asian handicap (best-effort)
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

PLATFORM = "mrpunter_http"

IDX_EVENT_ID = 0
IDX_COMPETITORS = 8
IDX_NAME = 10
IDX_START = 11
IDX_SCORE = 12
IDX_CLOCK = 15
IDX_MARKETS = 19

_LINE_RE = re.compile(r"([+-]?\d+(?:\.\d+)?)")


def _f(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _i(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _competitors(ev: list[Any]) -> tuple[str, str, Any, Any]:
    comps = ev[IDX_COMPETITORS] if len(ev) > IDX_COMPETITORS and isinstance(ev[IDX_COMPETITORS], list) else []
    home = away = ""
    home_id = away_id = None

    def name(entry: Any) -> str:
        if len(entry) > 1 and isinstance(entry[1], dict):
            return str(entry[1].get("ES") or "").strip()
        return ""

    for entry in comps:
        if not isinstance(entry, list) or len(entry) < 3:
            continue
        role = str(entry[2]).lower()
        if role == "home":
            home, home_id = name(entry), entry[0]
        elif role == "away":
            away, away_id = name(entry), entry[0]
    return home, away, home_id, away_id


def _markets(ev: list[Any]) -> list[list[Any]]:
    if len(ev) > IDX_MARKETS and isinstance(ev[IDX_MARKETS], list):
        return [m for m in ev[IDX_MARKETS] if isinstance(m, list)]
    return []


def _market_name(market: list[Any]) -> str:
    return str(market[1]) if len(market) > 1 else ""


def _outcomes(market: list[Any]) -> list[list[Any]]:
    return [o for o in (market[7] if len(market) > 7 and isinstance(market[7], list) else []) if isinstance(o, list)]


def _outcome_label(outcome: list[Any]) -> str:
    if len(outcome) > 1 and isinstance(outcome[1], dict):
        return str(outcome[1].get("ES") or "").strip()
    return ""


def _outcome_price(outcome: list[Any]) -> float | None:
    return _f(outcome[4]) if len(outcome) > 4 else None


def _format_line(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{int(value)}" if float(value).is_integer() else f"{sign}{value:g}"


def _find_market(markets: list[list[Any]], *patterns: str) -> list[Any] | None:
    for market in markets:
        name = _market_name(market).lower()
        if any(p in name for p in patterns):
            return market
    return None


def _odds_1x2(markets: list[list[Any]], *, home: str, away: str) -> Odds1X2:
    market = _find_market(markets, "resultado del partido")
    if market is None:
        market = next((m for m in markets if (m[3][0] if len(m) > 3 and isinstance(m[3], list) and m[3] else "") == "ML0"), None)
    if market is None:
        return Odds1X2(home=None, draw=None, away=None)
    by_label: dict[str, float | None] = {_outcome_label(o): _outcome_price(o) for o in _outcomes(market)}
    draw = next((p for lbl, p in by_label.items() if lbl.lower() in ("empate", "draw", "x")), None)
    return Odds1X2(home=by_label.get(home), draw=draw, away=by_label.get(away))


def _goal_line(markets: list[list[Any]], *, target: float = 2.5) -> dict[str, Any] | None:
    market = _find_market(markets, "total de goles más/menos", "total de goles mas/menos")
    if market is None:
        market = next((m for m in markets if (m[3][0] if len(m) > 3 and isinstance(m[3], list) and m[3] else "") == "OU200"), None)
    if market is None:
        return None
    lines: dict[float, dict[str, float]] = {}
    for outcome in _outcomes(market):
        price = _outcome_price(outcome)
        if not price:  # skip closed (0) / missing
            continue
        label = _outcome_label(outcome).lower()
        match = _LINE_RE.search(label)
        if not match:
            continue
        line = float(match.group(1))
        side = "over" if ("más" in label or "mas" in label or "over" in label) else "under"
        lines.setdefault(line, {})[side] = price
    if not lines:
        return None
    selections: list[dict[str, Any]] = []
    for line in sorted(lines.keys(), key=lambda v: abs(v - target)):
        label = _format_line(line).lstrip("+")
        if "over" in lines[line]:
            selections.append({"selection": "Over", "line": label, "odds": lines[line]["over"]})
        if "under" in lines[line]:
            selections.append({"selection": "Under", "line": label, "odds": lines[line]["under"]})
    if not selections:
        return None
    return {"market_id": "fsb_total", "market_name": "Goal Line", "selections": selections}


def _asian_handicap(markets: list[list[Any]], *, home: str, away: str) -> dict[str, Any] | None:
    market = _find_market(markets, "hándicap asiático", "handicap asiático", "hándicap asiatico", "asian handicap")
    if market is None:
        return None
    rows_home: list[tuple[float, str, float]] = []
    rows_away: list[tuple[float, str, float]] = []
    for outcome in _outcomes(market):
        price = _outcome_price(outcome)
        label = _outcome_label(outcome)
        match = _LINE_RE.search(label)
        if not price or not match:
            continue
        line = float(match.group(1))
        side_rows = rows_home if home and home.lower() in label.lower() else rows_away if away and away.lower() in label.lower() else None
        if side_rows is None:
            continue
        side_rows.append((abs(line), _format_line(line), price))
    if not (rows_home and rows_away):
        return None
    rows_home.sort(key=lambda r: r[0])
    rows_away.sort(key=lambda r: r[0])
    selections = [{"selection": home, "line": lbl, "odds": p} for _, lbl, p in rows_home[:3]]
    selections += [{"selection": away, "line": lbl, "odds": p} for _, lbl, p in rows_away[:3]]
    return {"market_id": "fsb_asian_handicap", "market_name": "Asian Handicap", "selections": selections}


def _kickoff_iso(raw: Any) -> str | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _score(ev: list[Any]) -> tuple[int | None, int | None]:
    sc = ev[IDX_SCORE] if len(ev) > IDX_SCORE and isinstance(ev[IDX_SCORE], list) else []
    s1 = _i(sc[0]) if len(sc) > 0 else None
    s2 = _i(sc[1]) if len(sc) > 1 else None
    return s1, s2


def event_snapshot_from_array(
    ev: list[Any],
    *,
    competition_external_id: str,
    competition_name: str,
    source_url: str | None,
) -> EventSnapshot | None:
    if not isinstance(ev, list) or len(ev) <= IDX_NAME:
        return None
    home, away, home_id, away_id = _competitors(ev)
    event_id = ev[IDX_EVENT_ID]
    if not home or not away or event_id is None:
        return None

    markets = _markets(ev)
    markets_payload: dict[str, Any] = {}
    ah = _asian_handicap(markets, home=home, away=away)
    if ah is not None:
        markets_payload["asian_handicap"] = ah
    gl = _goal_line(markets)
    if gl is not None:
        markets_payload["goal_line"] = gl

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
        scheduled_at=_kickoff_iso(ev[IDX_START] if len(ev) > IDX_START else None),
        source_url=source_url,
        odds_1x2=_odds_1x2(markets, home=home, away=away),
        extracted_at=utc_now_iso(),
        markets_payload=markets_payload or None,
        metadata={"fsb_event_id": str(event_id), "home_id": home_id, "away_id": away_id},
        raw_payload={"name": ev[IDX_NAME] if len(ev) > IDX_NAME else None},
    )


def build_competition_extraction(
    *,
    master_league_id: str,
    events: list[list[Any]],
    source_url: str,
    competition_name: str | None = None,
    country_name: str | None = None,
) -> CompetitionExtraction:
    league_name = competition_name
    if league_name is None and events:
        league_name = str(events[0][2]) if len(events[0]) > 2 else None
    name = league_name or f"MrPunter liga {master_league_id}"
    display_name = f"{country_name} · {name}" if country_name else name

    snapshots: list[EventSnapshot] = []
    for ev in events:
        snapshot = event_snapshot_from_array(
            ev,
            competition_external_id=str(master_league_id),
            competition_name=display_name,
            source_url=source_url,
        )
        if snapshot is not None:
            snapshots.append(snapshot)
    snapshots.sort(key=lambda item: item.scheduled_at or "")

    return CompetitionExtraction(
        competition=CompetitionKey(platform=PLATFORM, competition_external_id=str(master_league_id)),
        competition_name=display_name,
        source_url=source_url,
        events=snapshots,
        is_empty=not snapshots,
        is_provisional_name=competition_name is None and not (events and len(events[0]) > 2),
        extracted_at=utc_now_iso(),
        metadata={"master_league_id": str(master_league_id), "country": country_name, "provider": "fsb"},
        raw_payload={},
    )


def _clock_minute(clock: dict) -> str | None:
    """Human match minute from the FSB clock dict.

    FSB exposes the game clock in SECONDS (``GameTime``/``MatchTime``), e.g.
    2700 -> 45', 5690 -> 94'. The raw value was being shown as the "minute"
    ("5690"); convert it. A ``Minute`` key (already in minutes) wins if present.
    """

    if not isinstance(clock, dict):
        return None
    raw_minute = clock.get("Minute")
    if raw_minute is not None:
        return f"{raw_minute}'"
    for key in ("GameTime", "MatchTime", "Time"):
        value = clock.get(key)
        if value is None:
            continue
        try:
            return f"{int(value) // 60}'"
        except (TypeError, ValueError):
            return str(value)
    return None


def _live_snapshot_from_array(ev: Any, *, sport_id: str) -> LiveEventSnapshot | None:
    """Map one FSB positional event array to a live snapshot (or None)."""

    if not isinstance(ev, list) or len(ev) <= IDX_NAME:
        return None
    home, away, _, _ = _competitors(ev)
    event_id = ev[IDX_EVENT_ID]
    if not home or not away or event_id is None:
        return None
    ev_sport = str(ev[3]) if len(ev) > 3 else ""
    s1, s2 = _score(ev)
    clock = ev[IDX_CLOCK] if len(ev) > IDX_CLOCK and isinstance(ev[IDX_CLOCK], dict) else {}
    minute = _clock_minute(clock)
    t_name = str(ev[2]) if len(ev) > 2 else None
    c_name = str(ev[7]) if len(ev) > 7 else None
    comp_name = f"{c_name} · {t_name}" if c_name and t_name and c_name.lower() not in t_name.lower() else t_name
    return LiveEventSnapshot(
        platform=PLATFORM,
        external_event_id=str(event_id),
        home=home,
        away=away,
        competition_name=comp_name,
        country_name=c_name,
        minute=minute,
        home_score=s1,
        away_score=s2,
        scheduled_at=_kickoff_iso(ev[IDX_START] if len(ev) > IDX_START else None),
        source_url=f"mrpunter:league:{ev[31]}" if len(ev) > 31 else None,
        is_soccer=(ev_sport == str(sport_id)),
        extracted_at=utc_now_iso(),
        raw_payload={"sport_id": ev_sport},
    )


def live_events_from_initial(payload: dict[str, Any], *, sport_id: str = "1") -> list[LiveEventSnapshot]:
    """Map a live/initial payload's event arrays to live snapshots."""

    block = payload.get("events")
    data = block.get("data") if isinstance(block, dict) else None
    if not isinstance(data, list):
        return []
    live: list[LiveEventSnapshot] = []
    for ev in data:
        snapshot = _live_snapshot_from_array(ev, sport_id=sport_id)
        if snapshot is not None:
            live.append(snapshot)
    return live


def live_events_from_league_odds(
    events_by_league: dict[str, list[list[Any]]], *, sport_id: str = "1"
) -> list[LiveEventSnapshot]:
    """Map per-league live gameOdds arrays to deduped live snapshots.

    The ``events/v2/live/initial`` feed returns an empty ``data`` array even when
    live football exists, so live detection gathers each live league's gameOdds
    (``IsLive=true``) instead — same positional array shape.
    """

    live: list[LiveEventSnapshot] = []
    seen: set[str] = set()
    for events in events_by_league.values():
        if not isinstance(events, list):
            continue
        for ev in events:
            snapshot = _live_snapshot_from_array(ev, sport_id=sport_id)
            if snapshot is None or snapshot.external_event_id in seen:
                continue
            seen.add(snapshot.external_event_id)
            live.append(snapshot)
    return live

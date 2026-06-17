"""Parsing for Mystake prematch payloads into generic domain models.

Payload shape (mystake.bet ``getprematchgameall/<region>/<lang>/?games=,<ids>``):
  - ``game``: JSON string -> list of games. Each game: id, ch (= championship /
    league id), t1/t2 (team ids), st (ISO start), sport, ev (markets dict).
    Markets used here (``coef`` = decimal odd):
      * 448 = 1X2          (pos 1=home, 2=draw, 3=away)
      * 451 = Asian handicap (pos 70=home, 71=away; ``h`` = line)
      * 537 = Goal line / Over-Under (pos 81=over, 82=under; ``h`` = line)
  - ``teams``: JSON string -> list of {ID, Name}.
  - ``outrights``: JSON string (ignored here).

League names come from the header tree (see ``header.py``), not this payload.
"""

from __future__ import annotations

import json
from typing import Any

from core.models import (
    CompetitionExtraction,
    CompetitionKey,
    EventKey,
    EventSnapshot,
    Odds1X2,
    utc_now_iso,
)

PLATFORM = "mystake_http"


def decode_json_field(raw: Any) -> Any:
    """Decode a payload field that may be a JSON string or already-parsed."""

    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return []
    return []


def parse_teams(raw_teams: Any) -> dict[Any, str]:
    """Build an id -> team name map from the raw teams field."""

    teams: dict[Any, str] = {}
    for item in decode_json_field(raw_teams) or []:
        if isinstance(item, dict) and "ID" in item:
            teams[item["ID"]] = item.get("Name") or f"ID:{item['ID']}"
    return teams


def _odds_1x2(ev: dict[str, Any]) -> Odds1X2:
    market = ev.get("448") if isinstance(ev, dict) else None
    if not isinstance(market, dict):
        return Odds1X2(home=None, draw=None, away=None)
    by_pos = {entry.get("pos"): entry.get("coef") for entry in market.values() if isinstance(entry, dict)}
    return Odds1X2(home=_as_float(by_pos.get(1)), draw=_as_float(by_pos.get(2)), away=_as_float(by_pos.get(3)))


def _format_line(value: float, *, show_plus: bool = True) -> str:
    sign = "+" if (value > 0 and show_plus) else ""
    if float(value).is_integer():
        return f"{sign}{int(value)}"
    return f"{sign}{value:g}"


def _asian_handicap(ev: dict[str, Any], *, home: str, away: str) -> dict[str, Any] | None:
    """Map Mystake market 451 (pos 70=home, 71=away; h=line) to the bot's AH shape."""

    market = ev.get("451") if isinstance(ev, dict) else None
    if not isinstance(market, dict):
        return None

    def _side(pos: int) -> list[tuple[float, float]]:
        rows = [
            (_as_float(e.get("h")), _as_float(e.get("coef")))
            for e in market.values()
            if isinstance(e, dict) and e.get("pos") == pos and e.get("h") is not None
        ]
        rows = [(line, odds) for line, odds in rows if line is not None and odds is not None]
        return sorted(rows, key=lambda item: abs(item[0]))  # main line (closest to 0) first

    selections: list[dict[str, Any]] = []
    home_rows = _side(70)
    away_rows = _side(71)
    for line, odds in home_rows[:3]:
        selections.append({"selection": home, "line": _format_line(line), "odds": odds})
    for line, odds in away_rows[:3]:
        selections.append({"selection": away, "line": _format_line(line), "odds": odds})
    if not (home_rows and away_rows):
        return None
    return {"market_id": "mystake_asian_handicap", "market_name": "Asian Handicap", "selections": selections}


def _goal_line(ev: dict[str, Any], *, target: float = 2.5) -> dict[str, Any] | None:
    """Map Mystake market 537 (pos 81=over, 82=under; h=line) to the bot's goal_line shape."""

    market = ev.get("537") if isinstance(ev, dict) else None
    if not isinstance(market, dict):
        return None
    overs = {e["h"]: _as_float(e.get("coef")) for e in market.values() if isinstance(e, dict) and e.get("pos") == 81 and "h" in e}
    unders = {e["h"]: _as_float(e.get("coef")) for e in market.values() if isinstance(e, dict) and e.get("pos") == 82 and "h" in e}
    if not overs:
        return None
    selections: list[dict[str, Any]] = []
    for line in sorted(overs.keys(), key=lambda value: abs(value - target)):
        label = _format_line(line, show_plus=False)
        if overs.get(line) is not None:
            selections.append({"selection": "Over", "line": label, "odds": overs[line]})
        if unders.get(line) is not None:
            selections.append({"selection": "Under", "line": label, "odds": unders[line]})
    if not selections:
        return None
    return {"market_id": "mystake_goal_line", "market_name": "Goal Line", "selections": selections}


def event_snapshot_from_game(
    game: dict[str, Any],
    teams: dict[Any, str],
    *,
    competition_external_id: str,
    competition_name: str,
    source_url: str | None,
) -> EventSnapshot | None:
    """Map one raw game to a generic EventSnapshot, or None if unusable."""

    game_id = game.get("id")
    if game_id is None:
        return None
    ev = game.get("ev") if isinstance(game.get("ev"), dict) else {}
    home = teams.get(game.get("t1")) or f"ID:{game.get('t1')}"
    away = teams.get(game.get("t2")) or f"ID:{game.get('t2')}"
    markets_payload: dict[str, Any] = {}
    asian_handicap = _asian_handicap(ev, home=str(home), away=str(away))
    if asian_handicap is not None:
        markets_payload["asian_handicap"] = asian_handicap
    goal_line = _goal_line(ev)
    if goal_line is not None:
        markets_payload["goal_line"] = goal_line
    return EventSnapshot(
        key=EventKey(
            platform=PLATFORM,
            competition_external_id=competition_external_id,
            external_event_id=str(game_id),
        ),
        competition_name=competition_name,
        home=str(home),
        away=str(away),
        scheduled_label_date=None,
        scheduled_label_time=None,
        scheduled_at=game.get("st"),
        source_url=source_url,
        odds_1x2=_odds_1x2(ev),
        extracted_at=utc_now_iso(),
        markets_payload=markets_payload or None,
        # Persist only identity keys, not the whole game blob (the rest is
        # reconstructable from a re-fetch and never read back for features).
        raw_payload={k: game.get(k) for k in ("id", "st") if k in game},
    )


def build_competition_extraction(
    *,
    champ_id: str,
    raw_response: dict[str, Any],
    source_url: str,
    competition_name: str | None = None,
) -> CompetitionExtraction:
    """Filter a getprematchgameall response to one league (championship id).

    A Mystake league is the championship id (``ch``) carried by each game.
    """

    games = decode_json_field(raw_response.get("game"))
    teams = parse_teams(raw_response.get("teams"))
    name = competition_name or f"Mystake liga {champ_id}"

    events: list[EventSnapshot] = []
    for game in games or []:
        if not isinstance(game, dict):
            continue
        if str(game.get("ch")) != str(champ_id):
            continue
        snapshot = event_snapshot_from_game(
            game,
            teams,
            competition_external_id=str(champ_id),
            competition_name=name,
            source_url=source_url,
        )
        if snapshot is not None:
            events.append(snapshot)

    return CompetitionExtraction(
        competition=CompetitionKey(platform=PLATFORM, competition_external_id=str(champ_id)),
        competition_name=name,
        source_url=source_url,
        events=events,
        is_empty=not events,
        is_provisional_name=competition_name is None,
        extracted_at=utc_now_iso(),
        metadata={"champ_id": str(champ_id)},
        raw_payload={},
    )


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

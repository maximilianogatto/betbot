"""Parsing for Mystake prematch payloads into generic domain models.

Payload shape (from research, mystake.bet ``/prematch/getprematch``):
  - ``game``: JSON string -> list of games. Each game:
      id, t1/t2 (team ids), st (ISO start), sport, region (= league id),
      ev (markets dict). Market 448 = 1X2 (pos 1=home, 2=draw, 3=away),
      537 = Over/Under (pos 81=over, 82=under, h = line). coef = decimal odd.
  - ``teams``: JSON string -> list of {ID, Name}.
  - ``outrights``: JSON string (ignored here).
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


def _over_under(ev: dict[str, Any], *, target: float = 2.5) -> dict[str, Any] | None:
    market = ev.get("537") if isinstance(ev, dict) else None
    if not isinstance(market, dict):
        return None
    overs = {e["h"]: e.get("coef") for e in market.values() if isinstance(e, dict) and e.get("pos") == 81 and "h" in e}
    unders = {e["h"]: e.get("coef") for e in market.values() if isinstance(e, dict) and e.get("pos") == 82 and "h" in e}
    if not overs:
        return None
    line = min(overs.keys(), key=lambda value: abs(value - target))
    return {"line": line, "over": _as_float(overs.get(line)), "under": _as_float(unders.get(line))}


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
    over_under = _over_under(ev)
    markets_payload: dict[str, Any] = {}
    if over_under is not None:
        markets_payload["over_under"] = over_under
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
        raw_payload=game,
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

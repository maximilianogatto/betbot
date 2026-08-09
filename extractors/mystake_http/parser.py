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

PLATFORM = "mystake_http"
_VIRTUAL_SOCCER_RE = re.compile(r"(esport|e-?soccer|eadriatic|gt sports|cyber|simulated)", re.IGNORECASE)


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


def prematch_event_from_game(
    game: dict[str, Any],
    teams: dict[Any, str],
    *,
    competition_external_id: str,
    competition_name: str,
    country_name: str | None = None,
) -> LiveEventSnapshot | None:
    """Map one listed Mystake game to a prematch-compatible live-watch event."""

    game_id = game.get("id")
    if game_id is None:
        return None
    home = teams.get(game.get("t1")) or f"ID:{game.get('t1')}"
    away = teams.get(game.get("t2")) or f"ID:{game.get('t2')}"
    if not home or not away:
        return None
    return LiveEventSnapshot(
        platform=PLATFORM,
        external_event_id=str(game_id),
        home=str(home),
        away=str(away),
        competition_name=competition_name,
        country_name=country_name,
        scheduled_at=_kickoff_iso(game.get("st")),
        odds_1x2=_odds_1x2(game.get("ev") if isinstance(game.get("ev"), dict) else {}),
        markets_payload=_markets_payload_from_game(game, home=str(home), away=str(away)),
        source_url=f"mystake:champ:{competition_external_id}",
        is_soccer=True,
        extracted_at=utc_now_iso(),
        raw_payload={
            "champ_id": str(competition_external_id),
            "status": game.get("s"),
            "status_type": game.get("sti"),
        },
    )


def live_events_from_mobile_header(
    payload: dict[str, Any],
    *,
    sport_id: int = 1,
) -> list[LiveEventSnapshot]:
    """Map Mystake ``live/headerformobile/<region>`` cache to live snapshots.

    This endpoint is the browserless live source observed in production. It
    carries a compact list of live games plus separate id/name maps for teams,
    competitions and regions. ``hprs`` contains highlighted live prices; for
    soccer, market ``mid=602`` is the live 1X2 market.
    """

    if not isinstance(payload, dict):
        return []

    teams = _name_map(payload.get("Teams"))
    competitions = _name_map(payload.get("Championats"))
    regions = _name_map(payload.get("Regions"))

    events: list[LiveEventSnapshot] = []
    for game in payload.get("Games") or []:
        if not isinstance(game, dict) or _as_int(game.get("Sport")) != sport_id:
            continue
        game_id = game.get("ID") or game.get("id")
        home_id = game.get("Team1")
        away_id = game.get("Team2")
        if game_id is None or home_id is None or away_id is None:
            continue

        home = teams.get(home_id) or f"ID:{home_id}"
        away = teams.get(away_id) or f"ID:{away_id}"
        champ_id = game.get("Champ")
        region_id = game.get("Region")
        competition_name = competitions.get(champ_id) or f"Mystake liga {champ_id}"
        country_name = regions.get(region_id)
        display_comp = (
            f"{country_name} · {competition_name}"
            if country_name and competition_name and country_name.lower() not in competition_name.lower()
            else competition_name
        )
        score = _score_pair(game)
        is_soccer = not _looks_virtual_soccer(
            competition_name=display_comp,
            country_name=country_name,
            home=str(home),
            away=str(away),
        )
        events.append(
            LiveEventSnapshot(
                platform=PLATFORM,
                external_event_id=str(game_id),
                home=str(home),
                away=str(away),
                competition_name=display_comp,
                country_name=country_name,
                minute=_minute_label(game),
                home_score=score[0],
                away_score=score[1],
                home_red_cards=_card_count(game, side="home", color="red"),
                away_red_cards=_card_count(game, side="away", color="red"),
                home_yellow_cards=_card_count(game, side="home", color="yellow"),
                away_yellow_cards=_card_count(game, side="away", color="yellow"),
                scheduled_at=_kickoff_iso(game.get("StartTime")),
                odds_1x2=_odds_1x2_from_live_rows(game.get("hprs")),
                markets_payload=_live_markets_payload(game.get("hprs"), home=str(home), away=str(away)),
                source_url=f"mystake:champ:{champ_id}",
                is_soccer=is_soccer,
                extracted_at=utc_now_iso(),
                live_stats={
                    "match_status_id": game.get("MatchStatusID"),
                    "match_time": game.get("MatchTime"),
                    "market_count": game.get("mc"),
                    "live_bet_status": game.get("LiveBetStatus"),
                },
                raw_payload={
                    "champ_id": str(champ_id) if champ_id is not None else None,
                    "region_id": str(region_id) if region_id is not None else None,
                    "sport_id": game.get("Sport"),
                    "live_status": game.get("ls"),
                },
            )
        )
    return events


def live_event_from_game(
    game: dict[str, Any],
    teams: dict[Any, str],
    *,
    competition_external_id: str,
    competition_name: str,
    country_name: str | None = None,
) -> LiveEventSnapshot | None:
    """Map one Mystake game detail to a live event when its status is in-play.

    Mystake's public REST endpoints expose prematch details reliably. The live
    cache only provides changed game ids; if a fetched detail still looks
    prematch (``s=0``/``sti=0`` and no score/clock fields), this returns None so
    the watcher does not fire a false live alert.
    """

    if not _looks_live(game):
        return None
    snapshot = prematch_event_from_game(
        game,
        teams,
        competition_external_id=competition_external_id,
        competition_name=competition_name,
        country_name=country_name,
    )
    if snapshot is None:
        return None
    score = _score_pair(game)
    return LiveEventSnapshot(
        platform=snapshot.platform,
        external_event_id=snapshot.external_event_id,
        home=snapshot.home,
        away=snapshot.away,
        competition_name=snapshot.competition_name,
        country_name=snapshot.country_name,
        minute=_minute_label(game),
        home_score=score[0],
        away_score=score[1],
        home_red_cards=_card_count(game, side="home", color="red"),
        away_red_cards=_card_count(game, side="away", color="red"),
        home_yellow_cards=_card_count(game, side="home", color="yellow"),
        away_yellow_cards=_card_count(game, side="away", color="yellow"),
        scheduled_at=snapshot.scheduled_at,
        odds_1x2=snapshot.odds_1x2,
        markets_payload=snapshot.markets_payload,
        source_url=snapshot.source_url,
        is_soccer=snapshot.is_soccer,
        extracted_at=snapshot.extracted_at,
        raw_payload=snapshot.raw_payload,
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


def _markets_payload_from_game(game: dict[str, Any], *, home: str, away: str) -> dict[str, Any] | None:
    ev = game.get("ev") if isinstance(game.get("ev"), dict) else {}
    markets_payload: dict[str, Any] = {}
    asian_handicap = _asian_handicap(ev, home=home, away=away)
    if asian_handicap is not None:
        markets_payload["asian_handicap"] = asian_handicap
    goal_line = _goal_line(ev)
    if goal_line is not None:
        markets_payload["goal_line"] = goal_line
    return markets_payload or None


def _live_markets_payload(raw_rows: Any, *, home: str, away: str) -> dict[str, Any] | None:
    rows = [row for row in raw_rows or [] if isinstance(row, dict)]
    if not rows:
        return None
    payload: dict[str, Any] = {}
    goal_line = _goal_line_from_live_rows(rows)
    if goal_line is not None:
        payload["goal_line"] = goal_line
    asian_handicap = _asian_handicap_from_live_rows(rows, home=home, away=away)
    if asian_handicap is not None:
        payload["asian_handicap"] = asian_handicap
    return payload or None


def _odds_1x2_from_live_rows(raw_rows: Any) -> Odds1X2:
    rows = [
        row
        for row in raw_rows or []
        if isinstance(row, dict) and _as_int(row.get("mid")) == 602 and row.get("v") is not None
    ]
    by_selection: dict[str, float | None] = {"home": None, "draw": None, "away": None}
    for row in rows:
        key = str(row.get("kname") or row.get("pname") or "").strip().lower()
        posn = _as_int(row.get("posn"))
        value = _as_float(row.get("v"))
        if key in {"1", "home"} or posn == 1:
            by_selection["home"] = value
        elif key in {"x", "draw"} or posn == 2:
            by_selection["draw"] = value
        elif key in {"2", "away"} or posn == 3:
            by_selection["away"] = value
    return Odds1X2(home=by_selection["home"], draw=by_selection["draw"], away=by_selection["away"])


def _goal_line_from_live_rows(rows: list[dict[str, Any]], *, target: float = 2.5) -> dict[str, Any] | None:
    # Observed live soccer totals use mid=603 in the mobile header and
    # kname/pname values "o"/"u" or "over"/"under".
    total_rows = [
        row
        for row in rows
        if _as_int(row.get("mid")) == 603 and row.get("h") is not None and row.get("v") is not None
    ]
    if not total_rows:
        return None
    grouped: dict[float, dict[str, float]] = {}
    for row in total_rows:
        line = _as_float(row.get("h"))
        odds = _as_float(row.get("v"))
        if line is None or odds is None:
            continue
        label = str(row.get("kname") or row.get("pname") or "").lower()
        side = "Over" if label in {"o", "over"} else ("Under" if label in {"u", "under"} else None)
        if side is None:
            continue
        grouped.setdefault(line, {})[side] = odds
    selections: list[dict[str, Any]] = []
    for line in sorted(grouped.keys(), key=lambda value: abs(value - target)):
        label = _format_line(line, show_plus=False)
        for side in ("Over", "Under"):
            if side in grouped[line]:
                selections.append({"selection": side, "line": label, "odds": grouped[line][side]})
    if not selections:
        return None
    return {"market_id": "mystake_live_goal_line", "market_name": "Goal Line", "selections": selections}


def _asian_handicap_from_live_rows(rows: list[dict[str, Any]], *, home: str, away: str) -> dict[str, Any] | None:
    # Main in-play handicap rows observed in Mystake use mid=625/627 with
    # kname "1"/"2". Keep the closest-to-zero lines first, like prematch.
    handicap_rows = [
        row
        for row in rows
        if _as_int(row.get("mid")) in {625, 627} and row.get("h") is not None and row.get("v") is not None
    ]
    if not handicap_rows:
        return None
    selections: list[dict[str, Any]] = []
    for wanted_key, label in (("1", home), ("2", away)):
        side_rows: list[tuple[float, float]] = []
        for row in handicap_rows:
            key = str(row.get("kname") or row.get("pname") or "").strip().lower()
            if key != wanted_key:
                continue
            line = _as_float(row.get("h"))
            odds = _as_float(row.get("v"))
            if line is not None and odds is not None:
                side_rows.append((line, odds))
        for line, odds in sorted(side_rows, key=lambda item: abs(item[0]))[:3]:
            selections.append({"selection": label, "line": _format_line(line), "odds": odds})
    if not selections:
        return None
    return {"market_id": "mystake_live_asian_handicap", "market_name": "Asian Handicap", "selections": selections}


def _kickoff_iso(raw_value: Any) -> str | None:
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _looks_live(game: dict[str, Any]) -> bool:
    # ``sti`` is a start timestamp in some Mystake payloads, not a live state.
    for key in ("s", "status", "Status", "liveStatus", "LiveBetStatus", "MatchStatusID", "EventStatus"):
        value = game.get(key)
        if value not in (None, "", 0, "0", False):
            return True
    return _score_pair(game) != (None, None) or _minute_label(game) is not None


def _score_pair(game: dict[str, Any]) -> tuple[int | None, int | None]:
    for key in ("score", "sc", "Score", "SC"):
        value = game.get(key)
        if isinstance(value, dict):
            home = _as_int(_first_present(value, ("home", "h", "S1", "Home")))
            away = _as_int(_first_present(value, ("away", "a", "S2", "Away")))
            if home is not None or away is not None:
                return home, away
        if isinstance(value, list) and len(value) >= 2:
            return _as_int(value[0]), _as_int(value[1])
        if isinstance(value, str) and ":" in value:
            left, right = value.split(":", 1)
            return _as_int(left.strip()), _as_int(right.strip())
    return _as_int(_first_present(game, ("hs", "homeScore"))), _as_int(_first_present(game, ("as", "awayScore")))


def _minute_label(game: dict[str, Any]) -> str | None:
    for key in ("minute", "min", "time", "timer", "clock", "liveTime", "lt", "MatchTime", "MatchTimeExtended", "mt"):
        value = game.get(key)
        if value not in (None, ""):
            return _format_minute_label(value)
    return None


def _card_count(game: dict[str, Any], *, side: str, color: str) -> int | None:
    side_keys = ("home", "h", "1") if side == "home" else ("away", "a", "2")
    color_keys = ("red", "reds", "rc", "redCards") if color == "red" else ("yellow", "yellows", "yc", "yellowCards")
    cards = game.get("cards") or game.get("Cards")
    if isinstance(cards, dict):
        for side_key in side_keys:
            side_payload = cards.get(side_key)
            if isinstance(side_payload, dict):
                for color_key in color_keys:
                    value = _as_int(side_payload.get(color_key))
                    if value is not None:
                        return value
            else:
                value = _as_int(side_payload)
                if value is not None and color == "red":
                    return value
    prefixes = ("hr", "homeRed") if side == "home" and color == "red" else (
        ("ar", "awayRed") if side == "away" and color == "red" else (
            ("hy", "homeYellow") if side == "home" else ("ay", "awayYellow")
        )
    )
    for key in prefixes:
        value = _as_int(game.get(key))
        if value is not None:
            return value
    direct_keys = {
        ("home", "red"): ("rct1", "RedCardsTeam1", "redCardsTeam1"),
        ("away", "red"): ("rct2", "RedCardsTeam2", "redCardsTeam2"),
        ("home", "yellow"): ("YellowCardsTeam1", "yellowCardsTeam1"),
        ("away", "yellow"): ("YellowCardsTeam2", "yellowCardsTeam2"),
    }
    for key in direct_keys.get((side, color), ()):
        value = _as_int(game.get(key))
        if value is not None:
            return value
    return None


def _name_map(raw_items: Any) -> dict[Any, str]:
    names: dict[Any, str] = {}
    if not isinstance(raw_items, list):
        return names
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        item_id = _first_present(item, ("ID", "Id", "id"))
        name = _first_present(item, ("Name", "N", "name"))
        if item_id is not None and name:
            names[item_id] = str(name)
            names[str(item_id)] = str(name)
    return names


def _format_minute_label(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return text
    if text.endswith("'"):
        return text
    if ":" in text:
        minute = text.split(":", 1)[0].strip()
        return f"{minute}'" if minute.isdigit() else text
    return f"{text}'" if text.isdigit() else text


def _looks_virtual_soccer(
    *,
    competition_name: str | None,
    country_name: str | None,
    home: str,
    away: str,
) -> bool:
    joined = " ".join(part for part in (competition_name, country_name, home, away) if part)
    return bool(_VIRTUAL_SOCCER_RE.search(joined))


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None

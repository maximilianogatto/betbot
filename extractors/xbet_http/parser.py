"""Defensive parsers for 1xBet-compatible LineFeed responses."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import re

from core.extractor_base import CompetitionUnavailableError
from core.models import (
    CompetitionExtraction,
    CompetitionKey,
    EventKey,
    EventSnapshot,
    LiveEventSnapshot,
    Odds1X2,
)
from core.models import utc_now_iso
from extractors.xbet_http.models import XBetFixture, XBetLeagueSnapshot

PLATFORM = "1xbet_http"
ONE_X_TWO_TYPES = {1: "home", 2: "draw", 3: "away"}
HANDICAP_HOME_TYPE = 7
HANDICAP_AWAY_TYPE = 8
TOTAL_OVER_TYPE = 9
TOTAL_UNDER_TYPE = 10

# Virtual / simulated "football" leagues to exclude from real-soccer live detection.
_VIRTUAL_LEAGUE_RE = re.compile(
    r"(short football|f[uú]tbol corto|cyber|\bfifa\b|volta|\blfl\b|e-?football|esoccer|"
    r"student league|\d+x\d+|daily league|battle)",
    re.IGNORECASE,
)


def live_events_from_1x2_vzip(payload: dict[str, Any]) -> list[LiveEventSnapshot]:
    """Map a LiveFeed Get1x2_VZip response to in-play soccer live snapshots."""

    live: list[LiveEventSnapshot] = []
    for event in payload.get("Value") or []:
        if not isinstance(event, dict):
            continue
        home = str(event.get("O1") or "").strip()
        away = str(event.get("O2") or "").strip()
        event_id = event.get("I")
        if not home or not away or event_id is None:
            continue

        sc = event.get("SC") if isinstance(event.get("SC"), dict) else {}
        status_text = str(sc.get("I") or "")
        sls = str(sc.get("SLS") or "")
        # Skip events that are in the live feed but have not actually kicked off.
        if status_text == "Apuestas prepartido" or sls.lower().startswith("comienza"):
            continue

        full_score = sc.get("FS") if isinstance(sc.get("FS"), dict) else {}
        league = event.get("L") or event.get("LE")
        odds_1x2, _ = _extract_markets(event, home=home, away=away)
        league_id = event.get("LI") or event.get("CI")
        country_name = event.get("CN")
        comp_name = f"{country_name} · {league}" if country_name and league and country_name.lower() not in league.lower() else league

        live.append(
            LiveEventSnapshot(
                platform=PLATFORM,
                external_event_id=str(event_id),
                home=home,
                away=away,
                competition_name=comp_name,
                country_name=country_name,
                minute=sls or status_text or None,
                home_score=_coerce_int(full_score.get("S1")),
                away_score=_coerce_int(full_score.get("S2")),
                home_red_cards=_extract_card_value(sc, side=1, color="red"),
                away_red_cards=_extract_card_value(sc, side=2, color="red"),
                home_yellow_cards=_extract_card_value(sc, side=1, color="yellow"),
                away_yellow_cards=_extract_card_value(sc, side=2, color="yellow"),
                odds_1x2=odds_1x2,
                source_url=f"https://spinbetter.com/service-api/LineFeed/GetGameZip?id={event_id}",
                is_soccer=not bool(_VIRTUAL_LEAGUE_RE.search(str(league or ""))),
                extracted_at=utc_now_iso(),
                raw_payload={
                    "sport_id": event.get("SI"),
                    "current_period": sc.get("CP"),
                    "league_id": _safe_str(league_id) if league_id is not None else None,
                },
            )
        )
    return live


def live_events_from_champ_zip(payload: dict[str, Any]) -> list[LiveEventSnapshot]:
    """Map a LiveFeed GetChampZip response (single league) to in-play soccer live snapshots."""

    value = payload.get("Value")
    if not isinstance(value, dict):
        return []

    league_name = value.get("L")
    country_name = value.get("CN")
    sport_id = _safe_str(value.get("SI"))

    events = []
    for g in value.get("G") or []:
        if not isinstance(g, dict):
            continue
        event = dict(g)
        if "L" not in event and league_name:
            event["L"] = league_name
        if "CN" not in event and country_name:
            event["CN"] = country_name
        if "SI" not in event and sport_id:
            event["SI"] = sport_id
        if "LI" not in event and value.get("LI"):
            event["LI"] = value.get("LI")
        events.append(event)

    return live_events_from_1x2_vzip({"Value": events})


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_card_value(sc: dict[str, Any], *, side: int, color: str) -> int | None:
    """Best-effort card extraction from observed 1xBet live score payloads."""

    prefixes = ("RC", "R", "Red", "RED") if color == "red" else ("YC", "Y", "Yellow", "YELLOW")
    for prefix in prefixes:
        for key in (f"{prefix}{side}", f"{prefix}_{side}", f"{prefix}S{side}"):
            value = _coerce_int(sc.get(key))
            if value is not None:
                return value

    cards = sc.get("Cards") or sc.get("cards")
    if isinstance(cards, dict):
        side_keys = (f"S{side}", str(side), "home" if side == 1 else "away")
        color_keys = ("red", "reds", "RC") if color == "red" else ("yellow", "yellows", "YC")
        for side_key in side_keys:
            side_payload = cards.get(side_key)
            if isinstance(side_payload, dict):
                for color_key in color_keys:
                    value = _coerce_int(side_payload.get(color_key))
                    if value is not None:
                        return value
    return None


def parse_champ_zip_payload(
    payload: dict[str, Any],
    *,
    source_url: str,
    event_url_builder: Callable[[str], str | None] | None = None,
) -> CompetitionExtraction:
    """Parse `GetChampZip` into the bot's generic competition model."""

    snapshot = parse_champ_zip_snapshot(payload, source_url=source_url)
    competition_key = CompetitionKey(
        platform=snapshot.platform,
        competition_external_id=snapshot.league_id,
    )
    events = [
        _fixture_to_event_snapshot(
            fixture,
            snapshot=snapshot,
            event_url_builder=event_url_builder,
        )
        for fixture in snapshot.fixtures
    ]

    return CompetitionExtraction(
        competition=competition_key,
        competition_name=snapshot.league_name,
        source_url=snapshot.source_url,
        events=events,
        is_empty=not events,
        is_provisional_name=False,
        extracted_at=snapshot.extracted_at,
        metadata={
            "sport_id": snapshot.sport_id,
            "country": snapshot.country,
            "source": "GetChampZip",
        },
        raw_payload=snapshot.raw_payload,
    )


def parse_champ_zip_snapshot(payload: dict[str, Any], *, source_url: str) -> XBetLeagueSnapshot:
    if payload.get("Success") is False:
        raise CompetitionUnavailableError(
            str(payload.get("Error") or "1xBet GetChampZip returned Success=false."),
            platform=PLATFORM,
            source_url=source_url,
            reason_code="competition_unavailable",
            details={"error_code": payload.get("ErrorCode")},
        )

    value = payload.get("Value")
    if not isinstance(value, dict):
        raise CompetitionUnavailableError(
            "1xBet GetChampZip response did not include a league object.",
            platform=PLATFORM,
            source_url=source_url,
            reason_code="competition_unavailable",
        )

    league_id = _safe_str(value.get("LI"))
    league_name = _safe_str(value.get("L"))
    if league_id is None:
        raise CompetitionUnavailableError(
            "1xBet GetChampZip response did not include LI.",
            platform=PLATFORM,
            source_url=source_url,
            reason_code="competition_unavailable",
        )

    extracted_at = utc_now_iso()
    fixtures = [
        fixture
        for raw_game in value.get("G") or []
        for fixture in [_parse_fixture(raw_game, fallback_country=value.get("CN"))]
        if fixture is not None
    ]

    country_name = _safe_str(value.get("CN"))
    l_name = league_name or f"1xBet liga {league_id}"
    if country_name and country_name.lower() not in l_name.lower():
        l_name = f"{country_name} · {l_name}"

    return XBetLeagueSnapshot(
        platform=PLATFORM,
        source_url=source_url,
        league_id=league_id,
        league_name=l_name,
        sport_id=_safe_str(value.get("SI")),
        country=country_name,
        extracted_at=extracted_at,
        fixtures=fixtures,
        raw_payload={
            "source": "GetChampZip",
            "league_id": league_id,
            "league_name": league_name,
            "sport_id": _safe_str(value.get("SI")),
            "country": _safe_str(value.get("CN")),
            "events_count": len(fixtures),
        },
    )


def enrich_event_snapshot_with_game_detail(
    event: EventSnapshot,
    payload: dict[str, Any],
) -> EventSnapshot:
    """Merge GetGameZip market detail into an already parsed fixture snapshot."""

    detail = _unwrap_value_dict(payload)
    raw_market_count = _raw_market_count(detail) if detail is not None else 0
    raw_payload = {
        **event.raw_payload,
        "game_detail_source": "GetGameZip",
        "game_detail_raw_market_count": raw_market_count,
    }

    if detail is None:
        return replace(event, raw_payload=raw_payload)

    odds_1x2, markets_payload = _extract_markets(detail, home=event.home, away=event.away)
    if markets_payload is None and not any(
        value is not None for value in (odds_1x2.home, odds_1x2.draw, odds_1x2.away)
    ):
        return replace(event, raw_payload=raw_payload)

    merged_markets = _merge_markets_payload(event.markets_payload, markets_payload)
    merged_odds = Odds1X2(
        home=odds_1x2.home if odds_1x2.home is not None else event.odds_1x2.home,
        draw=odds_1x2.draw if odds_1x2.draw is not None else event.odds_1x2.draw,
        away=odds_1x2.away if odds_1x2.away is not None else event.odds_1x2.away,
    )
    metadata = {
        **event.metadata,
        "game_detail_event_id": (
            _safe_str(detail.get("I")) or event.metadata.get("game_detail_event_id")
        ),
    }

    return replace(
        event,
        odds_1x2=merged_odds,
        markets_payload=merged_markets,
        metadata=metadata,
        raw_payload=raw_payload,
    )


def _parse_fixture(raw_game: object, *, fallback_country: object | None) -> XBetFixture | None:
    if not isinstance(raw_game, dict):
        return None

    event_id = _safe_str(raw_game.get("I"))
    home = _safe_str(raw_game.get("O1"))
    away = _safe_str(raw_game.get("O2"))
    if event_id is None or home is None or away is None:
        return None

    start_time_unix, start_time_utc, label_date, label_time = _parse_start_time(raw_game.get("S"))
    odds_1x2, markets_payload = _extract_markets(raw_game, home=home, away=away)
    raw_payload = {
        "event_id": event_id,
        "game_code": _safe_str(raw_game.get("N")),
        "competition_id": _safe_str(raw_game.get("CI")),
        "home_id": _safe_str(raw_game.get("O1I")),
        "away_id": _safe_str(raw_game.get("O2I")),
        "country": _safe_str(raw_game.get("CE") or fallback_country),
        "source": "GetChampZip",
        "raw_market_count": _raw_market_count(raw_game),
    }

    return XBetFixture(
        event_id=event_id,
        home=home,
        away=away,
        start_time_unix=start_time_unix,
        start_time_utc=start_time_utc,
        label_date=label_date,
        label_time=label_time,
        home_id=_safe_str(raw_game.get("O1I")),
        away_id=_safe_str(raw_game.get("O2I")),
        odds_home=odds_1x2.home,
        odds_draw=odds_1x2.draw,
        odds_away=odds_1x2.away,
        markets_payload=markets_payload,
        raw_payload=raw_payload,
    )


def _fixture_to_event_snapshot(
    fixture: XBetFixture,
    *,
    snapshot: XBetLeagueSnapshot,
    event_url_builder: Callable[[str], str | None] | None,
) -> EventSnapshot:
    event_url = event_url_builder(fixture.event_id) if event_url_builder is not None else None
    raw_payload = {
        **fixture.raw_payload,
        "league_id": snapshot.league_id,
        "league_name": snapshot.league_name,
        "sport_id": snapshot.sport_id,
        "country": snapshot.country or fixture.raw_payload.get("country"),
    }

    return EventSnapshot(
        key=EventKey(
            platform=snapshot.platform,
            competition_external_id=snapshot.league_id,
            external_event_id=fixture.event_id,
        ),
        competition_name=snapshot.league_name,
        home=fixture.home,
        away=fixture.away,
        scheduled_label_date=fixture.label_date,
        scheduled_label_time=fixture.label_time,
        scheduled_at=fixture.start_time_utc,
        source_url=event_url,
        odds_1x2=Odds1X2(
            home=fixture.odds_home,
            draw=fixture.odds_draw,
            away=fixture.odds_away,
        ),
        extracted_at=snapshot.extracted_at,
        markets_payload=fixture.markets_payload,
        metadata={
            "home_id": fixture.home_id,
            "away_id": fixture.away_id,
        },
        raw_payload=raw_payload,
    )


def _parse_start_time(value: object | None) -> tuple[int | None, str | None, str | None, str | None]:
    if value in (None, ""):
        return None, None, None, None

    try:
        start_time_unix = int(float(str(value)))
    except (TypeError, ValueError):
        return None, None, None, None

    kickoff = datetime.fromtimestamp(start_time_unix, tz=UTC)
    return (
        start_time_unix,
        kickoff.isoformat(),
        kickoff.date().isoformat(),
        kickoff.strftime("%H:%M"),
    )


def _extract_markets(raw_game: dict[str, Any], *, home: str, away: str) -> tuple[Odds1X2, dict[str, Any] | None]:
    outcomes = raw_game.get("E")
    if not isinstance(outcomes, list):
        return Odds1X2(home=None, draw=None, away=None), None

    one_x_two = _extract_1x2(outcomes)
    asian_handicap = _extract_asian_handicap(outcomes, home=home, away=away)
    goal_line = _extract_goal_line(outcomes)
    btts = _extract_both_teams_to_score(outcomes)
    markets_payload: dict[str, Any] = {}

    if any(value is not None for value in (one_x_two.home, one_x_two.draw, one_x_two.away)):
        markets_payload["1x2"] = {
            "home": one_x_two.home,
            "draw": one_x_two.draw,
            "away": one_x_two.away,
        }
    if asian_handicap is not None:
        markets_payload["asian_handicap"] = asian_handicap
    if goal_line is not None:
        markets_payload["goal_line"] = goal_line
    if btts is not None:
        markets_payload["both_teams_to_score"] = btts

    return one_x_two, markets_payload or None


def _extract_both_teams_to_score(outcomes: list[object]) -> dict[str, Any] | None:
    yes_odds = None
    no_odds = None
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        outcome_type = outcome.get("T")
        if outcome_type == 180:
            yes_odds = _coerce_float(outcome.get("C"))
        elif outcome_type == 181:
            no_odds = _coerce_float(outcome.get("C"))

    if yes_odds is not None or no_odds is not None:
        selections = []
        if yes_odds is not None:
            selections.append({"selection": "Yes", "odds": yes_odds})
        if no_odds is not None:
            selections.append({"selection": "No", "odds": no_odds})
        return {
            "market_id": "1xbet_both_teams_to_score",
            "market_name": "Both Teams to Score",
            "selections": selections,
        }
    return None



def _merge_markets_payload(
    current: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not current:
        return incoming
    if not incoming:
        return current

    merged = dict(current)
    merged.update(incoming)
    return merged


def _extract_1x2(outcomes: list[object]) -> Odds1X2:
    values: dict[str, float | None] = {"home": None, "draw": None, "away": None}

    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        outcome_type = outcome.get("T")
        market_key = ONE_X_TWO_TYPES.get(outcome_type)
        if market_key is None:
            continue
        values[market_key] = _coerce_float(outcome.get("C"))

    return Odds1X2(
        home=values["home"],
        draw=values["draw"],
        away=values["away"],
    )


def _extract_asian_handicap(
    outcomes: list[object],
    *,
    home: str,
    away: str,
) -> dict[str, Any] | None:
    grouped: dict[tuple[float, str], dict[str, Any]] = {}

    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        outcome_type = outcome.get("T")
        if outcome_type not in {HANDICAP_HOME_TYPE, HANDICAP_AWAY_TYPE}:
            continue
        raw_line = _coerce_float(outcome.get("P"))
        if raw_line is None and outcome.get("CE") == 1:
            raw_line = 0.0
        if raw_line is None:
            continue
        normalized_line = -raw_line if outcome_type == HANDICAP_AWAY_TYPE else raw_line
        group = _safe_str(outcome.get("G")) or "handicap"
        record = grouped.setdefault(
            (normalized_line, group),
            {
                "line": normalized_line,
                "group": group,
                "home": None,
                "away": None,
            },
        )
        odds = _coerce_float(outcome.get("C"))
        if outcome_type == HANDICAP_HOME_TYPE:
            record["home"] = odds
        else:
            record["away"] = odds

    selections: list[dict[str, Any]] = []
    for record in sorted(grouped.values(), key=lambda item: (abs(float(item["line"])), float(item["line"]))):
        line = float(record["line"])
        if record.get("home") is not None:
            selections.append({"selection": home, "line": _format_line(line), "odds": record["home"]})
        if record.get("away") is not None:
            selections.append({"selection": away, "line": _format_line(-line), "odds": record["away"]})

    if not selections:
        return None

    return {
        "market_id": "1xbet_asian_handicap",
        "market_name": "Asian Handicap",
        "selections": selections,
    }


def _extract_goal_line(outcomes: list[object]) -> dict[str, Any] | None:
    grouped: dict[tuple[float, str], dict[str, Any]] = {}

    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        outcome_type = outcome.get("T")
        if outcome_type not in {TOTAL_OVER_TYPE, TOTAL_UNDER_TYPE}:
            continue
        line = _coerce_float(outcome.get("P"))
        if line is None and outcome.get("CE") == 1:
            line = 0.0
        if line is None:
            continue
        group = _safe_str(outcome.get("G")) or "total"
        record = grouped.setdefault(
            (line, group),
            {
                "line": line,
                "group": group,
                "over": None,
                "under": None,
            },
        )
        odds = _coerce_float(outcome.get("C"))
        if outcome_type == TOTAL_OVER_TYPE:
            record["over"] = odds
        else:
            record["under"] = odds

    selections: list[dict[str, Any]] = []
    for record in sorted(grouped.values(), key=lambda item: (abs(float(item["line"]) - 2.5), float(item["line"]))):
        line = _format_line(float(record["line"]), show_plus=False)
        if record.get("over") is not None:
            selections.append({"selection": "Over", "line": line, "odds": record["over"]})
        if record.get("under") is not None:
            selections.append({"selection": "Under", "line": line, "odds": record["under"]})

    if not selections:
        return None

    return {
        "market_id": "1xbet_goal_line",
        "market_name": "Goal Line",
        "selections": selections,
    }


def _raw_market_count(raw_game: dict[str, Any]) -> int:
    outcomes = raw_game.get("E")
    return len(outcomes) if isinstance(outcomes, list) else 0


def _unwrap_value_dict(payload: dict[str, Any]) -> dict[str, Any] | None:
    value = payload.get("Value")
    if isinstance(value, dict):
        return value
    if isinstance(payload, dict) and isinstance(payload.get("E"), list):
        return payload
    return None


def _coerce_float(value: object | None) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _format_line(value: float, *, show_plus: bool = True) -> str:
    if value > 0 and show_plus:
        sign = "+"
    else:
        sign = ""

    if value.is_integer():
        return f"{sign}{int(value)}"
    return f"{sign}{value:g}"


def _safe_str(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None

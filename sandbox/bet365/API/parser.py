from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from models import Event, Market, Selection


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def is_blank(value: str | None) -> bool:
    return clean_text(value) is None


def parse_record(record: str) -> tuple[str, dict[str, str]] | None:
    candidate = record.strip()
    if not candidate or candidate == "F" or candidate == "\x08F":
        return None

    parts = candidate.split(";")
    record_type = parts[0].strip()
    if not record_type:
        return None

    fields: dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", maxsplit=1)
        fields[key] = value
    return record_type, fields


def extract_topic_from_value(raw: str | None) -> str | None:
    if not raw:
        return None
    stripped = raw.strip()
    if stripped.startswith("#AC#"):
        return stripped
    match = re.search(r"(#AC#[^;|]+?#)", stripped)
    if match:
        return match.group(1)
    return None


def extract_competition_name_from_tb(raw: str | None) -> str | None:
    if not raw or "¬" not in raw:
        return None
    parts = raw.split("¬")
    if len(parts) < 2:
        return None
    return clean_text(parts[1].split(",", maxsplit=1)[0])


def extract_event_id_from_topic(topic: str | None) -> str | None:
    if not topic:
        return None
    match = re.search(r"#E(\d+)#", topic)
    if match:
        return match.group(1)
    return None


def build_event_token(event_id: str | None, topic: str | None = None) -> str | None:
    if event_id:
        return f"E{event_id}"
    extracted = extract_event_id_from_topic(topic)
    if extracted:
        return f"E{extracted}"
    return None


def extract_sportradar_url(raw: str | None) -> str | None:
    if not raw:
        return None
    for part in raw.split("~"):
        part = part.strip()
        if part.startswith("http://") or part.startswith("https://"):
            return part
    match = re.search(r"https?://[^\s~;]+", raw)
    if match:
        return match.group(0)
    return None


def build_event_url(event_pd: str | None, *, host: str) -> str | None:
    if not event_pd:
        return None
    stripped = event_pd.strip().strip("#")
    if not stripped:
        return None
    return f"https://{host}/#/{stripped.replace('#', '/')}/"


def fractional_to_decimal(raw: str | None) -> float | None:
    candidate = clean_text(raw)
    if not candidate:
        return None
    if "/" not in candidate:
        try:
            return round(float(candidate), 3)
        except ValueError:
            return None
    left, right = candidate.split("/", maxsplit=1)
    try:
        return round(float(left) / float(right) + 1, 3)
    except (ValueError, ZeroDivisionError):
        return None


def odds_to_decimal(fields: dict[str, str]) -> float | None:
    raw_do = clean_text(fields.get("DO"))
    if raw_do:
        try:
            return round(float(raw_do), 3)
        except ValueError:
            pass
    return fractional_to_decimal(fields.get("OD"))


def normalize_line(raw: str | None) -> str | None:
    value = clean_text(raw)
    if value is None:
        return None
    normalized = value.replace("+", "")
    if normalized in {"-0", "0", "0.0", "-0.0"}:
        return "0.0"
    return normalized


def looks_like_markets_payload(text: str) -> bool:
    return (
        "|EV;" in text
        and "|MG;ID=40" in text
        and "|MA;" in text
        and "|PA;" in text
        and "matchmarketscontentapi" in text
    )


def looks_like_coupon_payload(text: str) -> bool:
    return (
        "|EV;" in text
        and "|MG;" in text
        and "|MA;" in text
        and "|PA;" in text
        and "matchbettingcontentapi" in text
    )


def detect_payload_kind(text: str) -> str:
    if looks_like_coupon_payload(text):
        return "coupon"
    if looks_like_markets_payload(text):
        return "markets"
    return "unknown"


def parse_markets_payload_text(text: str, *, host: str = "www.bet365.es") -> dict[str, Any]:
    competition_topic: str | None = None
    competition_name_lmab: str | None = None
    competition_name_ev_l3: str | None = None
    competition_name_ev_tb: str | None = None
    current_market_group_id: str | None = None
    current_market_name: str | None = None
    record_counts: Counter[str] = Counter()
    league_lt: str | None = None
    league_market_catalog: list[dict[str, str | None]] = []

    fixtures: dict[str, dict[str, Any]] = {}

    for raw_record in text.split("|"):
        parsed_record = parse_record(raw_record)
        if parsed_record is None:
            continue
        record_type, fields = parsed_record
        record_counts[record_type] += 1

        if record_type == "CL":
            competition_topic = competition_topic or extract_topic_from_value(fields.get("IT"))
            continue

        if record_type == "EV":
            competition_name_ev_l3 = competition_name_ev_l3 or clean_text(fields.get("L3"))
            competition_name_ev_tb = competition_name_ev_tb or extract_competition_name_from_tb(fields.get("TB"))
            competition_topic = competition_topic or extract_topic_from_value(fields.get("IT"))
            league_lt = league_lt or clean_text(fields.get("LT"))
            continue

        if record_type == "MG":
            if clean_text(fields.get("ID")) == "LMAB":
                competition_name_lmab = competition_name_lmab or clean_text(fields.get("CC"))
            current_market_group_id = clean_text(fields.get("ID"))
            current_market_name = None
            continue

        if record_type == "MA":
            current_market_name = fields.get("NA")
            competition_topic = competition_topic or extract_topic_from_value(fields.get("PD"))
            market_name = clean_text(fields.get("NA"))
            market_pd = clean_text(fields.get("PD"))
            market_it = clean_text(fields.get("IT"))
            if market_name or market_pd or market_it:
                league_market_catalog.append(
                    {
                        "group_id": current_market_group_id,
                        "name": market_name,
                        "pd": market_pd,
                        "it": market_it,
                    }
                )
            continue

        if record_type != "PA" or current_market_group_id != "40":
            continue

        fixture_id = clean_text(fields.get("FI") or fields.get("OI"))
        if not fixture_id:
            continue

        fixture = fixtures.setdefault(
            fixture_id,
            {
                "fixture_id": fixture_id,
                "home": None,
                "away": None,
                "start_raw": None,
                "event_token": None,
                "event_it": None,
                "event_pd": None,
                "event_url": None,
                "sportradar_url": None,
                "stats_identifier": None,
                "source_meta": {},
                "odds_1x2": {"1": None, "X": None, "2": None},
                "odds_1x2_fractional": {"1": None, "X": None, "2": None},
            },
        )

        if is_blank(current_market_name):
            if clean_text(fields.get("NA")) and clean_text(fields.get("N2")):
                fixture["home"] = clean_text(fields.get("NA"))
                fixture["away"] = clean_text(fields.get("N2"))
                fixture["name"] = clean_text(fields.get("FD")) or (
                    f"{fixture['home']} v {fixture['away']}"
                    if fixture["home"] and fixture["away"]
                    else None
                )
                fixture["start_raw"] = fixture["start_raw"] or clean_text(fields.get("BC"))
                fixture["event_it"] = fixture["event_it"] or clean_text(fields.get("IT"))
                fixture["event_pd"] = fixture["event_pd"] or clean_text(fields.get("PD"))
                fixture["event_token"] = fixture["event_token"] or build_event_token(
                    fixture_id,
                    fixture["event_pd"],
                )
                fixture["event_url"] = fixture["event_url"] or build_event_url(
                    fixture["event_pd"], host=host
                )
                fixture["sportradar_url"] = fixture["sportradar_url"] or extract_sportradar_url(
                    fields.get("EX")
                )
                fixture["stats_identifier"] = fixture["stats_identifier"] or clean_text(
                    fields.get("LI")
                )
                fixture["source_meta"] = {
                    "league_lt": league_lt,
                    "stats_link": fixture["sportradar_url"],
                    "li": clean_text(fields.get("LI")),
                    "lt": clean_text(fields.get("LT")),
                    "ce": clean_text(fields.get("CE")),
                    "lp": clean_text(fields.get("LP")),
                    "oi": clean_text(fields.get("OI")),
                    "ht": clean_text(fields.get("HT")),
                    "at": clean_text(fields.get("AT")),
                    "ki": clean_text(fields.get("KI")),
                    "k1": clean_text(fields.get("K1")),
                    "k2": clean_text(fields.get("K2")),
                }
            continue

        participant_code = clean_text(current_market_name)
        if participant_code not in {"1", "X", "2"}:
            continue
        fixture["odds_1x2_fractional"][participant_code] = clean_text(fields.get("OD"))
        fixture["odds_1x2"][participant_code] = odds_to_decimal(fields)

    competition_name = (
        competition_name_lmab
        or competition_name_ev_l3
        or competition_name_ev_tb
    )

    events: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []

    for fixture_id, fixture in sorted(fixtures.items(), key=lambda item: item[0]):
        home = fixture.get("home")
        away = fixture.get("away")
        odds = fixture["odds_1x2"]
        odds_fractional = fixture["odds_1x2_fractional"]
        event_pd = fixture.get("event_pd")
        event = Event(
            event_id=fixture_id,
            fixture_id=fixture_id,
            topic=event_pd,
            competition_name=competition_name,
            name=fixture.get("name") or (f"{home} v {away}" if home and away else None),
            home=home,
            away=away,
            start_raw=fixture.get("start_raw"),
            event_token=fixture.get("event_token"),
            event_it=fixture.get("event_it"),
            event_pd=event_pd,
            event_url=fixture.get("event_url"),
            sportradar_url=fixture.get("sportradar_url"),
            stats_identifier=fixture.get("stats_identifier"),
            source_meta=fixture.get("source_meta") or {},
            markets=[
                Market(
                    market_id="40",
                    name="Full Time Result",
                    selections=[
                        Selection(
                            selection_id=f"{fixture_id}-1",
                            name=home or "1",
                            odds_fractional=odds_fractional.get("1"),
                            odds_decimal=odds.get("1"),
                            participant_code="1",
                        ),
                        Selection(
                            selection_id=f"{fixture_id}-X",
                            name="Draw",
                            odds_fractional=odds_fractional.get("X"),
                            odds_decimal=odds.get("X"),
                            participant_code="X",
                        ),
                        Selection(
                            selection_id=f"{fixture_id}-2",
                            name=away or "2",
                            odds_fractional=odds_fractional.get("2"),
                            odds_decimal=odds.get("2"),
                            participant_code="2",
                        ),
                    ],
                )
            ],
        )
        events.append(event.to_dict())
        matches.append(
            {
                "fixture_id": fixture_id,
                "home": home,
                "away": away,
                "start_raw": fixture.get("start_raw"),
                "event_token": fixture.get("event_token"),
                "event_it": fixture.get("event_it"),
                "event_pd": event_pd,
                "event_url": fixture.get("event_url"),
                "sportradar_url": fixture.get("sportradar_url"),
                "stats_identifier": fixture.get("stats_identifier"),
                "source_meta": fixture.get("source_meta") or {},
                "odds_1x2": odds,
                "odds_1x2_fractional": odds_fractional,
            }
        )

    return {
        "payload_type": "markets",
        "competition": {
            "name": competition_name,
            "topic": competition_topic,
        },
        "events": events,
        "matches": matches,
        "league_market_catalog": league_market_catalog,
        "record_counts": dict(record_counts),
    }


def build_coupon_selection_name(
    *,
    market_id: str | None,
    market_name: str | None,
    current_ma_name: str | None,
    fields: dict[str, str],
    current_line: str | None,
) -> tuple[str | None, str | None]:
    ma_name = clean_text(current_ma_name)
    pa_name = clean_text(fields.get("NA"))

    if market_id == "40":
        return pa_name or ma_name, None

    if market_id == "981":
        if ma_name in {"Over", "Under"}:
            if current_line:
                return f"{ma_name} {current_line}", current_line
            return ma_name, None
        return pa_name or ma_name, current_line

    if market_id == "10150":
        return pa_name or ma_name, None

    if pa_name:
        return pa_name, current_line
    return ma_name, current_line


def parse_coupon_payload_text(text: str, *, host: str = "www.bet365.es") -> dict[str, Any]:
    competition_name: str | None = None
    topic: str | None = None
    current_market_id: str | None = None
    current_market_name: str | None = None
    current_market: Market | None = None
    current_ma_name: str | None = None
    current_line: str | None = None
    record_counts: Counter[str] = Counter()
    co_records: list[dict[str, Any]] = []
    event_tb: str | None = None
    event_lt: str | None = None

    event = Event(
        event_id=None,
        fixture_id=None,
        topic=None,
        competition_name=None,
        name=None,
        home=None,
        away=None,
        start_raw=None,
    )
    markets_by_id: dict[str, Market] = {}

    for raw_record in text.split("|"):
        parsed_record = parse_record(raw_record)
        if parsed_record is None:
            continue
        record_type, fields = parsed_record
        record_counts[record_type] += 1

        if record_type == "CL":
            topic = topic or extract_topic_from_value(fields.get("IT"))
            competition_name = competition_name or clean_text(fields.get("L3"))
            continue

        if record_type == "EV":
            topic = topic or extract_topic_from_value(fields.get("IT"))
            competition_name = (
                competition_name
                or clean_text(fields.get("CC"))
                or clean_text(fields.get("L3"))
                or extract_competition_name_from_tb(fields.get("TB"))
            )
            event.name = event.name or clean_text(fields.get("EX"))
            event.fixture_id = event.fixture_id or clean_text(fields.get("FI") or fields.get("OI"))
            event.event_id = event.event_id or event.fixture_id or extract_event_id_from_topic(topic)
            event.event_token = event.event_token or build_event_token(event.event_id, topic)
            event.event_it = event.event_it or clean_text(fields.get("IT"))
            event.start_raw = event.start_raw or clean_text(fields.get("BC"))
            event.home = event.home or clean_text(fields.get("N2"))
            event.away = event.away or clean_text(fields.get("N3"))
            event_tb = event_tb or clean_text(fields.get("TB"))
            event_lt = event_lt or clean_text(fields.get("LT"))
            if (not event.home or not event.away) and event.name and " v " in event.name:
                home, away = event.name.split(" v ", maxsplit=1)
                event.home = event.home or clean_text(home)
                event.away = event.away or clean_text(away)
            continue

        if record_type == "MG":
            current_market_id = clean_text(fields.get("ID"))
            current_market_name = clean_text(fields.get("NA"))
            current_ma_name = None
            current_line = None
            if current_market_id:
                current_market = markets_by_id.get(current_market_id)
                if current_market is None:
                    current_market = Market(
                        market_id=current_market_id,
                        name=current_market_name,
                    )
                    markets_by_id[current_market_id] = current_market
                elif current_market_name and not current_market.name:
                    current_market.name = current_market_name
            else:
                current_market = None
            continue

        if record_type == "MA":
            current_ma_name = fields.get("NA")
            continue

        if record_type == "PA":
            if current_market is None:
                continue

            if current_market.market_id == "981" and is_blank(current_ma_name):
                current_line = normalize_line(fields.get("NA"))
                continue

            selection_name, selection_line = build_coupon_selection_name(
                market_id=current_market.market_id,
                market_name=current_market.name,
                current_ma_name=current_ma_name,
                fields=fields,
                current_line=current_line,
            )
            odds_fractional = clean_text(fields.get("OD"))
            odds_decimal = odds_to_decimal(fields)

            if selection_name is None and odds_decimal is None and odds_fractional is None:
                continue

            current_market.selections.append(
                Selection(
                    selection_id=clean_text(fields.get("ID")),
                    name=selection_name,
                    odds_fractional=odds_fractional,
                    odds_decimal=odds_decimal,
                    participant_code=clean_text(fields.get("N2")),
                    line=selection_line,
                    raw_fields=fields,
                )
            )
            continue

        if record_type == "CO":
            co_records.append(
                {
                    "fixture_id": clean_text(fields.get("FI")),
                    "market_id": clean_text(fields.get("MA")),
                    "selection_name": clean_text(fields.get("NA")),
                    "market_name": clean_text(fields.get("MN")),
                    "odds_fractional": clean_text(fields.get("OD")),
                    "odds_decimal": odds_to_decimal(fields),
                }
            )
            continue

    event.topic = topic
    event.event_pd = topic
    event.event_url = build_event_url(topic, host=host)
    event.competition_name = competition_name
    event.source_meta = {
        "tb": event_tb,
        "lt": event_lt,
    }
    event.markets = [
        market for market in markets_by_id.values() if market.selections
    ]

    return {
        "payload_type": "coupon",
        "competition": {
            "name": competition_name,
            "topic": topic,
        },
        "events": [event.to_dict()],
        "co_records": co_records,
        "record_counts": dict(record_counts),
    }


def parse_bet365_payload_text(text: str, *, host: str = "www.bet365.es") -> dict[str, Any]:
    kind = detect_payload_kind(text)
    if kind == "coupon":
        return parse_coupon_payload_text(text, host=host)
    if kind == "markets":
        return parse_markets_payload_text(text, host=host)
    return {
        "payload_type": "unknown",
        "competition": {"name": None, "topic": None},
        "events": [],
        "record_counts": {},
    }


def parse_markets_payload_file(path: str | Path, *, host: str = "www.bet365.es") -> dict[str, Any]:
    return parse_markets_payload_text(Path(path).read_text(encoding="utf-8"), host=host)


def parse_coupon_payload_file(path: str | Path, *, host: str = "www.bet365.es") -> dict[str, Any]:
    return parse_coupon_payload_text(Path(path).read_text(encoding="utf-8"), host=host)


def parse_bet365_payload_file(path: str | Path, *, host: str = "www.bet365.es") -> dict[str, Any]:
    return parse_bet365_payload_text(Path(path).read_text(encoding="utf-8"), host=host)


def flatten_markets(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for event in events:
        for market in event.get("markets") or []:
            flattened.append(
                {
                    "event_id": event.get("event_id"),
                    "fixture_id": event.get("fixture_id"),
                    "event_name": event.get("name"),
                    "competition_name": event.get("competition_name"),
                    "market_id": market.get("market_id"),
                    "market_name": market.get("name"),
                    "selections": market.get("selections") or [],
                }
            )
    return flattened


def build_league_1x2_projection(parsed: dict[str, Any], *, league_url: str) -> dict[str, Any]:
    events_output: list[dict[str, Any]] = []

    for event in parsed.get("events") or []:
        full_time_market = next(
            (
                market
                for market in (event.get("markets") or [])
                if market.get("market_id") == "40" or market.get("name") == "Full Time Result"
            ),
            None,
        )
        if full_time_market is None:
            continue

        selections = full_time_market.get("selections") or []
        selection_by_code = {
            selection.get("participant_code"): selection
            for selection in selections
        }

        home_name = event.get("home")
        away_name = event.get("away")
        full_time_result = []

        for participant_code, fallback_name in (
            ("1", home_name or "1"),
            ("X", "Draw"),
            ("2", away_name or "2"),
        ):
            selection = selection_by_code.get(participant_code) or {}
            odds_value = selection.get("odds_fractional")
            if odds_value is None and selection.get("odds_decimal") is not None:
                odds_value = str(selection.get("odds_decimal"))
            full_time_result.append(
                {
                    "name": selection.get("name") or fallback_name,
                    "odds": odds_value,
                }
            )

        events_output.append(
            {
                "fixture_id": event.get("fixture_id"),
                "event_token": event.get("event_token"),
                "name": event.get("name"),
                "home": home_name,
                "away": away_name,
                "start_raw": event.get("start_raw"),
                "event_url": event.get("event_url"),
                "event_pd": event.get("event_pd"),
                "event_it": event.get("event_it"),
                "sportradar_url": event.get("sportradar_url"),
                "stats_identifier": event.get("stats_identifier"),
                "full_time_result": full_time_result,
            }
        )

    return {
        "league_url": league_url,
        "competition": parsed.get("competition") or {},
        "events": events_output,
    }


def summarize_parsed_payload(parsed: dict[str, Any]) -> str:
    payload_type = parsed.get("payload_type")
    competition = parsed.get("competition") or {}
    events = parsed.get("events") or []

    lines = [
        f"Tipo: {payload_type or 'unknown'}",
        f"Liga: {competition.get('name') or 'N/D'}",
    ]

    if payload_type == "markets":
        matches = parsed.get("matches") or []
        lines.append(f"Partidos: {len(matches)}")
        for match in matches[:5]:
            odds = match.get("odds_1x2") or {}
            lines.append(
                " - {home} vs {away} | 1={one} X={draw} 2={away_odd}".format(
                    home=match.get("home") or "?",
                    away=match.get("away") or "?",
                    one=odds.get("1"),
                    draw=odds.get("X"),
                    away_odd=odds.get("2"),
                )
            )
        if len(matches) > 5:
            lines.append(f" ... y {len(matches) - 5} más")
        return "\n".join(lines)

    lines.append(f"Eventos: {len(events)}")
    for event in events[:3]:
        lines.append(f" - {event.get('name') or event.get('fixture_id')}")
        for market in (event.get("markets") or [])[:5]:
            selections = market.get("selections") or []
            rendered = ", ".join(
                f"{selection.get('name')}={selection.get('odds_fractional') or selection.get('odds_decimal')}"
                for selection in selections[:3]
            )
            lines.append(f"   * {market.get('name')}: {rendered}")
    return "\n".join(lines)

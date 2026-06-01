"""Pure parsing and data models for Bet365 payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

ASIAN_MARKET_NAMES = {
    "938": "Asian Handicap",
    "10143": "Goal Line",
    "50138": "Alternative Asian Handicap",
    "50139": "Alternative Goal Line",
    "50137": "1st Half Asian Handicap",
    "50136": "1st Half Goal Line",
    "50265": "Alternative 1st Half Asian Handicap",
    "50266": "Alternative 1st Half Goal Line",
    "10164": "Alternative Goal Line 2",
    "10165": "Alternative Goal Line 3",
    "10233": "Alternative Goal Line 4",
    "10166": "Alternative Goal Line 5",
    "10239": "Alternative Goal Line 6",
}
PRIMARY_ASIAN_MARKET_IDS = ("938", "10143")


@dataclass(frozen=True)
class Bet365AsianMatch:
    fixture_id: str
    home: str
    away: str
    league_name: str | None
    scheduled_label_date: str | None
    scheduled_label_time: str | None
    scheduled_at: str | None
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None
    event_url: str | None
    stats_url: str | None
    markets_payload: dict[str, Any] | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class Bet365AsianLeagueExtraction:
    platform: str
    url: str
    league_name: str
    topic: str
    matches: list[Bet365AsianMatch]
    payload: dict[str, Any]


def fraction_to_decimal(frac: str | None) -> float | None:
    if not frac:
        return None
    raw = frac.strip()
    if "/" not in raw:
        try:
            return round(float(raw), 6)
        except ValueError:
            return None
    left, right = raw.split("/", 1)
    try:
        return round(1 + float(left) / float(right), 6)
    except ValueError:
        return None


def parse_datetime(raw: str | None, *, host: str) -> tuple[str | None, str | None, str | None]:
    if not raw:
        return None, None, None
    try:
        parsed = datetime.strptime(raw, "%Y%m%d%H%M%S")
    except ValueError:
        return None, None, None
    timezone_name = resolve_bet365_timezone_name(host)
    try:
        site_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        site_timezone = timezone.utc

    localized = parsed.replace(tzinfo=site_timezone)
    date_label = localized.strftime("%Y-%m-%d")
    time_label = localized.strftime("%H:%M")
    return date_label, time_label, localized.astimezone(timezone.utc).isoformat()


def parse_record(record: str) -> tuple[str, dict[str, str]]:
    parts = [part for part in record.split(";") if part]
    if not parts:
        return "", {}
    tag = parts[0]
    fields: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key] = value
    return tag, fields


def tokenize(payload: str) -> list[tuple[str, dict[str, str]]]:
    cleaned = payload.replace("\x08", "")
    return [
        parsed
        for parsed in (parse_record(record.strip()) for record in cleaned.split("|"))
        if parsed[0]
    ]


def event_visual_url(host: str, event_id: str, section: str = "I3") -> str:
    return f"https://{host}/#/AC/B1/C1/D8/E{event_id}/F3/{section}/"


def parse_league_payload(payload: str, *, host: str) -> dict[str, Any]:
    tokens = tokenize(payload)
    league_name = None
    topic = None
    matches: dict[str, dict[str, Any]] = {}
    current_market = None
    current_selection = None

    for tag, fields in tokens:
        if tag == "CL":
            topic = topic or fields.get("IT")
        elif tag == "EV":
            topic = topic or fields.get("IT")
            league_name = fields.get("L3") or league_name
            tb = fields.get("TB", "")
            if "¬" in tb and not league_name:
                league_name = tb.split("¬")[-1].split(",")[0].strip()
        elif tag == "MG":
            current_market = fields.get("ID")
            current_selection = None
        elif tag == "MA":
            if current_market == "40" or fields.get("ID") == "M40":
                current_market = "40"
                current_selection = (fields.get("NA") or "").strip()
            else:
                current_selection = None
        elif tag == "PA":
            fixture_id = fields.get("FI")
            if not fixture_id:
                continue

            if fields.get("ID", "").startswith("PC") and fields.get("PD"):
                date_label, time_label, scheduled_at = parse_datetime(fields.get("BC"), host=host)
                home = (fields.get("NA") or "").strip()
                away = (fields.get("N2") or "").strip()
                matches[fixture_id] = {
                    "fixture_id": fixture_id,
                    "home": home,
                    "away": away,
                    "league": fields.get("L3") or league_name,
                    "scheduled_label_date": date_label,
                    "scheduled_label_time": time_label,
                    "scheduled_at": scheduled_at,
                    "event_url": event_visual_url(host, fixture_id, section="I1"),
                    "stats_url": extract_sportradar_url(fields.get("EX")),
                    "markets_payload": {
                        "1x2": {
                            "home": None,
                            "draw": None,
                            "away": None,
                        }
                    },
                    "odds_home": None,
                    "odds_draw": None,
                    "odds_away": None,
                }
                continue

            if current_market != "40" or current_selection not in {"1", "X", "2"}:
                continue
            if fixture_id not in matches:
                continue

            odds_decimal = fraction_to_decimal(fields.get("OD") or fields.get("DO"))
            if current_selection == "1":
                matches[fixture_id]["odds_home"] = odds_decimal
                matches[fixture_id]["markets_payload"]["1x2"]["home"] = odds_decimal
            elif current_selection == "X":
                matches[fixture_id]["odds_draw"] = odds_decimal
                matches[fixture_id]["markets_payload"]["1x2"]["draw"] = odds_decimal
            elif current_selection == "2":
                matches[fixture_id]["odds_away"] = odds_decimal
                matches[fixture_id]["markets_payload"]["1x2"]["away"] = odds_decimal

    ordered_matches = sorted(
        matches.values(),
        key=lambda item: (item.get("scheduled_at") or "", item.get("fixture_id") or ""),
    )
    return {
        "league_name": league_name or "Bet365 League",
        "topic": topic or "",
        "matches": ordered_matches,
    }


def parse_asian_payload(
    payload: str,
    event_id: str,
    *,
    include_alternative_markets: bool,
) -> dict[str, Any]:
    tokens = tokenize(payload)
    event = {
        "event_id": event_id,
        "name": None,
        "home": None,
        "away": None,
        "league": None,
        "start_raw": None,
        "start_iso": None,
    }
    markets: list[dict[str, Any]] = []
    current_market: dict[str, Any] | None = None
    current_selection_meta: dict[str, str] | None = None
    pending_line: str | None = None

    for tag, fields in tokens:
        if tag == "EV" and fields.get("ID") == "EMB":
            event.update(
                {
                    "event_id": fields.get("FI") or event_id,
                    "name": fields.get("EX"),
                    "home": fields.get("N2"),
                    "away": fields.get("N3"),
                    "league": fields.get("CC") or fields.get("L3"),
                    "start_raw": fields.get("BC"),
                    "start_iso": _raw_datetime_to_iso(fields.get("BC")),
                }
            )
        elif tag == "MG":
            market_id = fields.get("ID")
            if market_id in PRIMARY_ASIAN_MARKET_IDS or (
                include_alternative_markets and market_id in ASIAN_MARKET_NAMES
            ):
                current_market = {
                    "market_id": market_id,
                    "market_name": fields.get("NA") or ASIAN_MARKET_NAMES.get(market_id) or market_id,
                    "selections": [],
                }
                markets.append(current_market)
            else:
                current_market = None
            current_selection_meta = None
            pending_line = None
        elif tag == "MA" and current_market is not None:
            current_selection_meta = fields
        elif tag == "PA" and current_market is not None:
            if fields.get("ID", "").startswith("PC"):
                pending_line = normalize_line(fields.get("NA"))
                continue
            odds_decimal = fraction_to_decimal(fields.get("OD") or fields.get("DO"))
            selection_name = (
                (current_selection_meta or {}).get("NA")
                or fields.get("NA")
                or fields.get("HD")
                or fields.get("HA")
                or ""
            ).strip()
            current_market["selections"].append(
                {
                    "selection": selection_name,
                    "line": normalize_line(pending_line or fields.get("HD") or fields.get("HA")),
                    "odds_decimal": odds_decimal,
                }
            )

    markets_payload: dict[str, Any] = {}
    alternative_markets: list[dict[str, Any]] = []
    for market in markets:
        if not market["selections"]:
            continue
        if market["market_id"] == "938":
            markets_payload["asian_handicap"] = canonicalize_market(market)
        elif market["market_id"] == "10143":
            markets_payload["goal_line"] = canonicalize_market(market)
        else:
            alternative_markets.append(canonicalize_market(market))

    if alternative_markets:
        markets_payload["alternative_markets"] = sorted(
            alternative_markets,
            key=lambda market: (
                str(market.get("market_id") or ""),
                str(market.get("market_name") or ""),
            ),
        )

    return {"event": event, "markets_payload": markets_payload}


def canonicalize_market(market: dict[str, Any]) -> dict[str, Any]:
    selections = sorted(
        [
            {
                "selection": str(item.get("selection") or "").strip(),
                "line": normalize_line(item.get("line")),
                "odds": item.get("odds_decimal"),
            }
            for item in market.get("selections") or []
            if item.get("odds_decimal") is not None
        ],
        key=lambda item: (
            str(item.get("line") or ""),
            str(item.get("selection") or ""),
        ),
    )
    return {
        "market_id": market.get("market_id"),
        "market_name": market.get("market_name"),
        "selections": selections,
    }


def normalize_line(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip().replace("+", "")
    if not value:
        return None
    if value in {"0", "-0", "0.0", "-0.0"}:
        return "0.0"
    return value


def merge_market_payloads(
    base_payload: dict[str, Any] | None, asian_payload: dict[str, Any] | None
) -> dict[str, Any] | None:
    base = json.loads(json.dumps(base_payload or {}))
    extra = asian_payload or {}
    for key, value in extra.items():
        base[key] = value
    return base or None


def _raw_datetime_to_iso(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d%H%M%S").isoformat()
    except ValueError:
        return None


def resolve_bet365_timezone_name(host: str) -> str:
    normalized_host = host.strip().lower()
    if normalized_host.endswith(".bet.ar") or normalized_host.endswith("bet365.bet.ar"):
        return "America/Argentina/Buenos_Aires"
    if normalized_host.endswith(".es") or normalized_host.endswith("bet365.es"):
        return "Europe/Madrid"
    return "UTC"


def extract_sportradar_url(ex: str | None) -> str | None:
    normalized_ex = (ex or "").strip()
    if not normalized_ex:
        return None

    match = re.search(r"puw~(https?://[^~]+)~Bet365Stats", normalized_ex)
    if match is None:
        return None

    return match.group(1)

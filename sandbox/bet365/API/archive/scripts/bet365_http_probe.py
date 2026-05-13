from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from common import (
    extract_bet365_identifiers,
    iter_jsonl,
    latest_capture_dir,
    score_record,
    try_parse_json,
    write_json,
)
from parse_markets_payload import looks_like_markets_payload, parse_markets_payload_text
from replay_candidate import (
    build_request_headers,
    replay_record,
    scoped_cookies_from_capture,
    select_candidate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prototipo HTTP puro para investigar si Bet365 permite obtener datos sin navegador.",
    )
    parser.add_argument(
        "target",
        help="URL de liga/evento Bet365 o fixture_id/event_id cuando se usa --mode explícito.",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "league", "event-i1", "event-i3"),
        default="auto",
        help="Tipo de target a resolver.",
    )
    parser.add_argument("--capture-dir", help="Captura base para inferir la request candidata.")
    parser.add_argument("--captures-root", default="sandbox/bet365/API/captures")
    parser.add_argument("--candidate-id", help="Forzar record_id de la captura.")
    parser.add_argument("--url-contains", help="Forzar selección por substring de URL.")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument(
        "--header-profile",
        choices=("captured", "minimal", "browserlike"),
        default="captured",
    )
    parser.add_argument("--no-cookies", action="store_true")
    parser.add_argument("--http2", action="store_true")
    parser.add_argument("--trust-env", action="store_true")
    parser.add_argument("--user-agent")
    parser.add_argument("--accept")
    parser.add_argument("--accept-language")
    parser.add_argument("--referer")
    parser.add_argument("--origin")
    parser.add_argument("--warmup-home", action="store_true")
    parser.add_argument("--warmup-url", action="append", default=[])
    parser.add_argument(
        "--output",
        help="Archivo donde guardar el resultado JSON. Si se omite, se imprime igual por stdout.",
    )
    return parser.parse_args()


def infer_mode(target: str, explicit_mode: str) -> str:
    if explicit_mode != "auto":
        return explicit_mode

    identifiers = extract_bet365_identifiers(target)
    if identifiers["competition_id"]:
        return "league"
    if identifiers["event_id"] and identifiers["event_tab"] == "1":
        return "event-i1"
    if identifiers["event_id"] and identifiers["event_tab"] == "3":
        return "event-i3"
    if target.isdigit():
        return "event-i1"
    return "league"


def pick_capture_dir(args: argparse.Namespace) -> Path:
    if args.capture_dir:
        return Path(args.capture_dir)
    latest = latest_capture_dir(Path(args.captures_root))
    if latest is None:
        raise SystemExit("No encontré capturas. Corré primero capture_network.py")
    return latest


def target_identifiers(target: str, mode: str) -> dict[str, str | None]:
    identifiers = extract_bet365_identifiers(target)
    if target.isdigit():
        identifiers["event_id"] = target
        if mode == "event-i3":
            identifiers["event_tab"] = "3"
        elif mode.startswith("event-"):
            identifiers["event_tab"] = "1"
    return identifiers


def select_candidate_for_probe(
    capture_dir: Path,
    *,
    mode: str,
    identifiers: dict[str, str | None],
    candidate_id: str | None,
    url_contains: str | None,
) -> dict[str, Any]:
    if candidate_id or url_contains:
        return select_candidate(
            capture_dir,
            record_id=candidate_id,
            url_contains=url_contains,
        )

    records = iter_jsonl(capture_dir / "network.jsonl")
    responses = [record for record in records if record.get("type") == "response"]
    if not responses:
        raise SystemExit("La captura no tiene responses para usar como base del probe.")

    def candidate_bonus(record: dict[str, Any]) -> int:
        bonus = 0
        text_hits = record.get("text_hits") or {}
        target_event_id = identifiers.get("event_id")
        target_competition_id = identifiers.get("competition_id")
        market_ids = set(text_hits.get("market_ids") or [])
        url = record.get("url") or ""

        if target_event_id and (
            target_event_id in url or target_event_id in (record.get("body_preview") or "")
        ):
            bonus += 18

        if target_competition_id and (
            target_competition_id in url or target_competition_id in (record.get("body_preview") or "")
        ):
            bonus += 18

        if mode == "league" and "40" in market_ids:
            bonus += 14
        if mode == "event-i1" and market_ids.intersection({"40", "981"}):
            bonus += 14
        if mode == "event-i3" and market_ids.intersection({"938", "10143"}):
            bonus += 14

        resource_type = (record.get("resource_type") or "").lower()
        if resource_type in {"xhr", "fetch", "eventsource"}:
            bonus += 8

        return bonus

    ranked = sorted(
        responses,
        key=lambda record: score_record(record) + candidate_bonus(record),
        reverse=True,
    )
    return ranked[0]


def walk_nodes(payload: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if "nodeName" in value and "data" in value:
                nodes.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return nodes


def to_decimal(selection_data: dict[str, Any]) -> float | None:
    raw_do = selection_data.get("DO")
    if raw_do not in (None, ""):
        try:
            return round(float(raw_do), 3)
        except (TypeError, ValueError):
            pass

    raw_od = selection_data.get("OD")
    if isinstance(raw_od, str) and "/" in raw_od:
        left, right = raw_od.split("/", maxsplit=1)
        try:
            return round(float(left) / float(right) + 1, 3)
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    return None


def normalize_line(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().replace(" ", "")
    if normalized in {"-0", "+0", "0", "0.0", "-0.0", "+0.0"}:
        return "0.0"
    return str(value).strip()


def normalize_tree_payload(payload: Any, *, mode: str) -> dict[str, Any] | None:
    nodes = walk_nodes(payload)
    if not nodes:
        return None

    market_groups = [node for node in nodes if node.get("nodeName") == "MG"]
    if not market_groups:
        return None

    groups_by_id: dict[str, dict[str, Any]] = {}
    for group in market_groups:
        group_id = str((group.get("data") or {}).get("ID") or "")
        if group_id:
            groups_by_id[group_id] = group

    result: dict[str, Any] = {
        "mode": mode,
        "available_market_ids": sorted(groups_by_id.keys()),
    }

    if mode == "league" and "40" in groups_by_id:
        full_time_group = groups_by_id["40"]
        markets = [
            child for child in full_time_group.get("_actualChildren", [])
            if isinstance(child, dict) and child.get("nodeName") == "MA"
        ]
        by_name = {str((market.get("data") or {}).get("NA") or ""): market for market in markets}
        teams_market = by_name.get(" ")
        home_market = by_name.get("1")
        draw_market = by_name.get("X")
        away_market = by_name.get("2")
        if teams_market and home_market and draw_market and away_market:
            fixtures: dict[str, dict[str, Any]] = {}
            for selection in teams_market.get("_actualChildren", []):
                data = selection.get("data") or {}
                fixture_id = str(data.get("FI") or "")
                if not fixture_id:
                    continue
                fixtures[fixture_id] = {
                    "fixture_id": fixture_id,
                    "home": data.get("NA"),
                    "away": data.get("N2"),
                    "odds_1x2": {"1": None, "X": None, "2": None},
                }

            def merge_odds(market: dict[str, Any], key: str) -> None:
                for selection in market.get("_actualChildren", []):
                    data = selection.get("data") or {}
                    fixture_id = str(data.get("FI") or "")
                    if fixture_id in fixtures:
                        fixtures[fixture_id]["odds_1x2"][key] = to_decimal(data)

            merge_odds(home_market, "1")
            merge_odds(draw_market, "X")
            merge_odds(away_market, "2")
            result["events"] = list(fixtures.values())

    if mode == "event-i1":
        if "40" in groups_by_id:
            full_time_group = groups_by_id["40"]
            selections: list[dict[str, Any]] = []
            for market in full_time_group.get("_actualChildren", []):
                if market.get("nodeName") != "MA":
                    continue
                for selection in market.get("_actualChildren", []):
                    data = selection.get("data") or {}
                    if data:
                        selections.append(
                            {
                                "name": data.get("NA"),
                                "side": data.get("N2"),
                                "odds_decimal": to_decimal(data),
                            }
                        )
            result["full_time_result"] = selections

        if "981" in groups_by_id:
            over_under_group = groups_by_id["981"]
            over_under: dict[str, Any] = {
                "market_id": "981",
                "line_display": None,
                "line_average": None,
                "over": None,
                "under": None,
            }
            for market in over_under_group.get("_actualChildren", []):
                market_data = market.get("data") or {}
                name = market_data.get("NA")
                selection = next(
                    (child for child in market.get("_actualChildren", []) if child.get("nodeName") == "PA"),
                    None,
                )
                selection_data = (selection or {}).get("data") or {}
                if name == "Over":
                    over_under["over"] = {"odds_decimal": to_decimal(selection_data)}
                    over_under["line_display"] = normalize_line(selection_data.get("HD"))
                    over_under["line_average"] = normalize_line(selection_data.get("HA"))
                elif name == "Under":
                    over_under["under"] = {"odds_decimal": to_decimal(selection_data)}
                    over_under["line_display"] = over_under["line_display"] or normalize_line(selection_data.get("HD"))
                    over_under["line_average"] = over_under["line_average"] or normalize_line(selection_data.get("HA"))
                elif selection_data.get("NA"):
                    over_under["line_display"] = over_under["line_display"] or normalize_line(selection_data.get("NA"))
            result["goals_over_under"] = over_under

    if mode == "event-i3":
        if "938" in groups_by_id:
            asian_group = groups_by_id["938"]
            asian_rows: list[dict[str, Any]] = []
            for market in asian_group.get("_actualChildren", []):
                market_data = market.get("data") or {}
                selection = next(
                    (child for child in market.get("_actualChildren", []) if child.get("nodeName") == "PA"),
                    None,
                )
                selection_data = (selection or {}).get("data") or {}
                asian_rows.append(
                    {
                        "team": market_data.get("NA"),
                        "line_display": normalize_line(selection_data.get("HD")),
                        "line_average": normalize_line(selection_data.get("HA")),
                        "odds_decimal": to_decimal(selection_data),
                    }
                )
            result["asian_handicap"] = asian_rows

        if "10143" in groups_by_id:
            goal_line_group = groups_by_id["10143"]
            goal_line: dict[str, Any] = {
                "market_id": "10143",
                "line_display": None,
                "line_average": None,
                "over": None,
                "under": None,
            }
            for market in goal_line_group.get("_actualChildren", []):
                market_data = market.get("data") or {}
                name = market_data.get("NA")
                selection = next(
                    (child for child in market.get("_actualChildren", []) if child.get("nodeName") == "PA"),
                    None,
                )
                selection_data = (selection or {}).get("data") or {}
                if name == "Over":
                    goal_line["over"] = {"odds_decimal": to_decimal(selection_data)}
                    goal_line["line_display"] = normalize_line(selection_data.get("HD"))
                    goal_line["line_average"] = normalize_line(selection_data.get("HA"))
                elif name == "Under":
                    goal_line["under"] = {"odds_decimal": to_decimal(selection_data)}
                    goal_line["line_display"] = goal_line["line_display"] or normalize_line(selection_data.get("HD"))
                    goal_line["line_average"] = goal_line["line_average"] or normalize_line(selection_data.get("HA"))
                elif selection_data.get("NA"):
                    goal_line["line_display"] = goal_line["line_display"] or normalize_line(selection_data.get("NA"))
            result["goal_line"] = goal_line

    return result


async def main() -> int:
    args = parse_args()
    mode = infer_mode(args.target, args.mode)
    identifiers = target_identifiers(args.target, mode)
    capture_dir = pick_capture_dir(args)
    candidate = select_candidate_for_probe(
        capture_dir,
        mode=mode,
        identifiers=identifiers,
        candidate_id=args.candidate_id,
        url_contains=args.url_contains,
    )

    cookies = {} if args.no_cookies else scoped_cookies_from_capture(capture_dir, candidate["url"])
    headers = build_request_headers(
        candidate,
        profile=args.header_profile,
        overrides={
            "user-agent": args.user_agent,
            "accept": args.accept,
            "accept-language": args.accept_language,
            "referer": args.referer,
            "origin": args.origin,
        },
    )
    warmup_urls = list(args.warmup_url)
    if args.warmup_home:
        parsed_url = urlparse(candidate["url"])
        warmup_urls.insert(0, f"{parsed_url.scheme}://{parsed_url.netloc}/")
    replay_result = await replay_record(
        candidate,
        headers=headers,
        cookies=cookies,
        timeout=args.timeout,
        insecure=args.insecure,
        http2=args.http2,
        trust_env=args.trust_env,
        warmup_urls=warmup_urls,
    )
    text = replay_result["response"].pop("text", None)
    parsed = try_parse_json(text) if isinstance(text, str) else None
    normalized: dict[str, Any] | None = None
    normalization_source: str | None = None

    if parsed is not None:
        normalized = normalize_tree_payload(parsed, mode=mode)
        if normalized is not None:
            normalization_source = "json_tree"

    if (
        normalized is None
        and mode == "league"
        and isinstance(text, str)
        and looks_like_markets_payload(text)
    ):
        normalized = parse_markets_payload_text(
            text,
            host=urlparse(candidate["url"]).netloc or "www.bet365.es",
        )
        normalization_source = "markets_payload"

    result = {
        "target": args.target,
        "mode": mode,
        "identifiers": identifiers,
        "capture_dir": str(capture_dir),
        "candidate": {
            "id": candidate["id"],
            "url": candidate["url"],
            "resource_type": candidate.get("resource_type"),
            "captured_status": candidate.get("status"),
            "captured_body_hash": candidate.get("body_hash"),
            "captured_body_path": candidate.get("body_path"),
            "header_profile": args.header_profile,
            "cookies_used": not args.no_cookies,
            "http2": args.http2,
            "trust_env": args.trust_env,
        },
        "replay": replay_result["response"],
        "normalized": normalized,
        "normalization_source": normalization_source,
        "notes": [],
    }

    if parsed is None and normalization_source != "markets_payload":
        result["notes"].append(
            "La response replayed no parece JSON parseable. Puede ser script, HTML o payload ofuscado."
        )
    if normalized is None and parsed is not None:
        result["notes"].append(
            "La response es JSON parseable, pero no encontré un árbol reconocible tipo EV/MG/MA/PA."
        )
    if normalization_source == "json_tree":
        result["notes"].append(
            "Se detectó un árbol compatible con mercados Bet365 y se devolvió una normalización best-effort."
        )
    if normalization_source == "markets_payload":
        result["notes"].append(
            "Se detectó un payload pipe-separated de matchmarketscontentapi/markets y se parsearon partidos 1X2."
        )

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(output_path, result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

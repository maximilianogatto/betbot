from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

from common import iter_jsonl, latest_capture_dir, load_json, score_record, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analiza una captura de red de Bet365 y rankea endpoints/respuestas candidatas.",
    )
    parser.add_argument(
        "capture_dir",
        nargs="?",
        help="Directorio de captura. Si se omite, usa el último bajo captures/.",
    )
    parser.add_argument(
        "--captures-root",
        default="sandbox/bet365/API/captures",
        help="Root donde buscar capturas.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Cantidad máxima de candidatos a mostrar por sección.",
    )
    return parser.parse_args()


def pick_capture_dir(args: argparse.Namespace) -> Path:
    if args.capture_dir:
        return Path(args.capture_dir)

    latest = latest_capture_dir(Path(args.captures_root))
    if latest is None:
        raise SystemExit("No encontré capturas. Corré primero capture_network.py")
    return latest


def compact_hits(record: dict[str, Any]) -> str:
    hits = record.get("text_hits") or {}
    parts: list[str] = []
    if hits.get("fixture_ids"):
        parts.append(f"fixture={','.join(hits['fixture_ids'])}")
    if hits.get("contains_terms"):
        parts.append(f"contains={','.join(hits['contains_terms'][:5])}")
    if hits.get("market_ids"):
        parts.append(f"markets={','.join(hits['market_ids'])}")
    if hits.get("markers"):
        parts.append(f"markers={','.join(hits['markers'][:6])}")
    return " | ".join(parts) or "-"


def query_items(url: str) -> list[tuple[str, str]]:
    return parse_qsl(urlparse(url).query, keep_blank_values=True)


def useful_endpoint(record: dict[str, Any]) -> bool:
    url = (record.get("url") or "").lower()
    return any(
        marker in url
        for marker in (
            "matchmarketscontentapi/markets",
            "matchbettingcontentapi/coupon",
            "splashcontentapi/changecompetition",
            "splashcontentapi/changefixture",
        )
    )


def extract_set_cookie_names(header_value: str | None) -> list[str]:
    if not header_value:
        return []
    names: list[str] = []
    for chunk in header_value.split("\n"):
        name, _, _ = chunk.strip().partition("=")
        if name:
            names.append(name)
    return names


def classify_candidates(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    ranked = []
    for record in records:
        candidate = dict(record)
        candidate["score"] = score_record(record)
        ranked.append(candidate)

    ranked = [record for record in ranked if record["score"] > 0]
    ranked.sort(key=lambda item: item["score"], reverse=True)

    http_candidates = [
        record
        for record in ranked
        if record.get("type") == "response"
        and (record.get("resource_type") or "").lower() in {"xhr", "fetch", "eventsource", "document"}
    ]
    script_candidates = [
        record
        for record in ranked
        if record.get("type") == "response" and (record.get("resource_type") or "").lower() == "script"
    ]
    websocket_candidates = [
        record
        for record in ranked
        if record.get("type") in {"websocket_frame", "websocket_event"}
    ]

    return {
        "http": http_candidates,
        "script": script_candidates,
        "websocket": websocket_candidates,
        "all_ranked": ranked,
    }


def infer_viability(candidates: dict[str, list[dict[str, Any]]]) -> list[str]:
    conclusions: list[str] = []

    top_http = candidates["http"][:10]
    top_ws = candidates["websocket"][:10]
    top_scripts = candidates["script"][:10]

    http_with_markets = [
        record
        for record in top_http
        if (record.get("text_hits") or {}).get("market_ids")
    ]
    http_with_fixtures = [
        record
        for record in top_http
        if (record.get("text_hits") or {}).get("fixture_ids")
    ]

    if http_with_markets and http_with_fixtures:
        conclusions.append(
            "Hay responses HTTP candidatas que contienen fixture IDs y market IDs. Vale la pena intentar replay HTTP puro."
        )
    elif http_with_fixtures:
        conclusions.append(
            "Hay responses HTTP con fixture IDs, pero la presencia de mercados no es concluyente. Probable extractor híbrido."
        )
    else:
        conclusions.append(
            "No aparecen responses HTTP obvias con fixture IDs/markets entre los candidatos principales."
        )

    if top_ws:
        conclusions.append(
            "Hay tráfico WebSocket candidato. Conviene revisar si los datos de mercado viajan por frames y si son repetibles fuera del navegador."
        )

    if top_scripts:
        conclusions.append(
            "Hay scripts con señales del runtime. Es posible que parte del árbol EV/MG/MA/PA se hidrate desde JS y no desde una API simple."
        )

    if not top_http and not top_ws:
        conclusions.append(
            "La captura no mostró endpoints útiles en red. Puede haber bloqueos, sesión insuficiente o dependencia total del runtime."
        )

    return conclusions


def summarize_query_params(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for record in records:
        if not useful_endpoint(record):
            continue
        items = query_items(record.get("url") or "")
        summary.append(
            {
                "id": record.get("id"),
                "url": record.get("url"),
                "resource_type": record.get("resource_type"),
                "ordered_params": [{"name": key, "value": value} for key, value in items],
            }
        )
    return summary


def summarize_cookie_timeline(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    responses = [record for record in records if record.get("type") == "response"]
    result: list[dict[str, Any]] = []
    for index, record in enumerate(responses):
        if not useful_endpoint(record):
            continue
        prior = []
        for earlier in responses[:index]:
            set_cookie = (earlier.get("response_headers") or {}).get("set-cookie")
            names = extract_set_cookie_names(set_cookie)
            if not names:
                continue
            prior.append(
                {
                    "id": earlier.get("id"),
                    "url": earlier.get("url"),
                    "cookie_names": names,
                }
            )
        result.append(
            {
                "endpoint_id": record.get("id"),
                "endpoint_url": record.get("url"),
                "prior_set_cookie_events": prior[-10:],
            }
        )
    return result


def summarize_websockets(records: list[dict[str, Any]]) -> dict[str, Any]:
    frames = [record for record in records if record.get("type") == "websocket_frame"]
    relevant = [
        record for record in frames
        if any((record.get("text_hits") or {}).get(key) for key in ("fixture_ids", "market_ids", "markers"))
    ]
    return {
        "total_frames": len(frames),
        "relevant_frames": len(relevant),
        "top_relevant_frames": relevant[:20],
    }


def main() -> int:
    args = parse_args()
    capture_dir = pick_capture_dir(args)

    metadata = load_json(capture_dir / "metadata.json")
    records = iter_jsonl(capture_dir / "network.jsonl")
    candidates = classify_candidates(records)

    resource_counter = Counter(
        (record.get("resource_type") or "none")
        for record in records
        if record.get("type") == "response"
    )
    type_counter = Counter(record.get("type") or "unknown" for record in records)

    summary = {
        "capture_dir": str(capture_dir),
        "target_url": metadata.get("target_url"),
        "total_records": len(records),
        "record_types": dict(type_counter),
        "response_resource_types": dict(resource_counter),
        "top_http_candidates": candidates["http"][: args.top],
        "top_script_candidates": candidates["script"][: args.top],
        "top_websocket_candidates": candidates["websocket"][: args.top],
        "query_param_summary": summarize_query_params(records),
        "cookie_timeline": summarize_cookie_timeline(records),
        "websocket_summary": summarize_websockets(records),
        "conclusions": infer_viability(candidates),
    }
    write_json(capture_dir / "analysis.json", summary)

    print(f"Captura: {capture_dir}")
    print(f"URL: {metadata.get('target_url')}")
    print(f"Registros: {len(records)}")
    print(f"Tipos: {dict(type_counter)}")
    print(f"Resource types: {dict(resource_counter)}")
    print("")

    for section_name, key in (
        ("Endpoints HTTP candidatos", "http"),
        ("Scripts candidatos", "script"),
        ("WebSockets candidatos", "websocket"),
    ):
        print(section_name)
        section = candidates[key][: args.top]
        if not section:
            print("  - Sin candidatos")
            print("")
            continue

        for record in section:
            print(
                f"  score={record['score']:>3} type={record.get('type'):<16} "
                f"resource={record.get('resource_type') or '-':<10} "
                f"status={record.get('status') or '-':<3} "
                f"kind={record.get('body_kind') or '-':<10}"
            )
            print(f"    url: {record.get('url')}")
            print(f"    hits: {compact_hits(record)}")
            if record.get("body_path"):
                print(f"    body: {record['body_path']}")
        print("")

    print("Conclusiones preliminares")
    for conclusion in summary["conclusions"]:
        print(f"  - {conclusion}")

    if summary["query_param_summary"]:
        print("")
        print("Query params en endpoints útiles")
        for item in summary["query_param_summary"][: args.top]:
            rendered = ", ".join(f"{part['name']}={part['value']}" for part in item["ordered_params"])
            print(f"  - {item['id']}: {rendered}")

    print("")
    print(f"Análisis guardado en: {capture_dir / 'analysis.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

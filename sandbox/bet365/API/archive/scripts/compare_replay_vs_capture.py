from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

from common import iter_jsonl, latest_capture_dir, load_json, write_json
from replay_candidate import scoped_cookies_from_capture


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compara una request/response capturada contra un replay guardado.",
    )
    parser.add_argument("capture_dir", nargs="?", help="Directorio de captura.")
    parser.add_argument("--captures-root", default="sandbox/bet365/API/captures")
    parser.add_argument("--replay-json", help="Archivo JSON de replay. Si se omite, usa el más reciente.")
    parser.add_argument("--record-id", help="Forzar candidate id del capture.")
    parser.add_argument("--output", help="Guardar comparación JSON.")
    return parser.parse_args()


def pick_capture_dir(args: argparse.Namespace) -> Path:
    if args.capture_dir:
        return Path(args.capture_dir)
    latest = latest_capture_dir(Path(args.captures_root))
    if latest is None:
        raise SystemExit("No encontré capturas.")
    return latest


def pick_replay_json(capture_dir: Path, replay_json: str | None) -> Path:
    if replay_json:
        return Path(replay_json)
    replay_dir = capture_dir / "replays"
    files = sorted(replay_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise SystemExit("No encontré replay JSON en la captura.")
    return files[0]


def parse_cookie_names(cookie_header: str | None) -> list[str]:
    if not cookie_header:
        return []
    names: list[str] = []
    for item in cookie_header.split(";"):
        name, _, _ = item.strip().partition("=")
        if name:
            names.append(name)
    return sorted(dict.fromkeys(names))


def query_items(url: str) -> list[tuple[str, str]]:
    return parse_qsl(urlparse(url).query, keep_blank_values=True)


def as_map(items: list[tuple[str, str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for key, value in items:
        result.setdefault(key, []).append(value)
    return result


def find_capture_record(capture_dir: Path, record_id: str) -> dict[str, Any]:
    for record in iter_jsonl(capture_dir / "network.jsonl"):
        if record.get("id") == record_id:
            return record
    raise SystemExit(f"No encontré {record_id} en network.jsonl")


def compare_headers(captured: dict[str, str], replay: dict[str, str]) -> dict[str, Any]:
    captured_keys = set(captured)
    replay_keys = set(replay)
    common = sorted(captured_keys & replay_keys)
    differing = []
    for key in common:
        if captured.get(key) != replay.get(key):
            differing.append(
                {
                    "header": key,
                    "captured": captured.get(key),
                    "replay": replay.get(key),
                }
            )
    return {
        "missing_in_replay": sorted(captured_keys - replay_keys),
        "extra_in_replay": sorted(replay_keys - captured_keys),
        "differing_values": differing,
    }


def compare_queries(captured_url: str, replay_url: str) -> dict[str, Any]:
    captured_items = query_items(captured_url)
    replay_items = query_items(replay_url)
    captured_map = as_map(captured_items)
    replay_map = as_map(replay_items)
    keys = sorted(set(captured_map) | set(replay_map))
    differing = []
    for key in keys:
        if captured_map.get(key) != replay_map.get(key):
            differing.append(
                {
                    "param": key,
                    "captured": captured_map.get(key),
                    "replay": replay_map.get(key),
                }
            )
    return {
        "captured_order": captured_items,
        "replay_order": replay_items,
        "same_order": captured_items == replay_items,
        "differing_params": differing,
    }


def build_report(capture_record: dict[str, Any], replay_data: dict[str, Any], capture_dir: Path) -> dict[str, Any]:
    captured_request_headers = {k.lower(): v for k, v in (capture_record.get("request_headers") or {}).items()}
    replay_request_headers = {k.lower(): v for k, v in (replay_data.get("request", {}).get("headers") or {}).items()}
    captured_response_headers = {k.lower(): v for k, v in (capture_record.get("response_headers") or {}).items()}
    replay_response_headers = {k.lower(): v for k, v in (replay_data.get("response", {}).get("headers") or {}).items()}

    captured_cookie_names = parse_cookie_names(captured_request_headers.get("cookie"))
    if not captured_cookie_names:
        captured_cookie_names = sorted(scoped_cookies_from_capture(capture_dir, capture_record["url"]).keys())
    replay_cookie_names = sorted(replay_data.get("request", {}).get("cookie_names") or parse_cookie_names(replay_request_headers.get("cookie")))

    query_diff = compare_queries(capture_record["url"], replay_data["request"]["url"])
    request_header_diff = compare_headers(captured_request_headers, replay_request_headers)
    response_header_diff = compare_headers(captured_response_headers, replay_response_headers)

    critical_headers = [
        "referer",
        "origin",
        "accept",
        "accept-language",
        "accept-encoding",
        "user-agent",
        "sec-fetch-site",
        "sec-fetch-mode",
        "sec-fetch-dest",
        "sec-ch-ua",
        "x-net-sync-term",
        "x-request-id",
        "priority",
    ]
    critical = []
    for key in critical_headers:
        critical.append(
            {
                "header": key,
                "captured": captured_request_headers.get(key),
                "replay": replay_request_headers.get(key),
                "same": captured_request_headers.get(key) == replay_request_headers.get(key),
            }
        )

    captured_status = capture_record.get("status")
    replay_status = replay_data.get("response", {}).get("status_code")
    report = {
        "capture_record_id": capture_record["id"],
        "replay_file_candidate_id": replay_data.get("candidate", {}).get("id"),
        "request": {
            "captured_url": capture_record["url"],
            "replay_url": replay_data["request"]["url"],
            "captured_method": capture_record.get("method"),
            "replay_method": replay_data["request"].get("method"),
            "query_diff": query_diff,
            "critical_headers": critical,
            "request_header_diff": request_header_diff,
            "captured_cookie_names": captured_cookie_names,
            "replay_cookie_names": replay_cookie_names,
            "missing_cookies_in_replay": sorted(set(captured_cookie_names) - set(replay_cookie_names)),
            "extra_cookies_in_replay": sorted(set(replay_cookie_names) - set(captured_cookie_names)),
            "warmup_urls": replay_data["request"].get("warmup_urls"),
            "backend": replay_data["request"].get("backend"),
        },
        "response": {
            "captured_status": captured_status,
            "replay_status": replay_status,
            "same_status": captured_status == replay_status,
            "captured_content_type": capture_record.get("content_type"),
            "replay_content_type": replay_data["response"].get("content_type"),
            "captured_body_hash": capture_record.get("body_hash"),
            "replay_body_hash": replay_data["response"].get("body_hash"),
            "same_body_hash": capture_record.get("body_hash") == replay_data["response"].get("body_hash"),
            "captured_body_size": capture_record.get("body_size"),
            "replay_body_size": replay_data["response"].get("body_size"),
            "captured_preview": capture_record.get("body_preview"),
            "replay_preview": replay_data["response"].get("body_preview"),
            "response_header_diff": response_header_diff,
        },
    }
    return report


def main() -> int:
    args = parse_args()
    capture_dir = pick_capture_dir(args)
    replay_path = pick_replay_json(capture_dir, args.replay_json)
    replay_data = load_json(replay_path)
    record_id = args.record_id or replay_data.get("candidate", {}).get("id")
    if not record_id:
        raise SystemExit("No pude inferir record_id del replay.")
    capture_record = find_capture_record(capture_dir, record_id)
    report = build_report(capture_record, replay_data, capture_dir)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = replay_path.with_name(replay_path.stem + ".compare.json")
    write_json(output_path, report)

    print(f"Capture: {capture_dir}")
    print(f"Replay: {replay_path}")
    print(f"Record: {record_id}")
    print("Diferencias críticas:")
    for item in report["request"]["critical_headers"]:
        if not item["same"]:
            print(f"  - {item['header']}: captured={item['captured']!r} replay={item['replay']!r}")
    if report["request"]["missing_cookies_in_replay"]:
        print("Cookies faltantes en replay:", ", ".join(report["request"]["missing_cookies_in_replay"]))
    if report["request"]["query_diff"]["differing_params"]:
        print("Query params distintos:")
        for item in report["request"]["query_diff"]["differing_params"]:
            print(f"  - {item['param']}: captured={item['captured']} replay={item['replay']}")
    print(
        "Status/body:",
        report["response"]["captured_status"],
        "->",
        report["response"]["replay_status"],
        "| same_body_hash=",
        report["response"]["same_body_hash"],
    )
    print(f"Comparación guardada en: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

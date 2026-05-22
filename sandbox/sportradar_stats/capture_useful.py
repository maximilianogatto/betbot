from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
import sys
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Response, async_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.analysis import extract_sportradar_match_id, normalize_endpoint_path
from sandbox.sportradar_stats.capture_everything import (
    build_context,
    install_routes,
    now_iso,
    safe_json_loads,
)
from sandbox.sportradar_stats.capture_runtime import resolve_capture_user_data_dir
from sandbox.sportradar_stats.filtering import (
    extract_doc_data,
    extract_doc_event_name,
    extract_doc_maxage_seconds,
    extract_endpoint_key_from_path,
    extract_match_ids,
    extract_query_url,
    extract_top_level_keys,
    finalize_endpoint_index,
    is_static_asset_url,
    update_endpoint_index,
)


ALLOWED_GISMO_ENDPOINTS = {
    "match_info_statshub",
    "stats_match_get",
    "match_timeline",
    "match_timelinedelta",
    "match_details",
    "match_markets",
    "stats_match_tableslice",
    "stats_match_head2head",
    "stats_team_lastx",
    "stats_team_nextx",
    "stats_team_versus",
    "stats_h2h_versus",
    "stats_season_tables",
    "stats_formtable",
    "stats_season_teamscoringconceding",
    "stats_team_streaks",
    "stats_season_injuries",
    "stats_season_topgoals",
    "stats_season_topcards",
    "stats_season_topassists",
    "uniqueteam_markets",
    "odds_ukformat",
}
ALLOWED_RESOURCE_TYPES = {"fetch", "xhr", "document"}
DOCUMENT_ENDPOINTS = {
    "document_stats_url",
    "document_match_page",
    "document_deeplink",
}
MATCH_SCOPED_ENDPOINTS = {
    "match_info_statshub",
    "stats_match_get",
    "match_timeline",
    "match_timelinedelta",
    "match_details",
    "match_markets",
    "stats_match_tableslice",
    "stats_match_head2head",
}
REQUEST_HEADER_ALLOWLIST = {
    "accept",
    "accept-language",
    "origin",
    "referer",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "user-agent",
    "x-requested-with",
}
RESPONSE_HEADER_ALLOWLIST = {
    "access-control-allow-origin",
    "cache-control",
    "content-length",
    "content-type",
    "date",
    "etag",
    "expires",
    "last-modified",
    "location",
    "server",
    "vary",
}
MAX_PREVIEW_LENGTH = 1200


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture only useful Sportradar / Statshub endpoints from one stats URL.",
    )
    parser.add_argument("stats_url", help="Sportradar / Bet365Stats match URL.")
    parser.add_argument(
        "--seconds",
        type=float,
        default=30.0,
        help="How long to keep the stats page open after DOMContentLoaded.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("sandbox/sportradar_stats/captures/useful_capture"),
        help="Directory where useful capture artifacts will be written.",
    )
    parser.add_argument(
        "--bootstrap-url",
        default=None,
        help="Optional Bet365 page to open before the stats URL.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run the browser in headed mode.",
    )
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help="Optional persistent Chromium profile directory.",
    )
    return parser.parse_args()


def select_basic_headers(headers: dict[str, str], *, allowed: set[str]) -> dict[str, str]:
    selected: dict[str, str] = {}
    for key, value in headers.items():
        normalized_key = str(key).strip().lower()
        if normalized_key not in allowed:
            continue
        normalized_value = str(value).strip()
        if not normalized_value:
            continue
        selected[normalized_key] = normalized_value
    return dict(sorted(selected.items()))


def parse_query_segments(query_url_or_path: str | None) -> list[str]:
    raw = str(query_url_or_path or "").strip()
    if not raw:
        return []
    parsed = urlparse(raw)
    candidate = parsed.path or raw
    return [segment for segment in candidate.split("/") if segment]


def is_signed_url(url: str) -> bool:
    parsed = urlparse(url)
    t_values = parse_qs(parsed.query).get("T", [])
    if any(str(value).startswith("exp=") for value in t_values):
        return True
    return "T=exp=" in parsed.query


def detect_useful_endpoint_name(url: str, body_json: object | None = None) -> str | None:
    query_url = extract_query_url(body_json)
    endpoint_name = extract_endpoint_key_from_path(query_url) or extract_endpoint_key_from_path(url)
    if endpoint_name in ALLOWED_GISMO_ENDPOINTS:
        return endpoint_name

    parsed = urlparse(url)
    path = parsed.path.lower()
    host = parsed.netloc.lower()
    if "sportradar.com" not in host:
        return None
    if "/deeplink" in path:
        return "document_deeplink"
    if "/match/" in path:
        if "statshub.sportradar.com" in host:
            return "document_match_page"
        return "document_stats_url"
    return None


def should_capture_useful_response(
    *,
    url: str,
    resource_type: str,
    body_json: object | None = None,
) -> bool:
    normalized_url = str(url or "").strip()
    normalized_resource_type = str(resource_type or "").strip().lower()
    if not normalized_url or normalized_resource_type not in ALLOWED_RESOURCE_TYPES:
        return False
    if is_static_asset_url(normalized_url):
        return False

    endpoint_name = detect_useful_endpoint_name(normalized_url, body_json)
    if endpoint_name is None:
        return False
    if endpoint_name in DOCUMENT_ENDPOINTS:
        return normalized_resource_type == "document"
    return endpoint_name in ALLOWED_GISMO_ENDPOINTS


def build_endpoint_path(url: str, body_json: object | None = None) -> str:
    query_url = extract_query_url(body_json)
    if query_url:
        return query_url
    return urlparse(url).path or url


def extract_primary_match_id(endpoint_name: str | None, url: str, body_json: object | None = None) -> str | None:
    if endpoint_name in MATCH_SCOPED_ENDPOINTS:
        query_segments = parse_query_segments(extract_query_url(body_json) or url)
        if len(query_segments) >= 2 and query_segments[1].isdigit():
            return query_segments[1]

    if endpoint_name in DOCUMENT_ENDPOINTS:
        parsed_match_id = extract_sportradar_match_id(url)
        if parsed_match_id:
            return parsed_match_id

    payload_for_match_ids = extract_doc_data(body_json)
    if payload_for_match_ids is None:
        payload_for_match_ids = body_json

    match_ids = extract_match_ids(payload_for_match_ids)
    if match_ids:
        return str(match_ids[0])
    return None


def build_useful_endpoints_index(
    records: list[dict[str, Any]],
    *,
    source_file: str,
) -> dict[str, Any]:
    buckets: dict[str, dict[str, Any]] = {}
    for record in records:
        update_endpoint_index(buckets, record)
    return finalize_endpoint_index(
        buckets,
        source_file=source_file,
        filtered_records_count=len(records),
    )


async def build_useful_record(
    response: Response,
    *,
    started_at: float,
) -> dict[str, Any] | None:
    request = response.request
    url = response.url

    body_text = ""
    try:
        body_text = await response.text()
    except Exception as exc:
        body_text = f"<<body read failed: {exc}>>"

    body_json = safe_json_loads(body_text)
    if not should_capture_useful_response(
        url=url,
        resource_type=request.resource_type,
        body_json=body_json,
    ):
        return None

    query_url = extract_query_url(body_json)
    doc_data = extract_doc_data(body_json)
    payload_for_summary = doc_data if doc_data is not None else body_json
    endpoint_name = detect_useful_endpoint_name(url, body_json)
    endpoint_path = build_endpoint_path(url, body_json)
    request_headers = {}
    try:
        request_headers = await request.all_headers()
    except Exception:
        request_headers = {}

    preview = None
    if body_json is None and body_text:
        preview = body_text[:MAX_PREVIEW_LENGTH]

    body_size_bytes = len(body_text.encode("utf-8"))
    match_ids = extract_match_ids(payload_for_summary)
    primary_match_id = extract_primary_match_id(endpoint_name, url, body_json)
    if primary_match_id and primary_match_id not in match_ids:
        match_ids = [primary_match_id, *match_ids]

    return {
        "captured_at": now_iso(),
        "elapsed_ms": round((time.monotonic() - started_at) * 1000, 2),
        "method": request.method,
        "status": response.status,
        "resource_type": request.resource_type,
        "url": url,
        "host": urlparse(url).netloc,
        "endpoint_name": endpoint_name,
        "endpoint_path": endpoint_path,
        "endpoint_key": endpoint_name,
        "normalized_path": normalize_endpoint_path(query_url or url),
        "query_url": query_url,
        "body_size_bytes": body_size_bytes,
        "body_json": body_json,
        "preview": preview,
        "request_headers": select_basic_headers(request_headers, allowed=REQUEST_HEADER_ALLOWLIST),
        "response_headers": select_basic_headers(response.headers, allowed=RESPONSE_HEADER_ALLOWLIST),
        "content_type": response.headers.get("content-type"),
        "doc_event": extract_doc_event_name(body_json),
        "maxage_seconds": extract_doc_maxage_seconds(body_json),
        "top_level_keys": extract_top_level_keys(payload_for_summary),
        "match_id": primary_match_id,
        "match_ids": match_ids,
        "signed_url": is_signed_url(url),
    }


async def capture_useful(
    stats_url: str,
    *,
    out_dir: Path,
    seconds: float,
    headless: bool,
    user_data_dir: str | None,
    bootstrap_url: str | None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    useful_ndjson_path = out_dir / "useful_fetch.ndjson"
    useful_json_path = out_dir / "useful_fetch.json"
    useful_index_path = out_dir / "useful_endpoints_index.json"
    useful_metadata_path = out_dir / "useful_capture_metadata.json"

    useful_ndjson_path.write_text("", encoding="utf-8")

    async with async_playwright() as playwright:
        context = await build_context(
            playwright,
            headless=headless,
            user_data_dir=user_data_dir,
        )
        await install_routes(context)

        page = await context.new_page()
        started_at = time.monotonic()
        responses_seen = 0
        requests_seen = 0
        useful_records: list[dict[str, Any]] = []
        pending_tasks: set[asyncio.Task[None]] = set()

        async def handle_response(response: Response) -> None:
            nonlocal responses_seen
            responses_seen += 1

            useful_record = await build_useful_record(
                response,
                started_at=started_at,
            )
            if useful_record is None:
                return

            useful_records.append(useful_record)
            with useful_ndjson_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(useful_record, ensure_ascii=False))
                handle.write("\n")

            print(
                f"[USEFUL {len(useful_records)}] "
                f"{useful_record['status']} "
                f"{useful_record['endpoint_name']:<32} "
                f"{useful_record['url'][:160]}"
            )

        async def handle_request(_request) -> None:
            nonlocal requests_seen
            requests_seen += 1

        def track_response(response: Response) -> None:
            task = asyncio.create_task(handle_response(response))
            pending_tasks.add(task)
            task.add_done_callback(pending_tasks.discard)

        def track_request(request) -> None:
            task = asyncio.create_task(handle_request(request))
            pending_tasks.add(task)
            task.add_done_callback(pending_tasks.discard)

        page.on("response", track_response)
        page.on("request", track_request)

        if bootstrap_url:
            print(f"→ bootstrap: {bootstrap_url}")
            await page.goto(
                bootstrap_url,
                wait_until="domcontentloaded",
                timeout=120000,
            )
            await asyncio.sleep(5)

        print(f"→ stats_url: {stats_url}")
        await page.goto(
            stats_url,
            wait_until="domcontentloaded",
            timeout=120000,
        )
        await asyncio.sleep(seconds)
        await asyncio.sleep(1)

        if pending_tasks:
            await asyncio.gather(*list(pending_tasks), return_exceptions=True)

        index_payload = build_useful_endpoints_index(
            useful_records,
            source_file=str(useful_ndjson_path),
        )
        useful_index_path.write_text(
            json.dumps(index_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        useful_json_path.write_text(
            json.dumps(useful_records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        metadata = {
            "stats_url": stats_url,
            "bootstrap_url": bootstrap_url,
            "captured_at": now_iso(),
            "seconds": seconds,
            "user_data_dir": user_data_dir,
            "responses_seen": responses_seen,
            "requests_seen": requests_seen,
            "useful_records_count": len(useful_records),
            "endpoint_count": index_payload["endpoint_count"],
            "files": {
                "useful_fetch_ndjson": str(useful_ndjson_path),
                "useful_fetch_json": str(useful_json_path),
                "useful_endpoints_index": str(useful_index_path),
            },
        }
        useful_metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        await context.close()

    return {
        "useful_fetch_ndjson": useful_ndjson_path,
        "useful_fetch_json": useful_json_path,
        "useful_endpoints_index": useful_index_path,
        "useful_capture_metadata": useful_metadata_path,
        "useful_records_count": len(useful_records),
        "endpoint_count": index_payload["endpoint_count"],
    }


async def main_async() -> int:
    args = parse_args()
    user_data_dir = resolve_capture_user_data_dir(args.user_data_dir)
    result = await capture_useful(
        args.stats_url,
        out_dir=args.out_dir.resolve(),
        seconds=args.seconds,
        headless=not args.headed,
        user_data_dir=user_data_dir,
        bootstrap_url=args.bootstrap_url,
    )
    print(f"Wrote {result['useful_fetch_ndjson']}")
    print(f"Wrote {result['useful_fetch_json']}")
    print(f"Wrote {result['useful_endpoints_index']}")
    print(f"Wrote {result['useful_capture_metadata']}")
    print(
        "Useful responses:",
        result["useful_records_count"],
        "| endpoints:",
        result["endpoint_count"],
    )
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())

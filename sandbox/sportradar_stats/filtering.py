"""Streaming helpers for filtering and indexing captured Sportradar responses."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

from sandbox.sportradar_stats.analysis import normalize_endpoint_path


USEFUL_RESOURCE_TYPES = {"fetch", "xhr"}
STATIC_ASSET_EXTENSIONS = (
    ".css",
    ".gif",
    ".ico",
    ".jpg",
    ".jpeg",
    ".png",
    ".svg",
    ".ttf",
    ".otf",
    ".webp",
    ".woff",
    ".woff2",
)
STATIC_ASSET_TOKENS = (
    "/assets/",
    "/fonts/",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
)
LIVE_ENDPOINT_HINTS = {
    "event_get",
    "match_timeline",
    "match_timelinedelta",
}


def iter_ndjson_records(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            normalized = line.strip()
            if not normalized:
                continue
            try:
                payload = json.loads(normalized)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def extract_query_url(body_json: object | None) -> str | None:
    if isinstance(body_json, dict):
        raw = body_json.get("queryUrl")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def extract_doc0(body_json: object | None) -> dict[str, Any] | None:
    if not isinstance(body_json, dict):
        return None

    doc_entries = body_json.get("doc")
    if not isinstance(doc_entries, list) or not doc_entries:
        return None

    first_entry = doc_entries[0]
    if isinstance(first_entry, dict):
        return first_entry
    return None


def extract_doc_data(body_json: object | None) -> object | None:
    doc0 = extract_doc0(body_json)
    if not isinstance(doc0, dict):
        return None
    return doc0.get("data")


def extract_doc_event_name(body_json: object | None) -> str | None:
    doc0 = extract_doc0(body_json)
    if not isinstance(doc0, dict):
        return None
    event_name = doc0.get("event")
    if isinstance(event_name, str) and event_name.strip():
        return event_name.strip()
    return None


def extract_doc_maxage_seconds(body_json: object | None) -> int | None:
    doc0 = extract_doc0(body_json)
    if not isinstance(doc0, dict):
        return None

    raw_value = doc0.get("_maxage")
    if raw_value is None:
        return None

    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def is_static_asset_url(url: str) -> bool:
    normalized = url.strip().lower()
    if not normalized:
        return False

    if any(token in normalized for token in STATIC_ASSET_TOKENS):
        return True

    path = urlparse(normalized).path
    return path.endswith(STATIC_ASSET_EXTENSIONS)


def should_keep_capture_record(record: dict[str, Any]) -> bool:
    url = str(record.get("url") or "").strip()
    if not url:
        return False

    if is_static_asset_url(url):
        return False

    resource_type = str(record.get("resource_type") or "").strip().lower()
    path = urlparse(url).path.lower()
    return resource_type in USEFUL_RESOURCE_TYPES or "/gismo/" in path


def extract_endpoint_key_from_path(path_or_url: str | None) -> str | None:
    raw = str(path_or_url or "").strip()
    if not raw:
        return None

    parsed = urlparse(raw)
    candidate = parsed.path or raw
    segments = [segment for segment in candidate.split("/") if segment]
    if not segments:
        return None

    if "gismo" in segments:
        gismo_index = segments.index("gismo")
        if gismo_index + 1 < len(segments):
            return segments[gismo_index + 1]
        return None

    return segments[0]


def extract_content_type(record: dict[str, Any]) -> str | None:
    direct = record.get("content_type")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    response_headers = record.get("response_headers")
    if not isinstance(response_headers, dict):
        return None

    for key, value in response_headers.items():
        if str(key).lower() != "content-type":
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def extract_top_level_keys(payload: object | None) -> list[str]:
    if isinstance(payload, dict):
        return [str(key) for key in list(payload.keys())[:25]]

    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return [str(key) for key in list(payload[0].keys())[:25]]

    return []


def extract_match_ids(payload: object | None, *, limit: int = 25) -> list[str]:
    discovered: list[str] = []
    seen: set[str] = set()

    def add(value: object) -> None:
        if value is None:
            return
        candidate = str(value).strip()
        if not candidate or not candidate.isdigit() or candidate in seen:
            return
        seen.add(candidate)
        discovered.append(candidate)

    def visit(value: object, depth: int) -> None:
        if depth > 5 or len(discovered) >= limit:
            return

        if isinstance(value, dict):
            doc_name = str(value.get("_doc") or "").lower()
            if doc_name == "match":
                add(value.get("_id"))

            for key, child in value.items():
                normalized_key = str(key).strip().lower()
                if normalized_key in {"matchid", "match_id"}:
                    add(child)
                elif normalized_key == "match" and isinstance(child, dict):
                    add(child.get("_id"))
                    add(child.get("matchid"))
                visit(child, depth + 1)
            return

        if isinstance(value, list):
            for item in value[:25]:
                visit(item, depth + 1)

    visit(payload, 0)
    return discovered


def compact_json_example(value: object, *, max_items: int = 3, max_depth: int = 2) -> object:
    if max_depth < 0:
        return "..."

    if isinstance(value, dict):
        example: dict[str, object] = {}
        for key, child in list(value.items())[:10]:
            example[str(key)] = compact_json_example(
                child,
                max_items=max_items,
                max_depth=max_depth - 1,
            )
        return example

    if isinstance(value, list):
        return [
            compact_json_example(
                item,
                max_items=max_items,
                max_depth=max_depth - 1,
            )
            for item in value[:max_items]
        ]

    if isinstance(value, str):
        return value[:120]

    return value


def normalize_filtered_record(record: dict[str, Any]) -> dict[str, Any] | None:
    if not should_keep_capture_record(record):
        return None

    url = str(record.get("url") or "").strip()
    body_json = record.get("body_json")
    query_url = extract_query_url(body_json)
    doc_data = extract_doc_data(body_json)
    payload_for_summary = doc_data if doc_data is not None else body_json
    endpoint_key = (
        extract_endpoint_key_from_path(query_url)
        or extract_endpoint_key_from_path(url)
        or normalize_endpoint_path(query_url or url)
    )

    preview = record.get("body_preview")
    if preview is None:
        preview = record.get("preview")

    body_size_bytes = record.get("body_size_bytes")
    if body_size_bytes is None:
        body_size_bytes = record.get("body_size")

    try:
        body_size_bytes = int(body_size_bytes or 0)
    except (TypeError, ValueError):
        body_size_bytes = 0

    elapsed_ms = record.get("elapsed_ms")
    try:
        elapsed_ms = float(elapsed_ms) if elapsed_ms is not None else None
    except (TypeError, ValueError):
        elapsed_ms = None

    return {
        "captured_at": record.get("captured_at"),
        "elapsed_ms": elapsed_ms,
        "status": record.get("status"),
        "url": url,
        "host": urlparse(url).netloc,
        "resource_type": record.get("resource_type"),
        "content_type": extract_content_type(record),
        "normalized_path": normalize_endpoint_path(query_url or url),
        "endpoint_key": endpoint_key,
        "query_url": query_url,
        "doc_event": extract_doc_event_name(body_json),
        "maxage_seconds": extract_doc_maxage_seconds(body_json),
        "body_json": body_json,
        "preview": preview,
        "body_size_bytes": body_size_bytes,
        "top_level_keys": extract_top_level_keys(payload_for_summary),
        "match_ids": extract_match_ids(payload_for_summary),
    }


def _new_index_bucket(example_url: str) -> dict[str, Any]:
    return {
        "count": 0,
        "first_seen_ms": None,
        "last_seen_ms": None,
        "statuses": Counter(),
        "resource_types": Counter(),
        "content_types": Counter(),
        "top_level_keys": Counter(),
        "query_urls": [],
        "_query_urls_seen": set(),
        "normalized_paths": [],
        "_normalized_paths_seen": set(),
        "doc_events": [],
        "_doc_events_seen": set(),
        "match_ids": [],
        "_match_ids_seen": set(),
        "maxage_seconds": [],
        "_maxage_seen": set(),
        "body_size_total_bytes": 0,
        "body_size_min_bytes": None,
        "body_size_max_bytes": 0,
        "example_url": example_url,
        "has_json": False,
    }


def update_endpoint_index(
    buckets: dict[str, dict[str, Any]],
    filtered_record: dict[str, Any],
) -> None:
    endpoint_key = str(filtered_record.get("endpoint_key") or "").strip()
    if not endpoint_key:
        return

    bucket = buckets.setdefault(
        endpoint_key,
        _new_index_bucket(str(filtered_record.get("url") or "")),
    )
    bucket["count"] += 1

    elapsed_ms = filtered_record.get("elapsed_ms")
    if isinstance(elapsed_ms, (int, float)):
        first_seen = bucket["first_seen_ms"]
        last_seen = bucket["last_seen_ms"]
        if first_seen is None or elapsed_ms < first_seen:
            bucket["first_seen_ms"] = elapsed_ms
        if last_seen is None or elapsed_ms > last_seen:
            bucket["last_seen_ms"] = elapsed_ms

    status_key = str(filtered_record.get("status") or "")
    if status_key:
        bucket["statuses"][status_key] += 1

    resource_type = str(filtered_record.get("resource_type") or "").strip()
    if resource_type:
        bucket["resource_types"][resource_type] += 1

    content_type = str(filtered_record.get("content_type") or "").strip()
    if content_type:
        bucket["content_types"][content_type] += 1

    for key in filtered_record.get("top_level_keys") or []:
        bucket["top_level_keys"][str(key)] += 1

    body_size_bytes = filtered_record.get("body_size_bytes")
    if isinstance(body_size_bytes, int):
        bucket["body_size_total_bytes"] += body_size_bytes
        if bucket["body_size_min_bytes"] is None:
            bucket["body_size_min_bytes"] = body_size_bytes
        else:
            bucket["body_size_min_bytes"] = min(bucket["body_size_min_bytes"], body_size_bytes)
        bucket["body_size_max_bytes"] = max(bucket["body_size_max_bytes"], body_size_bytes)

    if filtered_record.get("body_json") is not None:
        bucket["has_json"] = True

    query_url = str(filtered_record.get("query_url") or "").strip()
    if query_url and query_url not in bucket["_query_urls_seen"]:
        bucket["_query_urls_seen"].add(query_url)
        bucket["query_urls"].append(query_url)

    normalized_path = str(filtered_record.get("normalized_path") or "").strip()
    if normalized_path and normalized_path not in bucket["_normalized_paths_seen"]:
        bucket["_normalized_paths_seen"].add(normalized_path)
        bucket["normalized_paths"].append(normalized_path)

    doc_event = str(filtered_record.get("doc_event") or "").strip()
    if doc_event and doc_event not in bucket["_doc_events_seen"]:
        bucket["_doc_events_seen"].add(doc_event)
        bucket["doc_events"].append(doc_event)

    for match_id in filtered_record.get("match_ids") or []:
        normalized_match_id = str(match_id).strip()
        if not normalized_match_id or normalized_match_id in bucket["_match_ids_seen"]:
            continue
        bucket["_match_ids_seen"].add(normalized_match_id)
        bucket["match_ids"].append(normalized_match_id)

    maxage_seconds = filtered_record.get("maxage_seconds")
    if isinstance(maxage_seconds, int) and maxage_seconds not in bucket["_maxage_seen"]:
        bucket["_maxage_seen"].add(maxage_seconds)
        bucket["maxage_seconds"].append(maxage_seconds)


def infer_polling_behavior_from_index(
    endpoint_key: str,
    bucket: dict[str, Any],
) -> tuple[bool, str]:
    reasons: list[str] = []
    if int(bucket.get("count") or 0) > 1:
        reasons.append("repeated_requests")
    if any(int(value) <= 60 for value in bucket.get("maxage_seconds") or []):
        reasons.append("short_maxage")
    if endpoint_key in LIVE_ENDPOINT_HINTS:
        reasons.append("live_endpoint_name")

    if not reasons:
        return False, "single_request"
    return True, "+".join(reasons)


def finalize_endpoint_index(
    buckets: dict[str, dict[str, Any]],
    *,
    source_file: str,
    filtered_records_count: int,
) -> dict[str, Any]:
    finalized_endpoints: dict[str, Any] = {}

    for endpoint_key in sorted(buckets):
        bucket = buckets[endpoint_key]
        polling_likely, polling_reason = infer_polling_behavior_from_index(endpoint_key, bucket)
        count = int(bucket.get("count") or 0)
        average_body_size = 0.0
        if count:
            average_body_size = round(
                bucket["body_size_total_bytes"] / count,
                2,
            )

        finalized_endpoints[endpoint_key] = {
            "count": count,
            "first_seen_ms": round(bucket["first_seen_ms"], 2)
            if isinstance(bucket.get("first_seen_ms"), (int, float))
            else None,
            "last_seen_ms": round(bucket["last_seen_ms"], 2)
            if isinstance(bucket.get("last_seen_ms"), (int, float))
            else None,
            "statuses": dict(sorted(bucket["statuses"].items())),
            "body_size_min_bytes": bucket["body_size_min_bytes"] or 0,
            "body_size_max_bytes": bucket["body_size_max_bytes"] or 0,
            "body_size_avg_bytes": average_body_size,
            "example_url": bucket["example_url"],
            "has_json": bool(bucket["has_json"]),
            "top_level_keys": [
                key
                for key, _ in bucket["top_level_keys"].most_common(20)
            ],
            "query_urls": bucket["query_urls"][:5],
            "normalized_paths": bucket["normalized_paths"][:5],
            "resource_types": dict(sorted(bucket["resource_types"].items())),
            "content_types": dict(sorted(bucket["content_types"].items())),
            "doc_events": bucket["doc_events"][:5],
            "match_ids": bucket["match_ids"][:10],
            "maxage_seconds": sorted(bucket["maxage_seconds"]),
            "repeated": count > 1,
            "polling_likely": polling_likely,
            "polling_reason": polling_reason,
        }

    return {
        "source_file": source_file,
        "filtered_records_count": filtered_records_count,
        "endpoint_count": len(finalized_endpoints),
        "endpoints": finalized_endpoints,
    }


def filter_capture_directory(
    capture_dir: Path,
    *,
    write_json: bool = False,
) -> dict[str, Any]:
    responses_path = capture_dir / "responses.ndjson"
    filtered_ndjson_path = capture_dir / "filtered_fetch.ndjson"
    filtered_json_path = capture_dir / "filtered_fetch.json"
    endpoints_index_path = capture_dir / "endpoints_index.json"

    buckets: dict[str, dict[str, Any]] = {}
    filtered_records_count = 0
    filtered_records: list[dict[str, Any]] | None = [] if write_json else None

    with filtered_ndjson_path.open("w", encoding="utf-8") as filtered_handle:
        for raw_record in iter_ndjson_records(responses_path):
            filtered_record = normalize_filtered_record(raw_record)
            if filtered_record is None:
                continue

            filtered_handle.write(json.dumps(filtered_record, ensure_ascii=False))
            filtered_handle.write("\n")
            update_endpoint_index(buckets, filtered_record)
            filtered_records_count += 1

            if filtered_records is not None:
                filtered_records.append(filtered_record)

    endpoints_index = finalize_endpoint_index(
        buckets,
        source_file=str(responses_path),
        filtered_records_count=filtered_records_count,
    )
    endpoints_index_path.write_text(
        json.dumps(endpoints_index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if filtered_records is not None:
        filtered_json_path.write_text(
            json.dumps(filtered_records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return {
        "responses_path": responses_path,
        "filtered_ndjson_path": filtered_ndjson_path,
        "filtered_json_path": filtered_json_path if write_json else None,
        "endpoints_index_path": endpoints_index_path,
        "filtered_records_count": filtered_records_count,
        "endpoint_count": endpoints_index["endpoint_count"],
    }


__all__ = [
    "STATIC_ASSET_EXTENSIONS",
    "USEFUL_RESOURCE_TYPES",
    "compact_json_example",
    "extract_content_type",
    "extract_doc0",
    "extract_doc_data",
    "extract_doc_event_name",
    "extract_doc_maxage_seconds",
    "extract_endpoint_key_from_path",
    "extract_match_ids",
    "extract_query_url",
    "extract_top_level_keys",
    "filter_capture_directory",
    "finalize_endpoint_index",
    "infer_polling_behavior_from_index",
    "is_static_asset_url",
    "iter_ndjson_records",
    "normalize_filtered_record",
    "should_keep_capture_record",
    "update_endpoint_index",
]

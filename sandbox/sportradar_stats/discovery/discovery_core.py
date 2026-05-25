"""Pure helpers for mapping Sportradar / Statshub discovery endpoints."""

from __future__ import annotations

from collections import Counter
import json
import re
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse


ALLOWED_RESOURCE_TYPES = {"fetch", "xhr", "document"}
STATIC_EXTENSIONS = (
    ".css",
    ".gif",
    ".ico",
    ".jpg",
    ".jpeg",
    ".js",
    ".map",
    ".png",
    ".svg",
    ".ttf",
    ".webp",
    ".woff",
    ".woff2",
)
STATIC_TOKENS = (
    "/assets/",
    "/fonts/",
    "/static/",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
)
SPORTRADAR_HOST_TOKENS = (
    "sportradar.com",
    "sportradarserving.com",
)
ID_SEGMENT_RE = re.compile(r"^\d+$")
HEXISH_RE = re.compile(r"^[0-9a-f]{10,}$", re.IGNORECASE)


ROLE_HINTS = {
    "navigation": ("config", "tree", "menu"),
    "sport": ("sport", "sports"),
    "league": ("league", "tournament", "competition", "category", "season", "realcategories", "uniquetournament"),
    "fixture": ("fixture", "schedule", "calendar", "matches", "matchlist"),
    "match": ("match", "event"),
    "standings": ("standing", "table"),
    "team": ("team", "competitor"),
    "player": ("player", "lineup", "squad"),
    "odds": ("odds", "market", "probability"),
    "live": ("timeline", "timelinedelta", "live"),
}


def is_static_asset_url(url: str) -> bool:
    normalized = str(url or "").strip().lower()
    if not normalized:
        return False
    if any(token in normalized for token in STATIC_TOKENS):
        return True
    return urlparse(normalized).path.endswith(STATIC_EXTENSIONS)


def is_sportradar_url(url: str) -> bool:
    host = urlparse(str(url or "")).netloc.lower()
    return any(token in host for token in SPORTRADAR_HOST_TOKENS)


def safe_json_loads(raw: str) -> object | None:
    text = raw.strip()
    if not text or text[0] not in "[{":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def extract_query_url(body_json: object | None) -> str | None:
    if isinstance(body_json, dict):
        value = body_json.get("queryUrl")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_doc0(body_json: object | None) -> dict[str, Any] | None:
    if not isinstance(body_json, dict):
        return None
    doc = body_json.get("doc")
    if not isinstance(doc, list) or not doc:
        return None
    first = doc[0]
    return first if isinstance(first, dict) else None


def extract_doc_data(body_json: object | None) -> object | None:
    doc0 = extract_doc0(body_json)
    return doc0.get("data") if isinstance(doc0, dict) else None


def extract_doc_event(body_json: object | None) -> str | None:
    doc0 = extract_doc0(body_json)
    if not isinstance(doc0, dict):
        return None
    event = doc0.get("event")
    if isinstance(event, str) and event.strip():
        return event.strip()
    return None


def split_endpoint_segments(url_or_path: str) -> list[str]:
    parsed = urlparse(str(url_or_path or ""))
    path = parsed.path or str(url_or_path or "")
    return [segment for segment in path.split("/") if segment]


def extract_endpoint_name(url: str, body_json: object | None = None) -> str | None:
    query_url = extract_query_url(body_json)
    candidates = [query_url, url]
    for candidate in candidates:
        if not candidate:
            continue
        segments = split_endpoint_segments(candidate)
        if "gismo" in segments:
            index = segments.index("gismo")
            if index + 1 < len(segments):
                return segments[index + 1]
        if segments:
            first = segments[0]
            if first not in {"bet365", "en", "Etc:UTC"}:
                return first
    return None


def normalize_endpoint_path(url: str, body_json: object | None = None) -> str:
    query_url = extract_query_url(body_json)
    candidate = query_url or url
    segments = split_endpoint_segments(candidate)
    normalized: list[str] = []
    for segment in segments:
        if ID_SEGMENT_RE.fullmatch(segment):
            normalized.append(":id")
        elif HEXISH_RE.fullmatch(segment):
            normalized.append(":hex")
        else:
            normalized.append(segment)
    return "/" + "/".join(normalized) if normalized else "/"


def should_capture_response(url: str, resource_type: str, body_json: object | None = None) -> bool:
    resource = str(resource_type or "").lower()
    if resource not in ALLOWED_RESOURCE_TYPES:
        return False
    if not is_sportradar_url(url) or is_static_asset_url(url):
        return False

    parsed = urlparse(url)
    path = parsed.path.lower()
    content_endpoint = extract_endpoint_name(url, body_json)
    if "/gismo/" in path or content_endpoint:
        return True
    return resource == "document" and "statshub.sportradar.com" in parsed.netloc.lower()


def compact_json(value: object, *, max_depth: int = 3, max_items: int = 5) -> object:
    if max_depth < 0:
        return "..."
    if isinstance(value, dict):
        return {
            str(key): compact_json(child, max_depth=max_depth - 1, max_items=max_items)
            for key, child in list(value.items())[:max_items]
        }
    if isinstance(value, list):
        return [
            compact_json(item, max_depth=max_depth - 1, max_items=max_items)
            for item in value[:max_items]
        ]
    if isinstance(value, str):
        return value[:160]
    return value


def extract_id_patterns(url: str, body_json: object | None = None) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {
        "path_ids": [],
        "query_ids": [],
        "payload_ids": [],
    }

    def add(bucket: str, value: object) -> None:
        text = str(value or "").strip()
        if not text or not text.isdigit():
            return
        if text not in buckets[bucket]:
            buckets[bucket].append(text)

    for segment in split_endpoint_segments(extract_query_url(body_json) or url):
        if ID_SEGMENT_RE.fullmatch(segment):
            add("path_ids", segment)

    for values in parse_qs(urlparse(url).query).values():
        for value in values:
            add("query_ids", value)

    payload = extract_doc_data(body_json)
    if payload is None:
        payload = body_json

    def visit(value: object, depth: int = 0) -> None:
        if depth > 5 or len(buckets["payload_ids"]) >= 40:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                normalized_key = str(key).lower()
                if normalized_key in {"id", "_id", "matchid", "match_id", "sportid", "sport_id", "tournamentid", "tournament_id", "seasonid", "season_id"}:
                    add("payload_ids", child)
                visit(child, depth + 1)
            return
        if isinstance(value, list):
            for item in value[:20]:
                visit(item, depth + 1)

    visit(payload)
    return {key: values[:20] for key, values in buckets.items()}


def infer_roles(endpoint_name: str | None, normalized_path: str, body_json: object | None = None) -> list[str]:
    haystack_parts = [endpoint_name or "", normalized_path]
    doc_event = extract_doc_event(body_json)
    if doc_event:
        haystack_parts.append(doc_event)
    payload = extract_doc_data(body_json)
    if isinstance(payload, dict):
        haystack_parts.extend(str(key) for key in list(payload.keys())[:20])
    haystack = " ".join(haystack_parts).lower()

    roles: list[str] = []
    for role, hints in ROLE_HINTS.items():
        if any(hint in haystack for hint in hints):
            roles.append(role)
    return roles


def summarize_body_json(body_json: object | None) -> dict[str, Any]:
    doc_data = extract_doc_data(body_json)
    payload = doc_data if doc_data is not None else body_json
    top_level_keys: list[str] = []
    if isinstance(payload, dict):
        top_level_keys = [str(key) for key in list(payload.keys())[:30]]
    elif isinstance(payload, list) and payload and isinstance(payload[0], dict):
        top_level_keys = [str(key) for key in list(payload[0].keys())[:30]]

    return {
        "has_json": body_json is not None,
        "doc_event": extract_doc_event(body_json),
        "query_url": extract_query_url(body_json),
        "top_level_keys": top_level_keys,
        "example": compact_json(payload, max_depth=2, max_items=4),
    }


def build_discovery_record(raw: dict[str, Any]) -> dict[str, Any] | None:
    url = str(raw.get("url") or "").strip()
    resource_type = str(raw.get("resource_type") or "").strip().lower()
    body_json = raw.get("body_json")
    if not should_capture_response(url, resource_type, body_json):
        return None

    endpoint_name = extract_endpoint_name(url, body_json)
    normalized_path = normalize_endpoint_path(url, body_json)
    params = {
        key: values[:5]
        for key, values in parse_qs(urlparse(url).query).items()
    }
    return {
        "captured_at": raw.get("captured_at"),
        "elapsed_ms": raw.get("elapsed_ms"),
        "method": raw.get("method"),
        "status": raw.get("status"),
        "resource_type": resource_type,
        "url": url,
        "host": urlparse(url).netloc,
        "params": params,
        "endpoint_name": endpoint_name,
        "endpoint_key": endpoint_name or normalized_path,
        "normalized_path": normalized_path,
        "roles": infer_roles(endpoint_name, normalized_path, body_json),
        "id_patterns": extract_id_patterns(url, body_json),
        "body_size_bytes": raw.get("body_size_bytes") or 0,
        "response_json_summary": summarize_body_json(body_json),
        "preview": raw.get("preview"),
        "content_type": raw.get("content_type"),
    }


def build_endpoints_index(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, dict[str, Any]] = {}
    total = 0
    for record in records:
        total += 1
        key = str(record.get("endpoint_key") or record.get("normalized_path") or "unknown")
        bucket = buckets.setdefault(
            key,
            {
                "count": 0,
                "statuses": Counter(),
                "resource_types": Counter(),
                "roles": Counter(),
                "hosts": Counter(),
                "normalized_paths": [],
                "_normalized_paths_seen": set(),
                "example_url": record.get("url"),
                "body_size_min_bytes": None,
                "body_size_max_bytes": 0,
                "body_size_total_bytes": 0,
                "id_patterns": {"path_ids": [], "query_ids": [], "payload_ids": []},
                "top_level_keys": Counter(),
                "doc_events": Counter(),
                "query_urls": [],
                "_query_urls_seen": set(),
            },
        )
        bucket["count"] += 1
        bucket["statuses"][str(record.get("status") or "")] += 1
        bucket["resource_types"][str(record.get("resource_type") or "")] += 1
        bucket["hosts"][str(record.get("host") or "")] += 1
        roles = set(str(role) for role in (record.get("roles") or []))
        summary = record.get("response_json_summary") or {}
        if isinstance(summary, dict):
            fake_payload = {
                "doc": [
                    {
                        "event": summary.get("doc_event"),
                        "data": {str(key): None for key in (summary.get("top_level_keys") or [])},
                    }
                ]
            }
            roles.update(
                infer_roles(
                    str(record.get("endpoint_key") or ""),
                    str(record.get("normalized_path") or ""),
                    fake_payload,
                )
            )

        for role in sorted(roles):
            bucket["roles"][str(role)] += 1
        path = str(record.get("normalized_path") or "")
        if path and path not in bucket["_normalized_paths_seen"]:
            bucket["_normalized_paths_seen"].add(path)
            bucket["normalized_paths"].append(path)

        size = int(record.get("body_size_bytes") or 0)
        bucket["body_size_total_bytes"] += size
        bucket["body_size_max_bytes"] = max(bucket["body_size_max_bytes"], size)
        if bucket["body_size_min_bytes"] is None:
            bucket["body_size_min_bytes"] = size
        else:
            bucket["body_size_min_bytes"] = min(bucket["body_size_min_bytes"], size)

        id_patterns = record.get("id_patterns") or {}
        for id_kind in ("path_ids", "query_ids", "payload_ids"):
            for value in id_patterns.get(id_kind) or []:
                text = str(value)
                if text not in bucket["id_patterns"][id_kind]:
                    bucket["id_patterns"][id_kind].append(text)

        for key_name in summary.get("top_level_keys") or []:
            bucket["top_level_keys"][str(key_name)] += 1
        doc_event = summary.get("doc_event")
        if doc_event:
            bucket["doc_events"][str(doc_event)] += 1
        query_url = summary.get("query_url")
        if query_url and query_url not in bucket["_query_urls_seen"]:
            bucket["_query_urls_seen"].add(query_url)
            bucket["query_urls"].append(query_url)

    endpoints: dict[str, Any] = {}
    for key in sorted(buckets):
        bucket = buckets[key]
        count = int(bucket["count"])
        endpoints[key] = {
            "count": count,
            "statuses": dict(sorted(bucket["statuses"].items())),
            "resource_types": dict(sorted(bucket["resource_types"].items())),
            "hosts": dict(sorted(bucket["hosts"].items())),
            "roles": dict(bucket["roles"].most_common()),
            "normalized_paths": bucket["normalized_paths"][:10],
            "example_url": bucket["example_url"],
            "body_size_min_bytes": bucket["body_size_min_bytes"] or 0,
            "body_size_max_bytes": bucket["body_size_max_bytes"],
            "body_size_avg_bytes": round(bucket["body_size_total_bytes"] / count, 2) if count else 0,
            "id_patterns": {
                kind: values[:20]
                for kind, values in bucket["id_patterns"].items()
            },
            "top_level_keys": [key_name for key_name, _ in bucket["top_level_keys"].most_common(20)],
            "doc_events": dict(bucket["doc_events"].most_common()),
            "query_urls": bucket["query_urls"][:10],
            "repeated": count > 1,
        }

    role_counts: Counter[str] = Counter()
    for endpoint in endpoints.values():
        role_counts.update(endpoint.get("roles") or {})

    return {
        "records_count": total,
        "endpoint_count": len(endpoints),
        "role_counts": dict(role_counts.most_common()),
        "endpoints": endpoints,
    }


def write_endpoint_report(index: dict[str, Any]) -> str:
    lines = [
        "# Sportradar / Statshub Discovery Endpoint Report",
        "",
        f"- Records: `{index.get('records_count', 0)}`",
        f"- Endpoints: `{index.get('endpoint_count', 0)}`",
        "",
        "## Role Coverage",
        "",
    ]
    role_counts = index.get("role_counts") or {}
    if role_counts:
        for role, count in role_counts.items():
            lines.append(f"- `{role}`: {count}")
    else:
        lines.append("- No roles detected.")

    lines.extend(["", "## Endpoints", ""])
    endpoints = index.get("endpoints") or {}
    for endpoint_key, endpoint in endpoints.items():
        roles = ", ".join(f"{role}={count}" for role, count in (endpoint.get("roles") or {}).items()) or "-"
        lines.extend(
            [
                f"### `{endpoint_key}`",
                "",
                f"- Count: `{endpoint.get('count')}`",
                f"- Statuses: `{endpoint.get('statuses')}`",
                f"- Roles: `{roles}`",
                f"- Paths: `{endpoint.get('normalized_paths')}`",
                f"- Query URLs: `{endpoint.get('query_urls')}`",
                f"- ID patterns: `{endpoint.get('id_patterns')}`",
                f"- Top-level keys: `{endpoint.get('top_level_keys')}`",
                f"- Example URL: `{endpoint.get('example_url')}`",
                "",
            ]
        )

    lines.extend(
        [
            "## Initial Conclusions",
            "",
            "- Endpoints with `sport`, `league`, `fixture`, `schedule`, or `standings` roles are candidates for browserless discovery.",
            "- Repeated signed URLs with `T=exp=...` should be treated as reusable only within their signature window until HTTP probing confirms otherwise.",
            "- This report intentionally maps API shape only; it does not normalize full fixtures or integrate with BetBot.",
        ]
    )
    return "\n".join(lines) + "\n"

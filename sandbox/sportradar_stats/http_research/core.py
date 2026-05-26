"""Pure helpers for Statshub/Sportradar HTTP replay research."""

from __future__ import annotations

import base64
from collections import Counter
from datetime import UTC, datetime
import json
import re
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote, urlencode, urlparse, urlunparse


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
STATIC_TOKENS = ("/assets/", "/fonts/", "/static/", "fonts.googleapis.com", "fonts.gstatic.com")
SPORTRADAR_HOST_TOKENS = ("sportradar.com", "sportradarserving.com")
IMPORTANT_HEADER_PREFIXES = ("x-",)
IMPORTANT_HEADERS = {
    "accept",
    "accept-language",
    "content-type",
    "origin",
    "referer",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "user-agent",
}
ID_RE = re.compile(r"^\d+$")
HEXISH_RE = re.compile(r"^[0-9a-f]{12,}$", re.IGNORECASE)


ENDPOINT_CLASSIFICATION: dict[str, set[str]] = {
    "config_tree_mini": {"discovery", "sport", "league"},
    "config_uniquetournamentsall": {"discovery", "league"},
    "unified_sport_matches": {"discovery", "fixtures", "prematch"},
    "unified_sport_matches_markets": {"discovery", "fixtures", "odds", "prematch"},
    "sport_matches_prevnext": {"discovery", "fixtures"},
    "stats_sport_matches_prevnext": {"discovery", "fixtures", "stats"},
    "event_get": {"match", "live_state"},
    "odds_ukformat": {"odds", "config"},
    "match_info_statshub": {"match", "prematch", "stats"},
    "stats_match_get": {"match", "prematch", "stats", "live_state"},
    "match_timeline": {"match", "live_state", "timeline"},
    "match_timelinedelta": {"match", "live_state", "timeline"},
    "match_details": {"match", "prematch", "stats"},
    "match_markets": {"match", "odds"},
    "stats_match_tableslice": {"match", "standings", "stats"},
    "stats_match_head2head": {"match", "h2h", "stats"},
    "stats_h2h_versus": {"h2h", "stats"},
    "stats_team_lastx": {"team", "form", "stats"},
    "stats_team_nextx": {"team", "fixtures", "stats"},
    "stats_team_versus": {"team", "h2h", "stats"},
    "stats_season_tables": {"league", "standings", "historical", "stats"},
    "stats_formtable": {"league", "form", "historical", "stats"},
    "stats_season_topgoals": {"league", "players", "historical", "stats"},
    "stats_season_topcards": {"league", "players", "historical", "stats"},
    "stats_season_topassists": {"league", "players", "historical", "stats"},
    "stats_season_teamscoringconceding": {"league", "team", "historical", "stats"},
    "stats_team_streaks": {"team", "form", "historical", "stats"},
    "stats_season_injuries": {"league", "injuries", "historical", "stats"},
    "uniqueteam_markets": {"team", "odds"},
}


def safe_json_loads(raw: str) -> object | None:
    text = raw.strip()
    if not text or text[0] not in "[{":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


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


def select_important_headers(headers: dict[str, str] | None) -> dict[str, str]:
    selected: dict[str, str] = {}
    for raw_key, raw_value in (headers or {}).items():
        key = str(raw_key).strip().lower()
        value = str(raw_value).strip()
        if not key or not value:
            continue
        if key in IMPORTANT_HEADERS or any(key.startswith(prefix) for prefix in IMPORTANT_HEADER_PREFIXES):
            selected[key] = value
    return dict(sorted(selected.items()))


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
    event = doc0.get("event") if isinstance(doc0, dict) else None
    if isinstance(event, str) and event.strip():
        return event.strip()
    return None


def split_segments(url_or_path: str) -> list[str]:
    parsed = urlparse(str(url_or_path or ""))
    path = parsed.path or str(url_or_path or "")
    return [unquote(segment) for segment in path.split("/") if segment]


def extract_gismo_endpoint_key(url_or_path: str, body_json: object | None = None) -> str | None:
    query_url = extract_query_url(body_json)
    candidates = [query_url, url_or_path]
    for candidate in candidates:
        if not candidate:
            continue
        segments = split_segments(candidate)
        if "gismo" in segments:
            index = segments.index("gismo")
            if index + 1 < len(segments):
                return segments[index + 1]
        if query_url and segments:
            return segments[0]
    return None


def normalize_endpoint_path(url_or_path: str, body_json: object | None = None) -> str:
    candidate = extract_query_url(body_json) or url_or_path
    normalized: list[str] = []
    for segment in split_segments(candidate):
        if ID_RE.fullmatch(segment):
            normalized.append(":id")
        elif HEXISH_RE.fullmatch(segment):
            normalized.append(":hex")
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", segment):
            normalized.append(":date")
        else:
            normalized.append(segment)
    return "/" + "/".join(normalized) if normalized else "/"


def parse_signed_t(raw_t: str | None) -> dict[str, Any] | None:
    raw = str(raw_t or "").strip()
    if not raw:
        return None

    parts: dict[str, str] = {}
    for segment in raw.split("~"):
        if "=" not in segment:
            continue
        key, value = segment.split("=", 1)
        parts[key] = value

    exp = _safe_int(parts.get("exp"))
    data_json = decode_token_data(parts.get("data"))
    expires_at = datetime.fromtimestamp(exp, tz=UTC).isoformat() if exp else None
    return {
        "raw": raw,
        "exp": exp,
        "expires_at_utc": expires_at,
        "acl": parts.get("acl"),
        "data_raw": parts.get("data"),
        "data_json": data_json,
        "hmac": parts.get("hmac"),
        "parts": parts,
    }


def parse_signed_t_from_url(url: str) -> dict[str, Any] | None:
    values = parse_qs(urlparse(url).query).get("T")
    if not values:
        return None
    return parse_signed_t(values[0])


def decode_token_data(raw_data: str | None) -> object | None:
    raw = str(raw_data or "").strip()
    if not raw:
        return None
    decoded_text = None
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            padded = raw + "=" * (-len(raw) % 4)
            decoded_text = decoder(padded.encode("utf-8")).decode("utf-8")
            break
        except Exception:
            continue
    if decoded_text is None:
        return None
    try:
        return json.loads(decoded_text)
    except json.JSONDecodeError:
        return {"decoded_text": decoded_text}


def classify_endpoint(endpoint_key: str | None, normalized_path: str = "") -> list[str]:
    key = str(endpoint_key or "").strip()
    labels = set(ENDPOINT_CLASSIFICATION.get(key, set()))
    haystack = f"{key} {normalized_path}".lower()
    if "timeline" in haystack:
        labels.update({"live_state", "timeline"})
    if "market" in haystack or "odds" in haystack:
        labels.add("odds")
    if "table" in haystack or "standing" in haystack:
        labels.add("standings")
    if "season" in haystack:
        labels.add("historical")
    if "match" in haystack or "event" in haystack:
        labels.add("match")
    if "sport" in haystack:
        labels.add("sport")
    if any(token in haystack for token in ("tournament", "league", "competition", "category")):
        labels.add("league")
    if any(token in haystack for token in ("fixture", "schedule", "prevnext")):
        labels.add("fixtures")
    return sorted(labels)


def should_keep_url(url: str, resource_type: str, body_json: object | None = None) -> bool:
    resource = str(resource_type or "").strip().lower()
    if resource not in {"fetch", "xhr", "document"}:
        return False
    if not is_sportradar_url(url) or is_static_asset_url(url):
        return False
    parsed = urlparse(url)
    path = parsed.path.lower()
    if "/gismo/" in path or extract_query_url(body_json):
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
        return [compact_json(item, max_depth=max_depth - 1, max_items=max_items) for item in value[:max_items]]
    if isinstance(value, str):
        return value[:180]
    return value


def summarize_json(body_json: object | None) -> dict[str, Any]:
    doc_data = extract_doc_data(body_json)
    payload = doc_data if doc_data is not None else body_json
    top_level_keys: list[str] = []
    if isinstance(payload, dict):
        top_level_keys = [str(key) for key in list(payload.keys())[:40]]
    elif isinstance(payload, list) and payload and isinstance(payload[0], dict):
        top_level_keys = [str(key) for key in list(payload[0].keys())[:40]]
    return {
        "has_json": body_json is not None,
        "query_url": extract_query_url(body_json),
        "doc_event": extract_doc_event(body_json),
        "top_level_keys": top_level_keys,
        "example": compact_json(payload, max_depth=2, max_items=4),
    }


def build_endpoint_record(raw_record: dict[str, Any]) -> dict[str, Any] | None:
    url = str(raw_record.get("url") or "").strip()
    resource_type = str(raw_record.get("resource_type") or "").lower()
    body_json = raw_record.get("body_json")
    if not should_keep_url(url, resource_type, body_json):
        return None
    endpoint_key = extract_gismo_endpoint_key(url, body_json)
    normalized_path = normalize_endpoint_path(url, body_json)
    token = parse_signed_t_from_url(url)
    return {
        "captured_at": raw_record.get("captured_at"),
        "elapsed_ms": raw_record.get("elapsed_ms"),
        "method": raw_record.get("method") or "GET",
        "url": url,
        "host": urlparse(url).netloc,
        "path": urlparse(url).path,
        "normalized_path": normalized_path,
        "query_params": {key: values[:5] for key, values in parse_qs(urlparse(url).query).items()},
        "endpoint_key": endpoint_key or normalized_path,
        "gismo_endpoint": endpoint_key,
        "classification": classify_endpoint(endpoint_key, normalized_path),
        "signed_token": token,
        "has_signed_token": token is not None,
        "request_headers": select_important_headers(raw_record.get("request_headers")),
        "cookies": raw_record.get("cookies") or [],
        "status": raw_record.get("status"),
        "content_type": raw_record.get("content_type"),
        "response_headers": select_important_headers(raw_record.get("response_headers")),
        "body_size_bytes": raw_record.get("body_size_bytes") or 0,
        "body_json": body_json,
        "response_json_summary": summarize_json(body_json),
        "preview": raw_record.get("preview"),
        "resource_type": resource_type,
    }


def build_endpoint_catalog(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, dict[str, Any]] = {}
    total = 0
    for record in records:
        total += 1
        key = str(record.get("endpoint_key") or "unknown")
        bucket = buckets.setdefault(
            key,
            {
                "count": 0,
                "statuses": Counter(),
                "resource_types": Counter(),
                "classifications": Counter(),
                "example_url": record.get("url"),
                "hosts": Counter(),
                "normalized_paths": [],
                "_normalized_paths_seen": set(),
                "query_urls": [],
                "_query_urls_seen": set(),
                "has_signed_token": False,
                "token_data_examples": [],
                "body_size_min_bytes": None,
                "body_size_max_bytes": 0,
                "body_size_total_bytes": 0,
                "top_level_keys": Counter(),
            },
        )
        bucket["count"] += 1
        bucket["statuses"][str(record.get("status") or "")] += 1
        bucket["resource_types"][str(record.get("resource_type") or "")] += 1
        bucket["hosts"][str(record.get("host") or "")] += 1
        for label in record.get("classification") or []:
            bucket["classifications"][str(label)] += 1
        path = str(record.get("normalized_path") or "")
        if path and path not in bucket["_normalized_paths_seen"]:
            bucket["_normalized_paths_seen"].add(path)
            bucket["normalized_paths"].append(path)
        summary = record.get("response_json_summary") or {}
        query_url = summary.get("query_url")
        if query_url and query_url not in bucket["_query_urls_seen"]:
            bucket["_query_urls_seen"].add(query_url)
            bucket["query_urls"].append(query_url)
        if record.get("has_signed_token"):
            bucket["has_signed_token"] = True
            token_data = ((record.get("signed_token") or {}).get("data_json") if isinstance(record.get("signed_token"), dict) else None)
            if token_data is not None and token_data not in bucket["token_data_examples"]:
                bucket["token_data_examples"].append(token_data)
        size = _safe_int(record.get("body_size_bytes")) or 0
        bucket["body_size_total_bytes"] += size
        bucket["body_size_max_bytes"] = max(bucket["body_size_max_bytes"], size)
        bucket["body_size_min_bytes"] = size if bucket["body_size_min_bytes"] is None else min(bucket["body_size_min_bytes"], size)
        for key_name in summary.get("top_level_keys") or []:
            bucket["top_level_keys"][str(key_name)] += 1

    endpoints: dict[str, Any] = {}
    classification_counts: Counter[str] = Counter()
    for key in sorted(buckets):
        bucket = buckets[key]
        count = int(bucket["count"])
        classification_counts.update(bucket["classifications"])
        endpoints[key] = {
            "count": count,
            "statuses": dict(sorted(bucket["statuses"].items())),
            "resource_types": dict(sorted(bucket["resource_types"].items())),
            "classifications": dict(bucket["classifications"].most_common()),
            "hosts": dict(sorted(bucket["hosts"].items())),
            "example_url": bucket["example_url"],
            "normalized_paths": bucket["normalized_paths"][:12],
            "query_urls": bucket["query_urls"][:12],
            "has_signed_token": bool(bucket["has_signed_token"]),
            "token_data_examples": bucket["token_data_examples"][:3],
            "body_size_min_bytes": bucket["body_size_min_bytes"] or 0,
            "body_size_max_bytes": bucket["body_size_max_bytes"],
            "body_size_avg_bytes": round(bucket["body_size_total_bytes"] / count, 2) if count else 0,
            "top_level_keys": [name for name, _ in bucket["top_level_keys"].most_common(25)],
        }
    return {
        "records_count": total,
        "endpoint_count": len(endpoints),
        "classification_counts": dict(classification_counts.most_common()),
        "endpoints": endpoints,
    }


def replace_endpoint_path_in_signed_url(url: str, new_gismo_path: str) -> str:
    """Replace only the `/gismo/...` path while preserving the signed query."""

    parsed = urlparse(url)
    segments = parsed.path.split("/")
    try:
        index = segments.index("gismo")
    except ValueError:
        return url
    prefix = "/".join(segments[: index + 1])
    path = f"{prefix}/{new_gismo_path.strip('/')}"
    return urlunparse(parsed._replace(path=path))


def strip_query(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(query=""))


def rebuild_query(url: str, params: dict[str, Any]) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))


def _safe_int(value: object) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

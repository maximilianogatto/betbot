from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_MARKERS = (
    "EV",
    "MG",
    "MA",
    "PA",
    "NavLib",
    "DataReactLib",
    "CurrentPageData",
    "getStemFromLookup",
    "40",
    "981",
    "938",
    "10143",
)

TEXTUAL_CONTENT_HINTS = (
    "json",
    "javascript",
    "text/",
    "xml",
    "html",
    "svg",
    "x-www-form-urlencoded",
)

SKIP_REQUEST_HEADERS = {
    "host",
    "content-length",
    "connection",
    "accept-encoding",
    "cookie",
    "authorization",
    ":authority",
    ":method",
    ":path",
    ":scheme",
}

SKIP_RESPONSE_HEADERS = {
    "content-encoding",
    "transfer-encoding",
    "content-length",
    "set-cookie",
}


@dataclass(slots=True)
class SearchContext:
    contains_terms: tuple[str, ...]
    fixture_ids: tuple[str, ...]

    @property
    def all_terms(self) -> tuple[str, ...]:
        dynamic_terms = list(self.contains_terms)
        dynamic_terms.extend(self.fixture_ids)
        return tuple(dict.fromkeys((*DEFAULT_MARKERS, *dynamic_terms)))


def now_ts() -> float:
    return time.time()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return normalized or "capture"


def infer_capture_slug(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc or "unknown-host"
    fragment = parsed.fragment or parsed.path or "root"
    return slugify(f"{host}-{fragment}")[:120]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            candidate = line.strip()
            if not candidate:
                continue
            records.append(json.loads(candidate))
    return records


def is_textual_content_type(content_type: str | None) -> bool:
    normalized = (content_type or "").lower()
    return any(hint in normalized for hint in TEXTUAL_CONTENT_HINTS)


def decode_body(raw_body: bytes, content_type: str | None) -> tuple[str | None, str | None]:
    if not raw_body:
        return "", "utf-8"

    if not is_textual_content_type(content_type):
        return None, None

    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw_body.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    return raw_body.decode("utf-8", errors="replace"), "utf-8-replace"


def truncate(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def safe_filename_from_url(url: str, prefix: str, suffix: str) -> str:
    parsed = urlparse(url)
    raw = f"{prefix}-{parsed.netloc}-{parsed.path}-{parsed.query}-{parsed.fragment}"
    return f"{slugify(raw)[:160]}{suffix}"


def analyze_text_hits(text: str, search: SearchContext) -> dict[str, Any]:
    lowered = text.lower()
    found_terms = [term for term in search.contains_terms if term.lower() in lowered]
    found_markers = [marker for marker in DEFAULT_MARKERS if marker.lower() in lowered]
    found_fixtures = [fixture for fixture in search.fixture_ids if fixture in text]
    market_ids = sorted(set(re.findall(r'\b(?:40|981|938|10143)\b', text)))

    return {
        "contains_terms": found_terms,
        "markers": found_markers,
        "fixture_ids": found_fixtures,
        "market_ids": market_ids,
    }


def guess_body_kind(text: str, content_type: str | None) -> str:
    normalized = (content_type or "").lower()
    stripped = text.lstrip()
    if "json" in normalized or stripped.startswith("{") or stripped.startswith("["):
        return "json_like"
    if "javascript" in normalized or stripped.startswith("(()=>") or "function(" in text[:500]:
        return "script"
    if "html" in normalized or stripped.startswith("<!doctype") or stripped.startswith("<html"):
        return "html"
    return "text"


def try_parse_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def score_record(record: dict[str, Any]) -> int:
    if record.get("type") not in {"response", "websocket_frame"}:
        return 0

    score = 0
    hits = record.get("text_hits") or {}
    resource_type = (record.get("resource_type") or "").lower()
    body_kind = record.get("body_kind") or ""
    url = record.get("url") or ""

    score += 8 * len(hits.get("fixture_ids", []))
    score += 6 * len(hits.get("contains_terms", []))
    score += 4 * len(hits.get("market_ids", []))
    score += 2 * len(hits.get("markers", []))

    if resource_type in {"xhr", "fetch", "websocket", "eventsource"}:
        score += 15
    elif resource_type == "script":
        score += 8
    elif resource_type == "document":
        score += 3

    if body_kind == "json_like":
        score += 10
    elif body_kind == "script":
        score += 5

    if "api" in url.lower() or "feed" in url.lower() or "websocket" in url.lower():
        score += 4

    lowered_url = url.lower()
    if "matchmarketscontentapi" in lowered_url:
        score += 30
    if "matchbettingcontentapi" in lowered_url:
        score += 30
    if "splashcontentapi/changecompetition" in lowered_url or "splashcontentapi/changefixture" in lowered_url:
        score += 12
    if "/api/1/blob" in lowered_url:
        score -= 8

    if record.get("status") == 200:
        score += 2

    return score


def latest_capture_dir(captures_root: Path) -> Path | None:
    if not captures_root.exists():
        return None

    candidates = [path for path in captures_root.iterdir() if path.is_dir()]
    if not candidates:
        return None

    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[0]


def summarize_header_subset(headers: dict[str, str] | None, *, kind: str) -> dict[str, str]:
    if not headers:
        return {}

    skipped = SKIP_REQUEST_HEADERS if kind == "request" else SKIP_RESPONSE_HEADERS
    result: dict[str, str] = {}
    for key, value in headers.items():
        normalized_key = key.lower()
        if normalized_key in skipped:
            continue
        result[normalized_key] = value
    return result


def extract_bet365_identifiers(url: str) -> dict[str, str | None]:
    normalized = url.strip()
    competition_match = re.search(r"/D1002/E(?P<competition_id>\d+)/G40/?", normalized)
    event_match = re.search(r"/D8/E(?P<event_id>\d+)/F3/I(?P<tab>\d+)/?", normalized)
    return {
        "competition_id": competition_match.group("competition_id") if competition_match else None,
        "event_id": event_match.group("event_id") if event_match else None,
        "event_tab": event_match.group("tab") if event_match else None,
    }


def build_search_context(contains: list[str], fixtures: list[str]) -> SearchContext:
    normalized_contains = tuple(term.strip() for term in contains if term.strip())
    normalized_fixtures = tuple(fixture.strip() for fixture in fixtures if fixture.strip())
    return SearchContext(normalized_contains, normalized_fixtures)

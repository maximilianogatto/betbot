"""Replay captured FootyStats URLs through lightweight HTTP clients.

The probe compares ordinary httpx requests against curl_cffi Chrome
impersonation. It is intentionally independent from Playwright.

Usage:
    ./betbot/bin/python sandbox/footystats_http/probe_http.py \
        sandbox/footystats_http/captures/home
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any

import httpx

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - optional dependency in other environments
    curl_requests = None


DEFAULT_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "accept-language": "es-AR,es;q=0.9,en;q=0.8",
    "referer": "https://footystats.org/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
}


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    """Read compact browser evidence records from NDJSON."""

    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for raw in handle if (line := raw.strip())]


def load_storage_cookies(path: Path) -> dict[str, str]:
    """Load Playwright storage-state cookies into a simple mapping."""

    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(item["name"]): str(item["value"])
        for item in payload.get("cookies") or []
        if item.get("name") and item.get("value")
    }


def unique_get_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one replay-safe GET sample per full URL."""

    unique: dict[str, dict[str, Any]] = {}
    for record in records:
        if str(record.get("method") or "GET").upper() == "GET":
            unique.setdefault(str(record["url"]), record)
    return list(unique.values())


def classify_result(status: int | None, body: bytes) -> str:
    """Classify one replay attempt without assuming a fixed payload schema."""

    if status is None:
        return "transport_error"
    if status in {401, 403}:
        return "blocked"
    if status == 429:
        return "rate_limited"
    if status >= 400:
        return "http_error"
    if not body.strip():
        return "empty"
    return "ok"


def probe_httpx(client: httpx.Client, record: dict[str, Any], *, mode: str) -> dict[str, Any]:
    """Replay one captured GET URL with httpx."""

    headers: dict[str, str] = {}
    if mode in {"default_headers", "captured_headers", "captured_headers_cookies"}:
        headers.update(DEFAULT_HEADERS)
    if mode in {"captured_headers", "captured_headers_cookies"}:
        headers.update(record.get("request_headers") or {})
    try:
        response = client.get(str(record["url"]), headers=headers)
        return {
            "mode": mode,
            "endpoint_key": record["endpoint_key"],
            "url": record["url"],
            "status": response.status_code,
            "body_size_bytes": len(response.content),
            "classification": classify_result(response.status_code, response.content),
            "content_type": response.headers.get("content-type", ""),
        }
    except httpx.HTTPError as exc:
        return {
            "mode": mode,
            "endpoint_key": record["endpoint_key"],
            "url": record["url"],
            "status": None,
            "body_size_bytes": 0,
            "classification": "transport_error",
            "preview": f"{type(exc).__name__}: {exc}",
        }


def probe_curl_cffi(record: dict[str, Any], *, include_headers: bool) -> dict[str, Any]:
    """Replay one GET URL with a Chrome-like TLS fingerprint when available."""

    mode = "curl_cffi_chrome_headers" if include_headers else "curl_cffi_chrome_bare"
    if curl_requests is None:
        return {
            "mode": mode,
            "endpoint_key": record["endpoint_key"],
            "url": record["url"],
            "status": None,
            "body_size_bytes": 0,
            "classification": "not_installed",
        }
    try:
        response = curl_requests.get(
            str(record["url"]),
            headers=DEFAULT_HEADERS if include_headers else None,
            impersonate="chrome",
            timeout=15,
        )
        return {
            "mode": mode,
            "endpoint_key": record["endpoint_key"],
            "url": record["url"],
            "status": response.status_code,
            "body_size_bytes": len(response.content),
            "classification": classify_result(response.status_code, response.content),
            "content_type": response.headers.get("content-type", ""),
        }
    except Exception as exc:  # curl_cffi exposes different exception classes by release
        return {
            "mode": mode,
            "endpoint_key": record["endpoint_key"],
            "url": record["url"],
            "status": None,
            "body_size_bytes": 0,
            "classification": "transport_error",
            "preview": f"{type(exc).__name__}: {exc}",
        }


def render_report(results: list[dict[str, Any]]) -> str:
    """Render HTTP replay evidence grouped by endpoint."""

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[str(result["endpoint_key"])].append(result)
    lines = ["# FootyStats HTTP Replay", "", "Playwright is not used by this replay step.", ""]
    for endpoint, endpoint_results in sorted(grouped.items()):
        lines.extend([f"## `{endpoint}`", ""])
        for result in endpoint_results:
            lines.append(
                f"- `{result['mode']}`: status=`{result['status']}`, "
                f"classification=`{result['classification']}`, bytes=`{result['body_size_bytes']}`"
            )
        lines.append("")
    return "\n".join(lines)


def run_probe(capture_dir: Path, *, timeout: float = 15.0) -> list[dict[str, Any]]:
    """Replay each unique captured GET URL in progressively richer modes."""

    records = unique_get_records(read_ndjson(capture_dir / "responses.ndjson"))
    cookies = load_storage_cookies(capture_dir / "storage_state.json")
    results: list[dict[str, Any]] = []
    with (
        httpx.Client(timeout=timeout, follow_redirects=True) as client,
        httpx.Client(timeout=timeout, follow_redirects=True, cookies=cookies) as cookie_client,
    ):
        for record in records:
            for mode in ("bare", "default_headers", "captured_headers", "captured_headers_cookies"):
                selected_client = cookie_client if mode == "captured_headers_cookies" else client
                results.append(probe_httpx(selected_client, record, mode=mode))
            results.append(probe_curl_cffi(record, include_headers=False))
            results.append(probe_curl_cffi(record, include_headers=True))
    (capture_dir / "http_probe_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (capture_dir / "http_probe_report.md").write_text(render_report(results), encoding="utf-8")
    return results


def main() -> None:
    """Run the pure-HTTP replay comparison."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    results = run_probe(args.capture_dir, timeout=args.timeout)
    print(f"Probed {len(results)} FootyStats HTTP replay attempts in {args.capture_dir}")


if __name__ == "__main__":
    main()

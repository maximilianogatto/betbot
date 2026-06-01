"""Replay captured SofaScore API URLs with a lightweight HTTP client.

This script deliberately does not use Playwright. It reads the compact browser
capture, repeats each unique endpoint with httpx and records whether browser
cookies or captured request headers are required.

Usage:
    ../BetBot/betbot/bin/python sandbox/sofascore_http/probe_http.py \
        sandbox/sofascore_http/captures/home
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any

import httpx
from curl_cffi import requests as curl_requests


DEFAULT_HEADERS = {
    "accept": "application/json,text/plain,*/*",
    "accept-language": "es-AR,es;q=0.9,en;q=0.8",
    "referer": "https://www.sofascore.com/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
}


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    """Read compact browser response records from NDJSON."""

    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_storage_cookies(path: Path) -> dict[str, str]:
    """Load Playwright storage-state cookies into an httpx-compatible mapping."""

    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(item["name"]): str(item["value"])
        for item in payload.get("cookies") or []
        if item.get("name") and item.get("value")
    }


def unique_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one replay sample per full captured URL."""

    unique: dict[str, dict[str, Any]] = {}
    for record in records:
        unique.setdefault(str(record["url"]), record)
    return list(unique.values())


def decode_response(response: httpx.Response) -> tuple[Any | None, str]:
    """Return parsed JSON when possible and a bounded text preview otherwise."""

    try:
        return response.json(), ""
    except ValueError:
        return None, response.text[:500]


def classify_result(*, status: int, body_json: Any | None, preview: str) -> str:
    """Classify replay viability without assuming a fixed SofaScore schema."""

    if status in {401, 403}:
        return "blocked"
    if status == 429:
        return "rate_limited"
    if status >= 400:
        return "http_error"
    if body_json is not None:
        return "json_ok"
    if not preview.strip():
        return "empty"
    return "non_json"


def probe_one(
    client: httpx.Client,
    record: dict[str, Any],
    *,
    mode: str,
) -> dict[str, Any]:
    """Replay one captured URL in one controlled header/cookie mode."""

    headers: dict[str, str] = {}
    if mode in {"default_headers", "captured_headers", "captured_headers_cookies"}:
        headers.update(DEFAULT_HEADERS)
    if mode in {"captured_headers", "captured_headers_cookies"}:
        headers.update(record.get("request_headers") or {})
    try:
        response = client.request(
            str(record.get("method") or "GET"),
            str(record["url"]),
            headers=headers,
        )
        body_json, preview = decode_response(response)
        return {
            "mode": mode,
            "endpoint_key": record["endpoint_key"],
            "url": record["url"],
            "status": response.status_code,
            "body_size_bytes": len(response.content),
            "has_json": body_json is not None,
            "classification": classify_result(
                status=response.status_code,
                body_json=body_json,
                preview=preview,
            ),
            "preview": preview,
        }
    except httpx.HTTPError as exc:
        return {
            "mode": mode,
            "endpoint_key": record["endpoint_key"],
            "url": record["url"],
            "status": None,
            "body_size_bytes": 0,
            "has_json": False,
            "classification": "transport_error",
            "preview": f"{type(exc).__name__}: {exc}",
        }


def probe_one_curl_cffi(record: dict[str, Any]) -> dict[str, Any]:
    """Replay one URL through libcurl to test TLS/client-fingerprint sensitivity."""

    try:
        response = curl_requests.get(str(record["url"]), timeout=15)
        try:
            body_json = response.json()
            preview = ""
        except ValueError:
            body_json = None
            preview = response.text[:500]
        return {
            "mode": "curl_cffi_bare",
            "endpoint_key": record["endpoint_key"],
            "url": record["url"],
            "status": response.status_code,
            "body_size_bytes": len(response.content),
            "has_json": body_json is not None,
            "classification": classify_result(
                status=response.status_code,
                body_json=body_json,
                preview=preview,
            ),
            "preview": preview,
        }
    except curl_requests.RequestsError as exc:
        return {
            "mode": "curl_cffi_bare",
            "endpoint_key": record["endpoint_key"],
            "url": record["url"],
            "status": None,
            "body_size_bytes": 0,
            "has_json": False,
            "classification": "transport_error",
            "preview": f"{type(exc).__name__}: {exc}",
        }


def render_report(results: list[dict[str, Any]]) -> str:
    """Render replay results grouped by endpoint and request mode."""

    by_endpoint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        by_endpoint[result["endpoint_key"]].append(result)
    lines = [
        "# SofaScore HTTP Replay Report",
        "",
        "This report compares pure-http replay modes after a short Playwright capture.",
        "",
    ]
    for endpoint, endpoint_results in sorted(by_endpoint.items()):
        lines.extend([f"## `{endpoint}`", ""])
        for result in endpoint_results:
            lines.append(
                f"- `{result['mode']}`: status=`{result['status']}`, "
                f"classification=`{result['classification']}`, bytes=`{result['body_size_bytes']}`"
            )
        lines.append("")
    return "\n".join(lines)


def run_probe(capture_dir: Path, *, timeout: float = 15.0) -> list[dict[str, Any]]:
    """Replay all unique captured API URLs using progressively richer context."""

    records = unique_records(read_ndjson(capture_dir / "responses.ndjson"))
    cookies = load_storage_cookies(capture_dir / "storage_state.json")
    results: list[dict[str, Any]] = []
    with (
        httpx.Client(timeout=timeout, follow_redirects=True) as client,
        httpx.Client(timeout=timeout, follow_redirects=True, cookies=cookies) as cookie_client,
    ):
        for record in records:
            for mode in ("bare", "default_headers", "captured_headers", "captured_headers_cookies"):
                mode_client = cookie_client if mode == "captured_headers_cookies" else client
                results.append(probe_one(mode_client, record, mode=mode))
            results.append(probe_one_curl_cffi(record))
    (capture_dir / "http_probe_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (capture_dir / "http_probe_report.md").write_text(render_report(results), encoding="utf-8")
    return results


def main() -> None:
    """Run the HTTP replay comparison."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    results = run_probe(args.capture_dir, timeout=args.timeout)
    print(f"Probed {len(results)} SofaScore HTTP replay attempts in {args.capture_dir}")


if __name__ == "__main__":
    main()

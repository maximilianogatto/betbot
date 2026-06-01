"""Capture useful SofaScore JSON traffic with a short-lived Playwright browser.

The page browser is used only as a research bootstrap. Static assets and ad
traffic are ignored so the output stays compact enough to inspect manually.

Usage:
    ../BetBot/betbot/bin/python sandbox/sofascore_http/capture_traffic.py \
        https://www.sofascore.com/es-la \
        --seconds 10 \
        --out-dir sandbox/sofascore_http/captures/home
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import parse_qsl, urlparse

from playwright.async_api import Response, async_playwright


DEFAULT_URL = "https://www.sofascore.com/es-la"
USEFUL_RESOURCE_TYPES = {"document", "fetch", "xhr"}
BLOCKED_RESOURCE_TYPES = {"font", "image", "media"}
CAPTURED_REQUEST_HEADERS = {
    "accept",
    "accept-language",
    "content-type",
    "origin",
    "referer",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "user-agent",
    "x-requested-with",
}
CAPTURED_RESPONSE_HEADERS = {
    "cache-control",
    "content-type",
    "etag",
    "server",
    "vary",
    "x-cache",
}
_NUMERIC_SEGMENT_RE = re.compile(r"^\d+$")
_DATE_SEGMENT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp suitable for NDJSON records."""

    return datetime.now(UTC).isoformat()


def is_sofascore_api_url(url: str) -> bool:
    """Return whether `url` is a SofaScore JSON API request worth capturing."""

    parsed = urlparse(url)
    return parsed.hostname in {"www.sofascore.com", "api.sofascore.com"} and "/api/" in parsed.path


def normalize_endpoint_path(url: str) -> str:
    """Collapse variable IDs and dates in one SofaScore API URL.

    The normalized path is used only for endpoint grouping. Full URLs remain in
    every record so exact HTTP replay is still possible.
    """

    path = urlparse(url).path.rstrip("/") or "/"
    normalized: list[str] = []
    for segment in path.split("/"):
        if not segment:
            continue
        if _DATE_SEGMENT_RE.match(segment):
            normalized.append("{date}")
        elif _NUMERIC_SEGMENT_RE.match(segment):
            normalized.append("{id}")
        else:
            normalized.append(segment)
    return "/" + "/".join(normalized)


def endpoint_key(url: str) -> str:
    """Build a stable endpoint key from a SofaScore API URL."""

    path = normalize_endpoint_path(url)
    if path.startswith("/api/v1/"):
        return path[len("/api/v1/") :]
    return path.lstrip("/")


def selected_headers(headers: dict[str, str], allowed: set[str]) -> dict[str, str]:
    """Keep only headers useful for HTTP replay analysis."""

    return {
        key.lower(): value
        for key, value in headers.items()
        if key.lower() in allowed
    }


def compact_json_preview(value: Any, *, max_chars: int = 500) -> str:
    """Serialize one JSON value into a bounded preview string."""

    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= max_chars else text[: max_chars - 3] + "..."


def build_endpoint_index(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group compact response metadata by normalized endpoint key."""

    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        key = str(record["endpoint_key"])
        item = grouped.setdefault(
            key,
            {
                "count": 0,
                "statuses": Counter(),
                "methods": Counter(),
                "body_size_min": None,
                "body_size_max": 0,
                "example_url": record["url"],
                "normalized_path": record["normalized_path"],
                "has_json": False,
                "top_level_keys": set(),
            },
        )
        size = int(record.get("body_size_bytes") or 0)
        item["count"] += 1
        item["statuses"][str(record.get("status"))] += 1
        item["methods"][str(record.get("method"))] += 1
        item["body_size_min"] = size if item["body_size_min"] is None else min(item["body_size_min"], size)
        item["body_size_max"] = max(item["body_size_max"], size)
        body_json = record.get("body_json")
        if body_json is not None:
            item["has_json"] = True
        if isinstance(body_json, dict):
            item["top_level_keys"].update(str(key) for key in body_json)

    serializable: dict[str, dict[str, Any]] = {}
    for key, item in sorted(grouped.items()):
        serializable[key] = {
            **item,
            "statuses": dict(sorted(item["statuses"].items())),
            "methods": dict(sorted(item["methods"].items())),
            "top_level_keys": sorted(item["top_level_keys"]),
        }
    return serializable


def render_endpoint_report(index: dict[str, dict[str, Any]], *, source_url: str) -> str:
    """Render a compact Markdown inventory for one captured navigation."""

    lines = [
        "# SofaScore Endpoint Capture",
        "",
        f"- Source URL: `{source_url}`",
        f"- Unique API endpoints: `{len(index)}`",
        "",
        "| Endpoint | Count | Statuses | JSON | Bytes |",
        "| --- | ---: | --- | --- | ---: |",
    ]
    for key, item in index.items():
        statuses = ", ".join(f"{status}:{count}" for status, count in item["statuses"].items())
        size = f"{item['body_size_min']}-{item['body_size_max']}"
        lines.append(f"| `{key}` | {item['count']} | {statuses} | {item['has_json']} | {size} |")
    return "\n".join(lines) + "\n"


async def response_record(response: Response, *, started_at: float) -> dict[str, Any] | None:
    """Convert one useful Playwright response into a JSON-serializable record."""

    request = response.request
    if request.resource_type not in USEFUL_RESOURCE_TYPES or not is_sofascore_api_url(response.url):
        return None
    try:
        body = await response.body()
    except Exception as exc:
        body = b""
        body_error = f"{type(exc).__name__}: {exc}"
    else:
        body_error = None
    decoded = body.decode("utf-8", errors="replace")
    try:
        body_json = json.loads(decoded) if decoded else None
    except json.JSONDecodeError:
        body_json = None
    return {
        "captured_at": utc_now_iso(),
        "elapsed_ms": round((time.monotonic() - started_at) * 1000, 3),
        "method": request.method,
        "status": response.status,
        "resource_type": request.resource_type,
        "url": response.url,
        "host": urlparse(response.url).hostname,
        "query_params": dict(parse_qsl(urlparse(response.url).query, keep_blank_values=True)),
        "normalized_path": normalize_endpoint_path(response.url),
        "endpoint_key": endpoint_key(response.url),
        "request_headers": selected_headers(await request.all_headers(), CAPTURED_REQUEST_HEADERS),
        "response_headers": selected_headers(await response.all_headers(), CAPTURED_RESPONSE_HEADERS),
        "body_size_bytes": len(body),
        "body_json": body_json,
        "preview": None if body_json is not None else decoded[:500],
        "body_error": body_error,
    }


async def capture(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Open one page, capture useful API responses and write research outputs."""

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    pending_tasks: set[asyncio.Task[None]] = set()
    started_at = time.monotonic()

    async def collect(response: Response) -> None:
        record = await response_record(response, started_at=started_at)
        if record is not None:
            records.append(record)

    def schedule_collect(response: Response) -> None:
        task = asyncio.create_task(collect(response))
        pending_tasks.add(task)
        task.add_done_callback(pending_tasks.discard)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not args.headed)
        context = await browser.new_context(locale=args.locale)
        page = await context.new_page()
        if args.block_heavy_resources:
            await page.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.resource_type in BLOCKED_RESOURCE_TYPES
                    else route.continue_()
                ),
            )
        page.on("response", schedule_collect)
        await page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout_ms)
        await page.wait_for_timeout(args.seconds * 1000)
        cookies = await context.cookies()
        await context.storage_state(path=str(out_dir / "storage_state.json"))
        await browser.close()

    if pending_tasks:
        await asyncio.gather(*pending_tasks, return_exceptions=True)
    records.sort(key=lambda record: record["elapsed_ms"])
    index = build_endpoint_index(records)
    (out_dir / "responses.ndjson").write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    (out_dir / "endpoints_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "endpoint_report.md").write_text(
        render_endpoint_report(index, source_url=args.url),
        encoding="utf-8",
    )
    (out_dir / "capture_metadata.json").write_text(
        json.dumps(
            {
                "source_url": args.url,
                "captured_at": utc_now_iso(),
                "seconds": args.seconds,
                "headed": args.headed,
                "locale": args.locale,
                "response_count": len(records),
                "endpoint_count": len(index),
                "cookie_names": sorted({cookie["name"] for cookie in cookies}),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return records


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for manual SofaScore captures."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", default=DEFAULT_URL)
    parser.add_argument("--seconds", type=int, default=10)
    parser.add_argument("--out-dir", default="sandbox/sofascore_http/captures/home")
    parser.add_argument("--locale", default="es-AR")
    parser.add_argument("--timeout-ms", type=int, default=45_000)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--no-block-heavy-resources", action="store_false", dest="block_heavy_resources")
    parser.set_defaults(block_heavy_resources=True)
    return parser


def main() -> None:
    """Run a manual Playwright capture."""

    args = build_parser().parse_args()
    records = asyncio.run(capture(args))
    print(f"Captured {len(records)} useful SofaScore API responses in {args.out_dir}")


if __name__ == "__main__":
    main()

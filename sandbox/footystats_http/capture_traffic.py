"""Capture compact FootyStats document/fetch/XHR evidence with Playwright.

Playwright is used only to observe real browser behavior. The resulting files
are intended for offline inspection and HTTP-replay testing, not production.

Usage:
    ./betbot/bin/python sandbox/footystats_http/capture_traffic.py \
        https://footystats.org/ \
        --seconds 5 \
        --out-dir sandbox/footystats_http/captures/home
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib.parse import parse_qsl, urlparse

from playwright.async_api import Response, async_playwright

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sandbox.footystats_http.normalizers import classify_url


DEFAULT_URL = "https://footystats.org/"
USEFUL_RESOURCE_TYPES = {"document", "fetch", "xhr"}
BLOCKED_RESOURCE_TYPES = {"font", "image", "media"}
ALLOWED_HOSTS = {"footystats.org", "www.footystats.org", "api.football-data-api.com"}
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
    "set-cookie",
    "vary",
}
_NUMERIC_SEGMENT_RE = re.compile(r"^\d+$")


def utc_now_iso() -> str:
    """Return one timezone-aware ISO-8601 UTC timestamp."""

    return datetime.now(UTC).isoformat()


def is_relevant_url(url: str) -> bool:
    """Return whether one URL belongs to FootyStats research scope."""

    return (urlparse(url).hostname or "") in ALLOWED_HOSTS


def normalize_endpoint_path(url: str) -> str:
    """Collapse numeric path segments for compact endpoint grouping."""

    path = urlparse(url).path.rstrip("/") or "/"
    return "/" + "/".join(
        "{id}" if _NUMERIC_SEGMENT_RE.match(segment) else segment
        for segment in path.split("/")
        if segment
    )


def endpoint_key(url: str) -> str:
    """Build a stable endpoint key preserving source-contract differences."""

    source = classify_url(url)
    path = normalize_endpoint_path(url)
    return f"{source}:{path}"


def selected_headers(headers: dict[str, str], allowed: set[str]) -> dict[str, str]:
    """Retain only headers useful for pure-HTTP replay analysis."""

    return {key.lower(): value for key, value in headers.items() if key.lower() in allowed}


async def response_record(response: Response, *, started_at: float) -> dict[str, Any] | None:
    """Convert one relevant browser response into bounded evidence."""

    request = response.request
    if request.resource_type not in USEFUL_RESOURCE_TYPES or not is_relevant_url(response.url):
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
        "source_type": classify_url(response.url),
        "request_headers": selected_headers(await request.all_headers(), CAPTURED_REQUEST_HEADERS),
        "response_headers": selected_headers(await response.all_headers(), CAPTURED_RESPONSE_HEADERS),
        "body_size_bytes": len(body),
        "body_json": body_json,
        "preview": None if body_json is not None else decoded[:1000],
        "body_error": body_error,
    }


def build_endpoint_index(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group response evidence by stable endpoint key."""

    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        key = str(record["endpoint_key"])
        item = grouped.setdefault(
            key,
            {
                "count": 0,
                "statuses": Counter(),
                "resource_types": Counter(),
                "body_size_min": None,
                "body_size_max": 0,
                "example_url": record["url"],
                "has_json": False,
            },
        )
        size = int(record.get("body_size_bytes") or 0)
        item["count"] += 1
        item["statuses"][str(record.get("status"))] += 1
        item["resource_types"][str(record.get("resource_type"))] += 1
        item["body_size_min"] = size if item["body_size_min"] is None else min(item["body_size_min"], size)
        item["body_size_max"] = max(item["body_size_max"], size)
        item["has_json"] = item["has_json"] or record.get("body_json") is not None
    return {
        key: {
            **item,
            "statuses": dict(sorted(item["statuses"].items())),
            "resource_types": dict(sorted(item["resource_types"].items())),
        }
        for key, item in sorted(grouped.items())
    }


def render_endpoint_report(index: dict[str, dict[str, Any]], *, source_url: str) -> str:
    """Render a Markdown endpoint inventory from compact evidence."""

    lines = [
        "# FootyStats Browser Traffic",
        "",
        f"- Source URL: `{source_url}`",
        f"- Unique endpoints: `{len(index)}`",
        "",
        "| Endpoint | Count | Statuses | Types | JSON | Bytes |",
        "| --- | ---: | --- | --- | --- | ---: |",
    ]
    for key, item in index.items():
        statuses = ", ".join(f"{status}:{count}" for status, count in item["statuses"].items())
        types = ", ".join(f"{kind}:{count}" for kind, count in item["resource_types"].items())
        lines.append(
            f"| `{key}` | {item['count']} | {statuses} | {types} | "
            f"{item['has_json']} | {item['body_size_min']}-{item['body_size_max']} |"
        )
    return "\n".join(lines) + "\n"


async def capture(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Open one page briefly and write bounded traffic evidence files."""

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
    (out_dir / "endpoints_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "endpoint_report.md").write_text(render_endpoint_report(index, source_url=args.url), encoding="utf-8")
    (out_dir / "capture_metadata.json").write_text(
        json.dumps(
            {
                "source_url": args.url,
                "captured_at": utc_now_iso(),
                "seconds": args.seconds,
                "headed": args.headed,
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
    """Build the manual browser-capture CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", default=DEFAULT_URL)
    parser.add_argument("--seconds", type=int, default=5)
    parser.add_argument("--out-dir", default="sandbox/footystats_http/captures/home")
    parser.add_argument("--locale", default="es-AR")
    parser.add_argument("--timeout-ms", type=int, default=45_000)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--no-block-heavy-resources", action="store_false", dest="block_heavy_resources")
    parser.set_defaults(block_heavy_resources=True)
    return parser


def main() -> None:
    """Run one manual Playwright traffic capture."""

    args = build_parser().parse_args()
    records = asyncio.run(capture(args))
    print(f"Captured {len(records)} FootyStats responses in {args.out_dir}")


if __name__ == "__main__":
    main()

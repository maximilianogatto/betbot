from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Response, async_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.analysis import (
    build_endpoint_key,
    decode_embedded_data_from_url,
    extract_sportradar_match_id,
    normalize_endpoint_path,
)


LOGGER = logging.getLogger("sandbox.sportradar_stats.capture")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
BLOCKED_RESOURCE_TYPES = {"image", "font", "media"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture Sportradar / Bet365Stats JSON-ish responses with Playwright."
    )
    parser.add_argument("stats_url", help="Full Bet365Stats / Sportradar match URL.")
    parser.add_argument(
        "--seconds",
        type=float,
        default=30.0,
        help="How long to keep the page open after DOMContentLoaded.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("sandbox/sportradar_stats/captures/latest"),
        help="Directory where capture artifacts will be stored.",
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run Chromium in headless mode.",
    )
    parser.add_argument(
        "--group-by-endpoint",
        action="store_true",
        help="Also emit a grouped raw JSON file keyed by endpoint.",
    )
    parser.add_argument(
        "--referer",
        default=None,
        help="Optional Referer header for the top-level stats page navigation.",
    )
    parser.add_argument(
        "--bootstrap-url",
        default=None,
        help="Optional page to open first in the same browser context before visiting the stats URL.",
    )
    return parser.parse_args()


async def capture_stats_feed(
    stats_url: str,
    *,
    seconds: float,
    out_dir: Path,
    headless: bool,
    group_by_endpoint: bool,
    referer: str | None,
    bootstrap_url: str | None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    capture_started_at = datetime.now(timezone.utc)
    started_monotonic = asyncio.get_running_loop().time()
    parsed_url = urlparse(stats_url)

    records: list[dict[str, Any]] = []
    pending_tasks: set[asyncio.Task[None]] = set()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        try:
            context = await browser.new_context(
                user_agent=USER_AGENT,
                locale="en-US",
                viewport={"width": 1440, "height": 900},
            )
            await context.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in BLOCKED_RESOURCE_TYPES
                else route.continue_(),
            )

            page = await context.new_page()

            if bootstrap_url:
                LOGGER.info("Opening bootstrap_url=%s", bootstrap_url)
                await page.goto(bootstrap_url, wait_until="domcontentloaded")
                await asyncio.sleep(2.0)

            def handle_response(response: Response) -> None:
                task = asyncio.create_task(
                    _process_response(
                        response,
                        records,
                        parsed_url.netloc,
                        capture_started_at,
                        started_monotonic,
                    )
                )
                pending_tasks.add(task)
                task.add_done_callback(pending_tasks.discard)

            page.on("response", handle_response)

            LOGGER.info("Opening stats_url=%s", stats_url)
            await page.goto(stats_url, wait_until="domcontentloaded", referer=referer)
            await asyncio.sleep(max(0.0, seconds))

            if pending_tasks:
                await asyncio.gather(*pending_tasks, return_exceptions=True)

            await context.close()
        finally:
            await browser.close()

    records.sort(key=lambda item: str(item.get("captured_at") or ""))
    ndjson_path = out_dir / "responses.ndjson"
    with ndjson_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")

    if group_by_endpoint:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            grouped.setdefault(str(record["endpoint_key"]), []).append(record)
        (out_dir / "responses_grouped_by_endpoint.json").write_text(
            json.dumps(grouped, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    metadata = {
        "stats_url": stats_url,
        "match_id": extract_sportradar_match_id(stats_url),
        "captured_at": capture_started_at.isoformat(),
        "capture_seconds": seconds,
        "responses_count": len(records),
        "out_dir": str(out_dir),
        "referer": referer,
        "bootstrap_url": bootstrap_url,
    }
    (out_dir / "capture_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return metadata


async def _process_response(
    response: Response,
    records: list[dict[str, Any]],
    expected_host: str,
    capture_started_at: datetime,
    started_monotonic: float,
) -> None:
    request = response.request
    resource_type = request.resource_type
    url = response.url
    parsed = urlparse(url)

    if resource_type not in {"fetch", "xhr", "document"} and parsed.netloc != expected_host:
        return

    content_type = response.headers.get("content-type", "")
    text_body = await _safe_response_text(response)
    parsed_json = _try_parse_json(text_body)
    decoded_request_data = decode_embedded_data_from_url(url)
    endpoint_key = build_endpoint_key(
        url,
        decoded_request_data=decoded_request_data,
        parsed_json=parsed_json,
    )
    captured_at = datetime.now(timezone.utc)

    records.append(
        {
            "captured_at": captured_at.isoformat(),
            "elapsed_ms": round((asyncio.get_running_loop().time() - started_monotonic) * 1000, 2),
            "timestamp_since_capture_start_ms": round(
                (captured_at - capture_started_at).total_seconds() * 1000,
                2,
            ),
            "url": url,
            "method": request.method,
            "status": response.status,
            "resource_type": resource_type,
            "content_type": content_type,
            "normalized_path": normalize_endpoint_path(url),
            "endpoint_key": endpoint_key,
            "host": parsed.netloc,
            "query_keys": sorted(set(dict.fromkeys(list(_query_keys(parsed.query))))),
            "decoded_request_data": decoded_request_data,
            "body_size_bytes": len(text_body.encode("utf-8")) if text_body else 0,
            "body_json": parsed_json,
            "preview": None if parsed_json is not None else _build_preview(text_body),
        }
    )


async def _safe_response_text(response: Response) -> str:
    try:
        return await response.text()
    except Exception as exc:
        return f"<<body read failed: {exc}>>"


def _query_keys(raw_query: str) -> list[str]:
    if not raw_query:
        return []
    keys: list[str] = []
    for chunk in raw_query.split("&"):
        if not chunk:
            continue
        keys.append(chunk.split("=", 1)[0])
    return keys


def _try_parse_json(raw_text: str) -> dict[str, Any] | list[Any] | None:
    normalized = raw_text.strip()
    if not normalized:
        return None
    if not (normalized.startswith("{") or normalized.startswith("[")):
        return None
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _build_preview(raw_text: str, *, limit: int = 400) -> str | None:
    normalized = raw_text.strip()
    if not normalized:
        return None
    return normalized[:limit]


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )
    args = parse_args()
    metadata = asyncio.run(
        capture_stats_feed(
            args.stats_url,
            seconds=args.seconds,
            out_dir=args.out_dir,
            headless=args.headless,
            group_by_endpoint=args.group_by_endpoint,
            referer=args.referer,
            bootstrap_url=args.bootstrap_url,
        )
    )
    LOGGER.info(
        "Capture finished match_id=%s responses=%s out_dir=%s",
        metadata.get("match_id"),
        metadata.get("responses_count"),
        metadata.get("out_dir"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

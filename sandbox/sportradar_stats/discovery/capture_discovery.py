from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from playwright.async_api import Response, async_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.capture_everything import build_context, install_routes, now_iso
from sandbox.sportradar_stats.capture_runtime import resolve_capture_user_data_dir
from sandbox.sportradar_stats.discovery.discovery_core import (
    build_discovery_record,
    build_endpoints_index,
    safe_json_loads,
    should_capture_response,
    write_endpoint_report,
)


REQUEST_HEADER_ALLOWLIST = {
    "accept",
    "accept-language",
    "origin",
    "referer",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "user-agent",
}
RESPONSE_HEADER_ALLOWLIST = {
    "cache-control",
    "content-type",
    "date",
    "etag",
    "expires",
    "last-modified",
    "server",
    "vary",
}
MAX_PREVIEW_LENGTH = 1000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture filtered Sportradar / Statshub discovery XHR/fetch endpoints.",
    )
    parser.add_argument("url", help="Statshub URL to open, for example /bet365/en/sport/1.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("sandbox/sportradar_stats/discovery/captures/sport_1"),
        help="Directory where discovery artifacts are written.",
    )
    parser.add_argument("--seconds", type=float, default=20.0, help="Seconds to wait after navigation.")
    parser.add_argument("--lang", default=None, help="Reserved for future URL builders; currently unused.")
    parser.add_argument("--headed", action="store_true", help="Run Chromium headed.")
    parser.add_argument("--user-data-dir", default=None, help="Optional persistent Chromium profile.")
    parser.add_argument(
        "--click-text",
        action="append",
        default=[],
        help="Visible text to click after initial load. Can be repeated.",
    )
    parser.add_argument(
        "--auto-click-links",
        action="store_true",
        help="Click a few visible sport/match links to discover extra endpoints.",
    )
    parser.add_argument("--max-auto-clicks", type=int, default=5)
    parser.add_argument("--wait-after-click", type=float, default=3.0)
    return parser.parse_args()


def select_headers(headers: dict[str, str], allowed: set[str]) -> dict[str, str]:
    selected: dict[str, str] = {}
    for key, value in headers.items():
        normalized_key = str(key).lower().strip()
        if normalized_key in allowed and str(value).strip():
            selected[normalized_key] = str(value).strip()
    return dict(sorted(selected.items()))


async def build_raw_record(response: Response, *, started_at: float) -> dict[str, Any] | None:
    request = response.request
    url = response.url
    body_text = ""
    try:
        body_text = await response.text()
    except Exception as exc:
        body_text = f"<<body read failed: {exc}>>"

    body_json = safe_json_loads(body_text)
    if not should_capture_response(url, request.resource_type, body_json):
        return None

    request_headers: dict[str, str] = {}
    try:
        request_headers = await request.all_headers()
    except Exception:
        request_headers = {}

    preview = None if body_json is not None else body_text[:MAX_PREVIEW_LENGTH]
    return {
        "captured_at": now_iso(),
        "elapsed_ms": round((time.monotonic() - started_at) * 1000, 2),
        "method": request.method,
        "status": response.status,
        "resource_type": request.resource_type,
        "url": url,
        "content_type": response.headers.get("content-type"),
        "request_headers": select_headers(request_headers, REQUEST_HEADER_ALLOWLIST),
        "response_headers": select_headers(response.headers, RESPONSE_HEADER_ALLOWLIST),
        "body_size_bytes": len(body_text.encode("utf-8")),
        "body_json": body_json,
        "preview": preview,
    }


async def click_text_sequence(page, labels: list[str], *, wait_after_click: float) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for label in labels:
        action: dict[str, Any] = {"type": "click_text", "label": label, "ok": False}
        try:
            await page.get_by_text(label, exact=False).first.click(timeout=5000)
            await asyncio.sleep(wait_after_click)
            action["ok"] = True
        except Exception as exc:
            action["error"] = str(exc)
        actions.append(action)
    return actions


async def auto_click_discovery_links(page, *, max_clicks: int, wait_after_click: float) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    candidates = await page.evaluate(
        """
        () => Array.from(document.querySelectorAll('a[href]'))
          .map((node, index) => ({
            index,
            text: (node.textContent || '').trim().slice(0, 120),
            href: node.href || ''
          }))
          .filter(item => /\\/sport\\/|\\/match\\/|\\/league\\/|\\/tournament\\//.test(item.href))
          .slice(0, 30)
        """
    )
    if not isinstance(candidates, list):
        return actions

    clicked = 0
    current_url = page.url
    for item in candidates:
        if clicked >= max_clicks:
            break
        href = str((item or {}).get("href") or "")
        if not href or href == current_url:
            continue
        action: dict[str, Any] = {"type": "auto_click_link", "href": href, "ok": False}
        try:
            await page.goto(href, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(wait_after_click)
            action["ok"] = True
            clicked += 1
        except Exception as exc:
            action["error"] = str(exc)
        actions.append(action)
    return actions


async def capture_discovery(
    url: str,
    *,
    out_dir: Path,
    seconds: float,
    headless: bool,
    user_data_dir: str | None,
    click_text: list[str],
    auto_click_links: bool,
    max_auto_clicks: int,
    wait_after_click: float,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ndjson_path = out_dir / "discovery_responses.ndjson"
    index_path = out_dir / "endpoints_index.json"
    map_path = out_dir / "discovery_map.json"
    report_path = out_dir / "endpoint_report.md"
    metadata_path = out_dir / "capture_metadata.json"
    ndjson_path.write_text("", encoding="utf-8")

    records: list[dict[str, Any]] = []
    pending_tasks: set[asyncio.Task[None]] = set()
    responses_seen = 0
    requests_seen = 0
    actions: list[dict[str, Any]] = []

    async with async_playwright() as playwright:
        context = await build_context(
            playwright,
            headless=headless,
            user_data_dir=user_data_dir,
        )
        await install_routes(context)
        page = await context.new_page()
        started_at = time.monotonic()

        async def handle_response(response: Response) -> None:
            nonlocal responses_seen
            responses_seen += 1
            raw = await build_raw_record(response, started_at=started_at)
            if raw is None:
                return
            record = build_discovery_record(raw)
            if record is None:
                return
            records.append(record)
            with ndjson_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False))
                handle.write("\n")
            print(
                f"[DISCOVERY {len(records)}] {record['status']} "
                f"{record['endpoint_key']} roles={','.join(record['roles']) or '-'}"
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

        await page.goto(url, wait_until="domcontentloaded", timeout=120000)
        await asyncio.sleep(seconds)
        actions.extend(await click_text_sequence(page, click_text, wait_after_click=wait_after_click))
        if auto_click_links:
            actions.extend(
                await auto_click_discovery_links(
                    page,
                    max_clicks=max_auto_clicks,
                    wait_after_click=wait_after_click,
                )
            )
        await asyncio.sleep(1)
        if pending_tasks:
            await asyncio.gather(*list(pending_tasks), return_exceptions=True)
        await context.close()

    index = build_endpoints_index(records)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    map_path.write_text(json.dumps(build_discovery_map(index), ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(write_endpoint_report(index), encoding="utf-8")

    metadata = {
        "url": url,
        "captured_at": now_iso(),
        "seconds": seconds,
        "user_data_dir": user_data_dir,
        "responses_seen": responses_seen,
        "requests_seen": requests_seen,
        "records_count": len(records),
        "endpoint_count": index["endpoint_count"],
        "actions": actions,
        "files": {
            "discovery_responses_ndjson": str(ndjson_path),
            "endpoints_index": str(index_path),
            "discovery_map": str(map_path),
            "endpoint_report": str(report_path),
        },
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def build_discovery_map(index: dict[str, Any]) -> dict[str, Any]:
    endpoints = index.get("endpoints") or {}
    by_role: dict[str, list[str]] = {}
    for endpoint_key, endpoint in endpoints.items():
        for role in (endpoint.get("roles") or {}).keys():
            by_role.setdefault(role, []).append(endpoint_key)
    return {
        "schema_version": 1,
        "records_count": index.get("records_count", 0),
        "endpoint_count": index.get("endpoint_count", 0),
        "by_role": {role: sorted(keys) for role, keys in sorted(by_role.items())},
        "endpoints": endpoints,
    }


async def main_async() -> int:
    args = parse_args()
    metadata = await capture_discovery(
        args.url,
        out_dir=args.out_dir.resolve(),
        seconds=args.seconds,
        headless=not args.headed,
        user_data_dir=resolve_capture_user_data_dir(args.user_data_dir),
        click_text=args.click_text,
        auto_click_links=args.auto_click_links,
        max_auto_clicks=args.max_auto_clicks,
        wait_after_click=args.wait_after_click,
    )
    print(f"Wrote {metadata['files']['discovery_responses_ndjson']}")
    print(f"Wrote {metadata['files']['endpoints_index']}")
    print(f"Wrote {metadata['files']['discovery_map']}")
    print(f"Wrote {metadata['files']['endpoint_report']}")
    print(f"Records: {metadata['records_count']} | endpoints: {metadata['endpoint_count']}")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())

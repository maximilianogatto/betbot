from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from playwright.async_api import Request, Response, async_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.capture_everything import build_context, install_routes
from sandbox.sportradar_stats.capture_runtime import resolve_capture_user_data_dir
from sandbox.sportradar_stats.http_research.core import (
    build_endpoint_catalog,
    build_endpoint_record,
    is_sportradar_url,
    is_static_asset_url,
    safe_json_loads,
    select_important_headers,
    should_keep_url,
)
from sandbox.sportradar_stats.http_research.reporting import (
    render_endpoint_catalog,
    summarize_tokens,
    utc_now_iso,
)


SCRIPT_HINTS = (
    "gismo",
    "sh.fn.sportradar.com",
    "T=",
    "exp=",
    "acl=",
    "data=",
    "signature",
    "token",
    "clientFetching",
    "queryKey",
    "feeds",
)
MAX_PREVIEW_LENGTH = 1200
DEFAULT_URLS = (
    "https://statshub.sportradar.com/bet365/en/sport/1",
    "https://statshub.sportradar.com/bet365/en/sport/1/tournament/8",
    "https://statshub.sportradar.com/bet365/en/sport/1/tournament/8/fixtures?view=round",
    "https://statshub.sportradar.com/bet365/en/match/61624678",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture Statshub/Sportradar request/response evidence for HTTP replay research.",
    )
    parser.add_argument("urls", nargs="*", help="Statshub/Sportradar URLs to open.")
    parser.add_argument(
        "--default-set",
        action="store_true",
        help="Capture the requested research URL set: sport, tournament, fixtures, match.",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=18.0)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--user-data-dir", default=None)
    parser.add_argument("--wait-between", type=float, default=2.0)
    return parser.parse_args()


async def build_request_record(request: Request, *, started_at: float, cookies: list[dict[str, Any]]) -> dict[str, Any] | None:
    url = request.url
    if not is_sportradar_url(url) or is_static_asset_url(url):
        return None
    headers: dict[str, str] = {}
    try:
        headers = await request.all_headers()
    except Exception:
        headers = {}
    return {
        "captured_at": utc_now_iso(),
        "elapsed_ms": round((time.monotonic() - started_at) * 1000, 2),
        "method": request.method,
        "url": url,
        "resource_type": request.resource_type,
        "headers": select_important_headers(headers),
        "cookie_names": sorted({str(cookie.get("name")) for cookie in cookies if cookie.get("name")}),
    }


async def build_response_record(
    response: Response,
    *,
    started_at: float,
    cookies: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    request = response.request
    url = response.url

    body_text = ""
    try:
        body_text = await response.text()
    except Exception as exc:
        body_text = f"<<body read failed: {exc}>>"

    body_json = safe_json_loads(body_text)
    raw_record = {
        "captured_at": utc_now_iso(),
        "elapsed_ms": round((time.monotonic() - started_at) * 1000, 2),
        "method": request.method,
        "url": url,
        "resource_type": request.resource_type,
        "request_headers": {},
        "cookies": [
            {
                "name": cookie.get("name"),
                "domain": cookie.get("domain"),
                "path": cookie.get("path"),
                "expires": cookie.get("expires"),
                "httpOnly": cookie.get("httpOnly"),
                "secure": cookie.get("secure"),
                "sameSite": cookie.get("sameSite"),
            }
            for cookie in cookies
            if cookie.get("name")
        ],
        "status": response.status,
        "content_type": response.headers.get("content-type"),
        "response_headers": select_important_headers(response.headers),
        "body_size_bytes": len(body_text.encode("utf-8")),
        "body_json": body_json,
        "preview": None if body_json is not None else body_text[:MAX_PREVIEW_LENGTH],
    }
    try:
        raw_record["request_headers"] = select_important_headers(await request.all_headers())
    except Exception:
        raw_record["request_headers"] = {}

    script_hint_record = build_script_hint_record(raw_record, body_text)
    endpoint_record = build_endpoint_record(raw_record)
    if endpoint_record is None and should_keep_url(url, request.resource_type, body_json):
        endpoint_record = raw_record
    return endpoint_record, script_hint_record


def build_script_hint_record(raw_record: dict[str, Any], body_text: str) -> dict[str, Any] | None:
    resource_type = str(raw_record.get("resource_type") or "")
    content_type = str(raw_record.get("content_type") or "")
    if resource_type != "script" and "javascript" not in content_type.lower():
        return None
    hits = [hint for hint in SCRIPT_HINTS if hint.lower() in body_text.lower()]
    if not hits:
        return None
    return {
        "captured_at": raw_record.get("captured_at"),
        "elapsed_ms": raw_record.get("elapsed_ms"),
        "url": raw_record.get("url"),
        "status": raw_record.get("status"),
        "content_type": raw_record.get("content_type"),
        "body_size_bytes": raw_record.get("body_size_bytes"),
        "hits": hits,
    }


async def capture_statshub(
    urls: list[str],
    *,
    out_dir: Path,
    seconds: float,
    headless: bool,
    user_data_dir: str | None,
    wait_between: float,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    requests_path = out_dir / "requests.ndjson"
    responses_path = out_dir / "responses.ndjson"
    fetch_only_path = out_dir / "fetch_only.ndjson"
    script_hints_path = out_dir / "script_hints.json"
    endpoints_index_path = out_dir / "endpoints_index.json"
    endpoint_report_path = out_dir / "endpoint_report.md"
    endpoint_catalog_path = out_dir / "endpoint_catalog.md"
    cookies_path = out_dir / "cookies.json"
    token_analysis_path = out_dir / "token_analysis.md"

    for path in (requests_path, responses_path, fetch_only_path):
        path.write_text("", encoding="utf-8")

    endpoint_records: list[dict[str, Any]] = []
    script_hints: list[dict[str, Any]] = []
    requests_seen = 0
    responses_seen = 0
    pending_tasks: set[asyncio.Task[None]] = set()
    accepting_events = True

    async with async_playwright() as playwright:
        context = await build_context(
            playwright,
            headless=headless,
            user_data_dir=user_data_dir,
        )
        await install_routes(context)
        page = await context.new_page()
        started_at = time.monotonic()

        async def current_cookies() -> list[dict[str, Any]]:
            try:
                return await context.cookies()
            except Exception:
                return []

        async def on_request(request: Request) -> None:
            nonlocal requests_seen
            requests_seen += 1
            record = await build_request_record(
                request,
                started_at=started_at,
                cookies=await current_cookies(),
            )
            if record is None:
                return
            with requests_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False))
                handle.write("\n")

        async def on_response(response: Response) -> None:
            nonlocal responses_seen
            responses_seen += 1
            endpoint_record, script_hint = await build_response_record(
                response,
                started_at=started_at,
                cookies=await current_cookies(),
            )
            if script_hint is not None:
                script_hints.append(script_hint)
            if endpoint_record is None:
                return
            endpoint_records.append(endpoint_record)
            with responses_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(endpoint_record, ensure_ascii=False))
                handle.write("\n")
            if str(endpoint_record.get("resource_type") or "") in {"fetch", "xhr"}:
                with fetch_only_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(endpoint_record, ensure_ascii=False))
                    handle.write("\n")
            print(
                "[HTTP-RESEARCH {count}] {status} {endpoint} {url}".format(
                    count=len(endpoint_records),
                    status=endpoint_record.get("status"),
                    endpoint=endpoint_record.get("endpoint_key") or endpoint_record.get("normalized_path"),
                    url=str(endpoint_record.get("url") or "")[:120],
                )
            )

        def track_request(request: Request) -> None:
            if not accepting_events:
                return
            task = asyncio.create_task(on_request(request))
            pending_tasks.add(task)
            task.add_done_callback(pending_tasks.discard)

        def track_response(response: Response) -> None:
            if not accepting_events:
                return
            task = asyncio.create_task(on_response(response))
            pending_tasks.add(task)
            task.add_done_callback(pending_tasks.discard)

        page.on("request", track_request)
        page.on("response", track_response)

        for url in urls:
            print(f"→ opening {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=120000)
            await asyncio.sleep(seconds)
            await asyncio.sleep(wait_between)

        accepting_events = False
        page.remove_listener("request", track_request)
        page.remove_listener("response", track_response)
        await page.close()
        if pending_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*list(pending_tasks), return_exceptions=True),
                    timeout=8,
                )
            except asyncio.TimeoutError:
                for task in list(pending_tasks):
                    task.cancel()
        cookies = await context.cookies()
        cookies_path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        await context.close()

    catalog = build_endpoint_catalog(endpoint_records)
    endpoints_index_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    rendered_catalog = render_endpoint_catalog(catalog)
    endpoint_report_path.write_text(rendered_catalog, encoding="utf-8")
    endpoint_catalog_path.write_text(rendered_catalog, encoding="utf-8")
    script_hints_path.write_text(json.dumps(script_hints, ensure_ascii=False, indent=2), encoding="utf-8")
    token_summary = {
        "generated_at": utc_now_iso(),
        "source": str(fetch_only_path),
        "signed_url_count": sum(1 for record in endpoint_records if record.get("has_signed_token")),
        "token_payloads": summarize_tokens(endpoint_records),
        "mutation_results": [],
    }
    token_analysis_path.write_text(render_simple_token_analysis(token_summary), encoding="utf-8")

    metadata = {
        "generated_at": utc_now_iso(),
        "urls": urls,
        "seconds": seconds,
        "headless": headless,
        "user_data_dir": user_data_dir,
        "requests_seen": requests_seen,
        "responses_seen": responses_seen,
        "records_count": len(endpoint_records),
        "endpoint_count": catalog["endpoint_count"],
        "script_hint_count": len(script_hints),
        "files": {
            "requests": str(requests_path),
            "responses": str(responses_path),
            "fetch_only": str(fetch_only_path),
            "endpoints_index": str(endpoints_index_path),
            "endpoint_report": str(endpoint_report_path),
            "endpoint_catalog": str(endpoint_catalog_path),
            "cookies": str(cookies_path),
            "script_hints": str(script_hints_path),
            "token_analysis": str(token_analysis_path),
        },
    }
    (out_dir / "capture_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return metadata


def render_simple_token_analysis(payload: dict[str, Any]) -> str:
    from sandbox.sportradar_stats.http_research.reporting import render_token_analysis

    return render_token_analysis(payload)


async def main_async() -> int:
    args = parse_args()
    urls = list(args.urls)
    if args.default_set:
        urls.extend(DEFAULT_URLS)
    if not urls:
        raise SystemExit("Pass at least one URL or --default-set.")

    metadata = await capture_statshub(
        urls,
        out_dir=args.out_dir.resolve(),
        seconds=args.seconds,
        headless=not args.headed,
        user_data_dir=resolve_capture_user_data_dir(args.user_data_dir),
        wait_between=args.wait_between,
    )
    for key, path in metadata["files"].items():
        print(f"Wrote {key}: {path}")
    print(f"Records={metadata['records_count']} endpoints={metadata['endpoint_count']}")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())

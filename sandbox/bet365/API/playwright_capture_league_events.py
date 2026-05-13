from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from common import decode_body, ensure_dir, infer_capture_slug, safe_filename_from_url, write_json
from parser import build_event_url, flatten_markets, parse_bet365_payload_text, summarize_parsed_payload

TARGET_TYPES = (
    ("matchmarketscontentapi/markets", "markets"),
    ("matchbettingcontentapi/coupon", "coupon"),
    ("splashcontentapi/changefixture", "changefixture"),
    ("splashcontentapi", "splash"),
    ("blob", "blob"),
)

DEFAULT_OUT_DIR = str(Path(__file__).resolve().parent / "playwright_captures")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Captura una liga Bet365, descubre eventos desde markets y captura coupon por evento.",
    )
    parser.add_argument("url", help="URL de liga Bet365.")
    parser.add_argument(
        "--out-dir",
        default=DEFAULT_OUT_DIR,
        help="Directorio raíz para las capturas.",
    )
    parser.add_argument(
        "--host",
        default="www.bet365.es",
        help="Host para reconstruir event_url.",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=8.0,
        help="Espera adicional por navegación.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Timeout general de navegación.",
    )
    parser.add_argument(
        "--channel",
        default=None,
        help="Canal del navegador, por ejemplo chrome.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Ejecuta en headless. Por default abre ventana.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=None,
        help="Limita la cantidad de eventos a iterar.",
    )
    return parser.parse_args()


def classify_response(url: str) -> str | None:
    lowered = url.lower()
    for needle, label in TARGET_TYPES:
        if needle in lowered:
            return label
    return None


def derive_pd_from_visual_league_url(url: str) -> str:
    parsed = urlparse(url)
    fragment = (parsed.fragment or "").strip()
    if not fragment:
        raise ValueError("La URL visual no tiene fragmento '#/...'.")
    if fragment.startswith("/"):
        fragment = fragment[1:]
    fragment = fragment.strip("/")
    if not fragment:
        raise ValueError("No pude extraer el fragmento de liga desde la URL visual.")
    return f"#{fragment.replace('/', '#')}#"


def build_league_api_url(input_url: str, *, host: str) -> tuple[str, str]:
    parsed = urlparse(input_url)
    if "matchmarketscontentapi/markets" in parsed.path:
        query = parse_qs(parsed.query)
        pd = (query.get("pd") or [""])[0]
        return input_url, pd

    pd = derive_pd_from_visual_league_url(input_url)
    encoded_pd = quote(pd, safe="")
    api_url = (
        f"https://{host}/matchmarketscontentapi/markets"
        f"?lid=3&zid=0&pd={encoded_pd}&cid=171&cgid=4&ctid=171"
    )
    return api_url, pd


def build_capture_dir(base_dir: Path, source_url: str) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    slug = infer_capture_slug(source_url)
    return ensure_dir(base_dir / f"{timestamp}-{slug}")


def make_scope(scope_dir: Path) -> dict[str, Any]:
    return {
        "dir": scope_dir,
        "payload_dir": ensure_dir(scope_dir / "payloads"),
        "parsed_dir": ensure_dir(scope_dir / "parsed_payloads"),
        "records": [],
        "parsed_payloads": [],
        "counter": itertools.count(1),
    }


def build_preview(text: str | None, *, limit: int = 200) -> str:
    if text is None:
        return ""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def payload_looks_useful(text: str | None) -> bool:
    if not text:
        return False
    required_tokens = ("EV;", "MG;ID=40", "PA;", "FI=")
    return all(token in text for token in required_tokens)


def extract_browser_template_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    allowed = {
        "accept",
        "accept-language",
        "cache-control",
        "pragma",
        "x-net-sync-term",
        "x-request-id",
    }
    return {
        key.lower(): value
        for key, value in headers.items()
        if key.lower() in allowed and value
    }


def save_parsed_payload(
    scope: dict[str, Any],
    *,
    detected_type: str,
    response_url: str,
    body_path: Path,
    parsed: dict[str, Any],
) -> Path:
    index = len(scope["parsed_payloads"]) + 1
    parsed_path = scope["parsed_dir"] / f"parsed-{index:04d}-{detected_type}.json"
    write_json(parsed_path, parsed)
    scope["parsed_payloads"].append(
        {
            "source_url": response_url,
            "detected_type": detected_type,
            "body_path": str(body_path.relative_to(scope["dir"])),
            "parsed_path": str(parsed_path.relative_to(scope["dir"])),
            "parsed": parsed,
        }
    )
    return parsed_path


def latest_parsed_payload(scope: dict[str, Any], *, payload_type: str) -> dict[str, Any] | None:
    for item in reversed(scope["parsed_payloads"]):
        if item["parsed"].get("payload_type") == payload_type:
            return item
    return None


def write_scope_summary(scope: dict[str, Any]) -> None:
    write_json(scope["dir"] / "responses.json", scope["records"])


def finalize_league_scope(scope: dict[str, Any]) -> dict[str, Any] | None:
    write_scope_summary(scope)
    latest = latest_parsed_payload(scope, payload_type="markets")
    if latest is None:
        write_json(
            scope["dir"] / "summary.json",
            {
                "kind": "league",
                "events_count": 0,
                "markets_count": 0,
                "notes": "No se capturó un payload markets utilizable.",
            },
        )
        return None

    parsed = latest["parsed"]
    events = parsed.get("events") or []
    flattened = flatten_markets(events)

    write_json(scope["dir"] / "parsed_league.json", parsed)
    write_json(scope["dir"] / "parsed_league_events.json", events)
    write_json(scope["dir"] / "parsed_league_markets.json", flattened)
    write_json(
        scope["dir"] / "summary.json",
        {
            "kind": "league",
            "events_count": len(events),
            "markets_count": len(flattened),
            "payload_summary": summarize_parsed_payload(parsed),
        },
    )
    return parsed


def finalize_event_scope(scope: dict[str, Any], *, league_event: dict[str, Any]) -> None:
    write_scope_summary(scope)
    latest = latest_parsed_payload(scope, payload_type="coupon")
    event_summary = {
        "kind": "event",
        "fixture_id": league_event.get("fixture_id"),
        "event_token": league_event.get("event_token"),
        "name": league_event.get("name"),
        "event_url": league_event.get("event_url"),
        "coupon_captured": latest is not None,
    }

    if latest is None:
        event_summary["notes"] = "No se capturó un payload coupon utilizable."
        write_json(scope["dir"] / "summary.json", event_summary)
        return

    parsed = latest["parsed"]
    events = parsed.get("events") or []
    flattened = flatten_markets(events)
    write_json(scope["dir"] / "parsed_coupon.json", parsed)
    write_json(scope["dir"] / "parsed_events.json", events)
    write_json(scope["dir"] / "parsed_markets.json", flattened)
    event_summary["markets_count"] = len(flattened)
    event_summary["payload_summary"] = summarize_parsed_payload(parsed)
    write_json(scope["dir"] / "summary.json", event_summary)


async def navigate_and_wait(page: Any, url: str, *, timeout_ms: int, wait_seconds: float) -> None:
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 12000))
    except PlaywrightTimeoutError:
        pass
    await asyncio.sleep(wait_seconds)


async def request_league_api(
    page: Any,
    scope: dict[str, Any],
    *,
    api_url: str,
    host: str,
    timeout_ms: int,
    template_headers: dict[str, str] | None,
    referrer_url: str,
) -> dict[str, Any]:
    async def persist_attempt(
        *,
        source: str,
        resource_type: str,
        response_url: str,
        status: int | None,
        headers: dict[str, str] | None,
        raw_body: bytes,
    ) -> dict[str, Any]:
        index = next(scope["counter"])
        normalized_headers = dict(headers or {})
        content_type = normalized_headers.get("content-type")
        text_body, text_encoding = decode_body(raw_body, content_type)
        body_suffix = ".txt" if text_body is not None else ".bin"
        body_path = scope["payload_dir"] / safe_filename_from_url(
            response_url or api_url,
            prefix=f"response-{index:04d}-markets-explicit",
            suffix=body_suffix,
        )
        if text_body is not None:
            body_path.write_text(text_body, encoding="utf-8")
        else:
            body_path.write_bytes(raw_body)

        metadata = {
            "index": index,
            "timestamp": time.time(),
            "url": response_url or api_url,
            "status": status,
            "method": "GET",
            "resource_type": resource_type,
            "body_bytes": len(raw_body),
            "content_type": content_type,
            "text_encoding": text_encoding,
            "detected_type": "markets",
            "body_path": str(body_path.relative_to(scope["dir"])),
            "source": source,
            "body_preview": build_preview(text_body),
        }

        parsed = None
        parsed_path = None
        useful = payload_looks_useful(text_body)
        if useful:
            parsed = parse_bet365_payload_text(text_body or "", host=host)
            parsed_path = save_parsed_payload(
                scope,
                detected_type="markets",
                response_url=response_url or api_url,
                body_path=body_path,
                parsed=parsed,
            )
            metadata["parsed_path"] = str(parsed_path.relative_to(scope["dir"]))
            metadata["payload_type"] = parsed.get("payload_type")

        scope["records"].append(metadata)
        return {
            "source": source,
            "status": status,
            "body_bytes": len(raw_body),
            "body_preview": build_preview(text_body),
            "parsed": parsed,
            "useful": useful,
        }

    browser_headers = extract_browser_template_headers(template_headers)

    fetch_result = await page.evaluate(
        """async ({ apiUrl, referrerUrl, extraHeaders }) => {
            const response = await fetch(apiUrl, {
                method: "GET",
                credentials: "include",
                referrer: referrerUrl,
                headers: extraHeaders,
            });
            const text = await response.text();
            return {
                status: response.status,
                url: response.url,
                headers: Object.fromEntries(response.headers.entries()),
                text,
            };
        }""",
        {
            "apiUrl": api_url,
            "referrerUrl": referrer_url,
            "extraHeaders": browser_headers or {"accept": "*/*"},
        },
    )
    fetch_attempt = await persist_attempt(
        source="explicit_league_api_fetch",
        resource_type="page_fetch",
        response_url=fetch_result.get("url") or api_url,
        status=fetch_result.get("status"),
        headers=fetch_result.get("headers") or {},
        raw_body=(fetch_result.get("text") or "").encode("utf-8", errors="ignore"),
    )
    if fetch_attempt["useful"]:
        return fetch_attempt

    xhr_result = await page.evaluate(
        """async ({ apiUrl, extraHeaders }) => {
            return await new Promise((resolve) => {
                const request = new XMLHttpRequest();
                request.open("GET", apiUrl, true);
                for (const [key, value] of Object.entries(extraHeaders)) {
                    try {
                        request.setRequestHeader(key, value);
                    } catch (error) {
                    }
                }
                request.onload = () => {
                    resolve({
                        status: request.status,
                        url: apiUrl,
                        headers: {},
                        text: request.responseText || "",
                    });
                };
                request.onerror = () => {
                    resolve({
                        status: request.status || 0,
                        url: apiUrl,
                        headers: {},
                        text: "",
                    });
                };
                request.send();
            });
        }""",
        {
            "apiUrl": api_url,
            "extraHeaders": browser_headers or {"accept": "*/*"},
        },
    )
    xhr_attempt = await persist_attempt(
        source="explicit_league_api_xhr",
        resource_type="xhr",
        response_url=xhr_result.get("url") or api_url,
        status=xhr_result.get("status"),
        headers=xhr_result.get("headers") or {},
        raw_body=(xhr_result.get("text") or "").encode("utf-8", errors="ignore"),
    )
    if xhr_attempt["useful"]:
        return xhr_attempt

    api_page = await page.context.new_page()
    try:
        response = await api_page.goto(api_url, wait_until="domcontentloaded", timeout=timeout_ms)
        if response is None:
            return xhr_attempt if xhr_attempt["body_bytes"] > fetch_attempt["body_bytes"] else fetch_attempt
        goto_attempt = await persist_attempt(
            source="explicit_league_api_goto",
            resource_type="document",
            response_url=response.url,
            status=response.status,
            headers=await response.all_headers(),
            raw_body=await response.body(),
        )
        if goto_attempt["useful"]:
            return goto_attempt
        best_attempt = max(
            (fetch_attempt, xhr_attempt, goto_attempt),
            key=lambda attempt: attempt["body_bytes"],
        )
        if best_attempt["body_bytes"] > 0:
            return best_attempt
        if goto_attempt["body_bytes"] > fetch_attempt["body_bytes"]:
            return goto_attempt
        return fetch_attempt
    finally:
        await api_page.close()


async def capture_league_events(args: argparse.Namespace) -> Path:
    capture_dir = build_capture_dir(Path(args.out_dir), args.url)
    league_scope = make_scope(ensure_dir(capture_dir / "league"))
    events_root = ensure_dir(capture_dir / "events")
    league_api_url, derived_pd = build_league_api_url(args.url, host=args.host)

    scopes: dict[str, dict[str, Any]] = {"league": league_scope}
    active_scope_key = "league"
    pending_tasks: set[asyncio.Task[None]] = set()
    latest_browser_headers: dict[str, str] = {}

    async def handle_response(response: Any) -> None:
        nonlocal active_scope_key
        detected_type = classify_response(response.url)
        if detected_type is None:
            return

        scope = scopes[active_scope_key]
        index = next(scope["counter"])
        request = response.request
        headers = await response.all_headers()
        content_type = headers.get("content-type")

        raw_body = b""
        body_error: str | None = None
        try:
            raw_body = await response.body()
        except Exception as error:  # pragma: no cover
            body_error = str(error)

        text_body, text_encoding = decode_body(raw_body, content_type)
        body_suffix = ".txt" if text_body is not None else ".bin"
        body_path = scope["payload_dir"] / safe_filename_from_url(
            response.url,
            prefix=f"response-{index:04d}-{detected_type}",
            suffix=body_suffix,
        )
        if text_body is not None:
            body_path.write_text(text_body, encoding="utf-8")
        else:
            body_path.write_bytes(raw_body)

        metadata = {
            "index": index,
            "timestamp": time.time(),
            "url": response.url,
            "status": response.status,
            "method": request.method,
            "resource_type": request.resource_type,
            "body_bytes": len(raw_body),
            "content_type": content_type,
            "text_encoding": text_encoding,
            "detected_type": detected_type,
            "body_path": str(body_path.relative_to(scope["dir"])),
        }
        if body_error:
            metadata["body_error"] = body_error

        if text_body and detected_type in {"markets", "coupon"}:
            parsed = parse_bet365_payload_text(text_body, host=args.host)
            parsed_path = scope["parsed_dir"] / f"parsed-{index:04d}-{detected_type}.json"
            write_json(parsed_path, parsed)
            metadata["parsed_path"] = str(parsed_path.relative_to(scope["dir"]))
            metadata["payload_type"] = parsed.get("payload_type")
            scope["parsed_payloads"].append(
                {
                    "source_url": response.url,
                    "detected_type": detected_type,
                    "body_path": str(body_path.relative_to(scope["dir"])),
                    "parsed_path": str(parsed_path.relative_to(scope["dir"])),
                    "parsed": parsed,
                }
            )

        scope["records"].append(metadata)

    async def handle_request(request: Any) -> None:
        nonlocal latest_browser_headers
        lowered = request.url.lower()
        if "bet365.es" not in lowered:
            return
        if "/api/1/blob" not in lowered and "matchmarketscontentapi" not in lowered:
            return
        headers = await request.all_headers()
        template = extract_browser_template_headers(headers)
        if template:
            latest_browser_headers = template

    async def drain_tasks() -> None:
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
            pending_tasks.clear()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=args.headless, channel=args.channel)
        context = await browser.new_context()

        def on_response(response: Any) -> None:
            task = asyncio.create_task(handle_response(response))
            pending_tasks.add(task)
            task.add_done_callback(pending_tasks.discard)

        def on_request(request: Any) -> None:
            task = asyncio.create_task(handle_request(request))
            pending_tasks.add(task)
            task.add_done_callback(pending_tasks.discard)

        def attach_response_listener(bound_page: Any) -> None:
            bound_page.on("response", on_response)
            bound_page.on("request", on_request)

        try:
            bootstrap_page = await context.new_page()
            attach_response_listener(bootstrap_page)
            await navigate_and_wait(
                bootstrap_page,
                f"https://{args.host}/",
                timeout_ms=args.timeout_ms,
                wait_seconds=args.wait_seconds,
            )
            league_page = await context.new_page()
            attach_response_listener(league_page)
            await navigate_and_wait(
                league_page,
                args.url,
                timeout_ms=args.timeout_ms,
                wait_seconds=args.wait_seconds,
            )
            await drain_tasks()
            league_api_result = await request_league_api(
                league_page,
                league_scope,
                api_url=league_api_url,
                host=args.host,
                timeout_ms=args.timeout_ms,
                template_headers=latest_browser_headers,
                referrer_url=args.url,
            )
            await drain_tasks()
            parsed_league = finalize_league_scope(league_scope)
            league_events = (parsed_league or {}).get("events") or []
            if args.max_events is not None:
                league_events = league_events[: args.max_events]

            processed_events: list[dict[str, Any]] = []
            for league_event in league_events:
                fixture_id = league_event.get("fixture_id") or "unknown-fixture"
                event_dir = ensure_dir(events_root / str(fixture_id))
                scopes[str(fixture_id)] = make_scope(event_dir)
                active_scope_key = str(fixture_id)

                event_url = league_event.get("event_url") or build_event_url(
                    league_event.get("event_pd"),
                    host=args.host,
                )
                if not event_url:
                    finalize_event_scope(scopes[str(fixture_id)], league_event=league_event)
                    processed_events.append(
                        {
                            "fixture_id": fixture_id,
                            "name": league_event.get("name"),
                            "event_url": None,
                            "coupon_captured": False,
                            "notes": "No se pudo construir event_url.",
                        }
                    )
                    continue

                await navigate_and_wait(
                    league_page,
                    event_url,
                    timeout_ms=args.timeout_ms,
                    wait_seconds=args.wait_seconds,
                )
                await drain_tasks()
                finalize_event_scope(scopes[str(fixture_id)], league_event=league_event)
                event_summary = json.loads((event_dir / "summary.json").read_text(encoding="utf-8"))
                processed_events.append(event_summary)

            write_json(
                capture_dir / "summary.json",
                {
                    "input_league_url": args.url,
                    "resolved_league_api_url": league_api_url,
                    "derived_pd": derived_pd,
                    "league_api_status": league_api_result["status"],
                    "league_api_body_size": league_api_result["body_bytes"],
                    "league_api_body_preview": league_api_result["body_preview"],
                    "league_events_discovered": len((parsed_league or {}).get("events") or []),
                    "league_events_processed": len(processed_events),
                    "processed_events": processed_events,
                },
            )
        finally:
            await drain_tasks()
            await context.close()
            await browser.close()

    return capture_dir


def print_summary(capture_dir: Path) -> None:
    summary = json.loads((capture_dir / "summary.json").read_text(encoding="utf-8"))
    print(f"Captura liga: {capture_dir}")
    print(f"input_league_url: {summary['input_league_url']}")
    print(f"derived_pd: {summary['derived_pd']}")
    print(f"resolved_league_api_url: {summary['resolved_league_api_url']}")
    print(f"league_api_status: {summary['league_api_status']}")
    print(f"league_api_body_size: {summary['league_api_body_size']}")
    print(f"league_api_body_preview: {summary['league_api_body_preview']}")
    print(f"Eventos descubiertos: {summary['league_events_discovered']}")
    print(f"Eventos procesados: {summary['league_events_processed']}")
    for event in summary.get("processed_events", [])[:5]:
        print(
            f"- {event.get('fixture_id')} | {event.get('name')} | coupon={event.get('coupon_captured')}"
        )


async def async_main() -> int:
    args = parse_args()
    capture_dir = await capture_league_events(args)
    print_summary(capture_dir)
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())

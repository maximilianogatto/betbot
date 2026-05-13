from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import time
from pathlib import Path
from typing import Any

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from common import decode_body, ensure_dir, infer_capture_slug, safe_filename_from_url, write_json
from parser import flatten_markets, parse_bet365_payload_text, summarize_parsed_payload

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
        description="Captura responses de red de Bet365 con Playwright y parsea payloads útiles offline.",
    )
    parser.add_argument("url", help="URL de liga o evento Bet365.")
    parser.add_argument(
        "--out-dir",
        default=DEFAULT_OUT_DIR,
        help="Directorio raíz donde guardar capturas.",
    )
    parser.add_argument(
        "--host",
        default="www.bet365.es",
        help="Host para reconstruir event_url a partir de event_pd.",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=12.0,
        help="Tiempo adicional a esperar luego de la navegación inicial.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Timeout general de navegación y de respuesta.",
    )
    parser.add_argument(
        "--channel",
        default=None,
        help="Canal opcional del navegador, por ejemplo chrome o msedge.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Ejecuta Playwright en modo headless. Por default abre ventana.",
    )
    return parser.parse_args()


def classify_response(url: str) -> str | None:
    lowered = url.lower()
    for needle, label in TARGET_TYPES:
        if needle in lowered:
            return label
    return None


def build_capture_dir(base_dir: Path, source_url: str) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    slug = infer_capture_slug(source_url)
    return ensure_dir(base_dir / f"{timestamp}-{slug}")


def dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen: dict[str, dict[str, Any]] = {}
    for event in events:
        key = event.get("event_id") or event.get("fixture_id") or json.dumps(event, sort_keys=True)
        current = chosen.get(key)
        current_markets = len((current or {}).get("markets") or [])
        candidate_markets = len(event.get("markets") or [])
        if current is None or candidate_markets >= current_markets:
            chosen[key] = event
    return list(chosen.values())


async def capture(url: str, *, args: argparse.Namespace) -> Path:
    capture_dir = build_capture_dir(Path(args.out_dir), url)
    payload_dir = ensure_dir(capture_dir / "payloads")
    parsed_dir = ensure_dir(capture_dir / "parsed_payloads")

    response_index = itertools.count(1)
    records: list[dict[str, Any]] = []
    parsed_payloads: list[dict[str, Any]] = []
    pending_tasks: set[asyncio.Task[None]] = set()

    async def handle_response(response: Any) -> None:
        detected_type = classify_response(response.url)
        if detected_type is None:
            return

        index = next(response_index)
        timestamp = time.time()
        request = response.request
        status = response.status
        headers = await response.all_headers()
        content_type = headers.get("content-type")

        raw_body = b""
        body_error: str | None = None
        try:
            raw_body = await response.body()
        except Exception as error:  # pragma: no cover - defensive against Playwright transport issues
            body_error = str(error)

        text_body, text_encoding = decode_body(raw_body, content_type)
        body_suffix = ".txt" if text_body is not None else ".bin"
        body_path = payload_dir / safe_filename_from_url(
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
            "timestamp": timestamp,
            "url": response.url,
            "status": status,
            "method": request.method,
            "resource_type": request.resource_type,
            "body_bytes": len(raw_body),
            "content_type": content_type,
            "text_encoding": text_encoding,
            "detected_type": detected_type,
            "body_path": str(body_path.relative_to(capture_dir)),
        }
        if body_error:
            metadata["body_error"] = body_error

        if text_body and detected_type in {"coupon", "markets"}:
            parsed = parse_bet365_payload_text(text_body, host=args.host)
            parsed_path = parsed_dir / f"parsed-{index:04d}-{detected_type}.json"
            write_json(parsed_path, parsed)
            metadata["parsed_path"] = str(parsed_path.relative_to(capture_dir))
            metadata["payload_type"] = parsed.get("payload_type")
            parsed_payloads.append(
                {
                    "source_url": response.url,
                    "detected_type": detected_type,
                    "body_path": str(body_path.relative_to(capture_dir)),
                    "parsed_path": str(parsed_path.relative_to(capture_dir)),
                    "parsed": parsed,
                }
            )

        records.append(metadata)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=args.headless,
            channel=args.channel,
        )
        context = await browser.new_context()
        page = await context.new_page()

        def on_response(response: Any) -> None:
            task = asyncio.create_task(handle_response(response))
            pending_tasks.add(task)
            task.add_done_callback(pending_tasks.discard)

        page.on("response", on_response)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=args.timeout_ms)
            try:
                await page.wait_for_load_state("networkidle", timeout=min(args.timeout_ms, 12000))
            except PlaywrightTimeoutError:
                pass
            await asyncio.sleep(args.wait_seconds)
        finally:
            if pending_tasks:
                await asyncio.gather(*pending_tasks, return_exceptions=True)
            await context.close()
            await browser.close()

    write_json(capture_dir / "responses.json", records)

    all_events: list[dict[str, Any]] = []
    for item in parsed_payloads:
        all_events.extend(item["parsed"].get("events") or [])
    deduped_events = dedupe_events(all_events)
    flattened_markets = flatten_markets(deduped_events)

    write_json(capture_dir / "parsed_events.json", deduped_events)
    write_json(capture_dir / "parsed_markets.json", flattened_markets)

    summary = {
        "source_url": url,
        "capture_dir": str(capture_dir),
        "captured_responses": len(records),
        "captured_types": {
            label: sum(1 for record in records if record["detected_type"] == label)
            for _, label in TARGET_TYPES
        },
        "parsed_payloads": [
            {
                "source_url": item["source_url"],
                "detected_type": item["detected_type"],
                "body_path": item["body_path"],
                "parsed_path": item["parsed_path"],
                "payload_type": item["parsed"].get("payload_type"),
                "summary": summarize_parsed_payload(item["parsed"]),
            }
            for item in parsed_payloads
        ],
        "events_count": len(deduped_events),
        "markets_count": len(flattened_markets),
    }
    write_json(capture_dir / "summary.json", summary)

    return capture_dir


def print_summary(capture_dir: Path) -> None:
    summary = json.loads((capture_dir / "summary.json").read_text(encoding="utf-8"))
    print(f"Captura: {capture_dir}")
    print(f"Responses guardadas: {summary['captured_responses']}")
    print(f"Eventos parseados: {summary['events_count']}")
    print(f"Mercados parseados: {summary['markets_count']}")

    events_path = capture_dir / "parsed_events.json"
    if not events_path.exists():
        return

    events = json.loads(events_path.read_text(encoding="utf-8"))
    for event in events[:3]:
        print(f"- {event.get('name') or event.get('fixture_id')}")
        for market in (event.get("markets") or [])[:5]:
            selections = ", ".join(
                f"{selection.get('name')}={selection.get('odds_fractional') or selection.get('odds_decimal')}"
                for selection in (market.get("selections") or [])[:3]
            )
            print(f"  * {market.get('name')}: {selections}")


async def async_main() -> int:
    args = parse_args()
    capture_dir = await capture(args.url, args=args)
    print_summary(capture_dir)
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from common import decode_body, ensure_dir, infer_capture_slug, write_json
from parser import build_league_1x2_projection, clean_text, parse_bet365_payload_text, parse_record

DEFAULT_OUT_DIR = str(Path(__file__).resolve().parent / "playwright_captures")
BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
MENU_RESPONSE_MARKER = "leftnavcontentapi/allsportsmenu"
RELEVANT_RESPONSE_MARKERS = (
    "matchmarketscontentapi/markets",
    "sitecontent?id=3",
    "splashcontentapi/changecompetition",
    "leftnavcontentapi/allsportsmenu",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Captura solo matchmarketscontentapi/markets para una liga Bet365 y extrae Full Time Result.",
    )
    parser.add_argument("league_url", help="URL visual de liga Bet365.")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--wait-seconds", type=float, default=8.0)
    parser.add_argument("--response-timeout-ms", type=int, default=25000)
    parser.add_argument("--channel", default=None)
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Reservado para una pasada futura. En esta etapa se ignora y el navegador abre UI para depurar.",
    )
    return parser.parse_args()


def build_capture_dir(base_dir: Path, source_url: str) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    slug = infer_capture_slug(source_url)
    return ensure_dir(base_dir / f"{timestamp}-{slug}")


def derive_hash_and_pd_from_league_url(league_url: str) -> tuple[str, str]:
    parsed = urlparse(league_url)
    fragment = (parsed.fragment or "").strip()
    if not fragment:
        raise ValueError("La URL visual no tiene fragment '#/...'.")
    if not fragment.startswith("/"):
        fragment = "/" + fragment
    normalized_hash = "#" + fragment
    pd = "#" + fragment.strip("/").replace("/", "#") + "#"
    return normalized_hash, pd


def build_preview(text: str | None, *, limit: int = 200) -> str:
    if not text:
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


def extract_decoded_pd(url: str) -> str | None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    pd_values = query.get("pd")
    if not pd_values:
        return None
    return unquote(pd_values[0])


def extract_expected_pd_tokens(expected_pd: str) -> list[str]:
    return [part for part in expected_pd.strip("#").split("#") if part]


def response_matches_expected_pd(url: str, expected_pd: str) -> bool:
    decoded_pd = extract_decoded_pd(url)
    if decoded_pd == expected_pd:
        return True
    if decoded_pd:
        expected_tokens = extract_expected_pd_tokens(expected_pd)
        return all(token in decoded_pd for token in expected_tokens)
    return False


def parse_menu_entries(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw_record in text.split("|"):
        parsed = parse_record(raw_record)
        if parsed is None:
            continue
        record_type, fields = parsed
        if record_type != "EV":
            continue
        name = clean_text(fields.get("NA"))
        pd = clean_text(fields.get("PD"))
        it = clean_text(fields.get("IT"))
        if not name and not pd:
            continue
        entries.append(
            {
                "id": clean_text(fields.get("ID")),
                "name": name,
                "pd": pd,
                "it": it,
                "ed": clean_text(fields.get("ED")),
                "ex": clean_text(fields.get("EX")),
                "rs": clean_text(fields.get("RS")),
            }
        )
    return entries


def find_menu_entry(entries: list[dict[str, Any]], expected_pd: str) -> dict[str, Any] | None:
    for entry in entries:
        if entry.get("pd") == expected_pd:
            return entry
    return None


async def click_first_visible_text(
    page,
    texts: list[str],
    *,
    exact: bool = True,
    timeout_ms: int = 2500,
) -> dict[str, str] | None:
    for text in texts:
        candidates = [
            ("anchor", page.locator("a", has_text=text).first),
            ("role_link", page.locator("[role='link']", has_text=text).first),
            ("button", page.locator("button", has_text=text).first),
            ("role_button", page.locator("[role='button']", has_text=text).first),
            ("text", page.get_by_text(text, exact=exact).first),
        ]
        for strategy, locator in candidates:
            try:
                if await locator.is_visible(timeout=500):
                    await locator.click(timeout=timeout_ms)
                    return {"text": text, "strategy": strategy}
            except Exception:
                continue
    return None


def write_text_payload(path: Path, raw_body: bytes, content_type: str | None) -> str | None:
    text_body, _ = decode_body(raw_body, content_type)
    if text_body is not None:
        path.write_text(text_body, encoding="utf-8")
    else:
        path.write_bytes(raw_body)
    return text_body


async def capture_body_text_snapshot(page, path: Path) -> str:
    try:
        body_text = await page.locator("body").inner_text(timeout=3000)
    except Exception:
        body_text = ""
    path.write_text(body_text, encoding="utf-8")
    return body_text


def persist_capture(
    capture_dir: Path,
    *,
    league_url: str,
    response_url: str,
    status: int | None,
    source: str,
    raw_body: bytes,
    content_type: str | None,
) -> dict:
    text_body, _ = decode_body(raw_body, content_type)
    raw_path = capture_dir / "raw_league_market.txt"
    if text_body is not None:
        raw_path.write_text(text_body, encoding="utf-8")
    else:
        raw_path.write_bytes(raw_body)

    parsed_projection = None
    parsed_payload = None
    if payload_looks_useful(text_body):
        host = urlparse(league_url).netloc or "www.bet365.es"
        parsed_payload = parse_bet365_payload_text(text_body or "", host=host)
        parsed_projection = build_league_1x2_projection(parsed_payload, league_url=league_url)
        write_json(capture_dir / "parsed_league_1x2.json", parsed_projection)

    summary = {
        "league_url": league_url,
        "response_url": response_url,
        "source": source,
        "status": status,
        "body_size": len(raw_body),
        "body_preview": build_preview(text_body),
        "useful_payload": parsed_projection is not None,
        "events_extracted": len((parsed_projection or {}).get("events") or []),
    }
    write_json(capture_dir / "summary.json", summary)
    return summary


async def navigate_and_wait(page, url: str, *, timeout_ms: int, wait_seconds: float) -> None:
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 12000))
    except PlaywrightTimeoutError:
        pass
    await asyncio.sleep(wait_seconds)


async def wait_for_menu_response(page, *, timeout_ms: int):
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def on_response(response) -> None:
        if future.done():
            return
        lowered = response.url.lower()
        if MENU_RESPONSE_MARKER not in lowered:
            return
        future.set_result(response)

    page.on("response", on_response)
    try:
        return await asyncio.wait_for(future, timeout=timeout_ms / 1000)
    finally:
        page.remove_listener("response", on_response)


async def capture_league_1x2(args: argparse.Namespace) -> Path:
    capture_dir = build_capture_dir(Path(args.out_dir), args.league_url)
    _, expected_pd = derive_hash_and_pd_from_league_url(args.league_url)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False, channel=args.channel)
        context = await browser.new_context()
        page = await context.new_page()
        matched_response_future: asyncio.Future = asyncio.get_running_loop().create_future()
        debug_responses: list[dict] = []
        pending_tasks: set[asyncio.Task] = set()
        saved_response_bodies: list[dict[str, Any]] = []
        response_body_index = 0

        async def route_handler(route, request) -> None:
            if request.resource_type in BLOCKED_RESOURCE_TYPES:
                await route.abort()
                return
            await route.continue_()

        await page.route("**/*", route_handler)

        def on_response(response) -> None:
            lowered_url = response.url.lower()
            is_markets = "matchmarketscontentapi/markets" in lowered_url
            should_try_body = (
                not matched_response_future.done()
                and is_markets
            ) or any(marker in lowered_url for marker in RELEVANT_RESPONSE_MARKERS)
            task = asyncio.create_task(
                handle_response_debug(
                    response,
                    debug_responses,
                    matched_response_future,
                    should_try_body,
                    capture_dir,
                    saved_response_bodies,
                )
            )
            pending_tasks.add(task)
            task.add_done_callback(pending_tasks.discard)

        async def handle_response_debug(
            response,
            debug_records,
            response_future,
            should_try_body: bool,
            current_capture_dir: Path,
            saved_bodies: list[dict[str, Any]],
        ) -> None:
            nonlocal response_body_index
            request = response.request
            headers = await response.all_headers()
            content_type = headers.get("content-type")
            raw_body = b""
            text_body = None
            decoded_pd = extract_decoded_pd(response.url)
            lowered_url = response.url.lower()
            try:
                if should_try_body or content_type and "text" in content_type.lower():
                    raw_body = await response.body()
                    text_body, _ = decode_body(raw_body, content_type)
            except Exception:
                text_body = None
                raw_body = b""

            body_path = None
            if raw_body and ("markets?lid=" in lowered_url or any(marker in lowered_url for marker in RELEVANT_RESPONSE_MARKERS)):
                response_body_index += 1
                body_path = (
                    current_capture_dir
                    / f"response-{response_body_index:04d}.txt"
                )
                write_text_payload(body_path, raw_body, content_type)
                saved_bodies.append(
                    {
                        "url": response.url,
                        "status": response.status,
                        "content_type": content_type,
                        "path": body_path.name,
                    }
                )

            debug_records.append(
                {
                    "url": response.url,
                    "status": response.status,
                    "resource_type": request.resource_type,
                    "content_type": content_type,
                    "decoded_pd": decoded_pd,
                    "body_preview": build_preview(text_body),
                    "body_path": body_path.name if body_path is not None else None,
                }
            )

            if response_future.done():
                return
            if "matchmarketscontentapi/markets" not in response.url.lower():
                return
            if not response_matches_expected_pd(response.url, expected_pd):
                return
            if not text_body or not text_body.startswith("F|"):
                return
            response_future.set_result(
                {
                    "response_url": response.url,
                    "status": response.status,
                    "content_type": content_type,
                    "raw_body": raw_body,
                    "decoded_pd": decoded_pd,
                }
            )

        page.on("response", on_response)

        async def drain_tasks() -> None:
            if pending_tasks:
                await asyncio.gather(*pending_tasks, return_exceptions=True)
                pending_tasks.clear()

        try:
            menu_task = asyncio.create_task(
                wait_for_menu_response(
                    page,
                    timeout_ms=min(args.timeout_ms, args.response_timeout_ms),
                )
            )
            await navigate_and_wait(
                page,
                f"https://{urlparse(args.league_url).netloc or 'www.bet365.es'}/",
                timeout_ms=args.timeout_ms,
                wait_seconds=min(args.wait_seconds, 3.0),
            )
            menu_response = None
            menu_text = None
            menu_entries: list[dict[str, Any]] = []
            target_entry = None
            try:
                menu_response = await menu_task
            except asyncio.TimeoutError:
                menu_response = None

            if menu_response is not None:
                menu_headers = await menu_response.all_headers()
                menu_content_type = menu_headers.get("content-type")
                menu_raw_body = await menu_response.body()
                menu_text = write_text_payload(capture_dir / "bootstrap_allsportsmenu.txt", menu_raw_body, menu_content_type)
                menu_entries = parse_menu_entries(menu_text or "")
                target_entry = find_menu_entry(menu_entries, expected_pd)
                write_json(capture_dir / "bootstrap_allsportsmenu_entries.json", menu_entries)

            hash_before_ui = await page.evaluate("location.hash")
            click_steps: list[dict[str, Any]] = []
            target_name = (target_entry or {}).get("name") or "La Liga"
            text_snapshots: dict[str, str] = {}

            cookie_clicked = await click_first_visible_text(page, ["Aceptar todo", "Solo esenciales"], exact=True)
            click_steps.append({"step": "cookie_click", "result": cookie_clicked})
            if cookie_clicked is not None:
                await asyncio.sleep(1.5)
                cookie_text = await capture_body_text_snapshot(page, capture_dir / "body_after_cookie_click.txt")
                text_snapshots["after_cookie_click"] = build_preview(cookie_text, limit=500)

            direct_click = await click_first_visible_text(page, [target_name], exact=True)
            click_steps.append({"step": "direct_target_click", "result": direct_click})
            await asyncio.sleep(2.0)
            hash_after_direct_click = await page.evaluate("location.hash")

            if not matched_response_future.done() and hash_after_direct_click == hash_before_ui:
                sport_clicked = await click_first_visible_text(page, ["Fútbol", "Football", "Soccer"], exact=True)
                click_steps.append({"step": "sport_click", "result": sport_clicked})
                if sport_clicked is not None:
                    await asyncio.sleep(1.5)
                    sport_text = await capture_body_text_snapshot(page, capture_dir / "body_after_sport_click.txt")
                    text_snapshots["after_sport_click"] = build_preview(sport_text, limit=500)

                country_clicked = await click_first_visible_text(page, ["España", "Spain"], exact=False)
                click_steps.append({"step": "country_click", "result": country_clicked})
                if country_clicked is None:
                    az_clicked = await click_first_visible_text(page, ["A-Z"], exact=True)
                    click_steps.append({"step": "az_click", "result": az_clicked})
                    if az_clicked is not None:
                        await asyncio.sleep(1.5)
                        az_text = await capture_body_text_snapshot(page, capture_dir / "body_after_az_click.txt")
                        text_snapshots["after_az_click"] = build_preview(az_text, limit=500)
                        country_clicked = await click_first_visible_text(page, ["España", "Spain"], exact=False)
                        click_steps.append({"step": "country_click_after_az", "result": country_clicked})
                if country_clicked is not None:
                    await asyncio.sleep(1.5)
                    country_text = await capture_body_text_snapshot(page, capture_dir / "body_after_country_click.txt")
                    text_snapshots["after_country_click"] = build_preview(country_text, limit=500)

                league_clicked = await click_first_visible_text(page, [target_name], exact=False)
                click_steps.append({"step": "league_click", "result": league_clicked})
                if league_clicked is not None:
                    await asyncio.sleep(1.5)
                    league_text = await capture_body_text_snapshot(page, capture_dir / "body_after_league_click.txt")
                    text_snapshots["after_league_click"] = build_preview(league_text, limit=500)

            await asyncio.sleep(args.wait_seconds)
            hash_after_ui = await page.evaluate("location.hash")

            response = None
            try:
                response = await asyncio.wait_for(
                    asyncio.shield(matched_response_future),
                    timeout=args.response_timeout_ms / 1000,
                )
            except asyncio.TimeoutError:
                response = None

            await drain_tasks()
            if response is not None:
                summary = persist_capture(
                    capture_dir,
                    league_url=args.league_url,
                    response_url=response["response_url"],
                    status=response["status"],
                    source="auto_response",
                    raw_body=response["raw_body"],
                    content_type=response["content_type"],
                )
                write_json(capture_dir / "debug_responses.json", debug_responses)
                summary["expected_pd"] = expected_pd
                summary["hash_before_ui"] = hash_before_ui
                summary["hash_after_direct_click"] = hash_after_direct_click
                summary["hash_after_ui"] = hash_after_ui
                summary["menu_url"] = menu_response.url if menu_response else None
                summary["menu_entries_count"] = len(menu_entries)
                summary["menu_target_entry"] = target_entry
                summary["click_steps"] = click_steps
                summary["text_snapshots"] = text_snapshots
                summary["captured_pd_urls"] = [
                    {
                        "url": item.get("url"),
                        "decoded_pd": item.get("decoded_pd"),
                        "status": item.get("status"),
                        "resource_type": item.get("resource_type"),
                    }
                    for item in debug_responses
                    if item.get("decoded_pd")
                ]
                summary["saved_response_bodies"] = saved_response_bodies
                summary["relevant_responses"] = [
                    {
                        "url": item.get("url"),
                        "status": item.get("status"),
                        "resource_type": item.get("resource_type"),
                        "content_type": item.get("content_type"),
                        "decoded_pd": item.get("decoded_pd"),
                        "body_path": item.get("body_path"),
                    }
                    for item in debug_responses
                    if any(marker in (item.get("url") or "").lower() for marker in RELEVANT_RESPONSE_MARKERS)
                    or (item.get("decoded_pd") and response_matches_expected_pd(item.get("url") or "", expected_pd))
                ]
                write_json(capture_dir / "summary.json", summary)
                if summary["useful_payload"]:
                    return capture_dir

            write_json(capture_dir / "debug_responses.json", debug_responses)
            write_json(
                capture_dir / "summary.json",
                {
                    "league_url": args.league_url,
                    "expected_pd": expected_pd,
                    "source": "no_auto_markets_response",
                    "status": None,
                    "body_size": 0,
                    "body_preview": "",
                    "useful_payload": False,
                    "events_extracted": 0,
                    "hash_before_ui": hash_before_ui,
                    "hash_after_direct_click": hash_after_direct_click,
                    "hash_after_ui": hash_after_ui,
                    "menu_url": menu_response.url if menu_response else None,
                    "menu_entries_count": len(menu_entries),
                    "menu_target_entry": target_entry,
                    "click_steps": click_steps,
                    "text_snapshots": text_snapshots,
                    "captured_pd_urls": [
                        {
                            "url": item.get("url"),
                            "decoded_pd": item.get("decoded_pd"),
                            "status": item.get("status"),
                            "resource_type": item.get("resource_type"),
                        }
                        for item in debug_responses
                        if item.get("decoded_pd")
                    ],
                    "saved_response_bodies": saved_response_bodies,
                    "relevant_responses": [
                        {
                            "url": item.get("url"),
                            "status": item.get("status"),
                            "resource_type": item.get("resource_type"),
                            "content_type": item.get("content_type"),
                            "decoded_pd": item.get("decoded_pd"),
                            "body_path": item.get("body_path"),
                        }
                        for item in debug_responses
                        if any(marker in (item.get("url") or "").lower() for marker in RELEVANT_RESPONSE_MARKERS)
                        or (item.get("decoded_pd") and response_matches_expected_pd(item.get("url") or "", expected_pd))
                    ],
                    "debug_responses_path": "debug_responses.json",
                },
            )
            return capture_dir
        finally:
            await drain_tasks()
            await context.close()
            await browser.close()

    write_json(
        capture_dir / "summary.json",
        {
            "league_url": args.league_url,
            "source": "none",
            "status": None,
            "body_size": 0,
            "body_preview": "",
            "useful_payload": False,
            "events_extracted": 0,
        },
    )
    return capture_dir


def print_summary(capture_dir: Path) -> None:
    summary = json.loads((capture_dir / "summary.json").read_text(encoding="utf-8"))
    print(f"capture_dir: {capture_dir}")
    print(f"league_url: {summary['league_url']}")
    if summary.get("expected_pd") is not None:
        print(f"expected_pd: {summary['expected_pd']}")
    print(f"source: {summary['source']}")
    print(f"status: {summary['status']}")
    print(f"body_size: {summary['body_size']}")
    print(f"body_preview: {summary['body_preview']}")
    print(f"events_extracted: {summary['events_extracted']}")
    if summary.get("hash_before_ui") is not None:
        print(f"hash_before_ui: {summary['hash_before_ui']}")
    if summary.get("hash_after_direct_click") is not None:
        print(f"hash_after_direct_click: {summary['hash_after_direct_click']}")
    if summary.get("hash_after_ui") is not None:
        print(f"hash_after_ui: {summary['hash_after_ui']}")
    if summary.get("menu_url") is not None:
        print(f"menu_url: {summary['menu_url']}")
    if summary.get("menu_target_entry") is not None:
        print(f"menu_target_entry: {summary['menu_target_entry']}")
    if summary.get("click_steps"):
        print("click_steps:")
        for step in summary["click_steps"]:
            print(f" - {step.get('step')}: {step.get('result')}")
    if summary.get("text_snapshots"):
        print("text_snapshots:")
        for key, value in summary["text_snapshots"].items():
            print(f" - {key}: {value}")
    if summary.get("captured_pd_urls"):
        print("captured_pd_urls:")
        for item in summary["captured_pd_urls"][:10]:
            print(
                f" - {item.get('resource_type')} | {item.get('status')} | {item.get('decoded_pd')} | {item.get('url')}"
            )
    if summary.get("relevant_responses"):
        print("relevant_responses:")
        for item in summary["relevant_responses"][:10]:
            print(
                f" - {item.get('resource_type')} | {item.get('status')} | {item.get('content_type')} | {item.get('url')}"
            )
    debug_path = capture_dir / "debug_responses.json"
    if debug_path.exists():
        debug_items = json.loads(debug_path.read_text(encoding="utf-8"))
        print("debug_responses:")
        for item in debug_items[:10]:
            print(
                f" - {item.get('resource_type')} | {item.get('status')} | {item.get('content_type')} | {item.get('url')}"
            )


async def async_main() -> int:
    args = parse_args()
    capture_dir = await capture_league_1x2(args)
    print_summary(capture_dir)
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())

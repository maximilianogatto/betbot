from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, unquote

from playwright.async_api import async_playwright, Response


HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
}


def clean_pd_from_hash(url: str) -> str:
    """
    https://www.bet365.es/#/AC/B1/C1/D1002/E120757998/G40/
    -> #AC#B1#C1#D1002#E120757998#G40#
    """
    frag = urlparse(url).fragment.strip("/")
    if not frag:
        raise ValueError("La URL no tiene hash de liga.")

    parts = [p for p in frag.split("/") if p]
    return "#" + "#".join(parts) + "#"


def event_url_from_fixture(host: str, fixture_id: str) -> str:
    return f"https://{host}/#/AC/B1/C1/D8/E{fixture_id}/F3/I1/"


def parse_record(record: str) -> tuple[str, dict[str, str]]:
    chunks = record.split(";")
    typ = chunks[0]
    data: dict[str, str] = {}

    for chunk in chunks[1:]:
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            data[k] = v

    return typ, data


def iter_records(payload: str):
    payload = payload.replace("\x08", "")
    for raw in payload.split("|"):
        raw = raw.strip()
        if not raw or raw == "F":
            continue
        yield parse_record(raw)


def parse_bet365_league_1x2(payload: str, *, source_url: str) -> dict[str, Any]:
    host = urlparse(source_url).netloc or "www.bet365.es"

    events: dict[str, dict[str, Any]] = {}
    current_event_id: str | None = None
    current_market: str | None = None

    for typ, data in iter_records(payload):
        if typ == "EV":
            fixture_id = data.get("FI") or data.get("ID")
            name = data.get("NA") or data.get("EX")

            if not fixture_id or not fixture_id.isdigit():
                continue

            current_event_id = fixture_id

            home = data.get("N2")
            away = data.get("N3")

            if not home and name and " v " in name:
                home, away = name.split(" v ", 1)

            events.setdefault(
                fixture_id,
                {
                    "fixture_id": fixture_id,
                    "event_token": f"E{fixture_id}",
                    "name": name,
                    "home": home,
                    "away": away,
                    "start_raw": data.get("BC") or data.get("SM"),
                    "event_it": data.get("IT"),
                    "event_pd": data.get("PD"),
                    "event_url": event_url_from_fixture(host, fixture_id),
                    "sportradar_url": None,
                    "full_time_result": {},
                },
            )

        elif typ == "MG":
            market_name = data.get("NA")
            market_id = data.get("ID")

            if market_id == "40" or market_name == "Full Time Result":
                current_market = "full_time_result"
            else:
                current_market = None

        elif typ == "PA":
            if not current_event_id:
                continue

            if current_market != "full_time_result":
                continue

            odd = data.get("OD")
            name = data.get("NA")
            n2 = data.get("N2")

            if not odd:
                continue

            if n2 == "1":
                key = "1"
            elif n2 == "X":
                key = "X"
            elif n2 == "2":
                key = "2"
            elif name == "Draw":
                key = "X"
            else:
                key = name or data.get("ID") or "unknown"

            events[current_event_id]["full_time_result"][key] = {
                "name": name,
                "odd_fractional": odd,
                "selection_id": data.get("ID"),
            }

    matches = []

    for event in events.values():
        ftr = event.get("full_time_result") or {}

        if not any(k in ftr for k in ("1", "X", "2")):
            continue

        matches.append(event)

    matches.sort(key=lambda e: e.get("start_raw") or "")

    return {
        "source_url": source_url,
        "expected_pd": clean_pd_from_hash(source_url),
        "matches_count": len(matches),
        "matches": matches,
    }


async def scrape_bet365_league_fast(
    url: str,
    *,
    max_wait_ms: int = 20000,
    stable_ms: int = 2500,
    tick_ms: int = 250,
    headless: bool = True,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    expected_pd = clean_pd_from_hash(url)
    expected_pd_decoded = unquote(expected_pd)

    seen_urls: set[str] = set()
    useful_payloads: list[dict[str, Any]] = []
    debug_responses: list[dict[str, Any]] = []

    best_parsed: dict[str, Any] | None = None
    last_count = 0
    last_growth_time = time.monotonic()
    start_time = time.monotonic()

    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
            ],
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=HEADERS["user-agent"],
            locale="es-ES",
        )

        page = await context.new_page()

        async def route_handler(route):
            req = route.request
            rt = req.resource_type
            ru = req.url

            # Mantener liviano, pero NO bloquear scripts/xhr/fetch/document.
            if rt in {"image", "font", "media"}:
                await route.abort()
                return

            if ru.endswith(".svg") or "/sports-assets/" in ru or "/sportsbook-static/" in ru:
                await route.abort()
                return

            blocked_hosts = (
                "googletagmanager.com",
                "google-analytics.com",
                "facebook.net",
                "sentry.io",
                "intercom.io",
            )
            if any(h in ru for h in blocked_hosts):
                await route.abort()
                return

            await route.continue_()

        await context.route("**/*", route_handler)

        async def handle_response(response: Response) -> None:
            nonlocal best_parsed, last_count, last_growth_time

            response_url = response.url

            if response_url in seen_urls:
                return
            seen_urls.add(response_url)

            if "matchmarketscontentapi/markets" not in response_url:
                return

            item = {
                "url": response_url,
                "status": response.status,
                "resource_type": response.request.resource_type,
            }

            try:
                body = await response.text()
            except Exception as exc:
                item["error"] = repr(exc)
                debug_responses.append(item)
                return

            item["preview"] = body[:300].replace("\n", " ")
            debug_responses.append(item)

            if response.status != 200:
                return

            if not body.startswith("F|"):
                return

            decoded_url = unquote(response_url)

            # Filtro de liga esperada. Si Bet365 usa equivalente sin slash, esto lo cubre.
            if expected_pd_decoded not in decoded_url and expected_pd not in response_url:
                return

            parsed = parse_bet365_league_1x2(body, source_url=url)
            count = parsed["matches_count"]

            useful_payloads.append(
                {
                    "url": response_url,
                    "matches_count": count,
                    "raw": body,
                    "parsed": parsed,
                }
            )

            if best_parsed is None or count > best_parsed["matches_count"]:
                best_parsed = parsed

            if count > last_count:
                last_count = count
                last_growth_time = time.monotonic()

            print(f"   ✓ markets útil | matches={count}")

            if out_dir:
                (out_dir / "raw_league_market.txt").write_text(body, encoding="utf-8")
                (out_dir / "parsed_league_1x2.json").write_text(
                    json.dumps(parsed, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

        page.on("response", handle_response)

        print(f"→ URL visual: {url}")
        print(f"→ expected_pd: {expected_pd}")
        print("→ Abriendo SPA y escuchando matchmarketscontentapi/markets...")

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # Fase suave: dejar que la SPA cargue.
        while True:
            await page.wait_for_timeout(tick_ms)

            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            quiet_ms = int((time.monotonic() - last_growth_time) * 1000)

            if last_count > 0 and quiet_ms >= stable_ms:
                print(f"→ Corte por estabilidad: {last_count} partidos, {quiet_ms} ms sin crecer.")
                break

            if elapsed_ms >= max_wait_ms:
                print(f"→ Corte por timeout: {elapsed_ms} ms.")
                break

        await context.close()
        await browser.close()

    payload = {
        "source_url": url,
        "expected_pd": expected_pd,
        "useful_payloads": len(useful_payloads),
        "matches_count": best_parsed["matches_count"] if best_parsed else 0,
        "matches": best_parsed["matches"] if best_parsed else [],
        "debug_responses": debug_responses,
    }

    if out_dir:
        (out_dir / "summary.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return payload


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--max-wait-ms", type=int, default=20000)
    parser.add_argument("--stable-ms", type=int, default=2500)
    parser.add_argument("--tick-ms", type=int, default=250)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else Path(
        "playwright_captures"
    ) / datetime.now().strftime("%Y%m%d-%H%M%S-bet365-league-1x2")

    data = await scrape_bet365_league_fast(
        args.url,
        max_wait_ms=args.max_wait_ms,
        stable_ms=args.stable_ms,
        tick_ms=args.tick_ms,
        headless=not args.headed,
        out_dir=out_dir,
    )

    print()
    print(f"→ Payloads útiles: {data['useful_payloads']}")
    print(f"→ Partidos extraídos: {data['matches_count']}")
    print(f"→ Guardado en: {out_dir}")

    for match in data["matches"]:
        ftr = match["full_time_result"]
        one = ftr.get("1", {}).get("odd_fractional")
        draw = ftr.get("X", {}).get("odd_fractional")
        two = ftr.get("2", {}).get("odd_fractional")

        print(
            f"{match.get('start_raw')} | "
            f"{match.get('home')} vs {match.get('away')} | "
            f"1={one} X={draw} 2={two}"
        )


if __name__ == "__main__":
    asyncio.run(main())

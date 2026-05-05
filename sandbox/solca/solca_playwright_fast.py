from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from playwright.async_api import async_playwright, Response


DEFAULTS = {
    "solcasino.io": {"platform": "solcasino"},
    "rainbet.com": {"platform": "rainbet"},
}

HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
}


def get_platform(url: str) -> str:
    host = urlparse(url).netloc.replace("www.", "")
    for domain, cfg in DEFAULTS.items():
        if domain in host:
            return cfg["platform"]
    raise ValueError(f"Dominio no soportado: {host}")


def extract_tournament_id(url: str) -> str:
    bt_path = parse_qs(urlparse(url).query).get("bt-path", [""])[0]
    bt_path = unquote(bt_path)

    m = re.search(r"-(\d{12,})/?$", bt_path)
    if not m:
        raise ValueError(f"No pude extraer tournament_id desde bt-path={bt_path!r}")

    return m.group(1)


def deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            deep_merge(dst[key], value)
        else:
            dst[key] = value
    return dst


def to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_1x2(markets: dict[str, Any]) -> dict[str, float | None]:
    # Solcasino/Rainbet soccer 1X2:
    # market "1", outcomes:
    # 1 = home, 2 = draw, 3 = away
    market = ((markets.get("1") or {}).get("") or {})
    return {
        "1": to_float((market.get("1") or {}).get("k")),
        "X": to_float((market.get("2") or {}).get("k")),
        "2": to_float((market.get("3") or {}).get("k")),
    }


def extract_matches(
    merged: dict[str, Any],
    *,
    tournament_id: str,
    platform: str,
) -> list[dict[str, Any]]:
    tournament = (merged.get("tournaments") or {}).get(tournament_id, {})
    category_id = tournament.get("category_id")
    category = (merged.get("categories") or {}).get(category_id, {}) if category_id else {}

    matches: list[dict[str, Any]] = []

    for event_id, event in (merged.get("events") or {}).items():
        desc = event.get("desc") or {}
        markets = event.get("markets") or {}

        if desc.get("type") != "match":
            continue

        if str(desc.get("tournament")) != str(tournament_id):
            continue

        competitors = desc.get("competitors") or []
        if len(competitors) < 2:
            continue

        odds = extract_1x2(markets)

        # Por ahora exigimos que tenga al menos una odd 1X2.
        if odds["1"] is None and odds["X"] is None and odds["2"] is None:
            continue

        scheduled = desc.get("scheduled")

        matches.append(
            {
                "platform": platform,
                "external_event_id": event_id,
                "external_competition_id": tournament_id,
                "competition_name": tournament.get("name"),
                "category_name": category.get("name"),
                "home": competitors[0].get("name", "").strip(),
                "away": competitors[1].get("name", "").strip(),
                "scheduled_raw": scheduled,
                "scheduled": (
                    datetime.fromtimestamp(scheduled).strftime("%Y-%m-%d %H:%M:%S")
                    if scheduled
                    else None
                ),
                "odds_1x2": odds,
                "markets_json": markets,
            }
        )

    matches.sort(key=lambda x: x.get("scheduled_raw") or 0)
    return matches


async def scrape_league_fast(
    url: str,
    *,
    max_wait_ms: int = 20000,
    stable_ms: int = 3000,
    tick_ms: int = 250,
    headless: bool = True,
    keep_raw: bool = True,
) -> dict[str, Any]:
    platform = get_platform(url)
    tournament_id = extract_tournament_id(url)

    merged: dict[str, Any] = {
        "sports": {},
        "categories": {},
        "tournaments": {},
        "events": {},
    }

    seen_response_urls: set[str] = set()
    useful_responses = 0
    all_prematch_responses = 0

    last_match_count = 0
    last_growth_time = time.monotonic()
    start_time = time.monotonic()

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
            viewport={"width": 1200, "height": 800},
            user_agent=HEADERS["user-agent"],
            locale="en-US",
        )

        page = await context.new_page()

        async def route_handler(route):
            request = route.request
            resource_type = request.resource_type
            request_url = request.url

            # Bloqueamos cosas pesadas. Dejamos scripts/xhr/fetch/document.
            if resource_type in {"image", "font", "media"}:
                await route.abort()
                return

            # Los SVG no son necesarios.
            if request_url.endswith(".svg"):
                await route.abort()
                return

            # Opcional: bloquear analytics/chat externos.
            blocked_hosts = (
                "intercom.io",
                "googletagmanager.com",
                "google-analytics.com",
                "facebook.net",
                "sentry.io",
            )
            if any(host in request_url for host in blocked_hosts):
                await route.abort()
                return

            await route.continue_()

        await context.route("**/*", route_handler)

        async def handle_response(response: Response) -> None:
            nonlocal useful_responses, all_prematch_responses
            nonlocal last_match_count, last_growth_time

            response_url = response.url

            if "/api/v4/prematch/brand/" not in response_url:
                return

            if response_url in seen_response_urls:
                return

            seen_response_urls.add(response_url)
            all_prematch_responses += 1

            try:
                if response.status != 200:
                    return

                data = await response.json()

                # Filtro barato antes de mergear.
                if tournament_id not in json.dumps(data, ensure_ascii=False):
                    return

                useful_responses += 1
                deep_merge(merged, data)

                count = len(
                    extract_matches(
                        merged,
                        tournament_id=tournament_id,
                        platform=platform,
                    )
                )

                if count > last_match_count:
                    last_match_count = count
                    last_growth_time = time.monotonic()

                print(
                    f"   ✓ response útil {useful_responses} | "
                    f"matches={count} | url_tail={response_url.rsplit('/', 1)[-1]}"
                )

            except Exception:
                return

        page.on("response", handle_response)

        print(f"→ platform: {platform}")
        print(f"→ tournament_id: {tournament_id}")
        print("→ Abriendo página headless y capturando JSON...")

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        while True:
            await page.wait_for_timeout(tick_ms)

            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            quiet_ms = int((time.monotonic() - last_growth_time) * 1000)

            current_matches = extract_matches(
                merged,
                tournament_id=tournament_id,
                platform=platform,
            )
            current_count = len(current_matches)

            if current_count > 0 and quiet_ms >= stable_ms:
                print(f"→ Corte por estabilidad: {current_count} matches, {quiet_ms} ms sin crecer.")
                break

            if elapsed_ms >= max_wait_ms:
                print(f"→ Corte por timeout: {elapsed_ms} ms.")
                break

        await context.close()
        await browser.close()

    matches = extract_matches(
        merged,
        tournament_id=tournament_id,
        platform=platform,
    )

    payload = {
        "source_url": url,
        "platform": platform,
        "tournament_id": tournament_id,
        "all_prematch_responses": all_prematch_responses,
        "useful_responses": useful_responses,
        "matches_count": len(matches),
        "matches": matches,
    }

    if keep_raw:
        payload["raw_merged"] = merged

    return payload


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--out", default=None)
    parser.add_argument("--max-wait-ms", type=int, default=20000)
    parser.add_argument("--stable-ms", type=int, default=3000)
    parser.add_argument("--tick-ms", type=int, default=250)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--no-raw", action="store_true")
    args = parser.parse_args()

    data = await scrape_league_fast(
        args.url,
        max_wait_ms=args.max_wait_ms,
        stable_ms=args.stable_ms,
        tick_ms=args.tick_ms,
        headless=not args.headed,
        keep_raw=not args.no_raw,
    )

    out = args.out or f"{data['platform']}_{data['tournament_id']}_fast.json"
    Path(out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"→ Responses prematch totales: {data['all_prematch_responses']}")
    print(f"→ Responses útiles: {data['useful_responses']}")
    print(f"→ Partidos extraídos: {data['matches_count']}")
    print(f"→ Guardado en: {out}")

    for match in data["matches"]:
        odds = match["odds_1x2"]
        print(
            f"{match['scheduled']} | "
            f"{match['home']} vs {match['away']} | "
            f"1={odds['1']} X={odds['X']} 2={odds['2']}"
        )


if __name__ == "__main__":
    asyncio.run(main())
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

import httpx
from playwright.async_api import async_playwright


CACHE_PATH = Path(".cache/solca_leagues.json")

DEFAULTS = {
    "solcasino.io": {
        "platform": "solcasino",
        "api_host": "api-g-c7818b61-607.sptpub.com",
        "brand_id": "2392759269461204992",
    },
    "rainbet.com": {
        "platform": "rainbet",
        "api_host": "api-g-c7818b61-607.sptpub.com",
        "brand_id": "2392759269461204992",
    },
}

HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "accept": "application/json,text/plain,*/*",
}


def extract_tournament_id(url: str) -> str:
    bt_path = parse_qs(urlparse(url).query).get("bt-path", [""])[0]
    bt_path = unquote(bt_path)
    m = re.search(r"-(\d{12,})/?$", bt_path)
    if not m:
        raise ValueError(f"No pude extraer tournament_id desde bt-path={bt_path!r}")
    return m.group(1)


def get_config(url: str) -> dict[str, str]:
    host = urlparse(url).netloc.replace("www.", "")
    for domain, cfg in DEFAULTS.items():
        if domain in host:
            return cfg
    raise ValueError(f"Dominio no soportado: {host}")


def cache_key(platform: str, tournament_id: str) -> str:
    return f"{platform}:{tournament_id}"


def load_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))


def save_cache(cache: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def to_float(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def extract_1x2(markets: dict[str, Any]) -> dict[str, float | None]:
    m = ((markets.get("1") or {}).get("") or {})
    return {
        "1": to_float((m.get("1") or {}).get("k")),
        "X": to_float((m.get("2") or {}).get("k")),
        "2": to_float((m.get("3") or {}).get("k")),
    }


def extract_matches(data: dict[str, Any], tournament_id: str, platform: str) -> list[dict[str, Any]]:
    tournament = (data.get("tournaments") or {}).get(tournament_id, {})
    matches = []

    for event_id, event in (data.get("events") or {}).items():
        desc = event.get("desc") or {}
        markets = event.get("markets") or {}

        if desc.get("type") != "match":
            continue
        if str(desc.get("tournament")) != str(tournament_id):
            continue

        competitors = desc.get("competitors") or []
        if len(competitors) < 2:
            continue

        scheduled = desc.get("scheduled")

        matches.append({
            "platform": platform,
            "external_event_id": event_id,
            "external_competition_id": tournament_id,
            "competition_name": tournament.get("name"),
            "home": competitors[0].get("name", "").strip(),
            "away": competitors[1].get("name", "").strip(),
            "scheduled_raw": scheduled,
            "scheduled": datetime.fromtimestamp(scheduled).strftime("%Y-%m-%d %H:%M:%S") if scheduled else None,
            "odds_1x2": extract_1x2(markets),
            "markets_json": markets,
        })

    return sorted(matches, key=lambda x: x.get("scheduled_raw") or 0)


async def fetch_versions(
    versions: list[str],
    *,
    api_host: str,
    brand_id: str,
    lang: str,
    tournament_id: str,
    platform: str,
) -> tuple[dict[str, Any], int, list[dict[str, Any]]]:
    merged = {"sports": {}, "categories": {}, "tournaments": {}, "events": {}}
    useful = 0

    async with httpx.AsyncClient(follow_redirects=True) as client:
        async def fetch(version: str):
            url = f"https://{api_host}/api/v4/prematch/brand/{brand_id}/{lang}/{version}"
            try:
                r = await client.get(url, headers=HEADERS, timeout=15)
                if r.status_code != 200:
                    return version, None
                return version, r.json()
            except Exception:
                return version, None

        results = await asyncio.gather(*(fetch(v) for v in versions))

    for version, data in results:
        if not data:
            continue
        if tournament_id not in json.dumps(data, ensure_ascii=False):
            continue

        useful += 1
        deep_merge(merged, data)
        print(f"   ✓ HTTP {version} | matches: {len(extract_matches(merged, tournament_id, platform))}")

    return merged, useful, extract_matches(merged, tournament_id, platform)


async def discover_with_playwright(url: str, wait_ms: int) -> list[str]:
    versions: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1600, "height": 1000},
            user_agent=HEADERS["user-agent"],
            locale="en-US",
        )
        page = await context.new_page()

        async def on_response(response):
            response_url = response.url
            if "/api/v4/prematch/brand/" not in response_url:
                return
            m = re.search(r"/en/(\d+)", response_url)
            if not m:
                return

            version = m.group(1)
            if version != "0":
                versions.add(version)
                print("   browser found:", version)

        page.on("response", on_response)

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(wait_ms)

        await context.close()
        await browser.close()

    return sorted(versions)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--out", default=None)
    parser.add_argument("--lang", default="en")
    parser.add_argument("--ttl", type=int, default=1800)
    parser.add_argument("--min-matches", type=int, default=1)
    parser.add_argument("--browser-wait-ms", type=int, default=20000)
    parser.add_argument("--force-browser", action="store_true")
    args = parser.parse_args()

    tournament_id = extract_tournament_id(args.url)
    cfg = get_config(args.url)

    platform = cfg["platform"]
    api_host = cfg["api_host"]
    brand_id = cfg["brand_id"]

    key = cache_key(platform, tournament_id)
    cache = load_cache()
    entry = cache.get(key)

    print(f"→ platform: {platform}")
    print(f"→ tournament_id: {tournament_id}")

    versions: list[str] = []
    cache_is_fresh = False

    if entry and not args.force_browser:
        age = time.time() - entry.get("updated_at", 0)
        cache_is_fresh = age <= args.ttl
        versions = entry.get("versions", [])
        print(f"→ cache encontrado: {len(versions)} versiones | age={age:.0f}s | fresh={cache_is_fresh}")

    should_bootstrap = args.force_browser or not versions or not cache_is_fresh

    if not should_bootstrap:
        print("→ Probando cache por HTTP...")
        merged, useful, matches = await fetch_versions(
            versions,
            api_host=api_host,
            brand_id=brand_id,
            lang=args.lang,
            tournament_id=tournament_id,
            platform=platform,
        )

        if useful > 0 and len(matches) >= args.min_matches:
            print("→ Cache OK.")
        else:
            print("→ Cache no sirvió. Reparando con Playwright...")
            should_bootstrap = True
    else:
        merged = {"sports": {}, "categories": {}, "tournaments": {}, "events": {}}
        useful = 0
        matches = []

    if should_bootstrap:
        print("→ Descubriendo versiones con Playwright...")
        versions = await discover_with_playwright(args.url, args.browser_wait_ms)

        if not versions:
            raise RuntimeError("No pude descubrir versiones con Playwright.")

        cache[key] = {
            "source_url": args.url,
            "platform": platform,
            "api_host": api_host,
            "brand_id": brand_id,
            "tournament_id": tournament_id,
            "versions": versions,
            "updated_at": time.time(),
        }
        save_cache(cache)

        print(f"→ Cache actualizado: {len(versions)} versiones.")

        merged, useful, matches = await fetch_versions(
            versions,
            api_host=api_host,
            brand_id=brand_id,
            lang=args.lang,
            tournament_id=tournament_id,
            platform=platform,
        )

    out = args.out or f"{platform}_{tournament_id}_merged.json"

    payload = {
        "source_url": args.url,
        "platform": platform,
        "tournament_id": tournament_id,
        "versions": versions,
        "matched_responses": useful,
        "matches_count": len(matches),
        "matches": matches,
        "raw_merged": merged,
    }

    Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"→ Responses útiles: {useful}")
    print(f"→ Partidos extraídos: {len(matches)}")
    print(f"→ Guardado en: {out}")

    for m in matches:
        odds = m["odds_1x2"]
        print(
            f"{m['scheduled']} | {m['home']} vs {m['away']} | "
            f"1={odds['1']} X={odds['X']} 2={odds['2']}"
        )


if __name__ == "__main__":
    asyncio.run(main())
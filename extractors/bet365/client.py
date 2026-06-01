"""Unified HTTP Client for Bet365 utilizing on-demand Playwright token harvesting."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import re
import time
import unicodedata
from typing import Any
from urllib.parse import urlparse, quote

from curl_cffi.requests import AsyncSession
from core.extractor_base import CompetitionUnavailableError
from extractors.bet365.parser import (
    Bet365AsianLeagueExtraction,
    Bet365AsianMatch,
    parse_league_payload,
    parse_asian_payload,
    merge_market_payloads,
)

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

UNAVAILABLE_COMPETITION_MESSAGE = (
    "Competition could not be refreshed because the source currently has no active events "
    "or the URL may have changed."
)

SPANISH_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


@dataclass(frozen=True)
class Bet365ExtractorSettings:
    """Runtime settings for the hybrid Bet365 client."""

    max_parallel_competitions: int = 1
    max_parallel_pages: int = 3
    max_parallel_event_pages: int = 1
    page_reuse_enabled: bool = False
    browser_restart_after_n_refreshes: int | None = None
    browser_restart_idle_ttl_seconds: int | None = None
    page_load_timeout_ms: int = 60_000
    post_load_wait_ms: int = 4_000
    headless: bool = True
    capture_wait_timeout_ms: int = 25_000
    capture_stable_ms: int = 1_500
    capture_attempts: int = 2
    event_capture_wait_timeout_ms: int = 20_000
    event_capture_stable_ms: int = 1_200
    event_capture_attempts: int = 1
    save_debug_payloads: bool = False
    debug_payload_dir: str | None = None
    extract_alternative_markets: bool = False
    allow_legacy_fallback: bool = False


def validate_bet365_league_url(url: str) -> str:
    """Validate and normalize a Bet365 league URL."""
    normalized_url = url.strip()
    if not normalized_url:
        raise ValueError("The URL must not be empty.")
    parsed = urlparse(normalized_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("The URL must start with http:// or https://.")
    if "bet365" not in parsed.netloc.lower():
        raise ValueError("The URL must belong to Bet365.")
    return normalized_url


def visual_url_to_pd(url: str) -> str | None:
    fragment = urlparse(url).fragment.strip("/")
    if not fragment:
        return None
    return "#" + fragment.replace("/", "#") + "#"


class Bet365HttpClient:
    """Unified HTTP-first client for Bet365 soccer data."""

    _playwright_lock: asyncio.Lock | None = None

    def __init__(self, settings: Bet365ExtractorSettings | None = None) -> None:
        self.settings = settings or Bet365ExtractorSettings()
        if Bet365HttpClient._playwright_lock is None:
            Bet365HttpClient._playwright_lock = asyncio.Lock()

    async def fetch_allsportsmenu(self, host: str, pd: str = "#AL#R^1#") -> str:
        """Fetch the left navigation menu over plain HTTP with on-demand Playwright fallback."""
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
            "Referer": f"https://{host}/",
            "Origin": f"https://{host}",
        }
        
        lid = "36" if "bet.ar" in host else "3"
        cid = "271" if "bet.ar" in host else "171"
        cgid = "1" if "bet.ar" in host else "4"
        ctid = cid
        
        menu_url = f"https://{host}/leftnavcontentapi/allsportsmenu?lid={lid}&zid=0&pd={quote(pd, safe='')}&cid={cid}&cgid={cgid}&ctid={ctid}"
        
        try:
            async with AsyncSession(impersonate="chrome120", timeout=15) as session:
                await session.get(f"https://{host}/")
                r = await session.get(menu_url, headers=headers)
                if r.status_code == 200 and r.content:
                    return r.content.decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning("Plain HTTP menu fetch failed, falling back to Playwright: %s", e)
            
        # On-demand Playwright fallback!
        from playwright.async_api import async_playwright
        logger.info("Spawning temporary Playwright instance to fetch allsportsmenu...")
        async with self._playwright_lock:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.settings.headless,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
                )
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    user_agent=DEFAULT_USER_AGENT,
                    locale="es-AR" if "bet.ar" in host else "es-ES",
                    timezone_id="America/Argentina/Buenos_Aires" if "bet.ar" in host else "Europe/Madrid",
                )
                page = await context.new_page()
                
                captured_menu = ""
                async def handle_response(response):
                    nonlocal captured_menu
                    if "allsportsmenu" in response.url:
                        try:
                            captured_menu = await response.text()
                        except Exception:
                            pass
                page.on("response", handle_response)
                
                await page.goto(f"https://{host}/", wait_until="load", timeout=30000)
                await page.wait_for_function("() => window.ns_datalib_net && window.ns_datalib_net.Loader && window.Locator", timeout=30000)
                
                # Wait a moment for menu response to trigger
                for _ in range(12):
                    await page.wait_for_timeout(250)
                    if captured_menu:
                        break
                        
                await context.close()
                await browser.close()
                
                if captured_menu:
                    return captured_menu
                
        raise RuntimeError("Failed to fetch allsportsmenu from both plain HTTP and Playwright fallback.")

    async def fetch_sports_config(self, host: str) -> dict[str, Any]:
        """Fetch sports configuration variables over plain HTTP."""
        async with AsyncSession(impersonate="chrome120", timeout=15) as session:
            await session.get(f"https://{host}/")
            r = await session.get(f"https://{host}/defaultapi/sports-configuration")
            if r.status_code == 200:
                try:
                    return r.json()
                except Exception:
                    pass
        return {}

    async def fetch_league(self, league_url: str) -> Bet365AsianLeagueExtraction:
        """Fetch soccer matches and their asian handicap/goal lines dynamically."""
        normalized_url = validate_bet365_league_url(league_url)
        parsed_url = urlparse(normalized_url)
        host = parsed_url.netloc
        
        # 1. Dynamically load config to parse lid/cid/cgid/ctid
        config = await self.fetch_sports_config(host)
        flashvars = config.get("flashvars", {})
        
        lid = str(flashvars.get("LANGUAGE_ID") or ("36" if "bet.ar" in host else "3"))
        cid = str(flashvars.get("REGISTERED_COUNTRY_CODE") or ("271" if "bet.ar" in host else "171"))
        cgid = str(flashvars.get("COUNTRY_GROUP_ID") or ("1" if "bet.ar" in host else "4"))
        ctid = cid
        
        expected_pd = visual_url_to_pd(normalized_url)
        if not expected_pd:
            raise ValueError(f"Could not parse tournament path from league URL: {league_url}")
            
        markets_api_url = f"https://{host}/matchmarketscontentapi/markets?lid={lid}&zid=0&pd={quote(expected_pd, safe='')}&cid={cid}&cgid={cgid}&ctid={ctid}"
        
        # 2. Boot temporary Playwright session to harvest cookies/Guid and generate tokens in a single batch
        from playwright.async_api import async_playwright
        
        cookies_dict = {}
        guid = ""
        league_token = ""
        coupon_tokens = {}
        matches_list = []
        
        logger.info("Spawning temporary Playwright instance on-demand...")
        async with self._playwright_lock:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.settings.headless,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
                )
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    user_agent=DEFAULT_USER_AGENT,
                    locale="es-AR" if "bet.ar" in host else "es-ES",
                    timezone_id="America/Argentina/Buenos_Aires" if "bet.ar" in host else "Europe/Madrid",
                )
                page = await context.new_page()
                
                # Go to base soccer page to bootstrap datalib loader with retry
                ready = False
                for attempt in range(2):
                    try:
                        await page.goto(f"https://{host}/#/AS/B1/", wait_until="load", timeout=20000)
                        await page.wait_for_function(
                            "() => window.ns_datalib_net && window.ns_datalib_net.Loader && window.Locator",
                            timeout=15000
                        )
                        ready = True
                        break
                    except Exception as e:
                        logger.warning("Page bootstrap attempt %d failed: %s. Retrying...", attempt + 1, e)
                        try:
                            await page.reload(wait_until="load", timeout=20000)
                            await page.wait_for_function(
                                "() => window.ns_datalib_net && window.ns_datalib_net.Loader && window.Locator",
                                timeout=15000
                            )
                            ready = True
                            break
                        except Exception as reload_err:
                            logger.warning("Page reload attempt %d failed: %s", attempt + 1, reload_err)
                
                if not ready:
                    # Last resort fallback: wait a moment and proceed anyway
                    logger.info("Page bootstrap failed to confirm loader; proceeding with best-effort wait")
                    await page.goto(f"https://{host}/#/AS/B1/", wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(3000)
                
                # Client-side route to the tournament to update routing state
                fragment = urlparse(normalized_url).fragment.strip("/")
                if fragment:
                    await page.evaluate(f"() => window.location.hash = '/{fragment}/'")
                    await page.wait_for_timeout(2000)
                
                # Extract cookies and Guid after client-side routing is complete
                playwright_cookies = await context.cookies()
                cookies_dict = {c["name"]: c["value"] for c in playwright_cookies}
                guid = await page.evaluate("() => window.Locator.Guid")
                
                # Generate Token for the league markets URL
                js_code = """
                async (url) => {
                    return new Promise((resolve) => {
                        const loader = new window.ns_datalib_net.Loader();
                        loader.url = url;
                        loader.options = { method: "GET" };
                        const tid = setTimeout(() => resolve(null), 4000);
                        loader.xcft((term, token) => {
                            clearTimeout(tid);
                            resolve(term);
                        });
                    });
                }
                """
                league_token = await page.evaluate(js_code, markets_api_url)
                if not league_token:
                    await context.close()
                    await browser.close()
                    raise CompetitionUnavailableError(
                        "Timed out generating token for league.",
                        platform="bet365",
                        source_url=normalized_url,
                    )
                
                # 3. Fetch league binary data browser-less
                cookie_header = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
                headers = {
                    "User-Agent": DEFAULT_USER_AGENT,
                    "Accept": "*/*",
                    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
                    "Referer": f"https://{host}/",
                    "Origin": f"https://{host}",
                    "X-Net-Sync-Term": league_token,
                    "X-Request-Id": guid,
                    "Cookie": cookie_header,
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                }
                
                async with AsyncSession(impersonate="chrome120", timeout=20) as session:
                    r = await session.get(markets_api_url, headers=headers)
                    logger.info("Markets fetch result - HTTP %d, length=%d, X-Net-Sync-Term=%s, X-Request-Id=%s", r.status_code, len(r.content or b""), league_token, guid)
                    if r.status_code != 200 or not r.content:
                        await context.close()
                        await browser.close()
                        raise CompetitionUnavailableError(
                            f"Bet365 league markets payload returned empty content (status={r.status_code}, len={len(r.content or b'')}).",
                            platform="bet365",
                            source_url=normalized_url,
                        )
                    
                    parsed_league = parse_league_payload(r.content.decode("utf-8", errors="replace"), host=host)
                    matches_list = parsed_league.get("matches", [])
                    
                # 4. Construct Coupon URLs and generate tokens concurrently in JavaScript
                if matches_list:
                    coupon_urls = [
                        f"https://{host}/matchbettingcontentapi/coupon?lid={lid}&zid=0&pd={quote('#AC#B1#C1#D8#E' + m['fixture_id'] + '#F3#I3#', safe='')}&cid={cid}&cgid={cgid}&ctid={ctid}"
                        for m in matches_list
                    ]
                    
                    js_batch_code = """
                    async (urls) => {
                        const promises = urls.map(url => {
                            return new Promise((resolve) => {
                                const loader = new window.ns_datalib_net.Loader();
                                loader.url = url;
                                loader.options = { method: "GET" };
                                const tid = setTimeout(() => resolve({ url, term: null }), 4000);
                                loader.xcft((term, token) => {
                                    clearTimeout(tid);
                                    resolve({ url, term });
                                });
                            });
                        });
                        return Promise.all(promises);
                    }
                    """
                    results = await page.evaluate(js_batch_code, coupon_urls)
                    for res in results:
                        if res and res.get("term"):
                            coupon_tokens[res["url"]] = res["term"]
                
                await context.close()
                await browser.close()
            
        logger.info("Temporary Playwright instance closed. Spawning parallel HTTP calls...")
        
        # 5. Fetch all coupons concurrently in Python using curl_cffi AsyncSession
        sem = asyncio.Semaphore(self.settings.max_parallel_event_pages)
        
        async def fetch_one_coupon(match: dict[str, Any], url: str, token: str | None) -> dict[str, Any]:
            if not token:
                return {
                    "error": "token_generation_failed",
                    "captured_url": None,
                    "event": {},
                    "markets_payload": {},
                    "asian_lines_unavailable": True,
                    "duration_seconds": 0,
                }
            
            cookie_header = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
            headers = {
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "*/*",
                "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
                "Referer": f"https://{host}/",
                "Origin": f"https://{host}",
                "X-Net-Sync-Term": token,
                "X-Request-Id": guid,
                "Cookie": cookie_header,
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
            }
            
            async with sem:
                t0 = time.monotonic()
                async with AsyncSession(impersonate="chrome120", timeout=15) as session:
                    r = await session.get(url, headers=headers)
                    dur = time.monotonic() - t0
                    
                    if r.status_code != 200 or not r.content:
                        return {
                            "error": "coupon_fetch_failed",
                            "captured_url": url,
                            "event": {},
                            "markets_payload": {},
                            "asian_lines_unavailable": True,
                            "duration_seconds": dur,
                        }
                    
                    parsed = parse_asian_payload(
                        r.content.decode("utf-8", errors="replace"),
                        match["fixture_id"],
                        include_alternative_markets=self.settings.extract_alternative_markets,
                    )
                    return {
                        "error": None,
                        "captured_url": url,
                        "event": parsed["event"],
                        "markets_payload": parsed["markets_payload"],
                        "asian_lines_unavailable": False,
                        "duration_seconds": dur,
                    }
        
        # Launch coupon parallel fetches
        tasks = []
        for m in matches_list:
            c_url = f"https://{host}/matchbettingcontentapi/coupon?lid={lid}&zid=0&pd={quote('#AC#B1#C1#D8#E' + m['fixture_id'] + '#F3#I3#', safe='')}&cid={cid}&cgid={cgid}&ctid={ctid}"
            tok = coupon_tokens.get(c_url)
            tasks.append(fetch_one_coupon(m, c_url, tok))
            
        asian_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge odds and return normalized results
        normalized_matches: list[Bet365AsianMatch] = []
        for match, result in zip(matches_list, asian_results, strict=False):
            if isinstance(result, Exception) or result.get("error"):
                merged_markets = match["markets_payload"]
                raw = {
                    "asian_error": str(result),
                    "asian_lines_unavailable": True,
                }
            else:
                merged_markets = merge_market_payloads(
                    match["markets_payload"],
                    result["markets_payload"],
                )
                raw = {
                    "asian_error": None,
                    "asian_lines_unavailable": bool(result.get("asian_lines_unavailable")),
                }
                
            raw.update({
                "fixture_id": match["fixture_id"],
                "event_url": match["event_url"],
                "stats_url": match["stats_url"],
            })
            
            normalized_matches.append(
                Bet365AsianMatch(
                    fixture_id=match["fixture_id"],
                    home=match["home"],
                    away=match["away"],
                    league_name=match["league"],
                    scheduled_label_date=match["scheduled_label_date"],
                    scheduled_label_time=match["scheduled_label_time"],
                    scheduled_at=match["scheduled_at"],
                    odds_home=match["odds_home"],
                    odds_draw=match["odds_draw"],
                    odds_away=match["odds_away"],
                    event_url=match["event_url"],
                    stats_url=match["stats_url"],
                    markets_payload=merged_markets,
                    raw=raw,
                )
            )
            
        return Bet365AsianLeagueExtraction(
            platform="bet365",
            url=normalized_url,
            league_name=parsed_league.get("league_name") or "Bet365 League",
            topic=parsed_league.get("topic") or "",
            matches=normalized_matches,
            payload={},
        )

"""Lightweight Bet365 Playwright extractor based on network response capture."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.browser_handler import BrowserHandler, BrowserHandlerSettings
from core.extractor_base import CompetitionUnavailableError
from extractors.bet365.client import Bet365ExtractorSettings, validate_bet365_league_url

logger = logging.getLogger(__name__)

ASIAN_MARKET_NAMES = {
    "938": "Asian Handicap",
    "10143": "Goal Line",
    "50138": "Alternative Asian Handicap",
    "50139": "Alternative Goal Line",
    "50137": "1st Half Asian Handicap",
    "50136": "1st Half Goal Line",
    "50265": "Alternative 1st Half Asian Handicap",
    "50266": "Alternative 1st Half Goal Line",
    "10164": "Alternative Goal Line 2",
    "10165": "Alternative Goal Line 3",
    "10233": "Alternative Goal Line 4",
    "10166": "Alternative Goal Line 5",
    "10239": "Alternative Goal Line 6",
}
PRIMARY_ASIAN_MARKET_IDS = ("938", "10143")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class Bet365AsianMatch:
    fixture_id: str
    home: str
    away: str
    league_name: str | None
    scheduled_label_date: str | None
    scheduled_label_time: str | None
    scheduled_at: str | None
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None
    event_url: str | None
    stats_url: str | None
    markets_payload: dict[str, Any] | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class Bet365AsianLeagueExtraction:
    platform: str
    url: str
    league_name: str
    topic: str
    matches: list[Bet365AsianMatch]
    payload: dict[str, Any]


class Bet365PlaywrightAsianClient:
    """Capture league and I3 event payloads via Playwright responses only."""

    def __init__(
        self,
        settings: Bet365ExtractorSettings | None = None,
        *,
        browser_handler: BrowserHandler | None = None,
    ) -> None:
        self.settings = settings or Bet365ExtractorSettings()
        self._league_capture_semaphore = asyncio.Semaphore(
            max(1, self.settings.max_parallel_competitions)
        )
        self._event_capture_semaphore = asyncio.Semaphore(
            max(1, self.settings.max_parallel_event_pages)
        )
        self._refresh_counter = 0
        self._refresh_counter_lock = asyncio.Lock()
        self._browser_handler = browser_handler or BrowserHandler(
            BrowserHandlerSettings(
                browser_name="chromium",
                headless=self.settings.headless,
                max_parallel_pages=max(
                    1,
                    self.settings.max_parallel_pages,
                    self.settings.max_parallel_competitions,
                    self.settings.max_parallel_event_pages,
                ),
                page_reuse_enabled=False,
                launch_args=(
                    "--disable-blink-features=AutomationControlled",
                    "--disable-background-networking",
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-extensions",
                ),
                context_kwargs={
                    "viewport": {"width": 1280, "height": 900},
                    "user_agent": DEFAULT_USER_AGENT,
                    "locale": "es-AR",
                    "timezone_id": "America/Argentina/Cordoba",
                },
                idle_ttl_seconds=(
                    float(self.settings.browser_restart_idle_ttl_seconds)
                    if self.settings.browser_restart_idle_ttl_seconds is not None
                    else None
                ),
                page_default_timeout_ms=self.settings.page_load_timeout_ms,
                page_default_navigation_timeout_ms=self.settings.page_load_timeout_ms,
            )
        )

    async def start(self) -> None:
        await self._browser_handler.start()

    async def stop(self) -> None:
        await self._browser_handler.stop()

    async def _prepare_browser_for_refresh(self) -> None:
        threshold = self.settings.browser_restart_after_n_refreshes
        if threshold is None or threshold <= 0:
            return

        async with self._refresh_counter_lock:
            if self._refresh_counter < threshold:
                return
            self._refresh_counter = 0

        await self._browser_handler.request_restart(
            reason=f"bet365_refresh_threshold_reached:{threshold}",
        )

    async def _mark_refresh_completed(self) -> None:
        threshold = self.settings.browser_restart_after_n_refreshes
        if threshold is None or threshold <= 0:
            return

        async with self._refresh_counter_lock:
            self._refresh_counter += 1

    async def extract_league_with_asian_lines(self, league_url: str) -> Bet365AsianLeagueExtraction:
        normalized_url = validate_bet365_league_url(league_url)
        league_started_at = time.monotonic()
        await self._prepare_browser_for_refresh()
        await self.start()
        try:
            async with self._league_capture_semaphore:
                expected_pd = visual_url_to_pd(normalized_url)
                host = urlparse(normalized_url).netloc
                logger.info("Bet365 response-capture opening league url=%s", normalized_url)
                league_payload, league_capture_url, league_debug = await self._capture_payload_with_retry(
                    normalized_url,
                    lambda captured_url, body: looks_like_league_payload(
                        captured_url,
                        body,
                        expected_pd,
                    ),
                    max_wait_ms=self.settings.capture_wait_timeout_ms,
                    stable_ms=self.settings.capture_stable_ms,
                    debug_name="league",
                    attempts=self.settings.capture_attempts,
                    capture_kind="league",
                    capture_id=normalized_url,
                )

                if not league_payload:
                    self._save_debug_capture("league-debug", league_debug)
                    logger.warning(
                        "Bet365 league capture timeout url=%s responses_seen=%s duration_seconds=%.2f debug=%s",
                        normalized_url,
                        len(league_debug),
                        time.monotonic() - league_started_at,
                        self._compact_debug_records(league_debug),
                    )
                    raise CompetitionUnavailableError(
                        "Bet365 league payload was not captured.",
                        platform="bet365",
                        source_url=normalized_url,
                        reason_code="competition_unavailable",
                        details={"debug": league_debug, "expected_pd": expected_pd},
                    )

                logger.info(
                    "Captured league markets url=%s captured_url=%s duration_seconds=%.2f",
                    normalized_url,
                    league_capture_url,
                    time.monotonic() - league_started_at,
                )

                league = parse_league_payload(league_payload, host=host)
                matches = league["matches"]
                if not matches:
                    raise CompetitionUnavailableError(
                        "Bet365 league payload did not contain active matches.",
                        platform="bet365",
                        source_url=normalized_url,
                        reason_code="competition_unavailable",
                        details={
                            "captured_url": league_capture_url,
                            "league_name": league.get("league_name"),
                            "expected_pd": expected_pd,
                        },
                    )

                asian_results = await asyncio.gather(
                    *[
                        self._extract_event_asian_lines(host, match)
                        for match in matches
                    ],
                    return_exceptions=True,
                )

                normalized_matches: list[Bet365AsianMatch] = []
                events_with_asian = 0
                asian_unavailable_count = 0
                for match, result in zip(matches, asian_results, strict=False):
                    if isinstance(result, Exception):
                        logger.warning(
                            "Bet365 asian payload failed for fixture_id=%s home=%s away=%s: %s",
                            match["fixture_id"],
                            match["home"],
                            match["away"],
                            result,
                        )
                        merged_markets = match["markets_payload"]
                        raw = {
                            "capture_urls": {"league": league_capture_url, "asian": None},
                            "league_name": match["league"],
                            "asian_error": str(result),
                            "asian_lines_unavailable": True,
                            "asian_duration_seconds": None,
                        }
                        asian_unavailable_count += 1
                    else:
                        merged_markets = merge_market_payloads(
                            match["markets_payload"],
                            result["markets_payload"],
                        )
                        raw = {
                            "capture_urls": {"league": league_capture_url, "asian": result["captured_url"]},
                            "league_name": result["event"].get("league") or match["league"],
                            "asian_error": result.get("error"),
                            "asian_lines_unavailable": bool(result.get("asian_lines_unavailable")),
                            "asian_duration_seconds": result.get("duration_seconds"),
                        }
                        if result["markets_payload"].get("asian_handicap") or result["markets_payload"].get("goal_line"):
                            events_with_asian += 1
                        elif result.get("asian_lines_unavailable"):
                            asian_unavailable_count += 1

                    raw.update(
                        {
                            "fixture_id": match["fixture_id"],
                            "event_url": match["event_url"],
                            "stats_url": match["stats_url"],
                        }
                    )

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

                total_duration = time.monotonic() - league_started_at
                logger.info(
                    "Bet365 league extraction finished url=%s matches=%s events_with_asian=%s asian_unavailable=%s duration_seconds=%.2f",
                    normalized_url,
                    len(normalized_matches),
                    events_with_asian,
                    asian_unavailable_count,
                    total_duration,
                )

                return Bet365AsianLeagueExtraction(
                    platform="bet365",
                    url=normalized_url,
                    league_name=league["league_name"],
                    topic=league["topic"],
                    matches=normalized_matches,
                    payload={
                        "capture_urls": {"league": league_capture_url},
                        "debug_counts": {"league_responses": len(league_debug)},
                        "events_with_asian": events_with_asian,
                        "asian_unavailable_count": asian_unavailable_count,
                        "matches_count": len(normalized_matches),
                        "duration_seconds": total_duration,
                    },
                )
        finally:
            await self._mark_refresh_completed()

    async def _extract_event_asian_lines(
        self,
        host: str,
        match: dict[str, Any],
    ) -> dict[str, Any]:
        async with self._event_capture_semaphore:
            event_started_at = time.monotonic()
            fixture_id = str(match["fixture_id"])
            asian_url = event_visual_url(host, fixture_id, section="I3")
            logger.info(
                "Bet365 response-capture opening asian event fixture_id=%s url=%s",
                fixture_id,
                asian_url,
            )
            asian_payload, asian_capture_url, asian_debug = await self._capture_payload_with_retry(
                asian_url,
                lambda captured_url, body, event_id=fixture_id: looks_like_asian_payload(
                    captured_url,
                    body,
                    event_id,
                ),
                max_wait_ms=self.settings.event_capture_wait_timeout_ms,
                stable_ms=self.settings.event_capture_stable_ms,
                debug_name=f"asian-{fixture_id}",
                attempts=self.settings.event_capture_attempts,
                capture_kind="asian",
                capture_id=fixture_id,
            )

            if not asian_payload:
                self._save_debug_capture(f"asian-{fixture_id}-debug", asian_debug)
                logger.warning(
                    "Bet365 asian capture timeout fixture_id=%s responses_seen=%s duration_seconds=%.2f debug=%s",
                    fixture_id,
                    len(asian_debug),
                    time.monotonic() - event_started_at,
                    self._compact_debug_records(asian_debug),
                )
                return {
                    "error": "asian_payload_not_captured",
                    "captured_url": None,
                    "debug": asian_debug,
                    "event": {},
                    "markets_payload": {},
                    "asian_lines_unavailable": True,
                    "duration_seconds": time.monotonic() - event_started_at,
                }

            logger.info(
                "Captured asian coupon event_id=%s captured_url=%s duration_seconds=%.2f",
                fixture_id,
                asian_capture_url,
                time.monotonic() - event_started_at,
            )
            parsed = parse_asian_payload(
                asian_payload,
                fixture_id,
                include_alternative_markets=self.settings.extract_alternative_markets,
            )
            return {
                "error": None,
                "captured_url": asian_capture_url,
                "debug": asian_debug,
                "event": parsed["event"],
                "markets_payload": parsed["markets_payload"],
                "asian_lines_unavailable": False,
                "duration_seconds": time.monotonic() - event_started_at,
            }

    async def _capture_payload(
        self,
        url: str,
        predicate,
        *,
        max_wait_ms: int,
        stable_ms: int,
        debug_name: str,
    ) -> tuple[str | None, str | None, list[dict[str, Any]]]:
        async with self._browser_handler.capture_page() as page:
            captured_payload: str | None = None
            captured_url: str | None = None
            debug: list[dict[str, Any]] = []
            start = time.monotonic()
            last_capture = time.monotonic()
            relevant_response_seen = False

            async def route_handler(route):
                request = route.request
                if request.resource_type in {"image", "font", "media"}:
                    await route.abort()
                    return
                if request.url.endswith(".svg"):
                    await route.abort()
                    return
                await route.continue_()

            async def handle_response(response):
                nonlocal captured_payload, captured_url, last_capture, relevant_response_seen
                response_url = response.url
                if (
                    "matchmarketscontentapi/markets" not in response_url
                    and "matchbettingcontentapi/coupon" not in response_url
                ):
                    return

                relevant_response_seen = True
                record: dict[str, Any] = {
                    "url": response_url,
                    "status": response.status,
                    "content_type": response.headers.get("content-type", ""),
                }
                try:
                    text = await response.text()
                    record["preview"] = text[:300].replace("\n", " ")
                    last_capture = time.monotonic()
                    if predicate(response_url, text):
                        captured_payload = text
                        captured_url = response_url
                except Exception as error:  # pragma: no cover - best effort debug path
                    record["error"] = repr(error)
                debug.append(record)

            await page.route("**/*", route_handler)
            page.on("response", handle_response)
            try:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.settings.page_load_timeout_ms,
                )
                while True:
                    await page.wait_for_timeout(250)
                    elapsed_ms = int((time.monotonic() - start) * 1000)
                    quiet_ms = int((time.monotonic() - last_capture) * 1000)
                    if captured_payload and quiet_ms >= stable_ms:
                        break
                    if relevant_response_seen and not captured_payload and quiet_ms >= stable_ms:
                        break
                    if elapsed_ms >= max_wait_ms:
                        break
            finally:
                page.remove_listener("response", handle_response)
                try:
                    await page.unroute("**/*", route_handler)
                except Exception:
                    pass

        if self.settings.save_debug_payloads and captured_payload:
            self._save_debug_payload(debug_name, captured_payload)
        return captured_payload, captured_url, debug

    async def _capture_payload_with_retry(
        self,
        url: str,
        predicate,
        *,
        max_wait_ms: int,
        stable_ms: int,
        debug_name: str,
        attempts: int,
        capture_kind: str,
        capture_id: str,
    ) -> tuple[str | None, str | None, list[dict[str, Any]]]:
        last_payload: str | None = None
        last_captured_url: str | None = None
        last_debug: list[dict[str, Any]] = []

        for attempt in range(1, max(1, attempts) + 1):
            payload, captured_url, debug = await self._capture_payload(
                url,
                predicate,
                max_wait_ms=max_wait_ms,
                stable_ms=stable_ms,
                debug_name=debug_name,
            )
            if payload:
                return payload, captured_url, debug

            last_payload = payload
            last_captured_url = captured_url
            last_debug = debug

            if attempt >= max(1, attempts) or not self._should_retry_capture(debug):
                break

            logger.info(
                "Bet365 response-capture retrying %s id=%s attempt=%s/%s responses_seen=%s",
                capture_kind,
                capture_id,
                attempt + 1,
                attempts,
                len(debug),
            )
            await asyncio.sleep(0.5)

        return last_payload, last_captured_url, last_debug

    def _save_debug_payload(self, debug_name: str, payload: str) -> None:
        debug_dir = self.settings.debug_payload_dir
        if not debug_dir:
            return
        output_dir = Path(debug_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        (output_dir / f"{timestamp}-{debug_name}.txt").write_text(payload, encoding="utf-8")

    def _save_debug_capture(self, debug_name: str, debug: list[dict[str, Any]]) -> None:
        if not self.settings.save_debug_payloads:
            return
        debug_dir = self.settings.debug_payload_dir
        if not debug_dir:
            return
        output_dir = Path(debug_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        (output_dir / f"{timestamp}-{debug_name}.json").write_text(
            json.dumps(debug, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _compact_debug_records(self, debug: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "status": record.get("status"),
                "url": str(record.get("url") or "")[:200],
                "preview": str(record.get("preview") or "")[:120],
            }
            for record in debug[:5]
        ]

    def _should_retry_capture(self, debug: list[dict[str, Any]]) -> bool:
        if not debug:
            return True
        return any(int(record.get("status") or 0) >= 400 for record in debug)


def fraction_to_decimal(frac: str | None) -> float | None:
    if not frac:
        return None
    raw = frac.strip()
    if "/" not in raw:
        try:
            return round(float(raw), 6)
        except ValueError:
            return None
    left, right = raw.split("/", 1)
    try:
        return round(1 + float(left) / float(right), 6)
    except ValueError:
        return None


def parse_datetime(raw: str | None, *, host: str) -> tuple[str | None, str | None, str | None]:
    if not raw:
        return None, None, None
    try:
        parsed = datetime.strptime(raw, "%Y%m%d%H%M%S")
    except ValueError:
        return None, None, None
    timezone_name = resolve_bet365_timezone_name(host)
    try:
        site_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        site_timezone = timezone.utc

    localized = parsed.replace(tzinfo=site_timezone)
    date_label = localized.strftime("%Y-%m-%d")
    time_label = localized.strftime("%H:%M")
    return date_label, time_label, localized.astimezone(timezone.utc).isoformat()


def parse_record(record: str) -> tuple[str, dict[str, str]]:
    parts = [part for part in record.split(";") if part]
    if not parts:
        return "", {}
    tag = parts[0]
    fields: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key] = value
    return tag, fields


def tokenize(payload: str) -> list[tuple[str, dict[str, str]]]:
    cleaned = payload.replace("\x08", "")
    return [
        parsed
        for parsed in (parse_record(record.strip()) for record in cleaned.split("|"))
        if parsed[0]
    ]


def visual_url_to_pd(url: str) -> str | None:
    fragment = urlparse(url).fragment.strip("/")
    if not fragment:
        return None
    return "#" + fragment.replace("/", "#") + "#"


def event_visual_url(host: str, event_id: str, section: str = "I3") -> str:
    return f"https://{host}/#/AC/B1/C1/D8/E{event_id}/F3/{section}/"


def looks_like_league_payload(url: str, body: str, expected_pd: str | None) -> bool:
    if "matchmarketscontentapi/markets" not in url:
        return False
    if not body.startswith("F|"):
        return False
    if "MG;ID=40" not in body:
        return False
    if expected_pd and expected_pd not in body:
        return False
    return True


def looks_like_asian_payload(url: str, body: str, event_id: str) -> bool:
    if "matchbettingcontentapi/coupon" not in url:
        return False
    if not body.startswith("F|"):
        return False
    if f"E{event_id}" not in body:
        return False
    return any(f"MG;ID={market_id}" in body for market_id in ASIAN_MARKET_NAMES)


def parse_league_payload(payload: str, *, host: str) -> dict[str, Any]:
    tokens = tokenize(payload)
    league_name = None
    topic = None
    matches: dict[str, dict[str, Any]] = {}
    current_market = None
    current_selection = None

    for tag, fields in tokens:
        if tag == "CL":
            topic = topic or fields.get("IT")
        elif tag == "EV":
            topic = topic or fields.get("IT")
            league_name = fields.get("L3") or league_name
            tb = fields.get("TB", "")
            if "¬" in tb and not league_name:
                league_name = tb.split("¬")[-1].split(",")[0].strip()
        elif tag == "MG":
            current_market = fields.get("ID")
            current_selection = None
        elif tag == "MA":
            if current_market == "40" or fields.get("ID") == "M40":
                current_market = "40"
                current_selection = (fields.get("NA") or "").strip()
            else:
                current_selection = None
        elif tag == "PA":
            fixture_id = fields.get("FI")
            if not fixture_id:
                continue

            if fields.get("ID", "").startswith("PC") and fields.get("PD"):
                date_label, time_label, scheduled_at = parse_datetime(fields.get("BC"), host=host)
                home = (fields.get("NA") or "").strip()
                away = (fields.get("N2") or "").strip()
                matches[fixture_id] = {
                    "fixture_id": fixture_id,
                    "home": home,
                    "away": away,
                    "league": fields.get("L3") or league_name,
                    "scheduled_label_date": date_label,
                    "scheduled_label_time": time_label,
                    "scheduled_at": scheduled_at,
                    "event_url": event_visual_url(host, fixture_id, section="I1"),
                    "stats_url": extract_sportradar_url(fields.get("EX")),
                    "markets_payload": {
                        "1x2": {
                            "home": None,
                            "draw": None,
                            "away": None,
                        }
                    },
                    "odds_home": None,
                    "odds_draw": None,
                    "odds_away": None,
                }
                continue

            if current_market != "40" or current_selection not in {"1", "X", "2"}:
                continue
            if fixture_id not in matches:
                continue

            odds_decimal = fraction_to_decimal(fields.get("OD") or fields.get("DO"))
            if current_selection == "1":
                matches[fixture_id]["odds_home"] = odds_decimal
                matches[fixture_id]["markets_payload"]["1x2"]["home"] = odds_decimal
            elif current_selection == "X":
                matches[fixture_id]["odds_draw"] = odds_decimal
                matches[fixture_id]["markets_payload"]["1x2"]["draw"] = odds_decimal
            elif current_selection == "2":
                matches[fixture_id]["odds_away"] = odds_decimal
                matches[fixture_id]["markets_payload"]["1x2"]["away"] = odds_decimal

    ordered_matches = sorted(
        matches.values(),
        key=lambda item: (item.get("scheduled_at") or "", item.get("fixture_id") or ""),
    )
    return {
        "league_name": league_name or "Bet365 League",
        "topic": topic or "",
        "matches": ordered_matches,
    }


def parse_asian_payload(
    payload: str,
    event_id: str,
    *,
    include_alternative_markets: bool,
) -> dict[str, Any]:
    tokens = tokenize(payload)
    event = {
        "event_id": event_id,
        "name": None,
        "home": None,
        "away": None,
        "league": None,
        "start_raw": None,
        "start_iso": None,
    }
    markets: list[dict[str, Any]] = []
    current_market: dict[str, Any] | None = None
    current_selection_meta: dict[str, str] | None = None
    pending_line: str | None = None

    for tag, fields in tokens:
        if tag == "EV" and fields.get("ID") == "EMB":
            event.update(
                {
                    "event_id": fields.get("FI") or event_id,
                    "name": fields.get("EX"),
                    "home": fields.get("N2"),
                    "away": fields.get("N3"),
                    "league": fields.get("CC") or fields.get("L3"),
                    "start_raw": fields.get("BC"),
                    "start_iso": _raw_datetime_to_iso(fields.get("BC")),
                }
            )
        elif tag == "MG":
            market_id = fields.get("ID")
            if market_id in PRIMARY_ASIAN_MARKET_IDS or (
                include_alternative_markets and market_id in ASIAN_MARKET_NAMES
            ):
                current_market = {
                    "market_id": market_id,
                    "market_name": fields.get("NA") or ASIAN_MARKET_NAMES.get(market_id) or market_id,
                    "selections": [],
                }
                markets.append(current_market)
            else:
                current_market = None
            current_selection_meta = None
            pending_line = None
        elif tag == "MA" and current_market is not None:
            current_selection_meta = fields
        elif tag == "PA" and current_market is not None:
            if fields.get("ID", "").startswith("PC"):
                pending_line = normalize_line(fields.get("NA"))
                continue
            odds_decimal = fraction_to_decimal(fields.get("OD") or fields.get("DO"))
            selection_name = (
                (current_selection_meta or {}).get("NA")
                or fields.get("NA")
                or fields.get("HD")
                or fields.get("HA")
                or ""
            ).strip()
            current_market["selections"].append(
                {
                    "selection": selection_name,
                    "line": normalize_line(pending_line or fields.get("HD") or fields.get("HA")),
                    "odds_decimal": odds_decimal,
                }
            )

    markets_payload: dict[str, Any] = {}
    alternative_markets: list[dict[str, Any]] = []
    for market in markets:
        if not market["selections"]:
            continue
        if market["market_id"] == "938":
            markets_payload["asian_handicap"] = canonicalize_market(market)
        elif market["market_id"] == "10143":
            markets_payload["goal_line"] = canonicalize_market(market)
        else:
            alternative_markets.append(canonicalize_market(market))

    if alternative_markets:
        markets_payload["alternative_markets"] = sorted(
            alternative_markets,
            key=lambda market: (
                str(market.get("market_id") or ""),
                str(market.get("market_name") or ""),
            ),
        )

    return {"event": event, "markets_payload": markets_payload}


def canonicalize_market(market: dict[str, Any]) -> dict[str, Any]:
    selections = sorted(
        [
            {
                "selection": str(item.get("selection") or "").strip(),
                "line": normalize_line(item.get("line")),
                "odds": item.get("odds_decimal"),
            }
            for item in market.get("selections") or []
            if item.get("odds_decimal") is not None
        ],
        key=lambda item: (
            str(item.get("line") or ""),
            str(item.get("selection") or ""),
        ),
    )
    return {
        "market_id": market.get("market_id"),
        "market_name": market.get("market_name"),
        "selections": selections,
    }


def normalize_line(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip().replace("+", "")
    if not value:
        return None
    if value in {"0", "-0", "0.0", "-0.0"}:
        return "0.0"
    return value


def merge_market_payloads(base_payload: dict[str, Any] | None, asian_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    base = json.loads(json.dumps(base_payload or {}))
    extra = asian_payload or {}
    for key, value in extra.items():
        base[key] = value
    return base or None


def _raw_datetime_to_iso(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d%H%M%S").isoformat()
    except ValueError:
        return None


def resolve_bet365_timezone_name(host: str) -> str:
    normalized_host = host.strip().lower()
    if normalized_host.endswith(".bet.ar") or normalized_host.endswith("bet365.bet.ar"):
        return "America/Argentina/Buenos_Aires"
    if normalized_host.endswith(".es") or normalized_host.endswith("bet365.es"):
        return "Europe/Madrid"
    return "UTC"


def extract_sportradar_url(ex: str | None) -> str | None:
    """Extract the Bet365Stats / Sportradar URL embedded in one EX field."""

    normalized_ex = (ex or "").strip()
    if not normalized_ex:
        return None

    match = re.search(r"puw~(https?://[^~]+)~Bet365Stats", normalized_ex)
    if match is None:
        return None

    return match.group(1)


__all__ = [
    "Bet365AsianLeagueExtraction",
    "Bet365AsianMatch",
    "Bet365PlaywrightAsianClient",
    "extract_sportradar_url",
    "parse_asian_payload",
    "parse_league_payload",
]

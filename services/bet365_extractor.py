"""Bet365 league extraction helpers and persistent browser scraper.

This module provides two layers:

1. a persistent browser-backed extractor used by the running bot
2. a small compatibility helper that can extract one league on demand

The running bot reuses one Chromium browser and one browser context, then
opens a few pages in parallel for each monitoring cycle.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

EXTRACTOR_JS = r"""
() => {
  function findFirst(node, predicate) {
    if (!node) return null;
    if (predicate(node)) return node;
    for (const child of node._actualChildren || []) {
      const found = findFirst(child, predicate);
      if (found) return found;
    }
    return null;
  }

  function norm(s) {
    return (s || "").replace(/\s+/g, " ").trim();
  }

  function extractTreeMatches(stem) {
    const ev = findFirst(stem, n => n?.nodeName === "EV");
    if (!ev) return { leagueName: null, matches: [] };

    const marketGroups = ev._actualChildren || [];

    const leagueMeta = marketGroups.find(
      n => n?.nodeName === "MG" && n?.data?.ID === "LMAB"
    );

    const fullTimeGroup = marketGroups.find(
      n => n?.nodeName === "MG" && n?.data?.ID === "40"
    );

    if (!fullTimeGroup) {
      return {
        leagueName: leagueMeta?.data?.CC ?? null,
        matches: []
      };
    }

    const markets = fullTimeGroup._actualChildren || [];

    const teamsMarket = markets.find(
      m => m?.nodeName === "MA" && m?.data?.NA === " "
    );
    const homeMarket = markets.find(
      m => m?.nodeName === "MA" && m?.data?.NA === "1"
    );
    const drawMarket = markets.find(
      m => m?.nodeName === "MA" && m?.data?.NA === "X"
    );
    const awayMarket = markets.find(
      m => m?.nodeName === "MA" && m?.data?.NA === "2"
    );

    if (!teamsMarket || !homeMarket || !drawMarket || !awayMarket) {
      return {
        leagueName: leagueMeta?.data?.CC ?? null,
        matches: []
      };
    }

    const fixtures = new Map();

    for (const pa of teamsMarket?._actualChildren || []) {
      const fi = pa?.data?.FI;
      if (!fi) continue;

      fixtures.set(fi, {
        fixtureId: fi,
        home: pa?.data?.NA ?? null,
        away: pa?.data?.N2 ?? null,
        dateLabel: null,
        timeLabel: null,
        oddsDecimal: { "1": null, "X": null, "2": null }
      });
    }

    function mergeOdds(marketNode, key) {
      for (const pa of marketNode?._actualChildren || []) {
        const fi = pa?.data?.FI;
        if (!fi || !fixtures.has(fi)) continue;

        const rawDo = pa?.data?.DO ?? null;
        const value = rawDo !== null && rawDo !== "" ? Number(rawDo) : null;

        fixtures.get(fi).oddsDecimal[key] =
          value !== null && Number.isFinite(value)
            ? Math.round(value * 100) / 100
            : null;
      }
    }

    mergeOdds(homeMarket, "1");
    mergeOdds(drawMarket, "X");
    mergeOdds(awayMarket, "2");

    return {
      leagueName: leagueMeta?.data?.CC ?? null,
      matches: Array.from(fixtures.values())
    };
  }

  function extractDateHeaders() {
    const dateRegex = /^(Lun|Mar|Mié|Mie|Jue|Vie|Sáb|Sab|Dom)\s+\d{1,2}\s+[a-záéíóú]{3}$/i;

    return [...document.querySelectorAll("*")]
      .map(el => ({
        el,
        text: norm(el.innerText),
        top: el.getBoundingClientRect().top
      }))
      .filter(x => dateRegex.test(x.text));
  }

  function closestPreviousDate(top, headers) {
    const prev = headers.filter(h => h.top <= top).sort((a, b) => b.top - a.top);
    return prev[0]?.text || null;
  }

  function findRowForMatch(home, away) {
    const teamNodes = [...document.querySelectorAll(".rcl-ParticipantFixtureDetailsTeam_TeamName")]
      .filter(el => norm(el.innerText) === home);

    for (const node of teamNodes) {
      let cur = node;
      for (let i = 0; i < 8 && cur; i++) {
        const txt = norm(cur.innerText);
        const hasHome = txt.includes(home);
        const hasAway = txt.includes(away);
        const hasTime = /\b([01]?\d|2[0-3]):[0-5]\d\b/.test(txt);
        const smallEnough = txt.length < 80;

        if (hasHome && hasAway && hasTime && smallEnough) {
          return cur;
        }
        cur = cur.parentElement;
      }
    }

    return null;
  }

  function mergeDomDateTime(matches) {
    const headers = extractDateHeaders();

    return matches.map(m => {
      const row = findRowForMatch(m.home, m.away);
      const txt = norm(row?.innerText || "");
      const time = (txt.match(/\b([01]?\d|2[0-3]):[0-5]\d\b/) || [null])[0];
      const top = row?.getBoundingClientRect?.().top ?? null;
      const date = top != null ? closestPreviousDate(top, headers) : null;

      return {
        ...m,
        dateLabel: date,
        timeLabel: time
      };
    });
  }

  try {
    if (
      typeof NavLib === "undefined" ||
      !NavLib?.WebsiteNavigationManager?.CurrentPageData ||
      typeof DataReactLib === "undefined" ||
      typeof DataReactLib.getStemFromLookup !== "function"
    ) {
      return {
        error: "NavLib/DataReactLib no disponibles todavía."
      };
    }

    const topic = NavLib.WebsiteNavigationManager.CurrentPageData;
    const stem = DataReactLib.getStemFromLookup(topic);

    if (!stem) {
      return {
        error: "No se encontró stem para el topic actual.",
        topic
      };
    }

    const base = extractTreeMatches(stem);

    return {
      leagueId: stem?.data?.ID ?? null,
      topic: stem?.data?.IT ?? null,
      leagueName: base.leagueName,
      matches: mergeDomDateTime(base.matches)
    };
  } catch (err) {
    return {
      error: String(err)
    };
  }
}
"""

SPANISH_MONTHS = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}


@dataclass(frozen=True)
class Bet365ExtractorSettings:
    """Runtime settings for the persistent Bet365 extractor."""

    max_parallel_pages: int = 3
    page_load_timeout_ms: int = 60_000
    post_load_wait_ms: int = 4_000
    headless: bool = True


@dataclass(frozen=True)
class Bet365Match:
    """Represent one normalized Bet365 fixture extracted from the page."""

    fixture_id: str
    home: str
    away: str
    kickoff_label_date: str | None
    kickoff_label_time: str | None
    kickoff_at: str | None
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class Bet365LeagueExtraction:
    """Represent league metadata and fixtures extracted from Bet365."""

    platform: str
    url: str
    league_id: str | None
    topic: str
    league_name: str
    is_empty: bool
    is_provisional_name: bool
    matches: list[Bet365Match]
    payload: dict[str, Any]


class Bet365BrowserExtractor:
    """Persistent browser-backed Bet365 extractor.

    The bot keeps one browser and one context alive, then opens a limited
    number of pages in parallel during each cycle.
    """

    def __init__(self, settings: Bet365ExtractorSettings | None = None) -> None:
        self.settings = settings or Bet365ExtractorSettings()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._start_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(self.settings.max_parallel_pages)

    async def start(self) -> None:
        """Start the persistent Playwright browser and context if needed."""

        if self._browser is not None and self._context is not None:
            return

        async with self._start_lock:
            if self._browser is not None and self._context is not None:
                return

            try:
                from playwright.async_api import async_playwright
            except ImportError as error:
                raise RuntimeError(
                    "Playwright is not installed. Install dependencies and run "
                    "'python -m playwright install chromium' before using Bet365 commands."
                ) from error

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.settings.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="es-AR",
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
            )

            logger.info(
                "Persistent Bet365 browser started with max_parallel_pages=%s.",
                self.settings.max_parallel_pages,
            )

    async def stop(self) -> None:
        """Stop the persistent Playwright browser and context."""

        if self._context is not None:
            await self._context.close()
            self._context = None

        if self._browser is not None:
            await self._browser.close()
            self._browser = None

        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

        logger.info("Persistent Bet365 browser stopped.")

    async def extract_league(self, url: str) -> Bet365LeagueExtraction:
        """Extract league metadata and fixtures from one Bet365 league URL."""

        normalized_url = validate_bet365_league_url(url)
        await self.start()

        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        except ImportError as error:
            raise RuntimeError(
                "Playwright is not installed. Install dependencies and run "
                "'python -m playwright install chromium' before using Bet365 commands."
            ) from error

        async with self._semaphore:
            if self._context is None:
                raise RuntimeError("Bet365 browser context is not available.")

            data: dict[str, Any] | None = None

            for attempt in range(1, 3):
                page = await self._context.new_page()

                try:
                    data = await self._extract_page_payload(page, normalized_url)
                    break
                except PlaywrightTimeoutError as error:
                    logger.warning(
                        "Timed out while loading Bet365 runtime state for %s (attempt %s/2).",
                        normalized_url,
                        attempt,
                    )
                    if attempt == 2:
                        raise RuntimeError("Timed out while loading Bet365 runtime state.") from error
                    await page.wait_for_timeout(1_500)
                finally:
                    await page.close()

        if data is None:
            raise RuntimeError("The Bet365 extractor could not load any runtime payload.")

        league_id = _optional_text(data.get("leagueId"))
        topic = str(data.get("topic", "")).strip()
        raw_league_name = str(data.get("leagueName", "")).strip()
        extractor_error = str(data.get("error", "")).strip()

        if extractor_error:
            logger.warning("Bet365 extractor reported an error for %s: %s", normalized_url, extractor_error)

        if not topic:
            raise RuntimeError("The Bet365 page did not expose a usable topic.")

        raw_matches = data.get("matches", [])
        if not isinstance(raw_matches, list):
            raw_matches = []

        matches = [_normalize_match_payload(raw_match) for raw_match in raw_matches]
        is_empty = len(matches) == 0
        is_provisional_name = False
        league_name = raw_league_name

        if not league_name:
            if not is_empty:
                raise RuntimeError("The Bet365 page did not expose a usable league name.")

            league_name = _build_provisional_league_name(league_id, topic)
            is_provisional_name = True

        return Bet365LeagueExtraction(
            platform="bet365",
            url=normalized_url,
            league_id=league_id,
            topic=topic,
            league_name=league_name,
            is_empty=is_empty,
            is_provisional_name=is_provisional_name,
            matches=matches,
            payload=data,
        )

    async def _extract_page_payload(self, page: Any, normalized_url: str) -> dict[str, Any]:
        """Load one Bet365 league page and return the raw extracted payload."""

        await page.goto(
            normalized_url,
            wait_until="load",
            timeout=self.settings.page_load_timeout_ms,
        )
        await page.wait_for_function(
            """
            () =>
              typeof NavLib !== 'undefined' &&
              typeof DataReactLib !== 'undefined' &&
              NavLib?.WebsiteNavigationManager?.CurrentPageData &&
              typeof DataReactLib.getStemFromLookup === 'function'
            """,
            timeout=self.settings.page_load_timeout_ms,
        )
        await page.wait_for_timeout(self.settings.post_load_wait_ms)
        data = await page.evaluate(EXTRACTOR_JS)

        if not isinstance(data, dict):
            raise RuntimeError("The Bet365 extractor returned an unexpected payload format.")

        return data

def validate_bet365_league_url(url: str) -> str:
    """Validate and normalize a Bet365 league URL before scraping."""

    normalized_url = url.strip()

    if not normalized_url:
        raise ValueError("The URL must not be empty.")

    parsed = urlparse(normalized_url)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("The URL must start with http:// or https://.")

    if "bet365" not in parsed.netloc.lower():
        raise ValueError("The URL must belong to Bet365.")

    return normalized_url


async def extract_bet365_league(
    url: str,
    *,
    headless: bool = True,
    max_parallel_pages: int = 1,
    page_load_timeout_ms: int = 60_000,
    post_load_wait_ms: int = 4_000,
) -> Bet365LeagueExtraction:
    """Extract one Bet365 league using a temporary browser instance.

    This helper keeps backwards compatibility for one-off uses. The real bot
    should prefer `Bet365BrowserExtractor`.
    """

    extractor = Bet365BrowserExtractor(
        Bet365ExtractorSettings(
            max_parallel_pages=max_parallel_pages,
            page_load_timeout_ms=page_load_timeout_ms,
            post_load_wait_ms=post_load_wait_ms,
            headless=headless,
        )
    )

    try:
        return await extractor.extract_league(url)
    finally:
        await extractor.stop()


def _normalize_match_payload(raw_match: Any) -> Bet365Match:
    """Normalize one raw fixture payload extracted from Bet365."""

    raw = raw_match if isinstance(raw_match, dict) else {}

    fixture_id = str(raw.get("fixtureId", "")).strip()
    home = str(raw.get("home", "")).strip()
    away = str(raw.get("away", "")).strip()

    if not fixture_id or not home or not away:
        raise RuntimeError("A Bet365 match payload is missing fixtureId, home, or away.")

    date_label = _optional_text(raw.get("dateLabel"))
    time_label = _optional_text(raw.get("timeLabel"))
    kickoff_at = _parse_kickoff_labels(date_label, time_label)

    odds_decimal = raw.get("oddsDecimal") if isinstance(raw.get("oddsDecimal"), dict) else {}

    return Bet365Match(
        fixture_id=fixture_id,
        home=home,
        away=away,
        kickoff_label_date=date_label,
        kickoff_label_time=time_label,
        kickoff_at=kickoff_at,
        odds_home=_coerce_optional_float(odds_decimal.get("1")),
        odds_draw=_coerce_optional_float(odds_decimal.get("X")),
        odds_away=_coerce_optional_float(odds_decimal.get("2")),
        raw=raw,
    )


def _parse_kickoff_labels(date_label: str | None, time_label: str | None) -> str | None:
    """Try to normalize visible Bet365 date/time labels into ISO format."""

    if not date_label or not time_label:
        return None

    normalized_date = _strip_accents(date_label).lower()
    normalized_time = time_label.strip()

    if ":" not in normalized_time:
        return None

    try:
        hour, minute = [int(piece) for piece in normalized_time.split(":", maxsplit=1)]
    except ValueError:
        return None

    local_tz = datetime.now().astimezone().tzinfo or timezone.utc
    now_local = datetime.now(local_tz)

    if normalized_date == "hoy":
        target_date = now_local.date()
    elif normalized_date == "manana":
        target_date = (now_local + timedelta(days=1)).date()
    else:
        parts = normalized_date.split()
        if len(parts) < 3:
            return None

        try:
            day = int(parts[1])
        except ValueError:
            return None

        month = SPANISH_MONTHS.get(parts[2][:3])
        if month is None:
            return None

        year = now_local.year

        try:
            candidate = datetime(year, month, day, hour, minute, tzinfo=local_tz)
        except ValueError:
            return None

        # If the label belongs to the next season/year, roll over conservatively.
        if candidate < now_local - timedelta(days=30):
            try:
                candidate = candidate.replace(year=year + 1)
            except ValueError:
                return None

        return candidate.astimezone(timezone.utc).isoformat()

    try:
        candidate = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour,
            minute,
            tzinfo=local_tz,
        )
    except ValueError:
        return None

    return candidate.astimezone(timezone.utc).isoformat()


def _strip_accents(value: str) -> str:
    """Remove accents from a string before parsing Spanish month labels."""

    normalized = unicodedata.normalize("NFKD", value)
    return "".join(character for character in normalized if not unicodedata.combining(character))


def _optional_text(value: Any) -> str | None:
    """Normalize an optional text value coming from the extractor payload."""

    if value is None:
        return None

    normalized = str(value).strip()
    return normalized or None


def _coerce_optional_float(value: Any) -> float | None:
    """Normalize optional decimal odds values to Python floats."""

    if value is None:
        return None

    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _build_provisional_league_name(league_id: str | None, topic: str) -> str:
    """Build a stable placeholder name for a valid but currently empty league."""

    if league_id:
        normalized_league_id = league_id.strip()
        if normalized_league_id and not normalized_league_id.upper().startswith("E"):
            normalized_league_id = f"E{normalized_league_id}"

        if normalized_league_id:
            return f"Liga vacía {normalized_league_id}"

    topic_match = re.search(r"#E([^#]+)#", topic)
    if topic_match:
        return f"Liga vacía E{topic_match.group(1)}"

    return "Liga vacía Bet365"

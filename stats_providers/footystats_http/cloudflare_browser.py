"""Headed-browser fallback that clears FootyStats' Cloudflare challenge.

Why this exists:
    footystats.org now serves every public HTML page behind a Cloudflare
    "Managed Challenge" (``cf-mitigated: challenge`` + Turnstile). Plain httpx,
    ``curl_cffi`` TLS impersonation and vanilla headless Playwright are all
    detected and answered with HTTP 403. The only reliable, no-cost way to read
    the pages is to drive a real, headed Chrome through the challenge once and
    keep the warmed context alive: the first navigation solves the interactive
    Turnstile (a checkbox click inside the challenge iframe), subsequent
    navigations reuse the ``cf_clearance`` cookie and load in ~1-4s.

Design:
    One process-wide :class:`CloudflareBrowserFetcher` owns a dedicated daemon
    thread running its own asyncio loop and a single persistent Patchright
    context. The browser stays pinned to that one thread (Playwright objects are
    not thread-safe), while the rest of the code talks to it through the plain
    synchronous :meth:`fetch_html`. Navigations are serialized so the single
    warmed tab is never driven concurrently.

Safety:
    This solves the challenge the same way a human visitor's browser does. It
    does not forge tokens, defeat rate limits, or touch any account state.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PROFILE_DIR = Path(__file__).resolve().parent / ".chrome_profile"
_CHALLENGE_TITLE_MARKERS = ("just a moment", "un momento", "moment…", "checking")
_CHALLENGE_FRAME_HOST = "challenges.cloudflare.com"
_CHECKBOX_SELECTOR = "input[type=checkbox], .cb-lb, label, #challenge-stage"


class CloudflareBrowserError(RuntimeError):
    """Raised when the headed browser cannot return an un-challenged page."""


class CloudflareBrowserFetcher:
    """Fetch FootyStats HTML through a warm, challenge-cleared headed Chrome."""

    def __init__(
        self,
        *,
        channel: str | None = None,
        headless: bool | None = None,
        profile_dir: Path | None = None,
        clear_attempts: int = 20,
        clear_poll_seconds: float = 2.0,
        nav_timeout_seconds: float = 60.0,
        settle_timeout_seconds: float = 6.0,
    ) -> None:
        self._channel = channel if channel is not None else os.getenv("FOOTYSTATS_BROWSER_CHANNEL", "chrome").strip() or None
        env_headless = os.getenv("FOOTYSTATS_BROWSER_HEADLESS", "").strip().lower()
        if headless is not None:
            self._headless = headless
        else:
            self._headless = env_headless in {"1", "true", "yes"}
        env_profile = os.getenv("FOOTYSTATS_BROWSER_PROFILE", "").strip()
        self._profile_dir = profile_dir or (Path(env_profile) if env_profile else _DEFAULT_PROFILE_DIR)
        self._clear_attempts = clear_attempts
        self._clear_poll_ms = int(clear_poll_seconds * 1000)
        self._nav_timeout_ms = int(nav_timeout_seconds * 1000)
        self._settle_timeout_ms = int(settle_timeout_seconds * 1000)

        self._lifecycle_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._nav_lock: asyncio.Lock | None = None
        self._playwright = None
        self._context = None
        self._page = None
        self._closed = False

    # -- public sync API -------------------------------------------------

    def fetch_html(self, url: str, *, timeout: float = 90.0) -> str:
        """Return fully-rendered HTML for ``url`` after clearing any challenge."""

        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(self._fetch(url), loop)
        try:
            return future.result(timeout=timeout)
        except TimeoutError as exc:  # pragma: no cover - defensive
            future.cancel()
            raise CloudflareBrowserError(f"Timed out fetching {url} via headed browser.") from exc

    def close(self) -> None:
        """Tear down the browser and its dedicated loop/thread."""

        with self._lifecycle_lock:
            loop, thread = self._loop, self._thread
            if loop is None:
                return
            self._closed = True
        try:
            asyncio.run_coroutine_threadsafe(self._shutdown(), loop).result(timeout=30)
        except Exception:  # pragma: no cover - best-effort teardown
            logger.debug("FootyStats browser shutdown raised", exc_info=True)
        loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=10)
        with self._lifecycle_lock:
            self._loop = None
            self._thread = None

    # -- loop / thread management ---------------------------------------

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lifecycle_lock:
            if self._closed:
                raise CloudflareBrowserError("CloudflareBrowserFetcher is closed.")
            if self._loop is not None:
                return self._loop
            ready = threading.Event()
            loop_box: dict[str, asyncio.AbstractEventLoop] = {}

            def _run() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop_box["loop"] = loop
                ready.set()
                loop.run_forever()
                loop.close()

            thread = threading.Thread(target=_run, name="footystats-cf-browser", daemon=True)
            thread.start()
            ready.wait()
            self._loop = loop_box["loop"]
            self._thread = thread
            return self._loop

    # -- browser coroutines (run only on the dedicated loop) ------------

    async def _ensure_context(self):
        if self._nav_lock is None:
            self._nav_lock = asyncio.Lock()
        if self._context is not None and self._page is not None and not self._page.is_closed():
            return
        try:
            from patchright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - dependency missing
            raise CloudflareBrowserError(
                "patchright is required for the FootyStats Cloudflare fallback "
                "(pip install patchright && patchright install chromium)."
            ) from exc

        self._profile_dir.mkdir(parents=True, exist_ok=True)
        if self._playwright is None:
            self._playwright = await async_playwright().start()

        launch_kwargs = dict(
            user_data_dir=str(self._profile_dir),
            headless=self._headless,
            no_viewport=True,
        )
        try:
            self._context = await self._playwright.chromium.launch_persistent_context(
                channel=self._channel, **launch_kwargs
            )
        except Exception as exc:
            logger.warning(
                "FootyStats browser channel=%s unavailable (%s); falling back to bundled chromium.",
                self._channel,
                exc,
            )
            self._context = await self._playwright.chromium.launch_persistent_context(**launch_kwargs)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        logger.info(
            "🌐 FootyStats Cloudflare browser ready | headless=%s channel=%s profile=%s",
            self._headless,
            self._channel,
            self._profile_dir,
        )

    async def _fetch(self, url: str) -> str:
        await self._ensure_context()
        assert self._nav_lock is not None
        async with self._nav_lock:
            try:
                return await self._navigate(url)
            except Exception:
                # A crashed/closed context yields a fresh start on the next call.
                await self._discard_context()
                raise

    async def _navigate(self, url: str) -> str:
        page = self._page
        assert page is not None
        await page.goto(url, wait_until="domcontentloaded", timeout=self._nav_timeout_ms)
        cleared = await self._clear_challenge(page)
        if not cleared:
            raise CloudflareBrowserError(f"Cloudflare challenge not cleared for {url}.")
        try:
            await page.wait_for_load_state("networkidle", timeout=self._settle_timeout_ms)
        except Exception:
            pass  # networkidle is best-effort; partial render is still usable
        return await page.content()

    async def _clear_challenge(self, page) -> bool:
        for _ in range(self._clear_attempts):
            if not await self._is_challenge(page):
                return True
            await self._click_turnstile(page)
            await page.wait_for_timeout(self._clear_poll_ms)
        return not await self._is_challenge(page)

    async def _is_challenge(self, page) -> bool:
        try:
            title = (await page.title()).lower()
        except Exception:
            return True
        if any(marker in title for marker in _CHALLENGE_TITLE_MARKERS):
            return True
        # An active challenge iframe is the authoritative signal.
        return any(_CHALLENGE_FRAME_HOST in (frame.url or "") for frame in page.frames)

    async def _click_turnstile(self, page) -> None:
        for frame in page.frames:
            if _CHALLENGE_FRAME_HOST not in (frame.url or ""):
                continue
            try:
                target = await frame.query_selector(_CHECKBOX_SELECTOR)
                if target is not None:
                    await target.click(timeout=2000)
            except Exception:
                continue  # widget not interactable yet; retry on next poll

    async def _discard_context(self) -> None:
        for closer in (getattr(self._context, "close", None),):
            if closer is None:
                continue
            try:
                await closer()
            except Exception:
                pass
        self._context = None
        self._page = None

    async def _shutdown(self) -> None:
        await self._discard_context()
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None


__all__ = ["CloudflareBrowserFetcher", "CloudflareBrowserError"]

"""Shared persistent Playwright browser runtime for web extractors."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrowserHandlerSettings:
    """Generic runtime settings for browser-backed extractors."""

    browser_name: str = "chromium"
    headless: bool = True
    max_parallel_pages: int = 3
    page_reuse_enabled: bool = False
    launch_args: tuple[str, ...] = ()
    context_kwargs: dict[str, Any] = field(default_factory=dict)
    page_default_timeout_ms: int | None = None
    page_default_navigation_timeout_ms: int | None = None
    idle_ttl_seconds: float | None = None


class BrowserHandler:
    """Manage one persistent Playwright browser/context with limited page concurrency."""

    def __init__(self, settings: BrowserHandlerSettings | None = None) -> None:
        self.settings = settings or BrowserHandlerSettings()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._start_lock = asyncio.Lock()
        self._maintenance_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(self.settings.max_parallel_pages)
        self._page_pool: list[Any] = []
        self._page_pool_lock = asyncio.Lock()
        self._active_page_count = 0
        self._active_page_count_lock = asyncio.Lock()
        self._restart_requested = False
        self._last_release_monotonic: float | None = None

    async def start(self) -> None:
        """Start the Playwright runtime, browser, and context if needed."""

        if self._browser is not None:
            return

        async with self._start_lock:
            if self._browser is not None:
                return

            try:
                from playwright.async_api import async_playwright
            except ImportError as error:
                raise RuntimeError(
                    "Playwright is not installed. Install dependencies and run "
                    "'python -m playwright install chromium' before using browser extractors."
                ) from error

            self._playwright = await async_playwright().start()
            browser_type = getattr(self._playwright, self.settings.browser_name, None)
            if browser_type is None:
                raise RuntimeError(
                    f"Unsupported Playwright browser '{self.settings.browser_name}'."
                )

            self._browser = await browser_type.launch(
                headless=self.settings.headless,
                args=list(self.settings.launch_args),
            )

            logger.warning(
                "🌐 CHROME ABIERTO | subsistema=extractor(bet365) | browser=%s headless=%s "
                "max_parallel_pages=%s | motivo=captura de ligas vía Playwright",
                self.settings.browser_name,
                self.settings.headless,
                self.settings.max_parallel_pages,
            )

    async def stop(self) -> None:
        """Stop the browser context, browser, and Playwright runtime."""

        if self._context is not None:
            await self._context.close()
            self._context = None
            self._page_pool.clear()

        if self._browser is not None:
            await self._browser.close()
            self._browser = None

        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

        logger.info("Persistent browser stopped: browser=%s", self.settings.browser_name)

    async def request_restart(self, *, reason: str) -> None:
        """Mark the persistent browser for restart before the next safe capture."""

        self._restart_requested = True
        logger.info(
            "Persistent browser restart requested: browser=%s reason=%s",
            self.settings.browser_name,
            reason,
        )

    @asynccontextmanager
    async def page(self) -> Any:
        """Yield a fresh page from the shared persistent context."""

        async with self._semaphore:
            page = None
            await self._mark_page_opened()

            try:
                await self._prepare_runtime()
                await self._ensure_shared_context()
                if self._context is None:
                    raise RuntimeError("Browser context is not available.")

                page = await self._acquire_page()
                if self.settings.page_default_timeout_ms is not None:
                    page.set_default_timeout(self.settings.page_default_timeout_ms)
                if self.settings.page_default_navigation_timeout_ms is not None:
                    page.set_default_navigation_timeout(
                        self.settings.page_default_navigation_timeout_ms
                    )
                yield page
            finally:
                if page is not None:
                    if self.settings.page_reuse_enabled:
                        await self._recycle_page(page)
                    else:
                        await page.close()
                await self._mark_page_closed()

    @asynccontextmanager
    async def capture_page(self) -> Any:
        """Yield a fresh page backed by a fresh browser context.

        This is the safest mode for response-capture style extractors that want
        one clean context per capture while still reusing one persistent browser
        process underneath.
        """

        async with self._semaphore:
            context = None
            page = None
            await self._mark_page_opened()

            try:
                await self._prepare_runtime()
                if self._browser is None:
                    raise RuntimeError("Browser instance is not available.")

                context = await self._browser.new_context(**self.settings.context_kwargs)
                page = await context.new_page()
                if self.settings.page_default_timeout_ms is not None:
                    page.set_default_timeout(self.settings.page_default_timeout_ms)
                if self.settings.page_default_navigation_timeout_ms is not None:
                    page.set_default_navigation_timeout(
                        self.settings.page_default_navigation_timeout_ms
                    )
                yield page
            finally:
                try:
                    if page is not None and not page.is_closed():
                        await page.close()
                except Exception:
                    pass
                if context is not None:
                    await context.close()
                await self._mark_page_closed()

    async def _acquire_page(self) -> Any:
        if not self.settings.page_reuse_enabled:
            await self._ensure_shared_context()
            if self._context is None:
                raise RuntimeError("Browser context is not available.")
            return await self._context.new_page()

        async with self._page_pool_lock:
            while self._page_pool:
                page = self._page_pool.pop()
                try:
                    if not page.is_closed():
                        return page
                except Exception:
                    continue

        await self._ensure_shared_context()
        if self._context is None:
            raise RuntimeError("Browser context is not available.")
        return await self._context.new_page()

    async def _recycle_page(self, page: Any) -> None:
        try:
            if page.is_closed():
                return
        except Exception:
            return

        try:
            await page.goto("about:blank", wait_until="domcontentloaded", timeout=5_000)
        except Exception:
            try:
                await page.close()
            except Exception:
                pass
            return

        async with self._page_pool_lock:
            self._page_pool.append(page)

    async def _prepare_runtime(self) -> None:
        async with self._maintenance_lock:
            restart_reason = await self._restart_reason()
            if restart_reason is not None:
                logger.info(
                    "Persistent browser restarting: browser=%s reason=%s",
                    self.settings.browser_name,
                    restart_reason,
                )
                await self.stop()
                self._restart_requested = False

            await self.start()

    async def _restart_reason(self) -> str | None:
        if self._browser is None:
            return None

        if self._restart_requested and self._active_page_count == 0:
            return "restart_requested"

        idle_ttl_seconds = self.settings.idle_ttl_seconds
        if idle_ttl_seconds is None or idle_ttl_seconds <= 0:
            return None

        if self._active_page_count != 0 or self._last_release_monotonic is None:
            return None

        if (time.monotonic() - self._last_release_monotonic) >= idle_ttl_seconds:
            return f"idle_ttl_exceeded:{idle_ttl_seconds}"
        return None

    async def _mark_page_opened(self) -> None:
        async with self._active_page_count_lock:
            self._active_page_count += 1

    async def _mark_page_closed(self) -> None:
        async with self._active_page_count_lock:
            self._active_page_count = max(0, self._active_page_count - 1)
            self._last_release_monotonic = time.monotonic()

    async def _ensure_shared_context(self) -> None:
        if self._context is not None:
            return
        if self._browser is None:
            raise RuntimeError("Browser instance is not available.")
        self._context = await self._browser.new_context(**self.settings.context_kwargs)


__all__ = ["BrowserHandler", "BrowserHandlerSettings"]

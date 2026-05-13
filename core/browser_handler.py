"""Shared persistent Playwright browser runtime for web extractors."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import logging
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


class BrowserHandler:
    """Manage one persistent Playwright browser/context with limited page concurrency."""

    def __init__(self, settings: BrowserHandlerSettings | None = None) -> None:
        self.settings = settings or BrowserHandlerSettings()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._start_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(self.settings.max_parallel_pages)
        self._page_pool: list[Any] = []
        self._page_pool_lock = asyncio.Lock()

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

            logger.info(
                "Persistent browser started: browser=%s max_parallel_pages=%s",
                self.settings.browser_name,
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

    @asynccontextmanager
    async def page(self) -> Any:
        """Yield a fresh page from the shared persistent context."""

        await self.start()

        async with self._semaphore:
            await self._ensure_shared_context()
            if self._context is None:
                raise RuntimeError("Browser context is not available.")

            page = await self._acquire_page()

            try:
                if self.settings.page_default_timeout_ms is not None:
                    page.set_default_timeout(self.settings.page_default_timeout_ms)
                if self.settings.page_default_navigation_timeout_ms is not None:
                    page.set_default_navigation_timeout(
                        self.settings.page_default_navigation_timeout_ms
                    )
                yield page
            finally:
                if self.settings.page_reuse_enabled:
                    await self._recycle_page(page)
                else:
                    await page.close()

    @asynccontextmanager
    async def capture_page(self) -> Any:
        """Yield a fresh page backed by a fresh browser context.

        This is the safest mode for response-capture style extractors that want
        one clean context per capture while still reusing one persistent browser
        process underneath.
        """

        await self.start()

        async with self._semaphore:
            if self._browser is None:
                raise RuntimeError("Browser instance is not available.")

            context = await self._browser.new_context(**self.settings.context_kwargs)
            page = await context.new_page()

            try:
                if self.settings.page_default_timeout_ms is not None:
                    page.set_default_timeout(self.settings.page_default_timeout_ms)
                if self.settings.page_default_navigation_timeout_ms is not None:
                    page.set_default_navigation_timeout(
                        self.settings.page_default_navigation_timeout_ms
                    )
                yield page
            finally:
                try:
                    if not page.is_closed():
                        await page.close()
                except Exception:
                    pass
                await context.close()

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

    async def _ensure_shared_context(self) -> None:
        if self._context is not None:
            return
        if self._browser is None:
            raise RuntimeError("Browser instance is not available.")
        self._context = await self._browser.new_context(**self.settings.context_kwargs)


__all__ = ["BrowserHandler", "BrowserHandlerSettings"]

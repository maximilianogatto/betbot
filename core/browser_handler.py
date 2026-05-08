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

    async def start(self) -> None:
        """Start the Playwright runtime, browser, and context if needed."""

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
            self._context = await self._browser.new_context(**self.settings.context_kwargs)

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
            if self._context is None:
                raise RuntimeError("Browser context is not available.")

            page = await self._context.new_page()

            try:
                if self.settings.page_default_timeout_ms is not None:
                    page.set_default_timeout(self.settings.page_default_timeout_ms)
                if self.settings.page_default_navigation_timeout_ms is not None:
                    page.set_default_navigation_timeout(
                        self.settings.page_default_navigation_timeout_ms
                    )
                yield page
            finally:
                await page.close()


__all__ = ["BrowserHandler", "BrowserHandlerSettings"]

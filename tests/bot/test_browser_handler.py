from __future__ import annotations

import time
import unittest

from core.browser_handler import BrowserHandler, BrowserHandlerSettings


class BrowserHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_restart_is_blocked_while_capture_slot_is_reserved(self) -> None:
        handler = BrowserHandler(
            BrowserHandlerSettings(
                idle_ttl_seconds=10,
            )
        )
        handler._browser = object()
        handler._last_release_monotonic = time.monotonic() - 20

        await handler._mark_page_opened()
        try:
            self.assertIsNone(await handler._restart_reason())
        finally:
            await handler._mark_page_closed()

    async def test_idle_restart_triggers_when_browser_is_idle(self) -> None:
        handler = BrowserHandler(
            BrowserHandlerSettings(
                idle_ttl_seconds=10,
            )
        )
        handler._browser = object()
        handler._last_release_monotonic = time.monotonic() - 20

        self.assertEqual(
            await handler._restart_reason(),
            "idle_ttl_exceeded:10",
        )

    async def test_requested_restart_waits_until_no_active_pages(self) -> None:
        handler = BrowserHandler()
        handler._browser = object()

        await handler._mark_page_opened()
        try:
            await handler.request_restart(reason="ram_limit")
            self.assertIsNone(await handler._restart_reason())
        finally:
            await handler._mark_page_closed()

        self.assertEqual(await handler._restart_reason(), "restart_requested:ram_limit")


if __name__ == "__main__":
    unittest.main()

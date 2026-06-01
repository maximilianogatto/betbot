from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from bot.jobs import _tracking_monitor_loop
from monitors.models import RefreshSummary
from monitors.tracking import TrackingService


class TrackingMonitorLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_tracking_monitor_waits_before_first_cycle_by_default(self) -> None:
        tracking_service = TrackingService()
        tracking_service.monitor_once = AsyncMock()

        application = SimpleNamespace(
            bot_data={"tracking_service": tracking_service},
            bot=object(),
        )

        with patch("bot.jobs.asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await _tracking_monitor_loop(application, interval_seconds=120)

        tracking_service.monitor_once.assert_not_awaited()

    async def test_tracking_monitor_logs_duration(self) -> None:
        tracking_service = TrackingService()
        tracking_service.monitor_once = AsyncMock(
            return_value=RefreshSummary(
                tracks_requested=3,
                tracks_refreshed=2,
                active_matches=10,
                new_events=1,
                odds_changes=4,
                failed_leagues=["Liga A"],
                degraded_leagues=[],
                league_results=[],
                unavailable_competitions=[],
                elapsed_seconds=68.0,
            )
        )

        application = SimpleNamespace(
            bot_data={"tracking_service": tracking_service},
            bot=object(),
        )

        with (
            self.assertLogs("bot.jobs", level="INFO") as captured_logs,
            patch("bot.jobs.asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await _tracking_monitor_loop(
                    application,
                    interval_seconds=120,
                    initial_delay_seconds=0,
                )

        self.assertTrue(
            any("duration=1m 08s" in line and "duration_seconds=68.00" in line
                for line in captured_logs.output)
        )


if __name__ == "__main__":
    unittest.main()

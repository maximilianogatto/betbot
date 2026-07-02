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

        with patch("bot.jobs.legacy.asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)):
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
            patch("bot.jobs.legacy.asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)),
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


class DbPruningJobTests(unittest.IsolatedAsyncioTestCase):
    @patch("adapters.storage.get_storage")
    @patch("bot.jobs.tasks.datetime")
    async def test_orchestrated_pruning_runs_vacuum_on_sunday(self, mock_datetime, mock_get_storage) -> None:
        # Mock weekday() == 6 (Sunday)
        mock_now = mock_datetime.now.return_value
        mock_now.weekday.return_value = 6
        
        mock_repo = mock_get_storage.return_value
        mock_repo.prune_old_data = unittest.mock.Mock(return_value={"pruned": 5})
        mock_repo.run_db_vacuum = unittest.mock.Mock(return_value=True)

        from bot.jobs.tasks import _orchestrated_db_pruning
        await _orchestrated_db_pruning(None)

        mock_repo.prune_old_data.assert_called_once_with(days_threshold=14, sent_alerts_days=30, small_changes_days=7)
        mock_repo.run_db_vacuum.assert_called_once()

    @patch("adapters.storage.get_storage")
    @patch("bot.jobs.tasks.datetime")
    async def test_orchestrated_pruning_does_not_run_vacuum_on_monday(self, mock_datetime, mock_get_storage) -> None:
        # Mock weekday() == 0 (Monday)
        mock_now = mock_datetime.now.return_value
        mock_now.weekday.return_value = 0
        
        mock_repo = mock_get_storage.return_value
        mock_repo.prune_old_data = unittest.mock.Mock(return_value={"pruned": 5})
        mock_repo.run_db_vacuum = unittest.mock.Mock()

        from bot.jobs.tasks import _orchestrated_db_pruning
        await _orchestrated_db_pruning(None)

        mock_repo.prune_old_data.assert_called_once_with(days_threshold=14, sent_alerts_days=30, small_changes_days=7)
        mock_repo.run_db_vacuum.assert_not_called()

    @patch("adapters.storage.get_storage")
    @patch("bot.jobs.legacy.datetime")
    async def test_legacy_pruning_runs_vacuum_on_sunday(self, mock_datetime, mock_get_storage) -> None:
        # Mock weekday() == 6 (Sunday)
        mock_now = mock_datetime.now.return_value
        mock_now.weekday.return_value = 6
        
        mock_repo = mock_get_storage.return_value
        mock_repo.prune_old_data = unittest.mock.Mock(return_value={"pruned": 5})
        mock_repo.run_db_vacuum = unittest.mock.Mock(return_value=True)

        from bot.jobs.legacy import _db_pruning_loop
        
        with patch("bot.jobs.legacy.asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await _db_pruning_loop(None, interval_seconds=10, days_threshold=14)

        mock_repo.prune_old_data.assert_called_once_with(days_threshold=14, sent_alerts_days=30, small_changes_days=7)
        mock_repo.run_db_vacuum.assert_called_once()

    @patch("adapters.storage.get_storage")
    @patch("bot.jobs.legacy.datetime")
    async def test_legacy_pruning_does_not_run_vacuum_on_monday(self, mock_datetime, mock_get_storage) -> None:
        # Mock weekday() == 0 (Monday)
        mock_now = mock_datetime.now.return_value
        mock_now.weekday.return_value = 0
        
        mock_repo = mock_get_storage.return_value
        mock_repo.prune_old_data = unittest.mock.Mock(return_value={"pruned": 5})
        mock_repo.run_db_vacuum = unittest.mock.Mock()

        from bot.jobs.legacy import _db_pruning_loop
        
        with patch("bot.jobs.legacy.asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await _db_pruning_loop(None, interval_seconds=10, days_threshold=14)

        mock_repo.prune_old_data.assert_called_once_with(days_threshold=14, sent_alerts_days=30, small_changes_days=7)
        mock_repo.run_db_vacuum.assert_not_called()


if __name__ == "__main__":
    unittest.main()

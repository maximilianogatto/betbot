from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bot.jobs import _resource_monitor_loop


class ChromiumMemoryRecoveryTests(unittest.IsolatedAsyncioTestCase):
    @patch("bot.jobs.get_system_metrics")
    @patch("bot.jobs.kill_chromium_child_processes")
    @patch("bot.jobs.asyncio.sleep")
    async def test_chromium_ram_recovery_triggers_when_threshold_breached(
        self, mock_sleep, mock_kill, mock_metrics
    ) -> None:
        # Mock metrics returning 900MB RAM for Chromium (breaches 800MB threshold)
        mock_metrics.return_value = {
            "bot_process_ram_mb": 100.0,
            "bot_process_cpu_percent": 0.0,
            "child_processes_count": 5,
            "child_processes_ram_mb": 900.0,
            "chromium_child_processes_count": 4,
            "chromium_child_processes_ram_mb": 900.0,
            "total_app_ram_mb": 1000.0,
            "system_ram_percent": 50.0,
            "system_ram_used_mb": 4000.0,
            "db_size_mb": 10.0,
        }
        mock_kill.return_value = 4
        mock_sleep.side_effect = asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await _resource_monitor_loop(
                interval_seconds=60,
                log_to_file=False,
                chromium_ram_alert_mb=800.0,
            )

        # Verify that kill_chromium_child_processes was called once
        mock_kill.assert_called_once()

    @patch("bot.jobs.get_system_metrics")
    @patch("bot.jobs.kill_chromium_child_processes")
    @patch("bot.jobs.asyncio.sleep")
    async def test_chromium_ram_recovery_does_not_trigger_when_below_threshold(
        self, mock_sleep, mock_kill, mock_metrics
    ) -> None:
        # Mock metrics returning 500MB RAM for Chromium (below 800MB threshold)
        mock_metrics.return_value = {
            "bot_process_ram_mb": 100.0,
            "bot_process_cpu_percent": 0.0,
            "child_processes_count": 5,
            "child_processes_ram_mb": 500.0,
            "chromium_child_processes_count": 4,
            "chromium_child_processes_ram_mb": 500.0,
            "total_app_ram_mb": 6000.0,
            "system_ram_percent": 50.0,
            "system_ram_used_mb": 4000.0,
            "db_size_mb": 10.0,
        }
        mock_sleep.side_effect = asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await _resource_monitor_loop(
                interval_seconds=60,
                log_to_file=False,
                chromium_ram_alert_mb=800.0,
            )

        # Verify that kill_chromium_child_processes was NOT called
        mock_kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()

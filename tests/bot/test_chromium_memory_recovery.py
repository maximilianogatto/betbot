from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from bot.config import Settings
from bot.jobs import ResourceMonitorJob, _resource_monitor_loop


class ChromiumMemoryRecoveryTests(unittest.IsolatedAsyncioTestCase):
    @patch("bot.jobs.legacy.get_system_metrics")
    @patch("bot.jobs.legacy.asyncio.sleep")
    async def test_chromium_ram_recovery_triggers_when_threshold_breached(
        self, mock_sleep, mock_metrics
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
        mock_sleep.side_effect = asyncio.CancelledError
        browser_handler = SimpleNamespace(request_restart=AsyncMock())
        application = SimpleNamespace(bot_data={"browser_handler": browser_handler})

        with self.assertRaises(asyncio.CancelledError):
            await _resource_monitor_loop(
                application,
                interval_seconds=60,
                log_to_file=False,
                chromium_ram_alert_mb=800.0,
            )

        browser_handler.request_restart.assert_awaited_once()
        reason = browser_handler.request_restart.await_args.kwargs["reason"]
        self.assertIn("chromium_ram_mb=900.0>800.0", reason)

    @patch("bot.jobs.legacy.get_system_metrics")
    @patch("bot.jobs.legacy.asyncio.sleep")
    async def test_chromium_ram_recovery_does_not_trigger_when_below_threshold(
        self, mock_sleep, mock_metrics
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
        browser_handler = SimpleNamespace(request_restart=AsyncMock())
        application = SimpleNamespace(bot_data={"browser_handler": browser_handler})

        with self.assertRaises(asyncio.CancelledError):
            await _resource_monitor_loop(
                application,
                interval_seconds=60,
                log_to_file=False,
                chromium_ram_alert_mb=800.0,
            )

        browser_handler.request_restart.assert_not_awaited()

    @patch("bot.jobs.tasks.get_system_metrics")
    async def test_orchestrated_resource_monitor_requests_graceful_restart(self, mock_metrics) -> None:
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
        browser_handler = SimpleNamespace(request_restart=AsyncMock())
        settings = SimpleNamespace(monitor_log_to_file=False, monitor_chromium_ram_alert_mb=800.0)
        application = SimpleNamespace(bot_data={"settings": settings, "browser_handler": browser_handler})

        await ResourceMonitorJob(interval=60).run(application)

        browser_handler.request_restart.assert_awaited_once()

    def test_monitoring_is_enabled_by_default(self) -> None:
        self.assertTrue(Settings(telegram_bot_token="token").enable_monitoring)


if __name__ == "__main__":
    unittest.main()

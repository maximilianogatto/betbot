from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from bot.config import Settings
from bot.jobs import ResourceMonitorJob


def _metrics(chromium_ram_mb: float) -> dict[str, float]:
    return {
        "bot_process_ram_mb": 100.0,
        "bot_process_cpu_percent": 0.0,
        "child_processes_count": 5,
        "child_processes_ram_mb": chromium_ram_mb,
        "chromium_child_processes_count": 4,
        "chromium_child_processes_ram_mb": chromium_ram_mb,
        "total_app_ram_mb": 1000.0,
        "system_ram_percent": 50.0,
        "system_ram_used_mb": 4000.0,
        "db_size_mb": 10.0,
    }


def _application(browser_handler) -> SimpleNamespace:
    settings = SimpleNamespace(monitor_log_to_file=False, monitor_chromium_ram_alert_mb=800.0)
    return SimpleNamespace(bot_data={"settings": settings, "browser_handler": browser_handler})


class ChromiumMemoryRecoveryTests(unittest.IsolatedAsyncioTestCase):
    @patch("bot.jobs.tasks.get_system_metrics")
    async def test_orchestrated_resource_monitor_requests_graceful_restart(self, mock_metrics) -> None:
        mock_metrics.return_value = _metrics(900.0)  # supera el umbral de 800MB
        browser_handler = SimpleNamespace(request_restart=AsyncMock())

        await ResourceMonitorJob(interval=60).run(_application(browser_handler))

        browser_handler.request_restart.assert_awaited_once()
        reason = browser_handler.request_restart.await_args.kwargs["reason"]
        self.assertIn("chromium_ram_mb=900.0>800.0", reason)

    @patch("bot.jobs.tasks.get_system_metrics")
    async def test_orchestrated_resource_monitor_does_not_restart_below_threshold(
        self, mock_metrics
    ) -> None:
        mock_metrics.return_value = _metrics(500.0)  # debajo del umbral de 800MB
        browser_handler = SimpleNamespace(request_restart=AsyncMock())

        await ResourceMonitorJob(interval=60).run(_application(browser_handler))

        browser_handler.request_restart.assert_not_awaited()

    def test_monitoring_is_enabled_by_default(self) -> None:
        self.assertTrue(Settings(telegram_bot_token="token").enable_monitoring)


if __name__ == "__main__":
    unittest.main()

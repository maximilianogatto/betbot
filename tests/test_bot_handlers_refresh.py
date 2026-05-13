from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from bot.handlers import MANUAL_REFRESH_TASK_KEY, refresh_tracks_command
from monitors.models import RefreshSummary


class RefreshTracksHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_tracks_sends_immediate_message_and_final_summary(self) -> None:
        tracking_service = SimpleNamespace(
            refresh_chat_tracks=AsyncMock(
                return_value=RefreshSummary(
                    tracks_requested=1,
                    tracks_refreshed=1,
                    active_matches=3,
                    new_events=0,
                    odds_changes=0,
                    failed_leagues=[],
                    degraded_leagues=[],
                    league_results=[],
                    unavailable_competitions=[],
                )
            ),
            dispatch_notifications=AsyncMock(),
            build_refresh_summary_message=lambda summary: "Refresh completado.",
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"tracking_service": tracking_service})
        context = SimpleNamespace(application=application, bot=bot)
        update = SimpleNamespace(
            message=message,
            effective_chat=SimpleNamespace(id=123),
        )

        with patch("bot.handlers.get_tracking_service", return_value=tracking_service):
            await refresh_tracks_command(update, context)

        message.reply_text.assert_awaited_once_with("🔄 Refrescando tracks, aguardá un momento...")
        task = application.bot_data.get(MANUAL_REFRESH_TASK_KEY)
        self.assertIsInstance(task, asyncio.Task)
        await task
        tracking_service.refresh_chat_tracks.assert_awaited_once_with(123)
        tracking_service.dispatch_notifications.assert_awaited_once()
        bot.send_message.assert_awaited_once_with(
            chat_id=123,
            text="Refresh completado.",
            parse_mode=None,
        )
        self.assertNotIn(MANUAL_REFRESH_TASK_KEY, application.bot_data)

    async def test_refresh_tracks_rejects_when_one_is_already_running(self) -> None:
        tracking_service = SimpleNamespace()
        message = SimpleNamespace(reply_text=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())

        async def never_finishes() -> None:
            await asyncio.sleep(60)

        pending_task = asyncio.create_task(never_finishes())
        application = SimpleNamespace(
            bot_data={
                "tracking_service": tracking_service,
                MANUAL_REFRESH_TASK_KEY: pending_task,
            }
        )
        context = SimpleNamespace(application=application, bot=bot)
        update = SimpleNamespace(
            message=message,
            effective_chat=SimpleNamespace(id=123),
        )

        try:
            with patch("bot.handlers.get_tracking_service", return_value=tracking_service):
                await refresh_tracks_command(update, context)
        finally:
            pending_task.cancel()
            try:
                await pending_task
            except asyncio.CancelledError:
                pass

        message.reply_text.assert_awaited_once_with(
            "⏳ Ya hay un refresh en curso. Esperá a que termine."
        )
        bot.send_message.assert_not_called()

    async def test_refresh_tracks_reports_background_failure(self) -> None:
        tracking_service = SimpleNamespace(
            refresh_chat_tracks=AsyncMock(side_effect=RuntimeError("boom")),
            dispatch_notifications=AsyncMock(),
            build_refresh_summary_message=lambda summary: "unused",
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"tracking_service": tracking_service})
        context = SimpleNamespace(application=application, bot=bot)
        update = SimpleNamespace(
            message=message,
            effective_chat=SimpleNamespace(id=999),
        )

        with patch("bot.handlers.get_tracking_service", return_value=tracking_service):
            await refresh_tracks_command(update, context)

        task = application.bot_data.get(MANUAL_REFRESH_TASK_KEY)
        self.assertIsInstance(task, asyncio.Task)
        await task
        bot.send_message.assert_awaited_once_with(
            chat_id=999,
            text="❌ Ocurrió un error refrescando los tracks. Revisá logs.",
        )


if __name__ == "__main__":
    unittest.main()

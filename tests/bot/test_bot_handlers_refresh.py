from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from interfaces.telegram.handlers import MANUAL_REFRESH_TASK_KEY, refresh_tracks_command
from services.models import CommandResult
from services.models import RefreshSummary
from services.tracking import TrackingService


def _refresh_summary() -> RefreshSummary:
    return RefreshSummary(
        tracks_requested=1,
        tracks_refreshed=1,
        active_matches=3,
        new_events=0,
        odds_changes=0,
        failed_leagues=[],
        degraded_leagues=[],
        league_results=[],
        unavailable_competitions=[],
        elapsed_seconds=42.0,
    )


class RefreshTracksHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_tracks_sends_immediate_message_and_final_summary(self) -> None:
        tracking_service = SimpleNamespace(
            try_start_refresh=AsyncMock(return_value=True),
            finish_refresh=AsyncMock(),
            refresh_chat_tracks=AsyncMock(return_value=_refresh_summary()),
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"tracking_service": tracking_service})
        context = SimpleNamespace(application=application, bot=bot)
        update = SimpleNamespace(
            message=message,
            effective_chat=SimpleNamespace(id=123),
        )

        summary_result = CommandResult(ok=True, message="Refresh completado.\n⏱️ Tiempo total: 42s")
        with (
            patch("interfaces.telegram.handlers.tracking.get_tracking_service", return_value=tracking_service),
            patch("adapters.storage.get_storage", return_value=SimpleNamespace()),
            patch(
                "interfaces.telegram.notifications.dispatch_tracking_notifications",
                new=AsyncMock(),
            ) as dispatch_mock,
            patch(
                "interfaces.telegram.renderers.build_refresh_summary_message",
                return_value=summary_result,
            ),
        ):
            await refresh_tracks_command(update, context)
            message.reply_text.assert_awaited_once_with("🔄 Refrescando tracks, aguardá un momento...")
            task = application.bot_data.get(MANUAL_REFRESH_TASK_KEY)
            self.assertIsInstance(task, asyncio.Task)
            # La task corre DENTRO del with: si no, los patches ya expiraron.
            await task
        tracking_service.refresh_chat_tracks.assert_awaited_once_with(123)
        dispatch_mock.assert_awaited_once()
        tracking_service.finish_refresh.assert_awaited_once_with("manual")
        bot.send_message.assert_awaited_once_with(
            chat_id=123,
            text="Refresh completado.\n⏱️ Tiempo total: 42s",
            parse_mode=None,
        )
        self.assertNotIn(MANUAL_REFRESH_TASK_KEY, application.bot_data)

    async def test_refresh_tracks_rejects_when_shared_refresh_is_already_running(self) -> None:
        tracking_service = TrackingService()
        tracking_service.refresh_chat_tracks = AsyncMock()
        message = SimpleNamespace(reply_text=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"tracking_service": tracking_service})
        context = SimpleNamespace(application=application, bot=bot)
        update = SimpleNamespace(
            message=message,
            effective_chat=SimpleNamespace(id=123),
        )

        try:
            await tracking_service.try_start_refresh("automatic")
            with patch("interfaces.telegram.handlers.tracking.get_tracking_service", return_value=tracking_service):
                await refresh_tracks_command(update, context)
        finally:
            await tracking_service.finish_refresh("automatic")

        message.reply_text.assert_awaited_once_with(
            "⏳ Ya hay un refresh en curso. Esperá a que termine."
        )
        tracking_service.refresh_chat_tracks.assert_not_awaited()
        bot.send_message.assert_not_called()

    async def test_refresh_tracks_reports_background_failure(self) -> None:
        tracking_service = SimpleNamespace(
            try_start_refresh=AsyncMock(return_value=True),
            finish_refresh=AsyncMock(),
            refresh_chat_tracks=AsyncMock(side_effect=RuntimeError("boom")),
            dispatch_notifications=AsyncMock(),
            build_refresh_summary_message=lambda summary: CommandResult(
                ok=True,
                message="unused",
            ),
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"tracking_service": tracking_service})
        context = SimpleNamespace(application=application, bot=bot)
        update = SimpleNamespace(
            message=message,
            effective_chat=SimpleNamespace(id=999),
        )

        summary_result = CommandResult(ok=True, message="Refresh completado.\n⏱️ Tiempo total: 42s")
        with (
            patch("interfaces.telegram.handlers.tracking.get_tracking_service", return_value=tracking_service),
            patch("adapters.storage.get_storage", return_value=SimpleNamespace()),
            patch(
                "interfaces.telegram.notifications.dispatch_tracking_notifications",
                new=AsyncMock(),
            ) as dispatch_mock,
            patch(
                "interfaces.telegram.renderers.build_refresh_summary_message",
                return_value=summary_result,
            ),
        ):
            await refresh_tracks_command(update, context)

        task = application.bot_data.get(MANUAL_REFRESH_TASK_KEY)
        self.assertIsInstance(task, asyncio.Task)
        await task
        tracking_service.finish_refresh.assert_awaited_once_with("manual")
        bot.send_message.assert_awaited_once_with(
            chat_id=999,
            text="❌ Ocurrió un error refrescando los tracks. Revisá logs.",
        )

    async def test_refresh_tracks_sends_summary_message_string_not_command_result(self) -> None:
        tracking_service = SimpleNamespace(
            try_start_refresh=AsyncMock(return_value=True),
            finish_refresh=AsyncMock(),
            refresh_chat_tracks=AsyncMock(return_value=_refresh_summary()),
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"tracking_service": tracking_service})
        context = SimpleNamespace(application=application, bot=bot)
        update = SimpleNamespace(
            message=message,
            effective_chat=SimpleNamespace(id=321),
        )

        seen_texts: list[str] = []

        def _capture_split_text(text: str, max_len: int = 3900) -> list[str]:
            self.assertIsInstance(text, str)
            seen_texts.append(text)
            return [text]

        with (
            patch("interfaces.telegram.handlers.tracking.get_tracking_service", return_value=tracking_service),
            patch("interfaces.telegram.handlers.common.split_telegram_message", side_effect=_capture_split_text),
            patch("adapters.storage.get_storage", return_value=SimpleNamespace()),
            patch(
                "interfaces.telegram.notifications.dispatch_tracking_notifications",
                new=AsyncMock(),
            ),
            patch(
                "interfaces.telegram.renderers.build_refresh_summary_message",
                return_value=CommandResult(
                    ok=True, message="Refresh completado.\n⏱️ Tiempo total: 42s"
                ),
            ),
        ):
            await refresh_tracks_command(update, context)
            task = application.bot_data.get(MANUAL_REFRESH_TASK_KEY)
            self.assertIsInstance(task, asyncio.Task)
            await task

        self.assertEqual(seen_texts, ["Refresh completado.\n⏱️ Tiempo total: 42s"])


if __name__ == "__main__":
    unittest.main()

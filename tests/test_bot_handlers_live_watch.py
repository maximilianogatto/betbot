from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from bot.handlers import watch_live_command, watching_command, unwatch_command
from storage.tracking_repository import LiveWatchEntry


def _live_watch_entry(entry_id: int, home: str, away: str, status: str = "watching", matched_platform: str | None = None, matched_minute: str | None = None) -> LiveWatchEntry:
    return LiveWatchEntry(
        id=entry_id,
        chat_id=123,
        home=home,
        away=away,
        league_hint="Australia",
        note="Test note",
        status=status,
        matched_platform=matched_platform,
        matched_event_id="ev-123" if status == "fired" else None,
        matched_minute=matched_minute,
        created_at="2026-06-01T00:00:00+00:00",
        fired_at="2026-06-01T00:01:00+00:00" if status == "fired" else None,
    )


class LiveWatchCommandHandlersTests(unittest.IsolatedAsyncioTestCase):
    async def test_watch_live_without_lines_replies_usage(self) -> None:
        message = SimpleNamespace(text="/watch_live", reply_text=AsyncMock())
        context = SimpleNamespace(args=[], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        await watch_live_command(update, context)

        message.reply_text.assert_awaited_once()
        self.assertIn("Pegá tu fixture", message.reply_text.await_args.args[0])

    async def test_watch_live_adds_fixtures(self) -> None:
        added_entries = [
            _live_watch_entry(1, "Banyule", "Bundoora"),
            _live_watch_entry(2, "Subiaco", "UWA"),
        ]
        live_watch_service = SimpleNamespace(
            add_fixture_lines=Mock(return_value=added_entries)
        )
        message = SimpleNamespace(
            text="/watch_live\nAustralia | Banyule - Bundoora\nSubiaco vs UWA\nInvalidLineNoSeparator",
            reply_text=AsyncMock(),
        )
        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, bot=bot, args=[], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with patch("bot.handlers.get_live_watch_service", return_value=live_watch_service):
            await watch_live_command(update, context)

        message.reply_text.assert_awaited_once()
        reply_content = message.reply_text.await_args.args[0]
        self.assertIn("Vigilando 2 partido(s)", reply_content)
        self.assertIn("#1 · Banyule vs Bundoora", reply_content)
        self.assertIn("#2 · Subiaco vs UWA", reply_content)
        self.assertIn("1 renglón(es) no los pude interpretar", reply_content)

    async def test_watching_when_empty_replies_message(self) -> None:
        live_watch_service = SimpleNamespace(
            list_watches=Mock(return_value=[])
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, bot=bot, args=[], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with patch("bot.handlers.get_live_watch_service", return_value=live_watch_service):
            await watching_command(update, context)

        message.reply_text.assert_awaited_once()
        self.assertIn("No tenés partidos en vigilancia", message.reply_text.await_args.args[0])

    async def test_watching_lists_active_and_fired(self) -> None:
        watching_entries = [_live_watch_entry(1, "Banyule", "Bundoora", "watching")]
        fired_entries = [_live_watch_entry(2, "Subiaco", "UWA", "fired", matched_platform="betovo_http", matched_minute="45'")]
        
        def list_watches_mock(chat_id, status):
            if status == "watching":
                return watching_entries
            return fired_entries

        live_watch_service = SimpleNamespace(
            list_watches=Mock(side_effect=list_watches_mock)
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, bot=bot, args=[], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with patch("bot.handlers.get_live_watch_service", return_value=live_watch_service):
            await watching_command(update, context)

        message.reply_text.assert_awaited_once()
        reply_content = message.reply_text.await_args.args[0]
        self.assertIn("En vigilancia (1)", reply_content)
        self.assertIn("#1 · Banyule vs Bundoora", reply_content)
        self.assertIn("Ya salieron en vivo (1)", reply_content)
        self.assertIn("#2 · Subiaco vs UWA → betovo 45'", reply_content)

    async def test_unwatch_all(self) -> None:
        live_watch_service = SimpleNamespace(
            clear_watches=Mock(return_value=5)
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, bot=bot, args=["all"], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with patch("bot.handlers.get_live_watch_service", return_value=live_watch_service):
            await unwatch_command(update, context)

        message.reply_text.assert_awaited_once()
        self.assertIn("Borré 5 partido(s)", message.reply_text.await_args.args[0])

    async def test_unwatch_invalid_arg_replies_usage(self) -> None:
        live_watch_service = SimpleNamespace()
        message = SimpleNamespace(reply_text=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, bot=bot, args=["invalid"], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with patch("bot.handlers.get_live_watch_service", return_value=live_watch_service):
            await unwatch_command(update, context)

        message.reply_text.assert_awaited_once()
        self.assertIn("Usá /unwatch <id>", message.reply_text.await_args.args[0])

    async def test_unwatch_by_id_success(self) -> None:
        live_watch_service = SimpleNamespace(
            remove_watch=Mock(return_value=True)
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, bot=bot, args=["42"], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with patch("bot.handlers.get_live_watch_service", return_value=live_watch_service):
            await unwatch_command(update, context)

        message.reply_text.assert_awaited_once_with("🗑️ Borrado.")

    async def test_unwatch_by_id_not_found(self) -> None:
        live_watch_service = SimpleNamespace(
            remove_watch=Mock(return_value=False)
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, bot=bot, args=["42"], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with patch("bot.handlers.get_live_watch_service", return_value=live_watch_service):
            await unwatch_command(update, context)

        message.reply_text.assert_awaited_once_with("No encontré ese id en tu vigilancia.")


if __name__ == "__main__":
    unittest.main()

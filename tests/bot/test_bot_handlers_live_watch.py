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
        message = SimpleNamespace(text="/watch_live", photo=None, reply_to_message=None, reply_text=AsyncMock())
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
            photo=None,
            reply_to_message=None,
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
        self.assertIn("*#1* · `Banyule` vs `Bundoora`", reply_content)
        self.assertIn("*#2* · `Subiaco` vs `UWA`", reply_content)
        self.assertIn("Se omitieron 1 renglones no legibles", reply_content)

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
        self.assertIn("En vigilancia", reply_content)
        self.assertIn("*#1* · 🕒 `Pendiente` (Australia)\n     ⚽ `Banyule` vs `Bundoora`", reply_content)
        self.assertIn("Ya salieron en vivo", reply_content)
        self.assertIn("*#2* · ⚽ `Subiaco` vs `UWA`\n     🏦 → betovo 45'", reply_content)

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

    async def test_watch_live_with_photo_command(self) -> None:
        # Mock photo size
        mock_photo_size = SimpleNamespace(
            file_id="photo-123",
            get_file=AsyncMock(
                return_value=SimpleNamespace(
                    download_as_bytearray=AsyncMock(return_value=bytearray(b"dummy"))
                )
            )
        )

        # Mock ocr.space response
        ocr_response = {
            "IsErroredOnProcessing": False,
            "ParsedResults": [
                {
                    "ParsedText": "200\tAustralia Occidental (F)\tMurdoch - East Perth\tVisitantes +4/5\t"
                }
            ]
        }

        # Mock httpx AsyncClient
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = SimpleNamespace(
            status_code=200, json=lambda: ocr_response
        )

        added_entries = [_live_watch_entry(1, "Murdoch", "East Perth")]
        live_watch_service = SimpleNamespace(
            add_fixture_lines=Mock(return_value=added_entries)
        )

        message = SimpleNamespace(
            photo=[mock_photo_size],
            reply_to_message=None,
            reply_text=AsyncMock(return_value=SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())),
            delete=AsyncMock(),
        )

        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, bot=bot, args=[], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with (
            patch("bot.handlers.get_live_watch_service", return_value=live_watch_service),
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("bot.handlers._reply_text_chunks", new_callable=AsyncMock) as mock_reply_chunks
        ):
            await watch_live_command(update, context)

        mock_reply_chunks.assert_awaited_once()
        self.assertIn("`Murdoch` vs `East Perth`", mock_reply_chunks.await_args[0][1])

    async def test_photo_guidance_handler(self) -> None:
        from bot.handlers import photo_guidance_handler
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(message=message)
        context = SimpleNamespace()

        await photo_guidance_handler(update, context)

        message.reply_text.assert_awaited_once()
        self.assertIn("Recibí tu imagen", message.reply_text.await_args.args[0])

    async def test_watch_live_reply_to_photo_command(self) -> None:
        # Mock photo size
        mock_photo_size = SimpleNamespace(
            file_id="photo-456",
            get_file=AsyncMock(
                return_value=SimpleNamespace(
                    download_as_bytearray=AsyncMock(return_value=bytearray(b"dummy2"))
                )
            )
        )

        # Mock ocr.space response
        ocr_response = {
            "IsErroredOnProcessing": False,
            "ParsedResults": [
                {
                    "ParsedText": "200\tAustralia Victorian (F)\tBanyule - Bundoora\tVisitantes +3/4\t"
                }
            ]
        }

        # Mock httpx AsyncClient
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = SimpleNamespace(
            status_code=200, json=lambda: ocr_response
        )

        added_entries = [_live_watch_entry(1, "Banyule", "Bundoora")]
        live_watch_service = SimpleNamespace(
            add_fixture_lines=Mock(return_value=added_entries)
        )

        replied_message = SimpleNamespace(
            photo=[mock_photo_size],
        )

        message = SimpleNamespace(
            photo=None,
            reply_to_message=replied_message,
            reply_text=AsyncMock(return_value=SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())),
            delete=AsyncMock(),
        )

        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, bot=bot, args=[], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with (
            patch("bot.handlers.get_live_watch_service", return_value=live_watch_service),
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("bot.handlers._reply_text_chunks", new_callable=AsyncMock) as mock_reply_chunks
        ):
            await watch_live_command(update, context)

        mock_reply_chunks.assert_awaited_once()
        self.assertIn("`Banyule` vs `Bundoora`", mock_reply_chunks.await_args[0][1])

    async def test_watching_command_displays_chat_local_id_and_arg_kickoff_time(self) -> None:
        entry = LiveWatchEntry(
            id=123,
            chat_id=123,
            home="Banyule",
            away="Bundoora",
            league_hint="Australia",
            note="Test note",
            status="watching",
            matched_platform=None,
            matched_event_id=None,
            matched_minute=None,
            created_at="2026-06-01T00:00:00+00:00",
            fired_at=None,
            kickoff_at="2026-06-02T14:00:00+00:00",
            chat_local_id=5,
        )
        live_watch_service = SimpleNamespace(
            list_watches=Mock(side_effect=lambda chat_id, status: [entry] if status == "watching" else [])
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, bot=bot, args=[], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with (
            patch("bot.handlers.get_live_watch_service", return_value=live_watch_service),
            patch("bot.handlers._reply_text_chunks", new_callable=AsyncMock) as mock_reply_chunks
        ):
            await watching_command(update, context)

        mock_reply_chunks.assert_awaited_once()
        reply_content = mock_reply_chunks.await_args[0][1]
        self.assertIn("*#5*", reply_content)
        self.assertIn("`11:00`", reply_content)
        self.assertIn("`Banyule` vs `Bundoora`", reply_content)


    async def test_unwatch_command_deletes_by_local_id_and_falls_back(self) -> None:
        live_watch_service = SimpleNamespace(
            remove_watch_by_local_id=Mock(return_value=True),
            remove_watch=Mock(return_value=False)
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, bot=bot, args=["5"], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with patch("bot.handlers.get_live_watch_service", return_value=live_watch_service):
            await unwatch_command(update, context)

        live_watch_service.remove_watch_by_local_id.assert_called_once_with(123, 5)
        live_watch_service.remove_watch.assert_not_called()
        message.reply_text.assert_awaited_once_with("🗑️ Borrado.")

        live_watch_service_fallback = SimpleNamespace(
            remove_watch_by_local_id=Mock(return_value=False),
            remove_watch=Mock(return_value=True)
        )
        message_fallback = SimpleNamespace(reply_text=AsyncMock())
        context_fallback = SimpleNamespace(application=application, bot=bot, args=["999"], user_data={})
        update_fallback = SimpleNamespace(message=message_fallback, effective_chat=SimpleNamespace(id=123))

        with patch("bot.handlers.get_live_watch_service", return_value=live_watch_service_fallback):
            await unwatch_command(update_fallback, context_fallback)

        live_watch_service_fallback.remove_watch_by_local_id.assert_called_once_with(123, 999)
        live_watch_service_fallback.remove_watch.assert_called_once_with(123, 999)
        message_fallback.reply_text.assert_awaited_once_with("🗑️ Borrado.")

    async def test_watch_live_with_photo_command_extracts_time(self) -> None:
        mock_photo_size = SimpleNamespace(
            file_id="photo-time",
            get_file=AsyncMock(
                return_value=SimpleNamespace(
                    download_as_bytearray=AsyncMock(return_value=bytearray(b"dummy"))
                )
            )
        )

        ocr_response = {
            "IsErroredOnProcessing": False,
            "ParsedResults": [
                {
                    "ParsedText": "11:00\tEstonia U19\tLegion - Tallinn\t"
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = SimpleNamespace(
            status_code=200, json=lambda: ocr_response
        )

        live_watch_service = SimpleNamespace(
            add_fixture_lines=Mock(return_value=[])
        )

        message = SimpleNamespace(
            photo=[mock_photo_size],
            reply_to_message=None,
            reply_text=AsyncMock(return_value=SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())),
            delete=AsyncMock(),
        )

        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, bot=bot, args=[], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with (
            patch("bot.handlers.get_live_watch_service", return_value=live_watch_service),
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("bot.handlers._reply_text_chunks", new_callable=AsyncMock)
        ):
            await watch_live_command(update, context)

        live_watch_service.add_fixture_lines.assert_called_once_with(
            123, ["11:00 Estonia U19 | Legion - Tallinn"]
        )



if __name__ == "__main__":
    unittest.main()

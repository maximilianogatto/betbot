from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from interfaces.telegram.handlers import watch_live_command, watching_command, unwatch_command, import_sheet_command, view_match_command
from core.models import LiveWatchEntry


def _live_watch_entry(entry_id: int, home: str, away: str, status: str = "watching", matched_platform: str | None = None, matched_minute: str | None = None, chat_local_id: int | None = None, live_state_json: str | None = None) -> LiveWatchEntry:
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
        fired_platforms=matched_platform,
        chat_local_id=chat_local_id,
        live_state_json=live_state_json,
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

        with patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service):
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

        with patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service):
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

        with patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service):
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

        with patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service):
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

        with patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service):
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

        with patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service):
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

        with patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service):
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
            patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service),
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("interfaces.telegram.handlers.live_watch._reply_text_chunks", new_callable=AsyncMock) as mock_reply_chunks
        ):
            await watch_live_command(update, context)

        mock_reply_chunks.assert_awaited_once()
        self.assertIn("`Murdoch` vs `East Perth`", mock_reply_chunks.await_args[0][1])

    async def test_photo_guidance_handler(self) -> None:
        from interfaces.telegram.handlers import photo_guidance_handler
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
            patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service),
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("interfaces.telegram.handlers.live_watch._reply_text_chunks", new_callable=AsyncMock) as mock_reply_chunks
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
            patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service),
            patch("interfaces.telegram.handlers.live_watch._reply_text_chunks", new_callable=AsyncMock) as mock_reply_chunks
        ):
            await watching_command(update, context)

        mock_reply_chunks.assert_awaited_once()
        reply_content = mock_reply_chunks.await_args[0][1]
        self.assertIn("*#5*", reply_content)
        # Kickoff is not today, so the local time is shown with its date.
        self.assertIn("`02/06 11:00`", reply_content)
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

        with patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service):
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

        with patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service_fallback):
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
            patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service),
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("interfaces.telegram.handlers.live_watch._reply_text_chunks", new_callable=AsyncMock)
        ):
            await watch_live_command(update, context)

        live_watch_service.add_fixture_lines.assert_called_once_with(
            123, ["11:00 Estonia U19 | Legion - Tallinn"]
        )

    async def test_import_sheet_success(self) -> None:
        csv_content = (
            "Horario,Competición,Partido,Detalle\n"
            "15:00,Australia Victoria NPL 1,Banyule vs Bundoora,Visitantes +5/6\n"
            "18:00,USA USL League Two,Texoma vs Fort Worth,Locales +4t5\n"
        )
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = SimpleNamespace(
            status_code=200, text=csv_content
        )

        added_entries = [
            _live_watch_entry(1, "Banyule", "Bundoora", chat_local_id=1),
            _live_watch_entry(2, "Texoma", "Fort Worth", chat_local_id=2),
        ]

        live_watch_service = SimpleNamespace(
            add_fixture_lines=Mock(return_value=added_entries)
        )

        loading_msg = SimpleNamespace(
            edit_text=AsyncMock(),
            delete=AsyncMock()
        )
        message = SimpleNamespace(
            reply_text=AsyncMock(return_value=loading_msg),
        )

        bot = SimpleNamespace(send_message=AsyncMock())
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, bot=bot, args=[], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with (
            patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service),
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("interfaces.telegram.handlers.live_watch._reply_text_chunks", new_callable=AsyncMock) as mock_reply_chunks
        ):
            await import_sheet_command(update, context)

        mock_client.get.assert_called_once()
        from services.live_watch import sheet_timezone

        live_watch_service.add_fixture_lines.assert_called_once_with(
            123,
            [
                "15:00 Australia Victoria NPL 1 | Banyule vs Bundoora (Visitantes +5/6)",
                "18:00 USA USL League Two | Texoma vs Fort Worth (Locales +4t5)",
            ],
            times_tz=sheet_timezone(),
            skip_recently_removed=True,
        )
        mock_reply_chunks.assert_awaited_once()
        reply_content = mock_reply_chunks.await_args[0][1]
        self.assertIn("Importación completada con éxito", reply_content)
        self.assertIn("Banyule", reply_content)
        self.assertIn("Texoma", reply_content)
        loading_msg.delete.assert_awaited_once()

    async def test_import_sheet_invalid_headers(self) -> None:
        csv_content = (
            "Wrong,Headers,Here\n"
            "1,2,3\n"
        )
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = SimpleNamespace(
            status_code=200, text=csv_content
        )

        live_watch_service = SimpleNamespace()
        loading_msg = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
        message = SimpleNamespace(reply_text=AsyncMock(return_value=loading_msg))
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, args=[], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            await import_sheet_command(update, context)

        loading_msg.edit_text.assert_awaited_once()
        self.assertIn("columnas", loading_msg.edit_text.await_args[0][0].lower())

    async def test_import_sheet_no_added(self) -> None:
        csv_content = (
            "Horario,Competición,Partido,Detalle\n"
            "15:00,Australia Victoria NPL 1,Banyule vs Bundoora,Visitantes +5/6\n"
        )
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = SimpleNamespace(
            status_code=200, text=csv_content
        )

        live_watch_service = SimpleNamespace(
            add_fixture_lines=Mock(return_value=[])
        )
        loading_msg = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
        message = SimpleNamespace(reply_text=AsyncMock(return_value=loading_msg))
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, args=[], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with (
            patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            await import_sheet_command(update, context)

        loading_msg.edit_text.assert_awaited_once()
        self.assertIn("todos fueron omitidos", loading_msg.edit_text.await_args[0][0])

    async def test_import_sheet_http_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = SimpleNamespace(
            status_code=500
        )

        loading_msg = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
        message = SimpleNamespace(reply_text=AsyncMock(return_value=loading_msg))
        context = SimpleNamespace(args=[], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            await import_sheet_command(update, context)

        loading_msg.edit_text.assert_awaited_once()
        self.assertIn("Error al descargar planilla (HTTP 500)", loading_msg.edit_text.await_args[0][0])

    async def test_live_stats_without_args_lists_the_live_matches(self) -> None:
        import json

        live = _live_watch_entry(7, "Banyule", "Bundoora", "fired", live_state_json=json.dumps(
            {"betovo_http": {"event_id": "1", "home_score": 1, "away_score": 0, "minute": "35'"}}))
        other = _live_watch_entry(8, "Altona", "Brunswick", "fired", live_state_json=json.dumps(
            {"betovo_http": {"event_id": "2", "home_score": 0, "away_score": 0, "minute": "10'"}}))
        service = SimpleNamespace(list_watches=Mock(side_effect=lambda chat, status: [live, other]
                                                    if status == "fired" else []))
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(application=SimpleNamespace(bot_data={}), args=[], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=service):
            await view_match_command(update, context)

        keyboard = message.reply_text.await_args.kwargs["reply_markup"].inline_keyboard
        self.assertEqual([row[0].callback_data for row in keyboard], ["lstats:7", "lstats:8"])
        self.assertEqual(keyboard[0][0].text, "Banyule 1-0 Bundoora · 35'")

        service.list_watches = Mock(return_value=[])
        message.reply_text.reset_mock()
        with patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=service):
            await view_match_command(update, context)
        self.assertIn("No hay partidos en vivo", message.reply_text.await_args.args[0])

    async def test_live_stats_not_found(self) -> None:
        live_watch_service = SimpleNamespace(
            list_watches=Mock(return_value=[]),
            repository=SimpleNamespace(
                get_live_watch_by_local_id=Mock(return_value=None),
                get_live_watch=Mock(return_value=None),
            )
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        for args in (["5"], ["abc"]):  # por id o por equipo
            message.reply_text.reset_mock()
            context = SimpleNamespace(application=application, args=args, user_data={})
            with patch("interfaces.telegram.handlers.live_watch.get_live_watch_service",
                       return_value=live_watch_service):
                await view_match_command(update, context)
            self.assertIn("No encontré ese partido", message.reply_text.await_args.args[0])

    async def test_live_stats_shows_the_panel_with_the_books_odds(self) -> None:
        import json

        from core.live_stats import LiveStatRow, LiveStatsView

        entry = _live_watch_entry(1, "Banyule", "Bundoora", "fired", live_state_json=json.dumps(
            {"1xbet_http": {"event_id": "ev", "odds": {"home": 1.5, "draw": 3.4, "away": 5.5}}}))
        view = LiveStatsView(home="Banyule", away="Bundoora", home_score=1, away_score=0, period="2T",
                             minute="60'", sources=("1xbet",),
                             rows=(LiveStatRow("possession", "Posesión", "%", 60, 40, "1xbet"),))
        service = SimpleNamespace(repository=SimpleNamespace(get_live_watch_by_local_id=Mock(return_value=entry)))
        loading = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
        message = SimpleNamespace(reply_text=AsyncMock(return_value=loading))
        stats = SimpleNamespace(for_entry=AsyncMock(return_value=view))
        context = SimpleNamespace(application=SimpleNamespace(bot_data={"live_stats_service": stats}),
                                  args=["#1"], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=service):
            await view_match_command(update, context)

        text = loading.edit_text.await_args.args[0]
        self.assertIn("<b>Banyule 1-0 Bundoora</b>", text)
        self.assertIn(" 60%  Posesión           40%", text)
        self.assertIn("💰 1xbet: 1=1.50 | X=3.40 | 2=5.50", text)
        [[button]] = loading.edit_text.await_args.kwargs["reply_markup"].inline_keyboard
        self.assertEqual(button.callback_data, "lstatsr:1")

    async def test_live_stats_without_a_stats_source_shows_what_the_books_saw(self) -> None:
        live_state_val = {
            "bet365": {
                "home": "Banyule", "away": "Bundoora", "minute": "45'", "home_score": 1, "away_score": 0,
                "home_red_cards": 0, "away_red_cards": 0, "home_yellow_cards": 1, "away_yellow_cards": 2,
                "live_stats": {"possession_home": 60, "possession_away": 40},
                "odds": {"home": 1.50, "draw": 3.40, "away": 5.50},
            }
        }
        import json
        entry = _live_watch_entry(1, "Banyule", "Bundoora", "watching", live_state_json=json.dumps(live_state_val))

        live_watch_service = SimpleNamespace(
            repository=SimpleNamespace(get_live_watch_by_local_id=Mock(return_value=entry)))
        loading_msg = SimpleNamespace(delete=AsyncMock())
        message = SimpleNamespace(reply_text=AsyncMock(return_value=loading_msg))
        application = SimpleNamespace(bot_data={"live_watch_service": live_watch_service})
        context = SimpleNamespace(application=application, args=["1"], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with (
            patch("interfaces.telegram.handlers.live_watch.get_live_watch_service", return_value=live_watch_service),
            patch("interfaces.telegram.handlers.live_watch._reply_text_chunks", new_callable=AsyncMock) as mock_reply_chunks,
        ):
            await view_match_command(update, context)

        loading_msg.delete.assert_awaited_once()
        content = mock_reply_chunks.await_args[0][1]
        self.assertIn("🔴 *EN VIVO (BET365)*", content)
        self.assertIn("⏱️ Estado: 45'  |  Marcador: *1-0*", content)
        self.assertIn("• Posesión: 60% vs 40%", content)
        self.assertIn("💰 *Odds (1X2):* 1=1.50 | X=3.40 | 2=5.50", content)
        self.assertIn("Ni 1xBet ni Statshub", content)

if __name__ == "__main__":
    unittest.main()

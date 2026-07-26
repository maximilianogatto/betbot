"""El aviso en vivo viaja service -> EventBus -> TelegramEventListener -> chat.

Antes el job de live-watch mandaba los mensajes él mismo. Ahora `poll_once()`
publica y el listener envía, así que estos tests cubren el tramo que dejó de
estar en `bot/jobs/tasks.py`.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from core.event_bus import EventBus, event_bus
from core.events import MatchLiveEvent
from core.models import LiveEventSnapshot, LiveWatchEntry, LiveWatchHit
from interfaces.telegram.listeners import TelegramEventListener
from services.live_watch import LiveWatchService


def _hit(chat_id: int = 42, *, phase: str = "goal", message: str | None = "⚽ GOL") -> LiveWatchHit:
    entry = LiveWatchEntry(
        id=1, chat_id=chat_id, home="Banyule", away="Bundoora", league_hint=None,
        note=None, status="watching", matched_platform=None, matched_event_id=None,
        matched_minute=None, created_at="...", fired_at=None,
    )
    return LiveWatchHit(entry=entry, phase=phase, custom_message=message)


class TelegramEventListenerTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_the_rendered_alert_to_the_watching_chat(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock())

        await TelegramEventListener(bot).handle(MatchLiveEvent(hit=_hit(chat_id=42)))

        bot.send_message.assert_awaited_once_with(chat_id=42, text="⚽ GOL")

    async def test_empty_render_is_not_sent(self) -> None:
        """Telegram rechaza los textos vacíos: no hay que intentar mandarlos."""

        bot = SimpleNamespace(send_message=AsyncMock())

        await TelegramEventListener(bot).handle(MatchLiveEvent(hit=_hit(message="")))

        bot.send_message.assert_not_awaited()


class ListenerRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_registered_listener_receives_published_hits(self) -> None:
        """register() + publish() es el camino que corre en producción."""

        bot = SimpleNamespace(send_message=AsyncMock())
        bus = EventBus()
        TelegramEventListener(bot).register(bus)

        result = await bus.publish(MatchLiveEvent(hit=_hit(chat_id=7)))

        self.assertEqual((result.delivered, result.failed), (1, 0))
        bot.send_message.assert_awaited_once_with(chat_id=7, text="⚽ GOL")

    async def test_a_failing_send_is_reported_not_swallowed(self) -> None:
        """Si Telegram rechaza el envío, el bus lo cuenta como entrega fallida."""

        bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("telegram caído")))
        bus = EventBus()
        TelegramEventListener(bot).register(bus)

        with self.assertLogs("core.event_bus", level="ERROR"):
            result = await bus.publish(MatchLiveEvent(hit=_hit()))

        self.assertEqual((result.delivered, result.failed), (0, 1))


class LiveWatchEndToEndTests(unittest.IsolatedAsyncioTestCase):
    """poll_once() publica en el bus GLOBAL, que es donde se registra el listener.

    Es la costura que importa: el service publica en `core.event_bus.event_bus` y
    `bot/application.py` suscribe ahí. Si fueran instancias distintas, el bot
    quedaría mudo sin que ningún test unitario lo notara.
    """

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp_dir.name) / "listener.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.repository = SqliteStorage()

    def tearDown(self) -> None:
        if self._prev_db is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db
        self.tmp_dir.cleanup()

    async def test_a_live_match_reaches_telegram_through_the_global_bus(self) -> None:
        service = LiveWatchService(repository=self.repository)
        chat_id = 888
        service.add_fixture_lines(chat_id, ["Australia Victorian | Banyule - Bundoora"])

        service.extractor_registry = SimpleNamespace(
            list_registered=lambda: [
                SimpleNamespace(
                    name="betovo",
                    display_name="Betovo",
                    supports_live_detection=True,
                    list_live_events=AsyncMock(
                        return_value=[
                            LiveEventSnapshot(
                                platform="betovo",
                                external_event_id="ev-99",
                                is_soccer=True,
                                home="Banyule City",
                                away="Bundoora FC",
                                country_name="Australia",
                                competition_name="Victorian State League",
                                minute="5'",
                                home_score=1,
                                away_score=0,
                            )
                        ]
                    ),
                )
            ]
        )

        bot = SimpleNamespace(send_message=AsyncMock())
        listener = TelegramEventListener(bot)
        listener.register(event_bus)
        try:
            hits = await service.poll_once()
        finally:
            event_bus.unsubscribe(MatchLiveEvent, listener.handle)

        self.assertEqual(len(hits), 1)
        bot.send_message.assert_awaited_once()
        sent = bot.send_message.await_args.kwargs
        self.assertEqual(sent["chat_id"], chat_id)
        self.assertIn("EN VIVO", sent["text"])
        self.assertIn("Banyule City", sent["text"])


if __name__ == "__main__":
    unittest.main()

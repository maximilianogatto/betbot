"""Listener de Telegram: convierte eventos de dominio en mensajes enviados.

Implementa el puerto `EventListener` de core y se suscribe al bus en el
arranque (`bot/application.py`). Los services publican sin saber que Telegram
existe; acá es donde el aviso se vuelve un mensaje.

Si el envío falla, la excepción se propaga a propósito: el bus la cuenta como
entrega fallida, y así el publicador NO marca el aviso como enviado y el
próximo ciclo lo reintenta. Tragarla acá rompería esa garantía.
"""
from __future__ import annotations

from contextlib import contextmanager
import logging

from telegram import Bot
from telegram.constants import ParseMode

from core.event_bus import EventBus
from core.events import (
    MatchLiveEvent,
    MatchRemindersEvent,
    NewMatchesEvent,
    OddsChangedEvent,
)
from core.listener import EventListener
from core.timezones import set_display_timezone
from interfaces.telegram.renderers import (
    build_grouped_new_event_alert_message,
    build_grouped_odds_change_alert_message,
    build_match_reminder_alert_message,
    build_new_event_alert_message,
    build_odds_change_alert_message,
    split_telegram_message,
)
from services.live_watch import render_live_hit
from services.timezones import resolve_chat_timezone

logger = logging.getLogger(__name__)


@contextmanager
def _display_timezone_of(chat_id: int):
    """Renderiza en la zona horaria del chat y la limpia al salir.

    Se limpia siempre para que la zona del último destinatario no se filtre al
    siguiente trabajo que corra en esta misma task.
    """

    set_display_timezone(resolve_chat_timezone(chat_id))
    try:
        yield
    finally:
        set_display_timezone(None)


class TelegramEventListener(EventListener):
    """Envía a Telegram los eventos de dominio publicados en el bus."""

    HANDLED_EVENTS = (
        MatchLiveEvent,
        NewMatchesEvent,
        OddsChangedEvent,
        MatchRemindersEvent,
    )

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    def register(self, bus: EventBus) -> None:
        """Suscribe este listener a los eventos que sabe manejar."""

        for event_type in self.HANDLED_EVENTS:
            bus.subscribe(event_type, self.handle)

    async def handle(self, event: object) -> None:
        """Redacta el evento y lo manda al chat correspondiente."""

        if isinstance(event, MatchLiveEvent):
            await self._handle_live(event)
        elif isinstance(event, NewMatchesEvent):
            await self._handle_new_matches(event)
        elif isinstance(event, OddsChangedEvent):
            await self._handle_odds_changed(event)
        elif isinstance(event, MatchRemindersEvent):
            await self._handle_reminders(event)
        else:
            logger.warning(
                "TelegramEventListener recibió un evento que no maneja: %s",
                type(event).__name__,
            )

    async def _handle_live(self, event: MatchLiveEvent) -> None:
        text = render_live_hit(event.hit)
        if not text:
            # Una fase sin mensaje propio no se manda: Telegram rechaza los vacíos.
            return
        await self._bot.send_message(chat_id=event.chat_id, text=text)

    async def _handle_new_matches(self, event: NewMatchesEvent) -> None:
        with _display_timezone_of(event.chat_id):
            text = (
                build_new_event_alert_message(event.tracked_league, event.matches[0])
                if len(event.matches) == 1
                else build_grouped_new_event_alert_message(
                    event.tracked_league, list(event.matches)
                )
            )
        await self._send_split(event.chat_id, text)

    async def _handle_odds_changed(self, event: OddsChangedEvent) -> None:
        with _display_timezone_of(event.chat_id):
            text = (
                build_odds_change_alert_message(event.tracked_league, event.alerts[0])
                if len(event.alerts) == 1
                else build_grouped_odds_change_alert_message(
                    event.tracked_league, list(event.alerts)
                )
            )
        await self._send_split(event.chat_id, text)

    async def _handle_reminders(self, event: MatchRemindersEvent) -> None:
        with _display_timezone_of(event.chat_id):
            texts = [
                build_match_reminder_alert_message(event.tracked_league, match)
                for match in event.matches
            ]
        for text in texts:
            await self._send_split(event.chat_id, text)

    async def _send_split(self, chat_id: int, text: str) -> None:
        for chunk in split_telegram_message(text):
            await self._bot.send_message(
                chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML
            )

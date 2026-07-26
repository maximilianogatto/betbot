"""Listener de Telegram: convierte eventos de dominio en mensajes enviados.

Implementa el puerto `EventListener` de core y se suscribe al bus en el
arranque (`bot/application.py`). Los services publican sin saber que Telegram
existe; acá es donde el aviso se vuelve un mensaje.
"""
from __future__ import annotations

import logging

from telegram import Bot

from core.event_bus import EventBus
from core.events import MatchLiveEvent
from core.listener import EventListener
from services.live_watch import render_live_hit

logger = logging.getLogger(__name__)


class TelegramEventListener(EventListener):
    """Envía a Telegram los eventos de dominio publicados en el bus."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    def register(self, bus: EventBus) -> None:
        """Suscribe este listener a los eventos que sabe manejar."""

        bus.subscribe(MatchLiveEvent, self.handle)

    async def handle(self, event: MatchLiveEvent) -> None:
        """Renderiza el evento y lo manda al chat que lo estaba esperando."""

        if not isinstance(event, MatchLiveEvent):
            logger.warning("TelegramEventListener recibió un evento que no maneja: %s", type(event).__name__)
            return

        text = render_live_hit(event.hit)
        if not text:
            # Una fase sin mensaje propio (custom_message vacío) no se manda:
            # Telegram rechaza los textos vacíos.
            return

        await self._bot.send_message(chat_id=event.chat_id, text=text)

"""Helpers compartidos entre los módulos de handlers.

Viven acá para que los módulos por dominio (special_leagues, stats, tracking...)
no tengan que importarse entre sí ni de `commands.py` — eso generaría ciclos de
importación. Es el punto de apoyo del corte incremental de E5.
"""
from __future__ import annotations

import logging

from interfaces.telegram.renderers import split_telegram_message

logger = logging.getLogger(__name__)


async def reply_text_chunks(
    message,
    text: str,
    *,
    parse_mode: str | None = None,
    reply_markup=None,
) -> None:
    """Responde en varios mensajes de Telegram cuando el texto es muy largo."""

    chunks = split_telegram_message(text)
    for index, chunk in enumerate(chunks):
        await message.reply_text(
            chunk,
            parse_mode=parse_mode,
            reply_markup=reply_markup if index == 0 else None,
        )

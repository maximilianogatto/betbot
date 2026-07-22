"""Resolución de la zona horaria de un chat contra el almacenamiento.

Vive acá y no en `core/timezones.py` porque necesita leer la preferencia
guardada: `core` no puede depender de `adapters`. En core quedan las utilidades
puras (parseo, formato, el ContextVar de la TZ activa).
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from core.timezones import default_timezone, get_zoneinfo


def resolve_chat_timezone(chat_id: int | None) -> ZoneInfo:
    """Devuelve la TZ guardada del chat, con fallback al default."""

    if chat_id is None:
        return default_timezone()
    try:
        from adapters.storage import get_storage

        name = get_storage().get_chat_timezone(chat_id)
    except Exception:
        # Sin storage disponible (tests, arranque temprano) se usa el default.
        name = None
    return get_zoneinfo(name) or default_timezone()

"""Handlers de Telegram (capa de interfaz).

`register_handlers(application)` registra todos los comandos, conversations y
callbacks. La implementación vive por ahora en `commands.py` (viene de
`bot/handlers.py`, 6000 líneas) y se va partiendo por dominio de forma incremental.
"""
from __future__ import annotations

from interfaces.telegram.handlers.commands import *  # noqa: F401,F403
from interfaces.telegram.handlers.commands import (  # noqa: F401  privados usados por tests
    _SWE_LEAGUES,
    _convert_fin_to_arg_datetime,
    _convert_swe_to_arg_datetime,
    _extract_statshub_tournament_id,
    _resolve_swe_league,
)

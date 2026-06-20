#!/usr/bin/env python3
"""Genera el token de Sportradar/Statshub en tu PC e imprime la línea para Telegram.

Akamai bloquea el navegador headless, así que el token se mintea en una PC con
navegador (headed) y se pasa al bot por `/sportradar_token <token>`.

Uso (en tu PC, dentro del repo):
    python scripts/sportradar_token.py

Copiá la línea del TOKEN que imprime y, en Telegram, mandá:
    /sportradar_token <token>
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stats_providers.sportradar_http.engine.session_manager import (  # noqa: E402
    DEFAULT_BOOTSTRAP_URLS,
    BootstrapConfig,
    bootstrap_sportradar_session,
)


async def _main() -> int:
    config = BootstrapConfig(
        bootstrap_urls=DEFAULT_BOOTSTRAP_URLS,
        headed=True,
        seconds_per_url=8.0,
    )
    state = await bootstrap_sportradar_session(config)
    if not state.is_usable() or state.signed_token is None:
        print(
            "\n❌ No se pudo generar un token usable.\n"
            "   Probá de nuevo; si persiste, abrí Statshub a mano en el navegador "
            "y reintentá (Akamai a veces pide interacción)."
        )
        return 1
    print("\n--- TOKEN (copiá esta línea y mandá en Telegram: /sportradar_token <token>) ---")
    print(state.signed_token.raw)
    print(f"--- expira (UTC): {state.token_expiration()} ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))

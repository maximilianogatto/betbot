"""Estadísticas en vivo de un partido de Statshub (Sportradar `match_details`).

Suma lo que las casas no muestran: faltas, offsides, atajadas, tiros libres, saques
de arco, laterales y tiros bloqueados. No trae posesión ni marcador (el marcador lo
da el estado del día, ver day_status.py).
"""

from __future__ import annotations

import asyncio
from typing import Any

from core.live_stats import LiveStatsSnapshot

SOURCE = "statshub"
#: Clave de `values` en match_details -> clave del panel.
_KEYS = {"1126": "attacks", "1029": "dangerous_attacks", "125": "shots_on_target",
         "126": "shots_off_target", "171": "shots_blocked", "124": "corners", "40": "yellow_cards",
         "50": "red_cards", "161": "penalties", "129": "fouls", "123": "offsides", "127": "saves",
         "120": "free_kicks", "121": "goal_kicks", "122": "throw_ins", "60": "substitutions"}


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_match_details(payload: dict[str, Any]) -> LiveStatsSnapshot | None:
    try:
        data = payload["doc"][0]["data"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    teams = data.get("teams") or {}
    stats: dict[str, tuple[int | None, int | None]] = {}
    for raw_key, key in _KEYS.items():
        value = ((data.get("values") or {}).get(raw_key) or {}).get("value")
        if isinstance(value, dict):
            stats[key] = (_int(value.get("home")), _int(value.get("away")))
    if not stats:
        return None
    return LiveStatsSnapshot(source=SOURCE, home=str(teams.get("home") or ""),
                             away=str(teams.get("away") or ""), stats=stats)


async def fetch_match_stats(provider: Any, match_id: str) -> LiveStatsSnapshot | None:
    """match_details con el token guardado (en el VPS no se abre Chromium)."""

    from stats_providers.sportradar_http.engine.endpoints.catalog import call_endpoint

    client = await asyncio.to_thread(provider._runtime._client)
    payload = await asyncio.to_thread(call_endpoint, client, "match_details", match_id=str(match_id))
    return parse_match_details(payload)

"""Panel de estadísticas en vivo de un partido vigilado.

Sale de los ids que el live-watch ya conoce: el evento de 1xBet (el mismo panel que
Melbet; las casas liquidan córners y tarjetas con esos números) y, si Statshub lo
cubre, lo que las casas no muestran (faltas, offsides, atajadas...). Un pedido por
fuente y por consulta, con un caché corto para que el botón de actualizar no
martille a nadie.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
import logging
import time
from typing import Any, Callable

from core.live_stats import LiveStatsSnapshot, LiveStatsView, merge_live_stats

logger = logging.getLogger(__name__)


def _event_id(live_state: dict[str, Any], platform: str) -> str | None:
    state = live_state.get(platform)
    if isinstance(state, dict) and state.get("event_id"):
        return str(state["event_id"])
    return None


def _scored_state(live_state: dict[str, Any]) -> dict[str, Any] | None:
    """El último estado con marcador que vio el watch, la fuente oficial primero."""
    states = [state for platform, state in live_state.items()
              if not str(platform).startswith("_") and isinstance(state, dict)
              and state.get("home_score") is not None and state.get("away_score") is not None]
    states.sort(key=lambda state: not state.get("official"))
    return states[0] if states else None


class LiveStatsService:
    def __init__(self, *, xbet_client: Any = None, statshub_provider: Any = None,
                 ttl_seconds: float = 15.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._xbet_client = xbet_client
        self._statshub = statshub_provider
        self._ttl = ttl_seconds
        self._clock = clock
        self._panels: dict[int, tuple[float, LiveStatsView | None]] = {}

    def _xbet(self) -> Any:
        if self._xbet_client is None:
            from extractors.xbet_http.client import XBetHttpClient

            self._xbet_client = XBetHttpClient()
        return self._xbet_client

    async def aclose(self) -> None:
        if self._xbet_client is not None:
            await self._xbet_client.aclose()

    async def for_entry(self, entry: Any) -> LiveStatsView | None:
        """El panel del partido, o None si ninguna fuente tiene estadísticas."""

        cached = self._panels.get(entry.id)
        if cached and self._clock() - cached[0] < self._ttl:
            return cached[1]
        live_state = entry.live_state or {}
        fetches = []
        xbet_id = _event_id(live_state, "1xbet_http")
        if xbet_id:
            from extractors.xbet_http.live_stats import fetch_game_stats

            fetches.append(("1xbet", fetch_game_stats(self._xbet(), xbet_id)))
        statshub_id = _event_id(live_state, "statshub")
        if statshub_id and self._statshub is not None:
            from stats_providers.sportradar_http.live_stats import fetch_match_stats

            fetches.append(("statshub", fetch_match_stats(self._statshub, statshub_id)))
        results = await asyncio.gather(*(fetch for _, fetch in fetches), return_exceptions=True)
        snapshots: list[LiveStatsSnapshot] = []
        for (source, _), result in zip(fetches, results):
            if isinstance(result, LiveStatsSnapshot):
                snapshots.append(result)
            elif isinstance(result, BaseException):
                logger.info("Stats en vivo: %s no respondió para el watch %s: %s",
                            source, entry.id, str(result)[:160])
        view = merge_live_stats(snapshots)
        if view is not None and view.home_score is None:
            # Statshub no trae marcador: el que ya vio el watch.
            scored = _scored_state(live_state)
            if scored:
                view = replace(view, home_score=scored["home_score"], away_score=scored["away_score"],
                               minute=view.minute or scored.get("minute"))
        if view is not None and not view.home:
            view = replace(view, home=entry.home, away=entry.away)
        self._panels[entry.id] = (self._clock(), view)
        return view

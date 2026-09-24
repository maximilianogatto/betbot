"""Estado de todos los partidos del día que cubre Statshub, en una sola llamada.

`unified_sport_matches/{sport}/{fecha}/0` devuelve cada partido cubierto de ese día
(~200-250) con estado ("1st half", "Halftime", "Ended"...), marcador y el
marcador de cada período (`periods.p1` = entretiempo). No está paginado: pedirle
otros cursores termina en `blocked_payload`, así que se llama poco y se cachea.

Trae partidos simulados ("SRL": equipos "Kosovo SRL"), que se descartan.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
import logging
import time
from typing import Any
from zoneinfo import ZoneInfo

from core.stats_models import MatchStatus

logger = logging.getLogger(__name__)

SOURCE = "statshub"
#: status._id de Sportradar -> fase. 6/7 = 1º/2º tiempo, 31 = entretiempo,
#: 41/42/50 = alargue y penales, 100/110/120 = terminado (normal/alargue/penales),
#: 60/70/90 = postergado/cancelado/abandonado, 80 = interrumpido.
_PHASES = {0: "scheduled", 6: "live", 7: "live", 31: "halftime", 41: "live", 42: "live",
           50: "live", 80: "live", 100: "ended", 110: "ended", 120: "ended",
           60: "cancelled", 70: "cancelled", 90: "cancelled"}
_LABELS = {6: "1T en juego", 7: "2T en juego", 31: "HT", 41: "alargue", 42: "alargue",
           50: "penales", 80: "interrumpido"}


def _status(match: dict[str, Any]) -> tuple[int | None, str | None]:
    status = match.get("status")
    if isinstance(status, dict):
        return status.get("_id"), status.get("name")
    return None, status if isinstance(status, str) else None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_day(payload: dict[str, Any]) -> list[MatchStatus]:
    """Todos los partidos (no simulados) del día con su estado."""
    try:
        categories = payload["doc"][0]["data"]["sport"]["realcategories"] or []
    except (KeyError, IndexError, TypeError):
        return []
    matches: list[MatchStatus] = []
    for category in categories:
        for tournament in category.get("tournaments") or []:
            name = str(tournament.get("name") or "")
            if "srl" in name.lower():
                continue
            women = tournament.get("_gender") == "women" and "women" not in name.lower()
            competition = f"{name} Women" if women else name
            for match in tournament.get("matches") or []:
                teams = match.get("teams") or {}
                home = ((teams.get("home") or {}).get("name") or "").strip()
                away = ((teams.get("away") or {}).get("name") or "").strip()
                if not home or not away or "srl" in f"{home} {away}".lower():
                    continue
                status_id, status_name = _status(match)
                if match.get("cancelled") or match.get("postponed") or match.get("removed"):
                    phase = "cancelled"
                elif status_id in _PHASES:
                    phase = _PHASES[status_id]
                elif match.get("matchstatus") == "result":
                    phase = "ended"
                elif match.get("matchstatus") == "live":
                    phase = "live"
                else:
                    phase = "scheduled"
                result = match.get("result") or {}
                first_half = (match.get("periods") or {}).get("p1") or {}
                # El p1 vale como entretiempo recién cuando el 1er tiempo terminó.
                halftime_known = phase in {"halftime", "ended"} or status_id in {7, 41, 42, 50}
                uts = _int((match.get("_dt") or {}).get("uts"))
                matches.append(MatchStatus(
                    source=SOURCE, match_id=str(match.get("_id") or ""), home=home, away=away,
                    scheduled_at=datetime.fromtimestamp(uts, tz=timezone.utc).isoformat() if uts else None,
                    competition_name=competition, phase=phase,
                    home_score=_int(result.get("home")), away_score=_int(result.get("away")),
                    ht_home_score=_int(first_half.get("home")) if halftime_known else None,
                    ht_away_score=_int(first_half.get("away")) if halftime_known else None,
                    minute="FT" if phase == "ended" else _LABELS.get(status_id, status_name),
                    country_name=category.get("name")))
    return [match for match in matches if match.match_id]


class StatshubDayStatus:
    """Fuente de estado para el live-watch: el día completo de Statshub, cacheado."""

    name = SOURCE

    def __init__(self, provider: Any, *, ttl_seconds: float = 60.0,
                 tz: ZoneInfo = ZoneInfo("America/Argentina/Buenos_Aires")) -> None:
        # El widget de Statshub arma el día en hora argentina (`_dt.tz = -03`).
        self._provider = provider
        self._ttl = ttl_seconds
        self.tz = tz
        self._cache: dict[date, tuple[float, list[MatchStatus]]] = {}
        self._warned_at = 0.0

    def day_for(self, when: datetime) -> date:
        return when.astimezone(self.tz).date()

    async def matches_on(self, day: date) -> list[MatchStatus]:
        cached = self._cache.get(day)
        if cached and time.monotonic() - cached[0] < self._ttl:
            return cached[1]
        try:
            from stats_providers.sportradar_http.engine.endpoints.catalog import call_endpoint

            client = await asyncio.to_thread(self._provider._runtime._client)
            payload = await asyncio.to_thread(call_endpoint, client, "unified_sport_matches",
                                              sport_id=1, date=day.isoformat(), cursor=0)
        except Exception as error:
            # Token vencido o bloqueo: se sigue con lo último que hubo (o nada), sin
            # llenar el log en cada ciclo.
            if time.monotonic() - self._warned_at > 3600:
                logger.warning("Statshub (estado de partidos) no disponible: %s", str(error)[:160])
                self._warned_at = time.monotonic()
            return cached[1] if cached else []
        matches = parse_day(payload)
        self._cache[day] = (time.monotonic(), matches)
        return matches

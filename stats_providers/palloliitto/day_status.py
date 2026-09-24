"""Estado de todos los partidos del día en Finlandia (Palloliitto), en una sola llamada.

La federación es la fuente propia de las ligas finlandesas: da el estado ("Played",
"Live", "Break" = descanso, "Fixture"), el marcador (fs_A/fs_B), el del entretiempo
(hts_A/hts_B) y el minuto en vivo.

Ojo con las categorías: el mismo club aparece con el mismo nombre en mayores y en
juveniles ("EPS" en Kolmonen y en "P13 Huuhkajaliiga"). La categoría se traduce a
una marca de edad (P13 -> U13, T15 -> U15 mujeres, A-juniorit -> U19) para que la
guarda de categoría del live-watch no mezcle un partido de mayores con uno juvenil.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
import logging
import re
import time
from typing import Any
from zoneinfo import ZoneInfo

from core.stats_models import MatchStatus

logger = logging.getLogger(__name__)

SOURCE = "palloliitto"
_PHASES = {"played": "ended", "finished": "ended", "live": "live", "break": "halftime",
           "fixture": "scheduled", "forfeited": "cancelled", "cancelled": "cancelled",
           "postponed": "cancelled"}
_JUNIOR = {"a": "U19", "b": "U17", "c": "U15", "d": "U13", "e": "U11"}


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _category_marker(category: str) -> str:
    """Marca de edad/género que la guarda de categoría entiende."""
    youth = re.match(r"\s*([PT])\s?(\d{2})\b", category)
    if youth:
        return f" U{youth.group(2)}" + (" Women" if youth.group(1) == "T" else "")
    junior = re.search(r"\b([A-E])-?(juniorit|tytöt|pojat)\b", category, re.IGNORECASE)
    if junior:
        return f" {_JUNIOR[junior.group(1).lower()]}" + (" Women" if "tyt" in junior.group(2).lower() else "")
    return ""


def _scheduled_at(match: dict[str, Any]) -> str | None:
    day, clock = match.get("date"), (match.get("time") or "")[:5]
    if not day or not clock:
        return None
    offset = str(match.get("time_zone_offset") or "+0300")
    offset = f"{offset[:3]}:{offset[3:]}" if re.fullmatch(r"[+-]\d{4}", offset) else "+03:00"
    return f"{day}T{clock}:00{offset}"


def parse_day(matches: list[dict[str, Any]]) -> list[MatchStatus]:
    statuses: list[MatchStatus] = []
    for match in matches:
        home = str(match.get("team_A_name") or match.get("club_A_name") or "").strip()
        away = str(match.get("team_B_name") or match.get("club_B_name") or "").strip()
        if not home or not away or not match.get("match_id"):
            continue
        phase = _PHASES.get(str(match.get("status") or "").lower(), "scheduled")
        if phase == "halftime" and str(match.get("live_period")) not in {"1", ""}:
            phase = "live"  # descanso entre otros períodos (alargue): no es el entretiempo
        halftime_known = phase in {"halftime", "ended"} or (
            phase == "live" and str(match.get("live_period")) not in {"1", "-1", ""})
        minutes = _int(match.get("live_minutes"))
        minute = {"ended": "FT", "halftime": "HT"}.get(phase) or (f"{minutes}'" if minutes else None)
        category = str(match.get("category_name") or "")
        statuses.append(MatchStatus(
            source=SOURCE, match_id=str(match["match_id"]), home=home, away=away,
            scheduled_at=_scheduled_at(match),
            competition_name=f"{match.get('competition_name') or ''} {category}{_category_marker(category)}".strip(),
            phase=phase, home_score=_int(match.get("fs_A")), away_score=_int(match.get("fs_B")),
            ht_home_score=_int(match.get("hts_A")) if halftime_known else None,
            ht_away_score=_int(match.get("hts_B")) if halftime_known else None,
            minute=minute, country_name="Finland"))
    return statuses


class PalloliittoDayStatus:
    """Fuente de estado para el live-watch: el día completo de Palloliitto, cacheado."""

    name = SOURCE

    def __init__(self, *, ttl_seconds: float = 60.0, tz: ZoneInfo = ZoneInfo("Europe/Helsinki")) -> None:
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
            from stats_providers.palloliitto.api_client import PalloliittoAPI

            def fetch() -> list[dict[str, Any]]:
                with PalloliittoAPI(timeout=30) as api:
                    return api.get_matches_by_date(day.isoformat())

            raw = await asyncio.to_thread(fetch)
        except Exception as error:
            if time.monotonic() - self._warned_at > 3600:
                logger.warning("Palloliitto (estado de partidos) no disponible: %s", str(error)[:160])
                self._warned_at = time.monotonic()
            return cached[1] if cached else []
        matches = parse_day(raw)
        self._cache[day] = (time.monotonic(), matches)
        return matches

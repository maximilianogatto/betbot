"""Completa un resultado archivado con los datos de un proveedor de stats.

La captura desde live-watch deja marcador y tarjetas, pero no xG ni los minutos
de los goles — eso lo tiene un proveedor. Acá se traduce el reporte del
proveedor a los indicadores normalizados de `MatchResult`.

El traductor es una función pura (`normalize_provider_report`) a propósito: es
donde se esconden los bugs, porque cada proveedor devuelve una forma distinta en
`MatchStatsReport.data`. Hoy está implementado SofaScore, que es el que expone
xG e incidencias; agregar otro es sumar una rama y su test.
"""
from __future__ import annotations

import dataclasses
import json
import logging
from typing import Any

from core.models import MatchResult
from core.stats_models import MatchIdentityCandidate, MatchStatsReport

logger = logging.getLogger(__name__)

# SofaScore -> nuestro vocabulario. Se compara en minúsculas y por "contiene",
# porque los nombres varían ("Expected goals", "Expected goals (xG)").
_SOFASCORE_STATUS = {
    "finished": "FINISHED",
    "postponed": "POSTPONED",
    "canceled": "SUSPENDED",
    "cancelled": "SUSPENDED",
    "interrupted": "SUSPENDED",
    "suspended": "SUSPENDED",
}


def _stat_pair(statistics: dict[str, Any], *needles: str) -> tuple[Any, Any]:
    """Busca una estadística por nombre aproximado y devuelve (local, visitante)."""

    for name, values in statistics.items():
        label = str(name).strip().lower()
        if any(needle in label for needle in needles) and isinstance(values, dict):
            return values.get("home"), values.get("away")
    return None, None


def _as_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    return int(number) if number is not None else None


def _incident_minute(incident: dict[str, Any]) -> int | None:
    minute = incident.get("time")
    if not isinstance(minute, (int, float)):
        return None
    # El descuento se suma al minuto: un gol al 90+3 vale 93.
    added = incident.get("addedTime")
    return int(minute) + (int(added) if isinstance(added, (int, float)) else 0)


def _timeline(incidents: list[Any]) -> tuple[list[dict], list[dict], tuple[int | None, int | None]]:
    """Extrae minutos de goles, de rojas, y el marcador del entretiempo."""

    goals: list[dict] = []
    reds: list[dict] = []
    halftime: tuple[int | None, int | None] = (None, None)

    for incident in incidents:
        if not isinstance(incident, dict):
            continue
        kind = str(incident.get("incidentType") or "").strip().lower()
        side = "home" if incident.get("isHome") else "away"
        minute = _incident_minute(incident)

        if kind == "goal" and minute is not None:
            goals.append({"minute": minute, "team": side})
        elif kind == "card":
            # `yellowred` es la segunda amarilla: deja al equipo con uno menos
            # igual que una roja directa, así que cuenta como expulsión.
            card = str(incident.get("incidentClass") or "").strip().lower()
            if card in ("red", "yellowred") and minute is not None:
                reds.append({"minute": minute, "team": side})
        elif kind == "period":
            label = str(incident.get("text") or "").strip().upper()
            if label in ("HT", "HALFTIME"):
                halftime = (
                    _as_int(incident.get("homeScore")),
                    _as_int(incident.get("awayScore")),
                )

    goals.sort(key=lambda item: item["minute"])
    reds.sort(key=lambda item: item["minute"])
    return goals, reds, halftime


def normalize_provider_report(report: MatchStatsReport) -> dict[str, Any]:
    """Traduce un reporte de proveedor a los campos de `MatchResult`.

    Devuelve sólo lo que el proveedor realmente informó: las claves ausentes se
    omiten en vez de mandar None, para que enriquecer nunca borre un dato que ya
    estaba archivado.
    """

    data = report.data if isinstance(report.data, dict) else {}
    match = data.get("match") if isinstance(data.get("match"), dict) else {}
    live_state = data.get("live_state") if isinstance(data.get("live_state"), dict) else {}
    statistics = live_state.get("statistics") if isinstance(live_state.get("statistics"), dict) else {}
    incidents = live_state.get("incidents") if isinstance(live_state.get("incidents"), list) else []

    fields: dict[str, Any] = {
        "stats_provider": report.provider,
        "stats_match_id": str(report.match_id),
        "raw_payload_json": json.dumps(data, ensure_ascii=False, sort_keys=True),
    }

    raw_status = str(match.get("status") or "").strip().lower()
    if raw_status:
        # Un estado que no conocemos NO se asume terminado: queda UNKNOWN y el
        # partido no entra a los análisis hasta que alguien lo confirme.
        fields["status"] = _SOFASCORE_STATUS.get(raw_status, "UNKNOWN")

    for key, source in (("final_home_score", "score_home"), ("final_away_score", "score_away")):
        value = _as_int(match.get(source))
        if value is not None:
            fields[key] = value

    if match.get("start_time_utc"):
        fields["actual_start_at"] = str(match["start_time_utc"])

    xg_home, xg_away = _stat_pair(statistics, "expected goals", "xg")
    if xg_home is not None or xg_away is not None:
        fields["xg_home"] = _as_float(xg_home)
        fields["xg_away"] = _as_float(xg_away)

    sot_home, sot_away = _stat_pair(statistics, "shots on target", "on target")
    if sot_home is not None or sot_away is not None:
        fields["shots_on_target_home"] = _as_int(sot_home)
        fields["shots_on_target_away"] = _as_int(sot_away)

    goals, reds, (ht_home, ht_away) = _timeline(incidents)
    if goals:
        fields["goal_minutes_json"] = json.dumps(goals, ensure_ascii=False)
    if reds:
        fields["red_card_minutes_json"] = json.dumps(reds, ensure_ascii=False)
        fields["red_cards_home"] = sum(1 for item in reds if item["team"] == "home")
        fields["red_cards_away"] = sum(1 for item in reds if item["team"] == "away")
    if ht_home is not None and ht_away is not None:
        fields["ht_home_score"] = ht_home
        fields["ht_away_score"] = ht_away

    return fields


def merge_into_result(result: MatchResult, fields: dict[str, Any]) -> MatchResult:
    """Aplica los campos del proveedor sobre un resultado ya archivado.

    Sólo pisa lo que el proveedor informó: si un campo no vino, se conserva el
    valor que ya estaba. Enriquecer nunca puede empeorar el registro.
    """

    usable = {name: value for name, value in fields.items() if value is not None}
    return dataclasses.replace(result, **usable)


class MatchEnrichmentService:
    """Completa resultados archivados usando un proveedor de stats."""

    def __init__(self, *, repository: Any, provider_registry: Any) -> None:
        self.repository = repository
        self.provider_registry = provider_registry

    async def enrich_one(self, result: MatchResult, *, provider_key: str) -> MatchResult | None:
        """Resuelve el partido en el proveedor, lo completa y lo guarda.

        Devuelve el resultado actualizado, o None si el proveedor no pudo
        identificar el partido (caso normal en ligas menores: se deja como está
        para reintentar más adelante, no se marca como fallido).
        """

        provider = self.provider_registry.get(provider_key)
        link = await provider.resolve_match(
            MatchIdentityCandidate(
                home=result.home,
                away=result.away,
                scheduled_at=result.kickoff_at,
                league_name=result.competition_name,
                platform=result.platform,
                external_event_id=result.external_event_id,
            )
        )
        if link is None:
            logger.info(
                "Enriquecimiento: %s no encontró %s vs %s", provider_key, result.home, result.away
            )
            return None

        report = await provider.build_match_report(link.stats_match_id)
        enriched = merge_into_result(result, normalize_provider_report(report))
        return self.repository.record_match_result(enriched)

    async def enrich_pending(self, *, provider_key: str, limit: int = 20) -> int:
        """Completa los resultados pendientes. Devuelve cuántos se enriquecieron."""

        pending = self.repository.list_match_results_pending_enrichment(limit=limit)
        enriched = 0
        for result in pending:
            try:
                if await self.enrich_one(result, provider_key=provider_key) is not None:
                    enriched += 1
            except Exception:
                # Un partido que falla no puede frenar a los demás.
                logger.exception(
                    "Enriquecimiento falló para %s vs %s", result.home, result.away
                )
        if pending:
            logger.info("Enriquecimiento: %d/%d completados.", enriched, len(pending))
        return enriched

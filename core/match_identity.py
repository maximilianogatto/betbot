"""Identidad física de partidos: decidir si dos eventos de plataformas distintas
son el MISMO partido, y agruparlos.

Es lógica de dominio pura (no sabe de Telegram ni de storage). Vivía en
`bot/alerts.py`, lo que obligaba a los services (`services/tracking.py`) a importar
de la capa de bot — una inversión de dependencia que PR2-E3 corrige.

La usan: el comparador cross-plataforma, el agrupado de `/matches` y el learner de
unificación de ligas.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.models import ActiveEventRecord

#: Máxima diferencia de horario para considerar dos eventos el mismo partido.
MAX_KICKOFF_DIFF_HOURS = 3.0
#: Similitud mínima por equipo (local y visitante por separado).
MIN_TEAM_SIMILARITY = 0.70
#: Similitud promedio mínima para aceptar el par como el mismo partido.
MIN_AVERAGE_SIMILARITY = 0.80
#: Umbral para agrupar un evento dentro de un grupo ya existente.
GROUPING_THRESHOLD = 0.80


def _parse_kickoff(value) -> datetime | None:
    """Parsea un kickoff a UTC (naive se asume UTC). None si no es parseable."""
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip())
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def physical_match_similarity(
    event_a: ActiveEventRecord, event_b: ActiveEventRecord
) -> float:
    """Score 0..1 de que dos eventos sean el mismo partido físico.

    Devuelve 0.0 si los horarios difieren más de `MAX_KICKOFF_DIFF_HOURS`, o si los
    nombres de equipos no superan los umbrales. Si pasa, devuelve el promedio de
    similitud local/visitante.
    """
    from core.league_naming import team_name_similarity

    dt_a = _parse_kickoff(event_a.scheduled_at)
    dt_b = _parse_kickoff(event_b.scheduled_at)
    if dt_a and dt_b:
        diff_hours = abs((dt_a - dt_b).total_seconds()) / 3600.0
        if diff_hours > MAX_KICKOFF_DIFF_HOURS:
            return 0.0

    home_sim = team_name_similarity(event_a.home, event_b.home)
    away_sim = team_name_similarity(event_a.away, event_b.away)

    if home_sim >= MIN_TEAM_SIMILARITY and away_sim >= MIN_TEAM_SIMILARITY:
        avg_score = (home_sim + away_sim) / 2.0
        if avg_score >= MIN_AVERAGE_SIMILARITY:
            return avg_score

    return 0.0


def group_events_by_physical_match(
    events: list[ActiveEventRecord],
) -> list[list[ActiveEventRecord]]:
    """Agrupa eventos de distintas plataformas que son el mismo partido físico."""
    groups: list[list[ActiveEventRecord]] = []
    for event in events:
        placed = False
        for group in groups:
            representative = group[0]
            if physical_match_similarity(representative, event) >= GROUPING_THRESHOLD:
                group.append(event)
                placed = True
                break
        if not placed:
            groups.append([event])
    return groups

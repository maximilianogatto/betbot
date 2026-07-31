from __future__ import annotations

from typing import Protocol

from core.models import MatchResult


class MatchResultsPort(Protocol):
    """Archivo histórico de cómo terminaron los partidos.

    Es la base sobre la que después corren los análisis: por eso el guardado es
    idempotente (un mismo partido re-consultado actualiza su fila en vez de
    duplicarla) y las lecturas van por liga y por ventana de fechas.
    """

    def record_match_result(self, result: MatchResult) -> MatchResult:
        """Guarda o actualiza el resultado de un partido. Devuelve la fila con su id."""
        ...

    def get_match_result(self, *, platform: str, external_event_id: str) -> MatchResult | None:
        """Devuelve el resultado archivado de un partido de una plataforma."""
        ...

    def list_match_results(
        self,
        *,
        unified_competition_id: int | None = None,
        since: str | None = None,
        until: str | None = None,
        only_settled: bool = False,
        limit: int | None = None,
    ) -> list[MatchResult]:
        """Lista resultados archivados, filtrando por liga y ventana temporal."""
        ...

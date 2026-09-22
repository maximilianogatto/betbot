from __future__ import annotations

from typing import Protocol

from core.models import OddsSnapshot


class OddsHistoryPort(Protocol):
    """Archivo append-only de cómo se movieron las cuotas.

    `events` guarda el estado actual y se pisa en cada poll; esto guarda la
    serie. Nunca se actualiza una fila: si el precio cambió, hay una fila nueva.

    Semántica honesta de los extremos (§6 del plan de Fase 0): la primera fila
    es *la primera vez que lo vimos*, no la apertura real de la casa, y el
    cierre es *el último snapshot pre-kickoff que alcanzamos a ver*, no la
    closing line oficial. Los nombres lo dicen para que ningún reporte lo
    confunda.
    """

    def archive_snapshots(self, snapshots: list[OddsSnapshot]) -> int:
        """Guarda los snapshots nuevos. Devuelve cuántos se escribieron."""
        ...

    def last_snapshot(self, *, platform: str, external_event_id: str) -> OddsSnapshot | None:
        """El último snapshot archivado de ese evento (para no repetir polls iguales)."""
        ...

    def list_snapshots(self, *, platform: str, external_event_id: str,
                       limit: int = 500) -> list[OddsSnapshot]:
        """La serie completa de un evento, del más viejo al más nuevo."""
        ...

    def last_prematch_snapshot(self, *, platform: str, external_event_id: str,
                               kickoff_at: str) -> OddsSnapshot | None:
        """El último snapshot estrictamente anterior al kickoff: el cierre observado."""
        ...

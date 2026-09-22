"""Archiva la serie de cuotas mientras el tracking las va leyendo.

El poll de tracking escribe el estado actual en `events` (lo pisa cada vez).
Este servicio guarda además la serie en `odds_history`, con dos reglas que
vienen del plan de Fase 0:

- **Sólo cambios.** Si el payload es idéntico al último archivado, no se
  escribe: un poll repetido no es información nueva. El hash cubre el 1X2 y
  todos los mercados, así que un movimiento de handicap también dispara fila
  aunque el 1X2 no se mueva.
- **Las suspensiones se archivan.** Si la casa deja de publicar cuotas, la fila
  va con ``is_suspended=1`` en vez de descartarse: el instante en que una casa
  suspende un mercado dice cuándo se enteró de algo.

Nunca rompe el poll: si el archivado falla, se registra en el log y las alertas
siguen funcionando.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Iterable, Optional

from core.models import OddsSnapshot
from core.ports.odds_history import OddsHistoryPort

logger = logging.getLogger(__name__)


def payload_hash(*, odds_home: Any, odds_draw: Any, odds_away: Any,
                 markets_json: str | None) -> str:
    """Huella del precio completo: 1X2 + todos los mercados."""
    material = json.dumps([odds_home, odds_draw, odds_away, markets_json], sort_keys=True,
                          ensure_ascii=False, default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def is_suspended(odds_home: Any, odds_draw: Any, odds_away: Any, markets_json: str | None) -> bool:
    """Sin 1X2 y sin mercados: la casa no está publicando precio."""
    return not any(v is not None for v in (odds_home, odds_draw, odds_away)) and not markets_json


def should_archive(previous: OddsSnapshot | None, candidate_hash: str) -> bool:
    """True si el payload cambió respecto del último archivado. Pura."""
    return previous is None or previous.payload_hash != candidate_hash


class OddsArchiveService:
    def __init__(self, archive: OddsHistoryPort, *, clock=lambda: datetime.now(timezone.utc)) -> None:
        self.archive = archive
        self.clock = clock
        # Último hash por evento, para no ir a la base en cada poll.
        self._last_hash: dict[tuple[str, str], str] = {}

    def archive_events(self, *, platform: str, events: Iterable[Any], status: str = "PREMATCH",
                       unified_competition_id: int | None = None,
                       competition_name: str | None = None) -> int:
        """Archiva los eventos cuyo precio cambió. Devuelve cuántas filas escribió.

        ``events`` son los mismos objetos que el tracking manda a `events`: basta
        con que expongan ``external_event_id``, ``home``, ``away``,
        ``odds_home/draw/away``, ``markets_payload`` y ``scheduled_at``.
        """
        try:
            captured_at = self.clock().isoformat()
            snapshots: list[OddsSnapshot] = []
            for event in events:
                snapshot = self._snapshot(event, platform=platform, captured_at=captured_at,
                                          status=status,
                                          unified_competition_id=unified_competition_id,
                                          competition_name=competition_name)
                if snapshot is None:
                    continue
                snapshots.append(snapshot)
            if not snapshots:
                return 0
            written = self.archive.archive_snapshots(snapshots)
            for snapshot in snapshots:
                self._last_hash[(platform, snapshot.external_event_id)] = snapshot.payload_hash
            return written
        except Exception:
            logger.exception("Odds archive failed platform=%s", platform)
            return 0

    def _snapshot(self, event: Any, *, platform: str, captured_at: str, status: str,
                  unified_competition_id: int | None,
                  competition_name: str | None) -> Optional[OddsSnapshot]:
        external_id = str(getattr(event, "external_event_id", "") or "")
        if not external_id:
            return None
        markets = getattr(event, "markets_payload", None)
        markets_json = markets if isinstance(markets, str) else (
            json.dumps(markets, ensure_ascii=False, sort_keys=True, default=str) if markets else None)
        odds_home = getattr(event, "odds_home", None)
        odds_draw = getattr(event, "odds_draw", None)
        odds_away = getattr(event, "odds_away", None)
        candidate_hash = payload_hash(odds_home=odds_home, odds_draw=odds_draw,
                                      odds_away=odds_away, markets_json=markets_json)

        cached = self._last_hash.get((platform, external_id))
        if cached is not None:
            if cached == candidate_hash:
                return None
        else:
            previous = self.archive.last_snapshot(platform=platform, external_event_id=external_id)
            if not should_archive(previous, candidate_hash):
                self._last_hash[(platform, external_id)] = candidate_hash
                return None

        return OddsSnapshot(
            platform=platform,
            external_event_id=external_id,
            captured_at=captured_at,
            payload_hash=candidate_hash,
            status=status,
            unified_competition_id=unified_competition_id,
            home=getattr(event, "home", None),
            away=getattr(event, "away", None),
            competition_name=competition_name,
            scheduled_at=getattr(event, "scheduled_at", None),
            odds_home=odds_home,
            odds_draw=odds_draw,
            odds_away=odds_away,
            markets_json=markets_json,
            is_suspended=is_suspended(odds_home, odds_draw, odds_away, markets_json),
        )

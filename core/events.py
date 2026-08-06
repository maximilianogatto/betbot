"""Domain event classes for the BetBot asynchronous event system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models import (
    ActiveEventRecord,
    LiveWatchHit,
    MatchSnapshot,
    Odds1X2,
    SubscriptionOddsAlert,
    TrackedCompetition,
)

@dataclass(frozen=True)
class NewMatchesEvent:
    """Aparecieron partidos nuevos en una liga que el chat sigue."""

    chat_id: int
    tracked_league: TrackedCompetition
    matches: tuple[ActiveEventRecord, ...]
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class OddsChangedEvent:
    """Cuotas que se movieron lo suficiente como para avisarle al chat.

    Transporta las alertas YA evaluadas contra el baseline del chat (con su
    confirmación y su anti-flapping): decidir si el movimiento amerita aviso es
    lógica de dominio y ocurre antes de publicar. El listener sólo redacta.

    La versión anterior de esta clase se diseñó contra un modelo imaginado
    (campos sueltos de odds) y nunca llegó a usarse.
    """

    chat_id: int
    tracked_league: TrackedCompetition
    alerts: tuple[SubscriptionOddsAlert, ...]
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class MatchRemindersEvent:
    """Se acercan partidos que el chat pidió que le recuerden."""

    chat_id: int
    tracked_league: TrackedCompetition
    matches: tuple[ActiveEventRecord, ...]
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class MatchLiveEvent:
    """Un fixture vigilado entró en vivo o tuvo un evento crítico (gol, roja...).

    Transporta el `LiveWatchHit` entero en vez de copiar sus campos sueltos: el
    mensaje que se le manda al usuario se arma con la entrada vigilada, la fase
    y el snapshot completo (tarjetas, país, competencia, stats). Aplanarlo
    perdería datos que el aviso necesita.
    """

    hit: LiveWatchHit
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def chat_id(self) -> int:
        """Chat al que va el aviso; la entrada vigilada es la fuente de verdad."""

        return self.hit.entry.chat_id

@dataclass(frozen=True)
class RotationAlertEvent:
    """Triggered when a high-value rotation peak is calculated for a match."""

    chat_id: int
    unified_competition_id: int
    match_snapshot: MatchSnapshot
    peak_score: float
    rotation_details: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)

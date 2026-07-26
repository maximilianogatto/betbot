"""Domain event classes for the BetBot asynchronous event system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models import LiveWatchHit, MatchSnapshot, Odds1X2

@dataclass(frozen=True)
class OddsChangedEvent:
    """Triggered when a significant odds variation is detected compared to baseline."""

    chat_id: int
    event_id: int
    home: str
    away: str
    platform: str
    previous_odds: Odds1X2
    current_odds: Odds1X2
    max_change_percent: float
    markets_diff: dict[str, Any]
    event_url: str | None = None
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

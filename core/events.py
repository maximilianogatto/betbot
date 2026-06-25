"""Domain event classes for the BetBot asynchronous event system."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.models import MatchSnapshot, Odds1X2

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
    timestamp: datetime = datetime.now()

@dataclass(frozen=True)
class MatchLiveEvent:
    """Triggered when a watched match starts or experiences a critical in-play event."""

    chat_id: int
    event_id: int | str
    home: str
    away: str
    platform: str
    minute: str
    home_score: int
    away_score: int
    home_red_cards: int
    away_red_cards: int
    is_kickoff: bool = False
    event_type: str = "update"  # 'kickoff' | 'goal' | 'red_card' | 'yellow_card' | 'update'
    timestamp: datetime = datetime.now()

@dataclass(frozen=True)
class RotationAlertEvent:
    """Triggered when a high-value rotation peak is calculated for a match."""

    chat_id: int
    unified_competition_id: int
    match_snapshot: MatchSnapshot
    peak_score: float
    rotation_details: dict[str, Any]
    timestamp: datetime = datetime.now()

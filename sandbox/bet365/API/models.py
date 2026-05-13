from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Selection:
    selection_id: str | None
    name: str | None
    odds_fractional: str | None
    odds_decimal: float | None
    participant_code: str | None = None
    line: str | None = None
    raw_fields: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selection_id": self.selection_id,
            "name": self.name,
            "odds_fractional": self.odds_fractional,
            "odds_decimal": self.odds_decimal,
            "participant_code": self.participant_code,
            "line": self.line,
        }


@dataclass(slots=True)
class Market:
    market_id: str | None
    name: str | None
    selections: list[Selection] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "name": self.name,
            "selections": [selection.to_dict() for selection in self.selections],
        }


@dataclass(slots=True)
class Event:
    event_id: str | None
    fixture_id: str | None
    topic: str | None
    competition_name: str | None
    name: str | None
    home: str | None
    away: str | None
    start_raw: str | None
    event_token: str | None = None
    event_it: str | None = None
    event_pd: str | None = None
    event_url: str | None = None
    sportradar_url: str | None = None
    stats_identifier: str | None = None
    source_meta: dict[str, Any] = field(default_factory=dict)
    markets: list[Market] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "fixture_id": self.fixture_id,
            "topic": self.topic,
            "competition_name": self.competition_name,
            "name": self.name,
            "home": self.home,
            "away": self.away,
            "start_raw": self.start_raw,
            "event_token": self.event_token,
            "event_it": self.event_it,
            "event_pd": self.event_pd,
            "event_url": self.event_url,
            "sportradar_url": self.sportradar_url,
            "stats_identifier": self.stats_identifier,
            "source_meta": self.source_meta,
            "markets": [market.to_dict() for market in self.markets],
        }

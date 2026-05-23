"""Typed internal models for 1xBet LineFeed payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class XBetFixture:
    """One fixture from `GetChampZip.Value.G[]`."""

    event_id: str
    home: str
    away: str
    start_time_unix: int | None
    start_time_utc: str | None
    label_date: str | None
    label_time: str | None
    home_id: str | None
    away_id: str | None
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class XBetLeagueSnapshot:
    """Normalized result from one `GetChampZip` response."""

    platform: str
    source_url: str
    league_id: str
    league_name: str
    sport_id: str | None
    country: str | None
    extracted_at: str
    fixtures: list[XBetFixture]
    raw_payload: dict[str, Any]

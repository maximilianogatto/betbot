from __future__ import annotations

from datetime import datetime
from typing import Protocol, Any
from core.models import ActiveEventRecord, ActiveEventUpsert

class EventsPort(Protocol):
    """Port defining active event storage operations."""

    def upsert_active_events(
        self,
        tracked_competition_id: int,
        events: list[ActiveEventUpsert],
    ) -> list[ActiveEventRecord]:
        """Insert or update a batch of active events for a tracked competition."""
        ...

    def get_active_events(
        self,
        tracked_competition_id: int,
        exclude_alerted: bool = False,
        limit: int | None = None,
    ) -> list[ActiveEventRecord]:
        """Retrieve active events for a tracked competition."""
        ...

    def get_all_active_events_with_league(
        self,
        chat_id: int,
    ) -> list[dict[str, Any]]:
        """Retrieve active events across all subscribed competitions for a chat."""
        ...

    def get_active_events_for_unified_competition(
        self,
        unified_id: int,
    ) -> list[ActiveEventRecord]:
        """Retrieve all active events linked to a canonical unified competition."""
        ...

    def get_earliest_kickoffs(
        self,
        minutes_threshold: int = 15,
    ) -> list[dict[str, Any]]:
        """Find upcoming matches starting soon that have not been reminded yet."""
        ...

    def remove_missing_events(
        self,
        tracked_competition_id: int,
        active_external_ids: list[str],
        max_missing_cycles: int = 3,
    ) -> int:
        """Mark missing events as inactive or increment their missing counter."""
        ...

    def remove_past_events(
        self,
        hours_ago: int = 4,
    ) -> int:
        """Purge or mark inactive events whose kickoff was more than hours_ago."""
        ...

    def mark_events_alerted(
        self,
        event_ids: list[int],
    ) -> None:
        """Mark events as alerted to prevent double notifications on new match detection."""
        ...

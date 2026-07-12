from __future__ import annotations

from typing import Protocol
from core.models import EventBaseline, SmallChangeRecord

class BaselinesPort(Protocol):
    """Port defining baseline odds, sent alerts, and small changes tracking operations."""

    def get_event_baseline(
        self,
        chat_id: int,
        active_event_id: int,
    ) -> EventBaseline | None:
        """Get the baseline odds for a specific chat and active event."""
        ...

    def initialize_event_baselines(
        self,
        chat_id: int,
        tracked_competition_id: int,
        active_events: list[dict[str, Any]],
    ) -> None:
        """Populate initial baseline odds for new events in a chat subscription."""
        ...

    def upsert_event_baseline(
        self,
        chat_id: int,
        active_event_id: int,
        tracked_competition_id: int,
        external_event_id: str,
        home: float | None,
        draw: float | None,
        away: float | None,
        markets_json: str | None = None,
    ) -> None:
        """Create or update a baseline odds entry for a specific chat."""
        ...

    def list_pending_small_changes(
        self,
        chat_id: int,
    ) -> list[SmallChangeRecord]:
        """List all pending small odds fluctuation records for a chat."""
        ...

    def upsert_small_change(
        self,
        chat_id: int,
        active_event_id: int,
        tracked_competition_id: int,
        external_event_id: str,
        competition_name: str,
        home: str,
        away: str,
        scheduled_label_date: str | None,
        scheduled_label_time: str | None,
        scheduled_at: str | None,
        baseline_home: float | None,
        baseline_draw: float | None,
        baseline_away: float | None,
        current_home: float | None,
        current_draw: float | None,
        current_away: float | None,
        max_percent_change: float,
        payload_json: str | None = None,
        status: str = "pending",
    ) -> None:
        """Log a new small change or update an existing pending one."""
        ...

    def confirm_small_change(
        self,
        chat_id: int,
        change_id: int,
    ) -> bool:
        """Confirm a small change, setting its status to 'confirmed' and updating baseline."""
        ...

    def confirm_all_small_changes(
        self,
        chat_id: int,
    ) -> int:
        """Confirm all pending small changes for a chat, returning the count confirmed."""
        ...

    def resolve_small_change_with_current_baseline(
        self,
        chat_id: int,
        active_event_id: int,
    ) -> None:
        """Remove a pending small change if odds return to matching baseline."""
        ...

    def has_sent_alert(
        self,
        chat_id: int,
        active_event_id: int,
        alert_type: str,
    ) -> bool:
        """Check if an alert of alert_type has already been sent for an event to a chat."""
        ...

    def mark_sent_alerts(
        self,
        chat_id: int,
        active_event_id: int,
        alert_type: str,
    ) -> None:
        """Record that an alert has been dispatched to prevent duplicate warnings."""
        ...

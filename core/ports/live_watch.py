from __future__ import annotations

from typing import Protocol, Any
from core.models import LiveWatchEntry, LiveWatchSettings

class LiveWatchPort(Protocol):
    """Port defining operations for registering and monitoring live fixture alerts."""

    def add_live_watch(
        self,
        chat_id: int,
        home: str,
        away: str,
        league_hint: str | None = None,
        note: str | None = None,
        kickoff_at: str | None = None,
        chat_local_id: int | None = None,
    ) -> LiveWatchEntry:
        """Register a new fixture to watch for in-play status."""
        ...

    def get_live_watch(
        self,
        entry_id: int,
    ) -> LiveWatchEntry | None:
        """Retrieve a live watch entry by its database ID."""
        ...

    def get_live_watch_by_local_id(
        self,
        chat_id: int,
        chat_local_id: int,
    ) -> LiveWatchEntry | None:
        """Retrieve a live watch entry by its chat-scoped local ID."""
        ...

    def list_live_watches(
        self,
        chat_id: int,
        status: str | None = None,
    ) -> list[LiveWatchEntry]:
        """List live watch entries for a specific chat, optionally filtered by status."""
        ...

    def list_all_active_live_watches(self) -> list[LiveWatchEntry]:
        """List all active live watches (status = 'watching') across all chats."""
        ...

    def remove_live_watch(
        self,
        chat_id: int,
        entry_id: int,
    ) -> bool:
        """Unregister a live watch entry by its database ID."""
        ...

    def remove_live_watch_by_local_id(
        self,
        chat_id: int,
        chat_local_id: int,
    ) -> bool:
        """Unregister a live watch entry by its chat-scoped local ID."""
        ...

    def clear_live_watches(
        self,
        chat_id: int,
        status: str | None = None,
    ) -> int:
        """Delete all live watch entries for a chat, optionally filtered by status."""
        ...

    def purge_expired_live_watches(self) -> int:
        """Clean up completed or expired live watch entries."""
        ...

    def get_live_watch_settings(
        self,
        chat_id: int,
    ) -> LiveWatchSettings:
        """Get the live watch notification preferences for a chat."""
        ...

    def set_live_watch_settings(
        self,
        chat_id: int,
        alert_goals: bool | None = None,
        alert_red_cards: bool | None = None,
        alert_yellow_cards: bool | None = None,
    ) -> None:
        """Update live watch notification preferences for a chat."""
        ...

    def mark_live_watch_fired(
        self,
        entry_id: int,
        platforms: list[str],
        live_state: dict[str, Any] | None = None,
    ) -> None:
        """Record that a live watch alert has been triggered for in-play status."""
        ...

    def mark_live_watch_countdown_fired(
        self,
        entry_id: int,
    ) -> None:
        """Record that a countdown notification (e.g. 5 minutes before kickoff) has fired."""
        ...

    def mark_live_watch_prematch_fired(
        self,
        entry_id: int,
        platforms: list[str],
    ) -> None:
        """Record that a pre-match odds/availability alert has been fired."""
        ...

    def update_live_watch_platform_state(
        self,
        entry_id: int,
        platform: str,
        live_state: dict[str, Any],
    ) -> None:
        """Update the last seen in-play state metadata for a specific platform."""
        ...

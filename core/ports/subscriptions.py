from __future__ import annotations

from typing import Protocol
from core.models import (
    CompetitionSubscription,
    TrackedCompetitionSubscription,
    StatsLeagueSubscription,
)

class SubscriptionsPort(Protocol):
    """Port defining chat subscription storage operations for odds and stats."""

    def get_tracked_competition_subscription(
        self,
        chat_id: int,
        tracked_id: int,
    ) -> CompetitionSubscription | None:
        """Get a subscription for a chat and specific tracked competition."""
        ...

    def get_tracked_competition_subscription_by_identity(
        self,
        chat_id: int,
        platform: str,
        external_id: str,
    ) -> TrackedCompetitionSubscription | None:
        """Get combined tracking and subscription info by platform identity."""
        ...

    def get_subscriptions_for_competition(
        self,
        tracked_id: int,
    ) -> list[CompetitionSubscription]:
        """List all active subscriptions for a tracked competition."""
        ...

    def get_enabled_subscription_count(self) -> int:
        """Get the total count of enabled subscriptions across all chats."""
        ...

    def remove_tracked_competition_subscription(
        self,
        chat_id: int,
        tracked_id: int,
    ) -> bool:
        """Remove a subscription from a chat to a tracked competition."""
        ...

    def remove_unified_subscription(
        self,
        chat_id: int,
        unified_id: int,
    ) -> bool:
        """Remove all subscriptions from a chat to child trackers of a unified league."""
        ...

    def set_change_percent_threshold(
        self,
        chat_id: int,
        tracked_id: int,
        percent: float,
    ) -> None:
        """Update the odds fluctuation alert threshold for a subscription."""
        ...

    def set_odds_notifications(
        self,
        chat_id: int,
        tracked_id: int,
        enabled: bool,
    ) -> None:
        """Enable or disable odds fluctuation alerts for a subscription."""
        ...

    def set_competition_reminders(
        self,
        chat_id: int,
        tracked_id: int,
        enabled: bool,
    ) -> None:
        """Enable or disable kick-off reminders for a competition subscription."""
        ...

    def competition_reminders_enabled(
        self,
        chat_id: int,
        tracked_id: int,
    ) -> bool:
        """Check if kick-off reminders are active for a competition subscription."""
        ...

    def set_event_reminder(
        self,
        chat_id: int,
        event_id: int,
        enabled: bool,
    ) -> None:
        """Subscribe or unsubscribe from a specific upcoming match kickoff reminder."""
        ...

    def event_reminder_enabled_ids(
        self,
        chat_id: int,
    ) -> set[int]:
        """Get the set of active event reminder IDs for a chat."""
        ...

    def list_stats_league_subscriptions(
        self,
        chat_id: int,
    ) -> list[StatsLeagueSubscription]:
        """List all independent stats provider subscriptions for a chat."""
        ...

    def upsert_stats_league_subscription(
        self,
        chat_id: int,
        provider: str,
        stats_league_id: str,
        stats_league_name: str,
        stats_country_name: str | None = None,
        source_url: str | None = None,
        enabled: bool = True,
    ) -> None:
        """Create or update a stats provider subscription."""
        ...

    def list_peak_digest_chats(self) -> list[int]:
        """Get all chat IDs subscribed to the daily peak digest."""
        ...

    def set_peak_digest_subscription(
        self,
        chat_id: int,
        enabled: bool,
    ) -> None:
        """Subscribe or unsubscribe a chat from the daily peak digest."""
        ...

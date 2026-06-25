from __future__ import annotations

from typing import Protocol, Any
from core.models import TrackedCompetition, PendingCompetitionTrackRequest

class CompetitionsPort(Protocol):
    """Port defining tracking, unified, and pending competition storage operations."""

    def create_pending_competition_request(
        self,
        chat_id: int,
        platform: str,
        source_url: str,
        competition_external_id: str,
        competition_name: str,
        requires_empty_confirmation: bool,
        needs_name_resolution: bool,
        payload_json: str | None = None,
    ) -> PendingCompetitionTrackRequest:
        """Create a new pending track request."""
        ...

    def get_latest_pending_competition_request(
        self,
        chat_id: int,
    ) -> PendingCompetitionTrackRequest | None:
        """Retrieve the most recent pending track request for a chat."""
        ...

    def confirm_pending_competition_request(
        self,
        chat_id: int,
    ) -> TrackedCompetition:
        """Confirm a pending request, converting it into a tracked competition."""
        ...

    def delete_pending_competition_request(
        self,
        chat_id: int,
    ) -> bool:
        """Delete a pending request without confirming."""
        ...

    def get_tracked_competition(
        self,
        competition_id: int,
    ) -> TrackedCompetition | None:
        """Get a tracked competition by its database ID."""
        ...

    def get_tracked_competition_by_identity(
        self,
        platform: str,
        external_id: str,
    ) -> TrackedCompetition | None:
        """Get a tracked competition by its platform and external ID."""
        ...

    def list_tracked_competitions(self) -> list[TrackedCompetition]:
        """List all tracked competitions, both enabled and disabled."""
        ...

    def list_globally_active_competitions(self) -> list[TrackedCompetition]:
        """List all enabled tracked competitions that require scraping."""
        ...

    def update_tracked_competition(
        self,
        competition_id: int,
        enabled: bool | None = None,
        last_synced_at: str | None = None,
        metadata_json: str | None = None,
        needs_name_resolution: bool | None = None,
    ) -> TrackedCompetition:
        """Update tracked competition parameters."""
        ...

    def update_tracked_competition_source(
        self,
        competition_id: int,
        source_url: str,
    ) -> None:
        """Update the scraping URL source for a tracked competition."""
        ...

    def sanitize_tracking_state(self) -> None:
        """Run cleanup routines on tracking metadata (e.g. resolve stale sync flags)."""
        ...

    def auto_track_live_detected_league(
        self,
        platform: str,
        external_id: str,
        name: str,
        source_url: str | None = None,
    ) -> TrackedCompetition | None:
        """Automatically create and enable tracking for a live-discovered competition."""
        ...

    def record_unavailable_refresh(
        self,
        competition_id: int,
        reason: str,
    ) -> TrackedCompetition:
        """Log a failed scraping cycle and increment consecutives fail counter."""
        ...

    def should_send_unavailable_refresh_warning(
        self,
        competition_id: int,
    ) -> bool:
        """Determine if a warning notification should be sent for repeated sync failures."""
        ...

    def mark_unavailable_refresh_warning_sent(
        self,
        competition_id: int,
    ) -> None:
        """Log that a repeated sync failure alert has been dispatched."""
        ...

    def create_unified_competition(
        self,
        name: str,
        country_name: str | None = None,
    ) -> int:
        """Create a new canonical unified competition and return its database ID."""
        ...

    def link_tracked_competition_to_unified(
        self,
        tracked_id: int,
        unified_id: int,
    ) -> None:
        """Link a platform-specific tracked competition to a canonical unified one."""
        ...

    def merge_unified_competitions(
        self,
        source_unified_id: int,
        target_unified_id: int,
    ) -> None:
        """Merge two unified competitions into one, re-linking child trackers."""
        ...

    def relink_unified_by_normalized_name(self) -> int:
        """Heuristically link untracked leagues based on fuzzy name alignment."""
        ...

    def suggest_similar_unified(
        self,
        name: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Suggest matching unified competitions using name similarity."""
        ...

    def list_subscribed_unified_competitions(
        self,
        chat_id: int,
    ) -> list[dict[str, Any]]:
        """List all canonical unified leagues that have active subscriptions for a chat."""
        ...

    def list_tracked_competitions_for_unified(
        self,
        unified_id: int,
    ) -> list[TrackedCompetition]:
        """List platform trackers linked to a unified competition."""
        ...

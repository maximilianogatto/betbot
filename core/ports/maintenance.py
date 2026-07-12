from __future__ import annotations

from typing import Protocol

class MaintenancePort(Protocol):
    """Port defining database hygiene and maintenance operations."""

    def prune_old_data(
        self,
        days_threshold: int = 14,
        sent_alerts_days: int = 30,
        small_changes_days: int = 7,
    ) -> dict[str, int]:
        """Delete inactive events, old sent alerts, expired cache, and pending small changes."""
        ...

    def run_db_vacuum(self) -> bool:
        """Run VACUUM command to defragment and shrink the database file on disk."""
        ...

    def purge_expired_stats_payloads(self) -> int:
        """Purge stats cache entries that have exceeded their TTL."""
        ...

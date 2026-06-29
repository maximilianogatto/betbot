from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timedelta, timezone

from core.ports.maintenance import MaintenancePort
from adapters.storage.connection import open_connection, resolve_database_path

logger = logging.getLogger(__name__)

STATS_PAYLOAD_CACHE_MAX_ROWS = 200

class SQLiteMaintenanceAdapter(MaintenancePort):
    """Adapter implementing MaintenancePort using SQLite."""

    def prune_old_data(
        self,
        days_threshold: int = 14,
        sent_alerts_days: int = 30,
        small_changes_days: int = 7,
    ) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        cutoff_iso = (now - timedelta(days=days_threshold)).isoformat()
        sent_alerts_cutoff_iso = (now - timedelta(days=sent_alerts_days)).isoformat()
        small_changes_cutoff_iso = (now - timedelta(days=small_changes_days)).isoformat()
        now_iso = now.isoformat()

        stats = {}
        with open_connection() as conn:
            # 1. Delete inactive events older than threshold.
            cursor = conn.execute(
                "DELETE FROM events WHERE is_active = 0 AND last_seen_at < ?",
                (cutoff_iso,)
            )
            stats["active_events_pruned"] = cursor.rowcount

            # 2. Delete sent_alerts older than threshold.
            cursor = conn.execute(
                "DELETE FROM sent_alerts WHERE sent_at < ?",
                (sent_alerts_cutoff_iso,)
            )
            stats["sent_alerts_pruned"] = cursor.rowcount

            # 3. Delete expired stats payload caches.
            cursor = conn.execute(
                "DELETE FROM stats_payload_cache WHERE expires_at < ?",
                (now_iso,)
            )
            stats["expired_cache_pruned"] = cursor.rowcount

            # 4. Clean up expired live watches.
            cursor = conn.execute(
                "DELETE FROM live_watch_entries WHERE created_at < ?",
                (cutoff_iso,)
            )
            stats["expired_live_watches_pruned"] = cursor.rowcount

            # 5. Delete pending small changes older than threshold.
            cursor = conn.execute(
                "DELETE FROM small_changes WHERE status = 'pending' AND created_at < ?",
                (small_changes_cutoff_iso,)
            )
            stats["small_changes_pruned"] = cursor.rowcount

        return stats

    def run_db_vacuum(self) -> bool:
        db_path = resolve_database_path()
        try:
            # Vacuum cannot run within a transaction block, isolation_level=None enables autocommit
            conn = sqlite3.connect(db_path, timeout=30)
            conn.isolation_level = None
            conn.execute("VACUUM")
            conn.close()
            logger.info("Database VACUUM executed successfully.")
            return True
        except Exception as e:
            logger.exception("Failed to execute VACUUM: %s", e)
            return False

    def purge_expired_stats_payloads(self) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM stats_payload_cache WHERE expires_at < ?",
                (now_iso,)
            )
            deleted_expired = cursor.rowcount
            
            # Enforce cache capacity limit (FIFO 200)
            row = conn.execute("SELECT COUNT(*) AS total FROM stats_payload_cache").fetchone()
            total = int(row["total"] if row is not None else 0)
            overflow = max(0, total - STATS_PAYLOAD_CACHE_MAX_ROWS)
            if overflow > 0:
                cursor_limit = conn.execute(
                    """
                    DELETE FROM stats_payload_cache
                    WHERE cache_key IN (
                        SELECT cache_key
                        FROM stats_payload_cache
                        ORDER BY fetched_at ASC, cache_key ASC
                        LIMIT ?
                    )
                    """,
                    (overflow,)
                )
                deleted_expired += cursor_limit.rowcount
                
            return deleted_expired

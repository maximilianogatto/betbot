from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

tracking_repository_module = importlib.import_module("storage.tracking_repository")
SqliteTrackingRepository = tracking_repository_module.SqliteTrackingRepository


class PruneOldDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_db = tracking_repository_module.DB_FILE_PATH
        self.old_dir = tracking_repository_module.DATA_DIR
        self.tmp = tempfile.TemporaryDirectory()
        tracking_repository_module.DATA_DIR = Path(self.tmp.name)
        tracking_repository_module.DB_FILE_PATH = Path(self.tmp.name) / "pruning_test.sqlite3"
        self.repo = SqliteTrackingRepository()

    def tearDown(self) -> None:
        self.tmp.cleanup()
        tracking_repository_module.DB_FILE_PATH = self.old_db
        tracking_repository_module.DATA_DIR = self.old_dir

    def _add_comp(self, platform: str, ext_id: str, name: str) -> int:
        with tracking_repository_module._connect() as con:
            cur = con.execute(
                "INSERT INTO tracked_competitions (platform, competition_external_id, competition_name, source_url, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (platform, ext_id, name, "http://x", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
            )
            return int(cur.lastrowid)

    def _add_event(self, comp_id: int, ext_event_id: str, is_active: int, last_seen: datetime) -> int:
        with tracking_repository_module._connect() as con:
            cur = con.execute(
                """
                INSERT INTO active_events (
                    tracked_competition_id, platform, competition_external_id, external_event_id,
                    home, away, first_seen_at, last_seen_at, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    comp_id, "platform", "comp_ext", ext_event_id,
                    "Home", "Away", last_seen.isoformat(), last_seen.isoformat(),
                    is_active, last_seen.isoformat(), last_seen.isoformat()
                )
            )
            return int(cur.lastrowid)

    def test_pruning_deletes_only_stale_inactive_events_and_cascades(self) -> None:
        comp_id = self._add_comp("platform", "comp_ext", "Competition")

        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=20)
        fresh_time = now - timedelta(days=5)

        # 1. Inactive & Old -> should be pruned
        event_pruned = self._add_event(comp_id, "event_pruned", 0, old_time)

        # 2. Inactive & Fresh -> should NOT be pruned
        event_keep_inactive = self._add_event(comp_id, "event_keep_inactive", 0, fresh_time)

        # 3. Active & Old -> should NOT be pruned (still active)
        event_keep_active_old = self._add_event(comp_id, "event_keep_active_old", 1, old_time)

        # Add references to verify cascades
        with tracking_repository_module._connect() as con:
            # Add user event baselines
            con.execute(
                "INSERT INTO user_event_baselines (chat_id, active_event_id, baseline_set_at, updated_at) VALUES (?, ?, ?, ?)",
                (999, event_pruned, now.isoformat(), now.isoformat())
            )
            con.execute(
                "INSERT INTO user_event_baselines (chat_id, active_event_id, baseline_set_at, updated_at) VALUES (?, ?, ?, ?)",
                (999, event_keep_inactive, now.isoformat(), now.isoformat())
            )

            # Add small changes
            con.execute(
                "INSERT INTO small_changes (chat_id, active_event_id, max_change_percent, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (999, event_pruned, 10.0, now.isoformat(), now.isoformat())
            )

            # Add sent alerts
            con.execute(
                "INSERT INTO sent_alerts (chat_id, active_event_id, alert_type, sent_at) VALUES (?, ?, ?, ?)",
                (999, event_pruned, "odds_change", old_time.isoformat())
            )
            # Fresh sent alert that shouldn't be pruned directly (associated with keep_inactive event)
            con.execute(
                "INSERT INTO sent_alerts (chat_id, active_event_id, alert_type, sent_at) VALUES (?, ?, ?, ?)",
                (999, event_keep_inactive, "odds_change", fresh_time.isoformat())
            )

            # Add expired stats cache
            con.execute(
                "INSERT INTO stats_payload_cache (cache_key, payload_json, fetched_at, expires_at) VALUES (?, ?, ?, ?)",
                ("expired_key", "{}", now.isoformat(), old_time.isoformat())
            )
            # Valid stats cache
            con.execute(
                "INSERT INTO stats_payload_cache (cache_key, payload_json, fetched_at, expires_at) VALUES (?, ?, ?, ?)",
                ("valid_key", "{}", now.isoformat(), (now + timedelta(days=1)).isoformat())
            )

        # Run pruning
        stats = self.repo.prune_old_data(days_threshold=14)

        # Verify pruned stats returned
        self.assertEqual(stats["active_events_pruned"], 1)
        self.assertEqual(stats["expired_cache_pruned"], 1)
        self.assertNotIn("vacuum_executed", stats)

        # Verify active_events
        with tracking_repository_module._connect() as con:
            events = {r["external_event_id"] for r in con.execute("SELECT external_event_id FROM active_events")}
            self.assertNotIn("event_pruned", events)
            self.assertIn("event_keep_inactive", events)
            self.assertIn("event_keep_active_old", events)

            # Verify baseline cascades
            baselines = {r["active_event_id"] for r in con.execute("SELECT active_event_id FROM user_event_baselines")}
            self.assertNotIn(event_pruned, baselines)
            self.assertIn(event_keep_inactive, baselines)

            # Verify small changes cascades
            small_changes = {r["active_event_id"] for r in con.execute("SELECT active_event_id FROM small_changes")}
            self.assertNotIn(event_pruned, small_changes)

            # Verify sent alerts cascades/pruning
            sent_alerts = {r["active_event_id"] for r in con.execute("SELECT active_event_id FROM sent_alerts")}
            self.assertNotIn(event_pruned, sent_alerts)
            self.assertIn(event_keep_inactive, sent_alerts)

            # Verify cache pruning
            cache = {r["cache_key"] for r in con.execute("SELECT cache_key FROM stats_payload_cache")}
            self.assertNotIn("expired_key", cache)
            self.assertIn("valid_key", cache)

    def test_run_db_vacuum_shrinks_file(self) -> None:
        import os

        # Connect and create a dummy table to fill with large data
        with tracking_repository_module._connect() as con:
            con.execute("CREATE TABLE dummy_vacuum (val TEXT)")
            # Insert 1000 rows of large text
            large_text = "a" * 1024
            con.executemany("INSERT INTO dummy_vacuum (val) VALUES (?)", [(large_text,)] * 1000)

        # Get size before vacuum
        size_before_delete = os.path.getsize(tracking_repository_module.DB_FILE_PATH)

        # Drop the table so space is marked as free/deleted inside SQLite
        with tracking_repository_module._connect() as con:
            con.execute("DROP TABLE dummy_vacuum")

        # Run VACUUM
        success = self.repo.run_db_vacuum()
        self.assertTrue(success)

        # File size should now be physically smaller
        size_after_vacuum = os.path.getsize(tracking_repository_module.DB_FILE_PATH)
        self.assertLess(size_after_vacuum, size_before_delete)


if __name__ == "__main__":
    unittest.main()

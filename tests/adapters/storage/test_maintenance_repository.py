import unittest
import os
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from adapters.storage.maintenance import SQLiteMaintenanceAdapter

class MaintenanceRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "test_db.sqlite3"
        self._prev_db_path = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(db_path)

        self.adapter = SQLiteMaintenanceAdapter()
        with open_connection() as conn:
            initialize_schema(conn)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        if self._prev_db_path is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db_path

    def test_prune_old_data(self) -> None:
        now = datetime.now(timezone.utc)
        old_iso = (now - timedelta(days=20)).isoformat()
        recent_iso = (now - timedelta(days=2)).isoformat()
        
        with open_connection() as conn:
            # 1. Setup events (1 active, 1 inactive+old, 1 inactive+recent)
            conn.execute(
                """
                INSERT INTO competitions(id, platform, external_id, name, source_url, created_at, updated_at)
                VALUES (1, 'bet365', 'comp-1', 'La Liga', 'http://url', '2026', '2026')
                """
            )
            conn.execute(
                """
                INSERT INTO events(id, competition_id, platform, external_event_id, home, away, is_active, first_seen_at, last_seen_at, created_at, updated_at)
                VALUES (1, 1, 'bet365', 'evt-1', 'A', 'B', 0, ?, ?, ?, ?)
                """,
                (old_iso, old_iso, old_iso, old_iso)
            )
            conn.execute(
                """
                INSERT INTO events(id, competition_id, platform, external_event_id, home, away, is_active, first_seen_at, last_seen_at, created_at, updated_at)
                VALUES (2, 1, 'bet365', 'evt-2', 'C', 'D', 0, ?, ?, ?, ?)
                """,
                (recent_iso, recent_iso, recent_iso, recent_iso)
            )
            conn.execute(
                """
                INSERT INTO events(id, competition_id, platform, external_event_id, home, away, is_active, first_seen_at, last_seen_at, created_at, updated_at)
                VALUES (3, 1, 'bet365', 'evt-3', 'E', 'F', 1, ?, ?, ?, ?)
                """,
                (old_iso, old_iso, old_iso, old_iso)
            )

            # 2. Setup sent_alerts (1 old, 1 recent)
            conn.execute("INSERT INTO sent_alerts(chat_id, event_id, alert_type, sent_at) VALUES (123, 3, 'fluctuation', ?)", (old_iso,))
            conn.execute("INSERT INTO sent_alerts(chat_id, event_id, alert_type, sent_at) VALUES (123, 3, 'kickoff', ?)", (recent_iso,))

            # 3. Setup stats_payload_cache (1 old, 1 recent)
            conn.execute("INSERT INTO stats_payload_cache(cache_key, payload_json, fetched_at, expires_at) VALUES ('k1', '{}', ?, ?)", (old_iso, old_iso))
            conn.execute("INSERT INTO stats_payload_cache(cache_key, payload_json, fetched_at, expires_at) VALUES ('k2', '{}', ?, ?)", (recent_iso, recent_iso))

            # 4. Setup live_watch_entries (1 old, 1 recent)
            conn.execute("INSERT INTO live_watch_entries(chat_id, chat_local_id, home, away, status, created_at) VALUES (123, 1, 'A', 'B', 'watching', ?)", (old_iso,))
            conn.execute("INSERT INTO live_watch_entries(chat_id, chat_local_id, home, away, status, created_at) VALUES (123, 2, 'C', 'D', 'watching', ?)", (recent_iso,))

            # 5. Setup small_changes (1 old, 1 recent)
            conn.execute(
                """
                INSERT INTO small_changes(chat_id, event_id, prev_home, cur_home, max_change_percent, status, created_at, updated_at)
                VALUES (123, 3, 1.8, 1.9, 5.0, 'pending', ?, ?)
                """,
                (old_iso, old_iso)
            )
            conn.execute(
                """
                INSERT INTO small_changes(chat_id, event_id, prev_home, cur_home, max_change_percent, status, created_at, updated_at)
                VALUES (123, 2, 1.8, 1.9, 5.0, 'pending', ?, ?)
                """,
                (recent_iso, recent_iso)
            )

        # Run prune
        res = self.adapter.prune_old_data(days_threshold=14, sent_alerts_days=14, small_changes_days=14)
        self.assertEqual(res.get("active_events_pruned"), 1)
        self.assertEqual(res.get("sent_alerts_pruned"), 1)
        self.assertEqual(res.get("expired_cache_pruned"), 2) # both k1 and k2 are in the past relative to now_iso
        self.assertEqual(res.get("expired_live_watches_pruned"), 1)
        self.assertEqual(res.get("small_changes_pruned"), 1)

    def test_run_db_vacuum(self) -> None:
        success = self.adapter.run_db_vacuum()
        self.assertTrue(success)

    def test_purge_expired_stats_payloads_and_fifo(self) -> None:
        now = datetime.now(timezone.utc)
        old_iso = (now - timedelta(days=2)).isoformat()
        future_iso = (now + timedelta(days=2)).isoformat()
        
        with open_connection() as conn:
            # 1. Insert expired payload
            conn.execute("INSERT INTO stats_payload_cache(cache_key, payload_json, fetched_at, expires_at) VALUES ('k-exp', '{}', ?, ?)", (old_iso, old_iso))
            
            # 2. Insert 205 future payloads to test FIFO limit
            for i in range(205):
                conn.execute("INSERT INTO stats_payload_cache(cache_key, payload_json, fetched_at, expires_at) VALUES (?, '{}', ?, ?)", (f"k-{i}", old_iso, future_iso))
                
        # Total rows is 206 (1 expired + 205 valid)
        # Pruning expired deletes 1.
        # Remaining valid is 205.
        # FIFO limit is 200, so overflow is 5.
        # Total deleted should be 1 (expired) + 5 (FIFO limit) = 6!
        deleted = self.adapter.purge_expired_stats_payloads()
        self.assertEqual(deleted, 6)
        
        with open_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM stats_payload_cache").fetchone()[0]
            self.assertEqual(count, 200)

    def test_stats_payload_cache_get_set_roundtrip(self) -> None:
        # Gap greenfield: los stats providers usan get/set_cached_stats_payload en
        # runtime (anti-ban/latencia). Faltaban en el facade → AttributeError.
        self.assertIsNone(self.adapter.get_cached_stats_payload("k1"))
        self.adapter.set_cached_stats_payload("k1", {"foo": "bar", "n": 3}, ttl_seconds=60)
        self.assertEqual(self.adapter.get_cached_stats_payload("k1"), {"foo": "bar", "n": 3})
        # Vencido → None.
        with open_connection() as conn:
            past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            conn.execute(
                "INSERT INTO stats_payload_cache (cache_key, payload_json, fetched_at, expires_at) "
                "VALUES ('old', '{\"a\": 1}', ?, ?)",
                (past, past),
            )
        self.assertIsNone(self.adapter.get_cached_stats_payload("old"))

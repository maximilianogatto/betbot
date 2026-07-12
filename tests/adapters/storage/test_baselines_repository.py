import unittest
import sqlite3
import json
import os
import tempfile
from pathlib import Path

from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from adapters.storage.baselines import SQLiteBaselinesAdapter
from core.models import EventBaseline, SmallChangeRecord

class BaselinesRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "test_db.sqlite3"
        self._prev_db_path = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(db_path)

        self.adapter = SQLiteBaselinesAdapter()
        with open_connection() as conn:
            initialize_schema(conn)
            
            # Setup dummy competition
            conn.execute(
                """
                INSERT INTO competitions(id, platform, external_id, name, source_url, created_at, updated_at)
                VALUES (1, 'bet365', 'comp-1', 'La Liga', 'http://url', '2026', '2026')
                """
            )
            # Setup events
            conn.execute(
                """
                INSERT INTO events(id, competition_id, platform, external_event_id, home, away, is_active, first_seen_at, last_seen_at, created_at, updated_at)
                VALUES (100, 1, 'bet365', 'evt-100', 'Real Madrid', 'Barcelona', 1, '2026', '2026', '2026', '2026')
                """
            )
            # Setup subscription
            conn.execute(
                """
                INSERT INTO subscriptions(chat_id, competition_id, enabled, created_at, updated_at)
                VALUES (123, 1, 1, '2026', '2026')
                """
            )

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        if self._prev_db_path is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db_path

    def test_event_baselines_both_signatures(self) -> None:
        chat_id = 123
        
        # 1. Port signature: upsert_event_baseline
        self.adapter.upsert_event_baseline(
            chat_id,
            100,
            1,
            "evt-100",
            1.8,
            3.4,
            4.2,
            '{"1x2": {}}'
        )
        
        # Port signature: get_event_baseline
        base = self.adapter.get_event_baseline(chat_id, 100)
        self.assertIsNotNone(base)
        self.assertEqual(base.baseline_home, 1.8)
        self.assertEqual(base.external_event_id, "evt-100")
        
        # 2. Legacy signature: upsert_event_baseline (keyword arguments after external_event_id)
        self.adapter.upsert_event_baseline(
            chat_id,
            1,
            "evt-100",
            baseline_home=2.0,
            baseline_draw=3.5,
            baseline_away=4.0,
            baseline_markets_json='{"1x2": {"updated": true}}'
        )
        
        # Legacy signature: get_event_baseline
        base_legacy = self.adapter.get_event_baseline(chat_id, 1, "evt-100")
        self.assertIsNotNone(base_legacy)
        self.assertEqual(base_legacy.baseline_home, 2.0)

    def test_initialize_event_baselines(self) -> None:
        chat_id = 123
        events = [
            {
                "id": 100,
                "competition_id": 1,
                "odds_home": 1.9,
                "odds_draw": 3.3,
                "odds_away": 4.1,
                "markets_json": None
            }
        ]
        
        initialized = self.adapter.initialize_event_baselines(chat_id, 1, events)
        self.assertEqual(initialized, 1)
        
        base = self.adapter.get_event_baseline(chat_id, 100)
        self.assertIsNotNone(base)
        self.assertEqual(base.baseline_home, 1.9)

    def test_small_changes_flow(self) -> None:
        chat_id = 123
        
        # 1. Port signature: upsert_small_change
        self.adapter.upsert_small_change(
            chat_id,
            100,
            1,
            "evt-100",
            "La Liga",
            "Real Madrid",
            "Barcelona",
            "2026",
            "20:00",
            "2026",
            1.8,
            3.4,
            4.2,
            1.9,
            3.4,
            4.0,
            5.5,
            None,
            "pending"
        )
        
        pending = self.adapter.list_pending_small_changes(chat_id)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].max_percent_change, 5.5)
        self.assertEqual(pending[0].home, "Real Madrid")
        
        # 2. Legacy signature: upsert_small_change (keyword arguments after external_event_id)
        self.adapter.upsert_small_change(
            chat_id,
            1,
            "evt-100",
            home="Real Madrid",
            away="Barcelona",
            scheduled_label_date="2026",
            scheduled_label_time="20:00",
            baseline_home=1.8,
            baseline_draw=3.4,
            baseline_away=4.2,
            current_home=2.0,
            current_draw=3.4,
            current_away=3.9,
            max_percent_change=11.1,
            status="pending"
        )
        
        pending_after = self.adapter.list_pending_small_changes(chat_id)
        self.assertEqual(len(pending_after), 1)
        self.assertEqual(pending_after[0].max_percent_change, 11.1)
        
        # Test confirm_small_change
        change_id = pending_after[0].id
        confirmed_rec = self.adapter.confirm_small_change(chat_id, change_id)
        self.assertEqual(confirmed_rec.status, "confirmed")
        
        # Test confirm_all_small_changes
        # Create another pending change
        self.adapter.upsert_small_change(
            chat_id,
            100,
            1,
            "evt-100",
            "La Liga",
            "Real Madrid",
            "Barcelona",
            "2026",
            "20:00",
            "2026",
            1.8,
            3.4,
            4.2,
            2.2,
            3.4,
            3.8,
            22.2,
            None,
            "pending"
        )
        
        all_confirmed = self.adapter.confirm_all_small_changes(chat_id)
        self.assertEqual(len(all_confirmed), 1)
        self.assertEqual(all_confirmed[0].status, "confirmed")
        
        # Test resolve_small_change_with_current_baseline (port signature)
        self.adapter.upsert_small_change(
            chat_id,
            100,
            1,
            "evt-100",
            "La Liga",
            "Real Madrid",
            "Barcelona",
            "2026",
            "20:00",
            "2026",
            1.8,
            3.4,
            4.2,
            2.2,
            3.4,
            3.8,
            22.2,
            None,
            "pending"
        )
        self.adapter.resolve_small_change_with_current_baseline(chat_id, 100)
        self.assertEqual(len(self.adapter.list_pending_small_changes(chat_id)), 0)
        
        # Test resolve_small_change_with_current_baseline (legacy signature)
        self.adapter.upsert_small_change(
            chat_id,
            100,
            1,
            "evt-100",
            "La Liga",
            "Real Madrid",
            "Barcelona",
            "2026",
            "20:00",
            "2026",
            1.8,
            3.4,
            4.2,
            2.2,
            3.4,
            3.8,
            22.2,
            None,
            "pending"
        )
        self.adapter.resolve_small_change_with_current_baseline(chat_id, 1, "evt-100")
        self.assertEqual(len(self.adapter.list_pending_small_changes(chat_id)), 0)

    def test_sent_alerts_both_signatures(self) -> None:
        chat_id = 123
        
        # 1. Port signature
        self.assertFalse(self.adapter.has_sent_alert(chat_id, 100, "fluctuation"))
        self.adapter.mark_sent_alerts(chat_id, 100, "fluctuation")
        self.assertTrue(self.adapter.has_sent_alert(chat_id, 100, "fluctuation"))
        
        # 2. Legacy signature
        self.assertFalse(self.adapter.has_sent_alert(chat_id, 1, "evt-100", "kickoff"))
        self.adapter.mark_sent_alert(chat_id, 1, "evt-100", "kickoff")
        self.assertTrue(self.adapter.has_sent_alert(chat_id, 1, "evt-100", "kickoff"))

import unittest
import sqlite3
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from adapters.storage.events import SQLiteEventsAdapter
from core.models import ActiveEventRecord, ActiveEventUpsert

class EventsRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "test_db.sqlite3"
        self._prev_db_path = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(db_path)

        self.adapter = SQLiteEventsAdapter()
        with open_connection() as conn:
            initialize_schema(conn)
            
            # Setup dummy competition
            conn.execute(
                """
                INSERT INTO competitions(id, platform, external_id, name, source_url, created_at, updated_at)
                VALUES (1, 'bet365', 'comp-1', 'La Liga', 'http://url', '2026', '2026')
                """
            )
            # Setup unified competition
            conn.execute(
                """
                INSERT INTO unified_competitions(id, public_id, name, created_at, updated_at)
                VALUES (10, 'la-liga', 'La Liga Canonical', '2026', '2026')
                """
            )
            conn.execute("UPDATE competitions SET unified_competition_id = 10 WHERE id = 1")
            
            # Setup chat subscription
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

    def test_upsert_and_retrieve_events(self) -> None:
        upsert_data = [
            ActiveEventUpsert(
                external_event_id="evt-1",
                home="Real Madrid",
                away="Barcelona",
                scheduled_label_date="2026-07-01",
                scheduled_label_time="20:00",
                scheduled_at=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                odds_home=1.8,
                odds_draw=3.4,
                odds_away=4.2,
                event_url="http://real-barca"
            ),
            ActiveEventUpsert(
                external_event_id="evt-2",
                home="Atletico",
                away="Sevilla",
                scheduled_label_date="2026-07-01",
                scheduled_label_time="18:00",
                scheduled_at=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                odds_home=2.0,
                odds_draw=3.2,
                odds_away=3.8,
                event_url="http://atletico-sevilla"
            )
        ]
        
        records = self.adapter.upsert_active_events(1, upsert_data)
        self.assertEqual(len(records), 2)
        
        # Check properties of Real Madrid vs Barcelona
        real_barca = [r for r in records if r.external_event_id == "evt-1"][0]
        self.assertEqual(real_barca.home, "Real Madrid")
        self.assertEqual(real_barca.away, "Barcelona")
        self.assertEqual(real_barca.odds_home, 1.8)
        self.assertEqual(real_barca.competition_external_id, "comp-1")
        self.assertFalse(real_barca.alerted)
        self.assertTrue(real_barca.is_active)
        
        # Test get_active_events
        active = self.adapter.get_active_events(1)
        self.assertEqual(len(active), 2)
        
        # Test get_active_events limit
        active_limited = self.adapter.get_active_events(1, limit=1)
        self.assertEqual(len(active_limited), 1)

    def test_get_all_active_events_with_league(self) -> None:
        upsert_data = [
            ActiveEventUpsert(
                external_event_id="evt-1",
                home="Real Madrid",
                away="Barcelona",
                scheduled_label_date="2026-07-01",
                scheduled_label_time="20:00",
                scheduled_at=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                odds_home=1.8,
                odds_draw=3.4,
                odds_away=4.2
            )
        ]
        self.adapter.upsert_active_events(1, upsert_data)
        
        events_with_league = self.adapter.get_all_active_events_with_league(123)
        self.assertEqual(len(events_with_league), 1)
        self.assertEqual(events_with_league[0]["league_name"], "La Liga")
        self.assertEqual(events_with_league[0]["home"], "Real Madrid")

    def test_get_active_events_for_unified_competition(self) -> None:
        upsert_data = [
            ActiveEventUpsert(
                external_event_id="evt-1",
                home="Real Madrid",
                away="Barcelona",
                scheduled_label_date="2026-07-01",
                scheduled_label_time="20:00",
                scheduled_at=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                odds_home=1.8,
                odds_draw=3.4,
                odds_away=4.2
            )
        ]
        self.adapter.upsert_active_events(1, upsert_data)
        
        unified_events = self.adapter.get_active_events_for_unified_competition(10)
        self.assertEqual(len(unified_events), 1)
        self.assertEqual(unified_events[0].home, "Real Madrid")

    def test_get_earliest_kickoffs_both_signatures(self) -> None:
        kickoff_time = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        upsert_data = [
            ActiveEventUpsert(
                external_event_id="evt-1",
                home="Real Madrid",
                away="Barcelona",
                scheduled_label_date="2026-07-01",
                scheduled_label_time="20:00",
                scheduled_at=kickoff_time,
                odds_home=1.8,
                odds_draw=3.4,
                odds_away=4.2
            )
        ]
        self.adapter.upsert_active_events(1, upsert_data)
        
        # 1. Legacy signature: list of competition IDs -> dict[int, str|None]
        legacy_res = self.adapter.get_earliest_kickoffs([1, 99])
        self.assertEqual(legacy_res[1], kickoff_time)
        self.assertIsNone(legacy_res[99])
        
        # 2. Port signature: minutes threshold -> list of dicts
        port_res = self.adapter.get_earliest_kickoffs(15)
        self.assertEqual(len(port_res), 1)
        self.assertEqual(port_res[0]["external_event_id"], "evt-1")

    def test_remove_missing_events(self) -> None:
        upsert_data = [
            ActiveEventUpsert(
                external_event_id="evt-1",
                home="Real Madrid",
                away="Barcelona",
                scheduled_label_date="2026-07-01",
                scheduled_label_time="20:00",
                scheduled_at=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                odds_home=1.8,
                odds_draw=3.4,
                odds_away=4.2
            )
        ]
        self.adapter.upsert_active_events(1, upsert_data)
        
        # Cycle 1: evt-1 is missing. It should increment missing_seen_count to 1.
        removed_count = self.adapter.remove_missing_events(1, [], max_missing_cycles=3)
        self.assertEqual(removed_count, 0) # Not yet marked inactive
        
        with open_connection() as conn:
            missing_count = conn.execute("SELECT missing_seen_count FROM events WHERE id = 1").fetchone()[0]
            self.assertEqual(missing_count, 1)
            
        # Cycle 2: still missing. It should increment to 2.
        self.adapter.remove_missing_events(1, [], max_missing_cycles=3)
        # Cycle 3: still missing. It should hit threshold (3) and mark is_active=0.
        removed_count = self.adapter.remove_missing_events(1, [], max_missing_cycles=3)
        self.assertEqual(removed_count, 1)
        
        with open_connection() as conn:
            active_flag = conn.execute("SELECT is_active FROM events WHERE id = 1").fetchone()[0]
            self.assertEqual(active_flag, 0)

    def test_remove_past_events_and_mark_alerted(self) -> None:
        past_kickoff = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        upsert_data = [
            ActiveEventUpsert(
                external_event_id="evt-1",
                home="Real Madrid",
                away="Barcelona",
                scheduled_label_date="2026-07-01",
                scheduled_label_time="20:00",
                scheduled_at=past_kickoff,
                odds_home=1.8,
                odds_draw=3.4,
                odds_away=4.2
            )
        ]
        records = self.adapter.upsert_active_events(1, upsert_data)
        self.assertEqual(len(records), 1)
        event_id = records[0].id
        
        # Test remove past events (older than 4 hours)
        removed = self.adapter.remove_past_events(hours_ago=4)
        self.assertEqual(removed, 1)
        
        # Verify is_active=0 in DB
        with open_connection() as conn:
            active_flag = conn.execute("SELECT is_active FROM events WHERE id = ?", (event_id,)).fetchone()[0]
            self.assertEqual(active_flag, 0)
            
        # Reset is_active and test mark alerted
        with open_connection() as conn:
            conn.execute("UPDATE events SET is_active = 1 WHERE id = ?", (event_id,))
            
        self.adapter.mark_events_alerted([event_id])
        
        # Verify reminder_sent_at is set
        with open_connection() as conn:
            reminder_sent = conn.execute("SELECT reminder_sent_at FROM events WHERE id = ?", (event_id,)).fetchone()[0]
            self.assertIsNotNone(reminder_sent)

    def test_get_active_events_only_future(self) -> None:
        # Paridad con el legacy: only_future devuelve futuros + sin horario y
        # descarta pasados. Lo usa el learner de unificación de ligas en prod.
        now = datetime.now(timezone.utc)

        def _ev(eid, when):
            return ActiveEventUpsert(
                external_event_id=eid, home="H", away="A",
                scheduled_label_date=None, scheduled_label_time=None,
                scheduled_at=when, odds_home=1.5, odds_draw=3.0, odds_away=5.0,
            )

        self.adapter.upsert_active_events(1, [
            _ev("past", (now - timedelta(days=1)).isoformat()),
            _ev("future", (now + timedelta(days=1)).isoformat()),
            _ev("unscheduled", None),
        ])

        # Sin only_future: los 3.
        self.assertEqual(len(self.adapter.get_active_events(1)), 3)
        # Con only_future: futuro + sin horario, el pasado se filtra.
        future_ids = {e.external_event_id for e in self.adapter.get_active_events(1, only_future=True)}
        self.assertEqual(future_ids, {"future", "unscheduled"})

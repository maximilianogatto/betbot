import unittest
import os
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from adapters.storage.live_watch import SQLiteLiveWatchAdapter
from core.models import LiveWatchEntry, LiveWatchSettings

class LiveWatchRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "test_db.sqlite3"
        self._prev_db_path = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(db_path)

        self.adapter = SQLiteLiveWatchAdapter()
        with open_connection() as conn:
            initialize_schema(conn)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        if self._prev_db_path is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db_path

    def test_live_watch_basic_flow_and_both_signatures(self) -> None:
        chat_id = 123
        
        # 1. Port signature: add_live_watch
        entry1 = self.adapter.add_live_watch(
            chat_id,
            "Real Madrid",
            "Barcelona",
            "La Liga",
            "Watch this!",
            "2026-06-29T20:00:00Z",
            1001
        )
        self.assertEqual(entry1.home, "Real Madrid")
        self.assertEqual(entry1.chat_local_id, 1001)
        self.assertEqual(entry1.status, "watching")
        
        # Port signature: get_live_watch (1 argument)
        entry_fetched = self.adapter.get_live_watch(entry1.id)
        self.assertIsNotNone(entry_fetched)
        self.assertEqual(entry_fetched.chat_local_id, 1001)

        # 2. Legacy signature: add_live_watch (kwargs)
        entry2 = self.adapter.add_live_watch(
            chat_id,
            home="Man City",
            away="Man United",
            league_hint="Premier League",
            note="Big derby",
            kickoff_at="2026-06-30T19:00:00Z"
        )
        self.assertEqual(entry2.home, "Man City")
        # Legacy signature: get_live_watch (2 arguments)
        entry2_fetched = self.adapter.get_live_watch(chat_id, entry2.id)
        self.assertIsNotNone(entry2_fetched)
        self.assertEqual(entry2_fetched.chat_local_id, 1002)

        # get_live_watch_by_local_id
        entry_by_local = self.adapter.get_live_watch_by_local_id(chat_id, 1001)
        self.assertIsNotNone(entry_by_local)
        self.assertEqual(entry_by_local.home, "Real Madrid")

        # list_live_watches
        watches = self.adapter.list_live_watches(chat_id)
        self.assertEqual(len(watches), 2)
        
        active_watches = self.adapter.list_all_active_live_watches()
        self.assertEqual(len(active_watches), 2)

    def test_live_watch_mark_fired_and_seen_states(self) -> None:
        chat_id = 456
        entry = self.adapter.add_live_watch(chat_id, "Ajax", "PSV", chat_local_id=1)
        
        # 1. Port signature: mark_live_watch_prematch_fired
        self.adapter.mark_live_watch_prematch_fired(entry.id, ["bet365", "novibet"])
        entry_pm = self.adapter.get_live_watch(entry.id)
        self.assertIsNotNone(entry_pm)
        self.assertEqual(entry_pm.prematch_fired_platforms, "bet365,novibet")
        self.assertEqual(entry_pm.fired_odds_mask, 1 | 64) # 1 for bet365, 64 for novibet

        # 2. Legacy signature: mark_live_watch_prematch_fired
        self.adapter.mark_live_watch_prematch_fired(entry.id, platform="betano", event_id="betano-123")
        entry_pm_leg = self.adapter.get_live_watch(entry.id)
        self.assertIsNotNone(entry_pm_leg)
        self.assertEqual(entry_pm_leg.prematch_fired_platforms, "bet365,novibet,betano")
        self.assertEqual(entry_pm_leg.fired_odds_mask, 1 | 64 | 32)
        self.assertEqual(entry_pm_leg.matched_event_id, "betano-123")

        # Legacy mark_live_watch_prematch_seen
        self.adapter.mark_live_watch_prematch_seen(entry.id, platform="betsson", event_id="betsson-456")
        entry_seen = self.adapter.get_live_watch(entry.id)
        self.assertEqual(entry_seen.prematch_platform, "betsson")

        # 3. Port signature: mark_live_watch_fired
        self.adapter.mark_live_watch_fired(entry.id, ["codere"], {"codere": {"goals": 1}})
        entry_f = self.adapter.get_live_watch(entry.id)
        self.assertEqual(entry_f.status, "watching")
        self.assertEqual(entry_f.fired_platforms, "codere")
        self.assertEqual(entry_f.fired_odds_mask, 101) # accumulated mask
        self.assertEqual(entry_f.live_state, {"codere": {"goals": 1}})

        # 4. Legacy signature: mark_live_watch_fired
        # Reset to watching for test
        with open_connection() as conn:
            conn.execute("UPDATE live_watch_entries SET status='watching', fired_platforms=NULL, fired_odds_mask=0 WHERE id=?", (entry.id,))
            
        self.adapter.mark_live_watch_fired(entry.id, platform="bet365", event_id="b365-1", minute="45")
        entry_f_leg = self.adapter.get_live_watch(entry.id)
        self.assertEqual(entry_f_leg.status, "watching")
        self.assertEqual(entry_f_leg.fired_platforms, "bet365")
        self.assertEqual(entry_f_leg.fired_odds_mask, 1)
        self.assertEqual(entry_f_leg.matched_minute, "45")

        # countdown fired
        self.adapter.mark_live_watch_countdown_fired(entry.id)
        entry_cd = self.adapter.get_live_watch(entry.id)
        self.assertIsNotNone(entry_cd.countdown_fired_at)

        # 5. Port signature: update_live_watch_platform_state
        self.adapter.update_live_watch_platform_state(entry.id, "bplay", {"score": "2-1"})
        entry_state = self.adapter.get_live_watch(entry.id)
        self.assertEqual(entry_state.live_state, {"codere": {"goals": 1}, "bplay": {"score": "2-1"}})

        # 6. Legacy signature: update_live_watch_platform_state
        self.adapter.update_live_watch_platform_state(entry.id, platform="codere", state={"score": "3-1"})
        entry_state_leg = self.adapter.get_live_watch(entry.id)
        self.assertEqual(entry_state_leg.live_state, {"bplay": {"score": "2-1"}, "codere": {"score": "3-1"}})

    def test_live_watch_settings(self) -> None:
        chat_id = 999
        
        # Default settings
        settings = self.adapter.get_live_watch_settings(chat_id)
        self.assertTrue(settings.alert_goals)
        self.assertTrue(settings.alert_red_cards)
        self.assertFalse(settings.alert_yellow_cards)

        # Port/Legacy: set_live_watch_settings
        self.adapter.set_live_watch_settings(chat_id, alert_goals=False, alert_yellow_cards=True)
        updated = self.adapter.get_live_watch_settings(chat_id)
        self.assertFalse(updated.alert_goals)
        self.assertTrue(updated.alert_red_cards)
        self.assertTrue(updated.alert_yellow_cards)

    def test_live_watch_deletion_and_purge(self) -> None:
        chat_id = 888
        e1 = self.adapter.add_live_watch(chat_id, "A", "B", chat_local_id=1)
        e2 = self.adapter.add_live_watch(chat_id, "C", "D", chat_local_id=2)
        
        # remove_live_watch
        removed = self.adapter.remove_live_watch(chat_id, e1.id)
        self.assertTrue(removed)
        self.assertIsNone(self.adapter.get_live_watch(e1.id))

        # remove_live_watch_by_local_id
        removed_local = self.adapter.remove_live_watch_by_local_id(chat_id, 2)
        self.assertTrue(removed_local)
        self.assertIsNone(self.adapter.get_live_watch(e2.id))

        # clear_live_watches
        e3 = self.adapter.add_live_watch(chat_id, "E", "F", chat_local_id=3)
        cleared = self.adapter.clear_live_watches(chat_id)
        self.assertEqual(cleared, 1)

        # purge_expired_live_watches
        e4 = self.adapter.add_live_watch(chat_id, "G", "H", chat_local_id=4)
        self.adapter.mark_live_watch_fired(e4.id, ["bet365"])
        old_created_at = (datetime.now(timezone.utc) - timedelta(hours=17)).isoformat()
        with open_connection() as conn:
            conn.execute(
                "UPDATE live_watch_entries SET created_at = ? WHERE id = ?",
                (old_created_at, e4.id),
            )
        purged = self.adapter.purge_expired_live_watches()
        self.assertEqual(purged, 1)
        self.assertIsNone(self.adapter.get_live_watch(e4.id))

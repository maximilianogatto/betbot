from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

trm = importlib.import_module("storage.tracking_repository")


class ReminderFlagsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_db = trm.DB_FILE_PATH
        self.old_dir = trm.DATA_DIR
        self.tmp = tempfile.TemporaryDirectory()
        trm.DATA_DIR = Path(self.tmp.name)
        trm.DB_FILE_PATH = Path(self.tmp.name) / "t.sqlite3"
        self.repo = trm.SqliteTrackingRepository()
        self.now = "2026-01-01T00:00:00+00:00"

    def tearDown(self) -> None:
        self.tmp.cleanup()
        trm.DB_FILE_PATH = self.old_db
        trm.DATA_DIR = self.old_dir

    def _comp(self) -> int:
        with trm._connect() as con:
            cur = con.execute(
                "INSERT INTO tracked_competitions (platform, competition_external_id, competition_name, source_url, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("1xbet_http", "L1", "Liga", "http://x", self.now, self.now),
            )
            return int(cur.lastrowid)

    def _event(self, comp_id: int, ext_id: str) -> None:
        with trm._connect() as con:
            con.execute(
                "INSERT INTO active_events (tracked_competition_id, platform, competition_external_id, external_event_id, "
                "home, away, first_seen_at, last_seen_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (comp_id, "1xbet_http", "L1", ext_id, "A", "B", self.now, self.now, self.now, self.now),
            )

    def test_league_flag_default_off_and_toggle(self) -> None:
        cid = self._comp()
        self.assertFalse(self.repo.competition_reminders_enabled(cid))  # default OFF
        self.repo.set_competition_reminders(cid, True)
        self.assertTrue(self.repo.competition_reminders_enabled(cid))
        self.repo.set_competition_reminders(cid, False)
        self.assertFalse(self.repo.competition_reminders_enabled(cid))

    def test_match_flag_default_off_and_toggle(self) -> None:
        cid = self._comp()
        self._event(cid, "ev1")
        self._event(cid, "ev2")
        self.assertEqual(self.repo.event_reminder_enabled_ids(cid), set())  # default OFF
        self.repo.set_event_reminder(cid, "ev1", True)
        self.assertEqual(self.repo.event_reminder_enabled_ids(cid), {"ev1"})
        self.repo.set_event_reminder(cid, "ev1", False)
        self.assertEqual(self.repo.event_reminder_enabled_ids(cid), set())

    def test_gating_filter_logic(self) -> None:
        # Replicates the tracking.py gate: default off -> nothing; league on -> all; match on -> that one.
        class M:
            def __init__(self, fid):
                self.fixture_id = fid
        due = [M("ev1"), M("ev2")]

        def gate(due, league_on, enabled_ids):
            if due and not league_on:
                return [m for m in due if m.fixture_id in enabled_ids]
            return due

        self.assertEqual(gate(due, False, set()), [])            # default off
        self.assertEqual(len(gate(due, True, set())), 2)         # league on -> all
        self.assertEqual([m.fixture_id for m in gate(due, False, {"ev2"})], ["ev2"])  # one match


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema


class ReminderFlagsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp.name) / "t.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.repo = SqliteStorage()
        self.now = "2026-01-01T00:00:00+00:00"

    def tearDown(self) -> None:
        self.tmp.cleanup()
        if self.old_db is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self.old_db

    def _comp(self) -> int:
        with open_connection() as con:
            cur = con.execute(
                "INSERT INTO competitions (platform, external_id, name, source_url, enabled, consecutive_unavailable_refreshes, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 1, 0, ?, ?)",
                ("1xbet_http", "L1", "Liga", "http://x", self.now, self.now),
            )
            return int(cur.lastrowid)

    def _event(self, comp_id: int, ext_id: str) -> None:
        with open_connection() as con:
            con.execute(
                "INSERT INTO events (competition_id, platform, external_event_id, "
                "home, away, is_active, first_seen_at, last_seen_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                (comp_id, "1xbet_http", ext_id, "A", "B", self.now, self.now, self.now, self.now),
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

from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

tracking_repository_module = importlib.import_module("storage.tracking_repository")
SqliteTrackingRepository = tracking_repository_module.SqliteTrackingRepository


class CanonicalLeagueRepoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_db = tracking_repository_module.DB_FILE_PATH
        self.old_dir = tracking_repository_module.DATA_DIR
        self.tmp = tempfile.TemporaryDirectory()
        tracking_repository_module.DATA_DIR = Path(self.tmp.name)
        tracking_repository_module.DB_FILE_PATH = Path(self.tmp.name) / "t.sqlite3"
        self.repo = SqliteTrackingRepository()

    def tearDown(self) -> None:
        self.tmp.cleanup()
        tracking_repository_module.DB_FILE_PATH = self.old_db
        tracking_repository_module.DATA_DIR = self.old_dir

    def test_create_get_list_find(self) -> None:
        cid = self.repo.create_canonical_league("Brazil. Campeonato Brasiliense U20")
        self.assertEqual(self.repo.get_canonical_league(cid)["name"], "Brazil. Campeonato Brasiliense U20")
        self.assertEqual(len(self.repo.list_canonical_leagues()), 1)
        # case-insensitive find
        self.assertEqual(self.repo.find_canonical_league_by_name("brazil. campeonato brasiliense u20")["id"], cid)
        self.assertIsNone(self.repo.find_canonical_league_by_name("nope"))

    def test_assign_and_query_competition(self) -> None:
        cid = self.repo.create_canonical_league("L")
        # insert a minimal tracked_competition directly
        with tracking_repository_module._connect() as con:
            cur = con.execute(
                "INSERT INTO tracked_competitions (platform, competition_external_id, competition_name, source_url, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("1xbet_http", "L1X", "Brasiliense U20", "http://x", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
            )
            comp_id = int(cur.lastrowid)
        self.assertIsNone(self.repo.get_canonical_league_id_for_competition(comp_id))
        self.repo.set_competition_canonical_league(comp_id, cid)
        self.assertEqual(self.repo.get_canonical_league_id_for_competition(comp_id), cid)
        comps = self.repo.list_competitions_for_canonical_league(cid)
        self.assertEqual(len(comps), 1)
        self.assertEqual(comps[0].platform, "1xbet_http")
        self.assertEqual(comps[0].competition_external_id, "L1X")
        # unlink
        self.repo.set_competition_canonical_league(comp_id, None)
        self.assertEqual(self.repo.list_competitions_for_canonical_league(cid), [])


if __name__ == "__main__":
    unittest.main()

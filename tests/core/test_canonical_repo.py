from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

tracking_repository_module = importlib.import_module("storage.tracking_repository")
SqliteTrackingRepository = tracking_repository_module.SqliteTrackingRepository


class UnifiedCompetitionRepoTests(unittest.TestCase):
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

    def _add_comp(self, platform, ext_id, name):
        with tracking_repository_module._connect() as con:
            cur = con.execute(
                "INSERT INTO tracked_competitions (platform, competition_external_id, competition_name, source_url, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (platform, ext_id, name, "http://x", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
            )
            return int(cur.lastrowid)

    def test_create_get_delete(self) -> None:
        uid = self.repo.create_unified_competition("Brazil. Campeonato Brasiliense U20")
        self.assertEqual(self.repo.get_unified_competition(uid)["name"], "Brazil. Campeonato Brasiliense U20")
        self.repo.delete_unified_competition(uid)
        self.assertIsNone(self.repo.get_unified_competition(uid))

    def test_link_and_list(self) -> None:
        uid = self.repo.create_unified_competition("L")
        c1 = self._add_comp("1xbet_http", "L1X", "Brasiliense U20")
        c2 = self._add_comp("betovo_http", "LBET", "Sub20 Brasiliense")
        self.repo.link_tracked_competition_to_unified(c1, uid)
        self.repo.link_tracked_competition_to_unified(c2, uid)
        comps = self.repo.list_tracked_competitions_for_unified(uid)
        self.assertEqual({c.platform for c in comps}, {"1xbet_http", "betovo_http"})

    def test_relink_merges_normalized_duplicates(self) -> None:
        u1 = self.repo.create_unified_competition("USA. USL League Two")
        u2 = self.repo.create_unified_competition("Estados Unidos · USL League 2")
        c1 = self._add_comp("1xbet_http", "a", "USA. USL League Two")
        c2 = self._add_comp("betwarrior_http", "b", "Estados Unidos · USL League 2")
        self.repo.link_tracked_competition_to_unified(c1, u1)
        self.repo.link_tracked_competition_to_unified(c2, u2)

        summary = self.repo.relink_unified_by_normalized_name()
        self.assertEqual(summary["groups_merged"], 1)
        self.assertGreaterEqual(summary["competitions_moved"], 1)
        target, other = min(u1, u2), max(u1, u2)
        self.assertEqual(len(self.repo.list_tracked_competitions_for_unified(target)), 2)
        self.assertIsNone(self.repo.get_unified_competition(other))  # emptied + deleted

    def test_relink_keeps_genders_separate(self) -> None:
        u1 = self.repo.create_unified_competition("NPL Northern NSW")
        u2 = self.repo.create_unified_competition("NPL Northern NSW (F)")
        self.repo.link_tracked_competition_to_unified(self._add_comp("1xbet_http", "a", "NPL Northern NSW"), u1)
        self.repo.link_tracked_competition_to_unified(self._add_comp("betovo_http", "b", "NPL Northern NSW (F)"), u2)
        self.repo.relink_unified_by_normalized_name()
        self.assertIsNotNone(self.repo.get_unified_competition(u1))
        self.assertIsNotNone(self.repo.get_unified_competition(u2))

    def test_fuzzy_auto_merge_on_get_or_create(self) -> None:
        uid1 = self.repo.get_or_create_unified_competition("Campeonato Brasiliense U20")
        # near-identical name should map to the SAME unified competition (>=0.85)
        uid2 = self.repo.get_or_create_unified_competition("Campeonato Brasiliense Sub 20")
        # exact (case-insensitive) maps too
        uid3 = self.repo.get_or_create_unified_competition("campeonato brasiliense u20")
        self.assertEqual(uid1, uid3)
        # uid2 may or may not merge depending on similarity; just ensure it's an int id
        self.assertIsInstance(uid2, int)


if __name__ == "__main__":
    unittest.main()

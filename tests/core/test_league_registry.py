from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

tracking_repository_module = importlib.import_module("storage.tracking_repository")


class LeagueRegistryTests(unittest.TestCase):
    """Fase 1: public_id/traits en unified + stats links a nivel liga unificada."""

    def setUp(self) -> None:
        self.old_db_path = tracking_repository_module.DB_FILE_PATH
        self.tmp = tempfile.TemporaryDirectory()
        tracking_repository_module.DB_FILE_PATH = Path(self.tmp.name) / "tracking.sqlite3"
        self.repo = tracking_repository_module.SqliteTrackingRepository()

    def tearDown(self) -> None:
        tracking_repository_module.DB_FILE_PATH = self.old_db_path
        self.tmp.cleanup()

    def _track(self, platform: str, ext_id: str, name: str) -> int:
        """Insert a tracked competition the way production code does (with unified)."""
        with tracking_repository_module._connect() as c:
            uc_id = tracking_repository_module._find_or_create_unified_competition_id(c, name)
            now = tracking_repository_module._utc_now_iso()
            cur = c.execute(
                """
                INSERT INTO tracked_competitions (
                    platform, competition_external_id, competition_name, source_url,
                    enabled, unified_competition_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (platform, ext_id, name, f"{platform}:{ext_id}", uc_id, now, now),
            )
            return int(cur.lastrowid)

    def test_unified_gets_public_id_and_traits(self) -> None:
        uid = self.repo.create_unified_competition("USA. WPSL (F)")
        uc = self.repo.get_unified_competition(uid)
        self.assertEqual(uc["public_id"], "usa-wpsl-f")
        self.assertEqual(uc["gender"], "F")
        self.assertEqual(uc["country"], "usa")
        self.assertEqual(uc["display_name"], "USA. WPSL (F)")

    def test_public_id_collision_gets_suffix(self) -> None:
        a = self.repo.create_unified_competition("Liga X!")
        b = self.repo.create_unified_competition("Liga X?")  # same slug base
        pa = self.repo.get_unified_competition(a)["public_id"]
        pb = self.repo.get_unified_competition(b)["public_id"]
        self.assertEqual(pa, "liga-x")
        self.assertEqual(pb, "liga-x-2")

    def test_stats_link_inherited_by_other_platform(self) -> None:
        tc_a = self._track("1xbet_http", "100", "Premier League")
        tc_b = self._track("betovo_http", "200", "Premier League")  # same unified
        self.repo.upsert_stats_league_link(
            tc_a, stats_provider="sofascore_http", stats_league_id="17",
            stats_league_name="Premier League",
        )
        links_b = self.repo.list_stats_league_links(tc_b)
        self.assertEqual([(l.stats_provider, l.stats_league_id) for l in links_b],
                         [("sofascore_http", "17")])

    def test_upsert_from_second_platform_updates_shared_row(self) -> None:
        tc_a = self._track("1xbet_http", "100", "Premier League")
        tc_b = self._track("betovo_http", "200", "Premier League")
        self.repo.upsert_stats_league_link(
            tc_a, stats_provider="sofascore_http", stats_league_id="17",
            stats_league_name="Premier League",
        )
        # Same provider via the OTHER platform: must update the shared link, not duplicate.
        self.repo.upsert_stats_league_link(
            tc_b, stats_provider="sofascore_http", stats_league_id="99",
            stats_league_name="Premier League (fixed)",
        )
        with tracking_repository_module._connect() as c:
            rows = c.execute(
                "SELECT stats_league_id FROM stats_league_links WHERE stats_provider='sofascore_http'"
            ).fetchall()
        self.assertEqual([r["stats_league_id"] for r in rows], ["99"])

    def test_multiple_providers_per_league(self) -> None:
        tc = self._track("1xbet_http", "100", "Premier League")
        self.repo.upsert_stats_league_link(
            tc, stats_provider="sofascore_http", stats_league_id="17", stats_league_name="PL")
        self.repo.upsert_stats_league_link(
            tc, stats_provider="flashscore_http", stats_league_id="abc", stats_league_name="PL")
        links = self.repo.list_stats_league_links(tc)
        self.assertEqual({l.stats_provider for l in links}, {"sofascore_http", "flashscore_http"})

    def test_legacy_duplicate_links_deduped_on_migration(self) -> None:
        tc_a = self._track("1xbet_http", "100", "Premier League")
        tc_b = self._track("betovo_http", "200", "Premier League")
        # Simulate legacy per-platform duplicates (pre-registry schema): same
        # provider linked separately from each platform, NULL unified column.
        with tracking_repository_module._connect() as c:
            now = tracking_repository_module._utc_now_iso()
            for tc_id, league_id, conf in ((tc_a, "17", 0.7), (tc_b, "99", 0.9)):
                c.execute(
                    """
                    INSERT INTO stats_league_links (
                        tracked_competition_id, stats_provider, stats_league_id,
                        stats_league_name, confidence, created_at, updated_at
                    ) VALUES (?, 'sofascore_http', ?, 'PL', ?, ?, ?)
                    """,
                    (tc_id, league_id, conf, now, now),
                )
        # Next connect runs the migration: backfill unified + dedupe keeps best confidence.
        links = self.repo.list_stats_league_links(tc_a)
        self.assertEqual([(l.stats_provider, l.stats_league_id) for l in links],
                         [("sofascore_http", "99")])


if __name__ == "__main__":
    unittest.main()

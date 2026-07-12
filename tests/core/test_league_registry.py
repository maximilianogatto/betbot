from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone

from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema


class LeagueRegistryTests(unittest.TestCase):
    """Fase 1: public_id/traits en unified + stats links a nivel liga unificada."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp.name) / "tracking.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.repo = SqliteStorage()

    def tearDown(self) -> None:
        self.tmp.cleanup()
        if self.old_db_path is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self.old_db_path

    def _track(self, platform: str, ext_id: str, name: str) -> int:
        """Insert a tracked competition the way production code does (with unified)."""
        now = datetime.now(timezone.utc).isoformat()
        with open_connection() as c:
            # We can use the helper method _find_or_create_unified_competition_id from the adapter's module,
            # or just call repo.get_or_create_unified_competition(name)!
            uc_id = self.repo.get_or_create_unified_competition(name)
            cur = c.execute(
                """
                INSERT INTO competitions (
                    platform, external_id, name, source_url,
                    enabled, unified_competition_id, consecutive_unavailable_refreshes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, 0, ?, ?)
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

    def test_duplicate_name_gets_suffixed(self) -> None:
        # /unlink_league re-creates a unified with the same name; the UNIQUE name
        # column must not crash (this was the "error inesperado" bug).
        a = self.repo.create_unified_competition("Svenska Cup")
        b = self.repo.create_unified_competition("Svenska Cup")
        self.assertNotEqual(a, b)
        self.assertEqual(self.repo.get_unified_competition(b)["name"], "Svenska Cup (2)")

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
        with open_connection() as c:
            rows = c.execute(
                "SELECT league_id FROM stats_league_links WHERE provider='sofascore_http'"
            ).fetchall()
        self.assertEqual([r["league_id"] for r in rows], ["99"])

    def test_multiple_providers_per_league(self) -> None:
        tc = self._track("1xbet_http", "100", "Premier League")
        self.repo.upsert_stats_league_link(
            tc, stats_provider="sofascore_http", stats_league_id="17", stats_league_name="PL")
        self.repo.upsert_stats_league_link(
            tc, stats_provider="flashscore_http", stats_league_id="abc", stats_league_name="PL")
        links = self.repo.list_stats_league_links(tc)
        self.assertEqual({l.stats_provider for l in links}, {"sofascore_http", "flashscore_http"})


class LeagueMatchingTests(unittest.TestCase):
    """Hotfix: auto-merge only on safe signals; fuzzy is a suggestion."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp.name) / "tracking.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.repo = SqliteStorage()

    def tearDown(self) -> None:
        self.tmp.cleanup()
        if self.old_db_path is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self.old_db_path

    def _track(self, platform: str, ext_id: str, name: str):
        self.repo.create_pending_competition_request(
            1, platform=platform, source_url=f"u/{ext_id}",
            competition_external_id=ext_id, competition_name=name,
            requires_empty_confirmation=False, needs_name_resolution=False,
        )
        return self.repo.confirm_pending_competition_request(1)

    def test_women_and_u20_are_not_merged(self) -> None:
        u20 = self._track("1xbet_http", "1", "Australia. New South Wales Premier League U20")
        women = self._track("1xbet_http", "2", "Australia. New South Wales Premier League. Women")
        self.assertNotEqual(u20.unified_competition_id, women.unified_competition_id)

    def test_same_named_cup_different_countries_not_merged(self) -> None:
        aus = self._track("1xbet_http", "1", "Australia Cup")
        swe = self._track("bz_http", "2", "Sweden · Svenska Cup")
        self.assertNotEqual(aus.unified_competition_id, swe.unified_competition_id)

    def test_word_shuffle_is_merged(self) -> None:
        a = self._track("1xbet_http", "1", "NPL League Tasmania")
        b = self._track("betovo_http", "2", "Tasmania League NPL")
        self.assertEqual(a.unified_competition_id, b.unified_competition_id)

    def test_canonical_number_words_merged(self) -> None:
        a = self._track("1xbet_http", "1", "USL League Two")
        b = self._track("betovo_http", "2", "USL League 2")
        self.assertEqual(a.unified_competition_id, b.unified_competition_id)

    def test_fuzzy_near_dup_is_suggested_not_merged(self) -> None:
        a = self._track("1xbet_http", "1", "Australia. Victoria Premier League 1")
        b = self._track("1xbet_http", "2", "Australia. Victoria Premier League One Extra")
        self.assertNotEqual(a.unified_competition_id, b.unified_competition_id)
        suggestions = self.repo.suggest_similar_unified(
            "Australia. Victoria Premier League 1", exclude_unified_id=a.unified_competition_id
        )
        self.assertIn(b.unified_competition_id, {s["id"] for s in suggestions})

    def test_suggestion_respects_discriminators(self) -> None:
        u20 = self._track("1xbet_http", "1", "Australia. NSW Premier League U20")
        suggestions = self.repo.suggest_similar_unified(
            "Australia. NSW Premier League Women", exclude_unified_id=-1
        )
        self.assertNotIn(u20.unified_competition_id, {s["id"] for s in suggestions})


if __name__ == "__main__":
    unittest.main()

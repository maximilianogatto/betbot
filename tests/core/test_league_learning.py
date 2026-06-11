from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

from core.registry import ExtractorRegistry
from monitors.tracking import TrackingService
from storage.tracking_repository import ActiveEventUpsert, SqliteTrackingRepository

tracking_repository_module = importlib.import_module("storage.tracking_repository")


def _event(eid: str, home: str, away: str, when: str) -> ActiveEventUpsert:
    return ActiveEventUpsert(
        external_event_id=eid,
        home=home,
        away=away,
        scheduled_label_date=None,
        scheduled_label_time=None,
        scheduled_at=when,
        odds_home=1.5,
        odds_draw=3.5,
        odds_away=5.0,
    )


class LeagueLearningTests(unittest.TestCase):
    """Fase 3: fusión automática de ligas por partidos físicos compartidos."""

    CHAT = 42

    def setUp(self) -> None:
        self.old_db_path = tracking_repository_module.DB_FILE_PATH
        self.tmp = tempfile.TemporaryDirectory()
        tracking_repository_module.DB_FILE_PATH = Path(self.tmp.name) / "tracking.sqlite3"
        self.repo = SqliteTrackingRepository()
        self.service = TrackingService(
            extractor_registry=ExtractorRegistry(),
            repository=self.repo,
        )

    def tearDown(self) -> None:
        tracking_repository_module.DB_FILE_PATH = self.old_db_path
        self.tmp.cleanup()

    def _track(self, platform: str, ext_id: str, name: str):
        self.repo.create_pending_competition_request(
            self.CHAT,
            platform=platform,
            source_url=f"https://{platform}.example/{ext_id}",
            competition_external_id=ext_id,
            competition_name=name,
        )
        return self.repo.confirm_pending_competition_request(self.CHAT).tracked_competition

    def test_merges_leagues_sharing_two_physical_matches(self) -> None:
        # Same physical league, names too different for the fuzzy auto-merge.
        a = self._track("1xbet_http", "100", "Inglaterra. Liga Premier")
        b = self._track("betovo_http", "200", "English Top Flight Special")
        self.assertNotEqual(a.unified_competition_id, b.unified_competition_id)

        self.repo.upsert_active_events(a.id, [
            _event("a1", "Arsenal FC", "Chelsea FC", "2030-01-01T15:00:00"),
            _event("a2", "Liverpool FC", "Everton FC", "2030-01-01T17:30:00"),
        ])
        self.repo.upsert_active_events(b.id, [
            _event("b1", "Arsenal", "Chelsea", "2030-01-01T15:00:00"),
            _event("b2", "Liverpool", "Everton", "2030-01-01T17:30:00"),
        ])

        merges = self.service.learn_unified_merges()
        self.assertEqual(len(merges), 1)
        self.assertEqual(merges[0]["matches"], 2)

        # Both platforms now share one unified league and the chat is on both.
        a2 = self.repo.get_tracked_competition(a.id)
        b2 = self.repo.get_tracked_competition(b.id)
        self.assertEqual(a2.unified_competition_id, b2.unified_competition_id)

    def test_single_shared_match_is_not_enough(self) -> None:
        a = self._track("1xbet_http", "100", "Inglaterra. Liga Premier")
        b = self._track("betovo_http", "200", "English Top Flight Special")
        self.repo.upsert_active_events(a.id, [
            _event("a1", "Arsenal FC", "Chelsea FC", "2030-01-01T15:00:00"),
        ])
        self.repo.upsert_active_events(b.id, [
            _event("b1", "Arsenal", "Chelsea", "2030-01-01T15:00:00"),
        ])
        self.assertEqual(self.service.learn_unified_merges(), [])

    def test_same_platform_coincidences_do_not_merge(self) -> None:
        # Two 1xbet leagues with overlapping fixtures must NOT be merged
        # (learning only links leagues ACROSS platforms).
        a = self._track("1xbet_http", "100", "Liga A")
        b = self._track("1xbet_http", "101", "Liga B")
        events = [
            _event("x1", "Arsenal FC", "Chelsea FC", "2030-01-01T15:00:00"),
            _event("x2", "Liverpool FC", "Everton FC", "2030-01-01T17:30:00"),
        ]
        self.repo.upsert_active_events(a.id, events)
        self.repo.upsert_active_events(b.id, events)
        self.assertEqual(self.service.learn_unified_merges(), [])

    def test_different_kickoffs_do_not_merge(self) -> None:
        a = self._track("1xbet_http", "100", "Inglaterra. Liga Premier")
        b = self._track("betovo_http", "200", "English Top Flight Special")
        self.repo.upsert_active_events(a.id, [
            _event("a1", "Arsenal FC", "Chelsea FC", "2030-01-01T15:00:00"),
            _event("a2", "Liverpool FC", "Everton FC", "2030-01-01T17:30:00"),
        ])
        self.repo.upsert_active_events(b.id, [
            _event("b1", "Arsenal", "Chelsea", "2030-01-01T16:00:00"),
            _event("b2", "Liverpool", "Everton", "2030-01-01T19:00:00"),
        ])
        self.assertEqual(self.service.learn_unified_merges(), [])

    def test_merge_preserves_stats_links(self) -> None:
        a = self._track("1xbet_http", "100", "Inglaterra. Liga Premier")
        b = self._track("betovo_http", "200", "English Top Flight Special")
        self.repo.upsert_stats_league_link(
            b.id, stats_provider="sofascore_http", stats_league_id="17",
            stats_league_name="Premier League",
        )
        self.repo.upsert_active_events(a.id, [
            _event("a1", "Arsenal FC", "Chelsea FC", "2030-01-01T15:00:00"),
            _event("a2", "Liverpool FC", "Everton FC", "2030-01-01T17:30:00"),
        ])
        self.repo.upsert_active_events(b.id, [
            _event("b1", "Arsenal", "Chelsea", "2030-01-01T15:00:00"),
            _event("b2", "Liverpool", "Everton", "2030-01-01T17:30:00"),
        ])
        self.assertEqual(len(self.service.learn_unified_merges()), 1)
        # The source league's stats link survives the merge.
        links = self.repo.list_stats_league_links(a.id)
        self.assertEqual([(l.stats_provider, l.stats_league_id) for l in links],
                         [("sofascore_http", "17")])

    def test_merges_with_mixed_naive_and_aware_kickoffs(self) -> None:
        a = self._track("1xbet_http", "100", "Inglaterra. Liga Premier")
        b = self._track("betovo_http", "200", "English Top Flight Special")
        self.repo.upsert_active_events(a.id, [
            _event("a1", "Arsenal FC", "Chelsea FC", "2030-01-01T15:00:00"),
            _event("a2", "Liverpool FC", "Everton FC", "2030-01-01T17:30:00"),
        ])
        self.repo.upsert_active_events(b.id, [
            _event("b1", "Arsenal", "Chelsea", "2030-01-01T15:00:00+00:00"),
            _event("b2", "Liverpool", "Everton", "2030-01-01T17:30:00+00:00"),
        ])

        merges = self.service.learn_unified_merges()
        self.assertEqual(len(merges), 1)
        self.assertEqual(merges[0]["matches"], 2)


if __name__ == "__main__":
    unittest.main()

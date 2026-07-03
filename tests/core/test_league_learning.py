from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.registry import ExtractorRegistry
from monitors.tracking import TrackingService
from core.models import ActiveEventUpsert
from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema


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
        self.tmp = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp.name) / "tracking.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.repo = SqliteStorage()
        self.service = TrackingService(
            extractor_registry=ExtractorRegistry(),
            repository=self.repo,
        )

    def tearDown(self) -> None:
        if self._prev_db is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db
        self.tmp.cleanup()

    def _track(self, platform: str, ext_id: str, name: str):
        self.repo.create_pending_competition_request(
            self.CHAT,
            platform=platform,
            source_url=f"https://{platform}.example/{ext_id}",
            competition_external_id=ext_id,
            competition_name=name,
            requires_empty_confirmation=False,
            needs_name_resolution=False,
        )
        return self.repo.confirm_pending_competition_request(self.CHAT)

    def _seed_shared_fixtures(self, a_id: int, b_id: int) -> None:
        """Three coinciding matches across platforms (>= MIN_MERGE_COINCIDENCES)."""
        self.repo.upsert_active_events(a_id, [
            _event("a1", "Arsenal FC", "Chelsea FC", "2030-01-01T15:00:00"),
            _event("a2", "Liverpool FC", "Everton FC", "2030-01-01T17:30:00"),
            _event("a3", "Manchester City FC", "Tottenham Hotspur FC", "2030-01-01T20:00:00"),
        ])
        self.repo.upsert_active_events(b_id, [
            _event("b1", "Arsenal", "Chelsea", "2030-01-01T15:00:00"),
            _event("b2", "Liverpool", "Everton", "2030-01-01T17:30:00"),
            _event("b3", "Manchester City", "Tottenham Hotspur", "2030-01-01T20:00:00"),
        ])

    def test_merges_leagues_sharing_three_physical_matches(self) -> None:
        # Same physical league, names too different for the fuzzy auto-merge.
        a = self._track("1xbet_http", "100", "Inglaterra. Liga Premier")
        b = self._track("betovo_http", "200", "English Top Flight Special")
        self.assertNotEqual(a.unified_competition_id, b.unified_competition_id)

        self._seed_shared_fixtures(a.id, b.id)

        merges = self.service.learn_unified_merges()
        self.assertEqual(len(merges), 1)
        self.assertEqual(merges[0]["matches"], 3)

        # Both platforms now share one unified league and the chat is on both.
        a2 = self.repo.get_tracked_competition(a.id)
        b2 = self.repo.get_tracked_competition(b.id)
        self.assertEqual(a2.unified_competition_id, b2.unified_competition_id)

    def test_two_shared_matches_is_not_enough(self) -> None:
        # Umbral estricto: exactamente 2 coincidencias ya no fusiona (>=3 requerido).
        a = self._track("1xbet_http", "100", "Inglaterra. Liga Premier")
        b = self._track("betovo_http", "200", "English Top Flight Special")
        self.repo.upsert_active_events(a.id, [
            _event("a1", "Arsenal FC", "Chelsea FC", "2030-01-01T15:00:00"),
            _event("a2", "Liverpool FC", "Everton FC", "2030-01-01T17:30:00"),
        ])
        self.repo.upsert_active_events(b.id, [
            _event("b1", "Arsenal", "Chelsea", "2030-01-01T15:00:00"),
            _event("b2", "Liverpool", "Everton", "2030-01-01T17:30:00"),
        ])
        self.assertEqual(self.service.learn_unified_merges(), [])

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
        self._seed_shared_fixtures(a.id, b.id)
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
            _event("a3", "Manchester City FC", "Tottenham Hotspur FC", "2030-01-01T20:00:00"),
        ])
        self.repo.upsert_active_events(b.id, [
            _event("b1", "Arsenal", "Chelsea", "2030-01-01T15:00:00+00:00"),
            _event("b2", "Liverpool", "Everton", "2030-01-01T17:30:00+00:00"),
            _event("b3", "Manchester City", "Tottenham Hotspur", "2030-01-01T20:00:00+00:00"),
        ])

        merges = self.service.learn_unified_merges()
        self.assertEqual(len(merges), 1)
        self.assertEqual(merges[0]["matches"], 3)

    def test_gender_mismatch_never_auto_merges(self) -> None:
        # Femenino vs masculino nunca se fusiona, aunque compartan partidos.
        a = self._track("1xbet_http", "100", "Australia. NPL. Women")
        b = self._track("betovo_http", "200", "Australia. NPL")
        self._seed_shared_fixtures(a.id, b.id)
        self.assertEqual(self.service.learn_unified_merges(), [])

    def _uid(self, comp_id: int) -> int:
        return self.repo.get_tracked_competition(comp_id).unified_competition_id

    def test_unlink_blocks_future_auto_merge(self) -> None:
        a = self._track("1xbet_http", "100", "Inglaterra. Liga Premier")
        b = self._track("betovo_http", "200", "English Top Flight Special")
        self._seed_shared_fixtures(a.id, b.id)
        self.assertEqual(len(self.service.learn_unified_merges()), 1)
        shared_uid = self._uid(a.id)

        # Simular /unlink_league sobre b: bloquear contra los miembros y separar.
        blocked = self.repo.block_unlinked_competition(b.id, shared_uid)
        self.assertEqual(blocked, 1)  # un único otro miembro: a
        new_uid = self.repo.create_unified_competition("English Top Flight Special")
        self.repo.link_tracked_competition_to_unified(b.id, new_uid)
        self.assertNotEqual(self._uid(a.id), self._uid(b.id))

        # El learner NO debe volver a fusionarlas.
        self.assertEqual(self.service.learn_unified_merges(), [])
        self.assertNotEqual(self._uid(a.id), self._uid(b.id))

    def test_unlink_blocks_against_every_platform(self) -> None:
        # Liga unificada con 3 plataformas; al separar una, se bloquea contra las OTRAS 2.
        a = self._track("1xbet_http", "100", "Inglaterra. Liga Premier")
        b = self._track("betovo_http", "200", "English Top Flight Special")
        c = self._track("betsson_http", "300", "Premier Ligue Angleterre")
        self._seed_shared_fixtures(a.id, b.id)
        self.repo.upsert_active_events(c.id, [
            _event("c1", "Arsenal AFC", "Chelsea", "2030-01-01T15:00:00"),
            _event("c2", "Liverpool", "Everton", "2030-01-01T17:30:00"),
            _event("c3", "Manchester City", "Tottenham Hotspur", "2030-01-01T20:00:00"),
        ])
        # Se fusionan las tres en una sola liga.
        self.service.learn_unified_merges()
        shared_uid = self._uid(a.id)
        self.assertEqual(self._uid(b.id), shared_uid)
        self.assertEqual(self._uid(c.id), shared_uid)

        # Separar la de 1xbet: debe bloquear 2 pares (contra betovo y betsson).
        blocked = self.repo.block_unlinked_competition(a.id, shared_uid)
        self.assertEqual(blocked, 2)
        new_uid = self.repo.create_unified_competition("Inglaterra. Liga Premier")
        self.repo.link_tracked_competition_to_unified(a.id, new_uid)

        # No se re-fusiona con NINGUNA de las otras plataformas.
        self.assertEqual(self.service.learn_unified_merges(), [])
        self.assertNotEqual(self._uid(a.id), self._uid(b.id))
        self.assertNotEqual(self._uid(a.id), self._uid(c.id))

    def test_manual_link_override_clears_block(self) -> None:
        a = self._track("1xbet_http", "100", "Inglaterra. Liga Premier")
        b = self._track("betovo_http", "200", "English Top Flight Special")
        self._seed_shared_fixtures(a.id, b.id)
        self.assertEqual(len(self.service.learn_unified_merges()), 1)
        shared_uid = self._uid(a.id)
        self.repo.block_unlinked_competition(b.id, shared_uid)
        new_uid = self.repo.create_unified_competition("English Top Flight Special")
        self.repo.link_tracked_competition_to_unified(b.id, new_uid)

        # Override manual: limpiar el bloqueo entre ambas ligas devuelve >=1 y permite fusionar.
        deleted = self.repo.clear_merge_exceptions_between(self._uid(a.id), self._uid(b.id))
        self.assertEqual(deleted, 1)
        self.assertEqual(self.repo.get_merge_exceptions(), set())
        # Con el bloqueo removido, el learner vuelve a poder unificarlas.
        self.assertEqual(len(self.service.learn_unified_merges()), 1)
        self.assertEqual(self._uid(a.id), self._uid(b.id))


if __name__ == "__main__":
    unittest.main()

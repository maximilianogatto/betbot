"""Archivo histórico de resultados: idempotencia, filtros y datos que no se pisan."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import EXPECTED_TABLES, initialize_schema, list_tables
from core.models import MatchResult


def _result(**overrides) -> MatchResult:
    payload = dict(
        home="Banyule", away="Bundoora", status="FINISHED",
        source="live_watch", recorded_at="2026-07-01T10:00:00+00:00",
        platform="betovo_http", external_event_id="ev-1",
        kickoff_at="2026-07-01T12:00:00+00:00",
        final_home_score=2, final_away_score=1,
    )
    payload.update(overrides)
    return MatchResult(**payload)


class MatchResultsStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp_dir.name) / "results.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.storage = SqliteStorage()

    def tearDown(self) -> None:
        if self._prev_db is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db
        self.tmp_dir.cleanup()

    def test_table_is_declared_in_the_schema_guard(self) -> None:
        self.assertIn("match_results", EXPECTED_TABLES)
        with open_connection() as conn:
            self.assertIn("match_results", list_tables(conn))

    def test_records_and_reads_back_a_result(self) -> None:
        saved = self.storage.record_match_result(_result())

        self.assertIsNotNone(saved.id)
        found = self.storage.get_match_result(platform="betovo_http", external_event_id="ev-1")
        self.assertIsNotNone(found)
        self.assertEqual((found.home, found.away), ("Banyule", "Bundoora"))
        self.assertEqual((found.final_home_score, found.final_away_score), (2, 1))
        self.assertTrue(found.is_settled)

    def test_re_recording_the_same_match_updates_instead_of_duplicating(self) -> None:
        """Re-consultar un partido tiene que corregir la fila, no duplicarla."""

        self.storage.record_match_result(_result(final_home_score=1, final_away_score=1))
        self.storage.record_match_result(_result(final_home_score=2, final_away_score=1, xg_home=1.8))

        rows = self.storage.list_match_results()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].final_home_score, rows[0].final_away_score), (2, 1))
        self.assertAlmostEqual(rows[0].xg_home, 1.8)

    def test_recorded_at_survives_an_update(self) -> None:
        """Cuándo se vio por primera vez es histórico: no se pisa."""

        first = self.storage.record_match_result(_result(recorded_at="2026-07-01T10:00:00+00:00"))
        second = self.storage.record_match_result(_result(recorded_at="2026-07-09T23:00:00+00:00"))

        self.assertEqual(second.recorded_at, first.recorded_at)
        self.assertIsNotNone(second.updated_at)

    def test_only_settled_excludes_suspended_matches(self) -> None:
        """Un suspendido NO es un 0-0: no puede entrar a los análisis."""

        self.storage.record_match_result(_result(external_event_id="ok"))
        self.storage.record_match_result(
            _result(
                external_event_id="susp", status="SUSPENDED",
                final_home_score=None, final_away_score=None,
            )
        )

        self.assertEqual(len(self.storage.list_match_results()), 2)
        settled = self.storage.list_match_results(only_settled=True)
        self.assertEqual([r.external_event_id for r in settled], ["ok"])

    def test_filters_by_competition_and_date_window(self) -> None:
        # La FK a unified_competitions es real: las ligas tienen que existir.
        liga_a = self.storage.create_unified_competition("Liga A")
        liga_b = self.storage.create_unified_competition("Liga B")

        self.storage.record_match_result(
            _result(external_event_id="a", unified_competition_id=liga_a, kickoff_at="2026-07-01T12:00:00+00:00")
        )
        self.storage.record_match_result(
            _result(external_event_id="b", unified_competition_id=liga_a, kickoff_at="2026-07-20T12:00:00+00:00")
        )
        self.storage.record_match_result(
            _result(external_event_id="c", unified_competition_id=liga_b, kickoff_at="2026-07-02T12:00:00+00:00")
        )

        by_league = self.storage.list_match_results(unified_competition_id=liga_a)
        self.assertEqual({r.external_event_id for r in by_league}, {"a", "b"})

        window = self.storage.list_match_results(
            since="2026-07-01T00:00:00+00:00", until="2026-07-05T00:00:00+00:00"
        )
        self.assertEqual({r.external_event_id for r in window}, {"a", "c"})

    def test_indicators_and_raw_payload_round_trip(self) -> None:
        """Los indicadores del nivel 2 y el crudo del provider se conservan."""

        self.storage.record_match_result(
            _result(
                xg_home=2.31, xg_away=0.74,
                shots_on_target_home=7, shots_on_target_away=2,
                red_cards_home=0, red_cards_away=1,
                goal_minutes_json='[{"minute": 23, "team": "home"}]',
                red_card_minutes_json='[{"minute": 61, "team": "away"}]',
                stats_provider="sofascore_http", stats_match_id="12345",
                raw_payload_json='{"possession_home": 61}',
            )
        )

        found = self.storage.get_match_result(platform="betovo_http", external_event_id="ev-1")
        self.assertAlmostEqual(found.xg_home, 2.31)
        self.assertEqual(found.red_cards_away, 1)
        self.assertIn('"minute": 23', found.goal_minutes_json)
        self.assertEqual(found.stats_provider, "sofascore_http")
        self.assertIn("possession_home", found.raw_payload_json)


if __name__ == "__main__":
    unittest.main()

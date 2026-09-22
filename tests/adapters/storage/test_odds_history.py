"""Archivo append-only de cuotas: idempotencia, serie y cierre observado."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from adapters.storage.connection import open_connection
from adapters.storage.odds_history import SQLiteOddsHistoryAdapter
from adapters.storage.schema import EXPECTED_TABLES, initialize_schema, list_tables
from core.models import OddsSnapshot


def _snapshot(captured_at: str, odds_home: float | None = 1.5, **overrides) -> OddsSnapshot:
    payload = dict(
        platform="1xbet_http", external_event_id="ev-1", captured_at=captured_at,
        payload_hash=f"h-{odds_home}-{captured_at}", home="Darwin", away="Palmerston",
        odds_home=odds_home, odds_draw=4.0, odds_away=6.0, status="PREMATCH",
        scheduled_at="2026-07-01T12:00:00+00:00",
    )
    payload.update(overrides)
    return OddsSnapshot(**payload)


class OddsHistoryStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp_dir.name) / "odds.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.archive = SQLiteOddsHistoryAdapter()

    def tearDown(self) -> None:
        if self._prev_db is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db
        self.tmp_dir.cleanup()

    def test_table_is_declared_in_the_schema_guard(self) -> None:
        self.assertIn("odds_history", EXPECTED_TABLES)
        with open_connection() as conn:
            self.assertIn("odds_history", list_tables(conn))

    def test_keeps_the_whole_series_instead_of_overwriting(self) -> None:
        self.archive.archive_snapshots([
            _snapshot("2026-07-01T08:00:00+00:00", 1.50),
            _snapshot("2026-07-01T10:00:00+00:00", 1.40),
            _snapshot("2026-07-01T11:50:00+00:00", 1.28),
        ])
        series = self.archive.list_snapshots(platform="1xbet_http", external_event_id="ev-1")
        self.assertEqual([s.odds_home for s in series], [1.50, 1.40, 1.28])
        self.assertEqual(self.archive.last_snapshot(
            platform="1xbet_http", external_event_id="ev-1").odds_home, 1.28)

    def test_same_payload_at_the_same_instant_is_not_duplicated(self) -> None:
        snapshot = _snapshot("2026-07-01T08:00:00+00:00", 1.50)
        self.assertEqual(self.archive.archive_snapshots([snapshot]), 1)
        self.assertEqual(self.archive.archive_snapshots([snapshot]), 0)
        self.assertEqual(len(self.archive.list_snapshots(
            platform="1xbet_http", external_event_id="ev-1")), 1)

    def test_closing_is_the_last_one_seen_before_kickoff(self) -> None:
        kickoff = "2026-07-01T12:00:00+00:00"
        self.archive.archive_snapshots([
            _snapshot("2026-07-01T11:50:00+00:00", 1.28),
            # En vivo, ya después del kickoff: no es cierre.
            _snapshot("2026-07-01T12:30:00+00:00", 3.10, status="LIVE"),
        ])
        closing = self.archive.last_prematch_snapshot(
            platform="1xbet_http", external_event_id="ev-1", kickoff_at=kickoff)
        self.assertEqual(closing.odds_home, 1.28)

    def test_a_suspended_snapshot_is_not_taken_as_closing(self) -> None:
        kickoff = "2026-07-01T12:00:00+00:00"
        self.archive.archive_snapshots([
            _snapshot("2026-07-01T11:00:00+00:00", 1.30),
            _snapshot("2026-07-01T11:59:00+00:00", None, odds_draw=None, odds_away=None,
                      is_suspended=True),
        ])
        closing = self.archive.last_prematch_snapshot(
            platform="1xbet_http", external_event_id="ev-1", kickoff_at=kickoff)
        self.assertEqual(closing.odds_home, 1.30)
        # Pero la suspensión quedó archivada: es dato, no ausencia de dato.
        series = self.archive.list_snapshots(platform="1xbet_http", external_event_id="ev-1")
        self.assertTrue(series[-1].is_suspended)


if __name__ == "__main__":
    unittest.main()

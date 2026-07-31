"""Al purgar un fixture vencido, su último estado en vivo queda archivado.

Antes de esto, `purge_expired` borraba la entrada y el partido se perdía sin
registro de cómo había terminado.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from services.live_watch import LiveWatchService


def _state(minute: str, *, home_score: int = 2, away_score: int = 1) -> dict:
    return {
        "event_id": "ev-77",
        "minute": minute,
        "home": "Banyule",
        "away": "Bundoora",
        "home_score": home_score,
        "away_score": away_score,
        "home_red_cards": 0,
        "away_red_cards": 1,
        "live_stats": {"possession_home": 61},
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


class LiveWatchArchivingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp_dir.name) / "archiving.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.repository = SqliteStorage()
        self.service = LiveWatchService(repository=self.repository)

    def tearDown(self) -> None:
        if self._prev_db is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db
        self.tmp_dir.cleanup()

    def _expired_entry_with_state(self, state: dict | None) -> int:
        """Crea una entrada ya vencida, opcionalmente con estado en vivo."""

        added = self.service.add_fixture_lines(888, ["Australia | Banyule - Bundoora"])
        entry_id = added[0].id
        long_ago = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
        with open_connection() as conn:
            conn.execute(
                """
                UPDATE live_watch_entries
                SET kickoff_at = ?, created_at = ?, live_state_json = ?
                WHERE id = ?
                """,
                (
                    long_ago,
                    long_ago,
                    json.dumps({"betovo_http": state}) if state else None,
                    entry_id,
                ),
            )
        return entry_id

    def test_a_finished_match_is_archived_with_its_score(self) -> None:
        self._expired_entry_with_state(_state("90+2"))

        purged = self.service.purge_expired()

        self.assertEqual(purged, 1)
        results = self.repository.list_match_results()
        self.assertEqual(len(results), 1)
        archived = results[0]
        self.assertEqual(archived.status, "FINISHED")
        self.assertEqual((archived.final_home_score, archived.final_away_score), (2, 1))
        self.assertEqual(archived.red_cards_away, 1)
        self.assertEqual(archived.platform, "betovo_http")
        self.assertEqual(archived.source, "live_watch")
        self.assertTrue(archived.is_settled)
        # El nivel 3 viaja en el crudo, no en columnas.
        self.assertIn("possession_home", archived.raw_payload_json)

    def test_a_partial_observation_is_archived_but_not_as_final(self) -> None:
        """Una foto del minuto 20 no es un resultado: no puede entrar a los análisis."""

        self._expired_entry_with_state(_state("20'"))

        self.service.purge_expired()

        archived = self.repository.list_match_results()[0]
        self.assertEqual(archived.status, "UNKNOWN")
        self.assertFalse(archived.is_settled)
        self.assertEqual(self.repository.list_match_results(only_settled=True), [])

    def test_a_fixture_never_seen_live_is_not_archived(self) -> None:
        self._expired_entry_with_state(None)

        purged = self.service.purge_expired()

        self.assertEqual(purged, 1)
        self.assertEqual(self.repository.list_match_results(), [])

    def test_archiving_failure_does_not_break_the_purge(self) -> None:
        """Archivar es best-effort: si falla, la purga tiene que seguir."""

        self._expired_entry_with_state(_state("90'"))

        def _explode(*args, **kwargs):
            raise RuntimeError("disco lleno")

        self.repository.record_match_result = _explode

        purged = self.service.purge_expired()

        self.assertEqual(purged, 1)
        with open_connection() as conn:
            remaining = conn.execute("SELECT COUNT(*) AS n FROM live_watch_entries").fetchone()["n"]
        self.assertEqual(remaining, 0)


if __name__ == "__main__":
    unittest.main()

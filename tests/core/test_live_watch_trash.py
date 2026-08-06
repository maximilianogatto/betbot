"""Papelera del live-watch: los partidos que ya salieron no se re-importan.

El auto-import de la planilla volvía a cargar partidos jugados el día anterior:
la fila seguía en el Excel y la entrada original ya había sido purgada, así que
no quedaba nada contra qué deduplicar. La papelera retiene esos fixtures 2 días.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest

from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from services.live_watch import LiveWatchService

CHAT_ID = 4242


class LiveWatchTrashTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp_dir.name) / "trash.sqlite3")
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

    def _add_and_expire(self, line: str) -> None:
        """Carga un fixture y lo empuja a la papelera vía purga (ya se jugó)."""

        added = self.service.add_fixture_lines(CHAT_ID, [line])
        self.assertEqual(len(added), 1)
        long_ago = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
        with open_connection() as conn:
            conn.execute(
                "UPDATE live_watch_entries SET kickoff_at = ?, created_at = ? WHERE id = ?",
                (long_ago, long_ago, added[0].id),
            )
        self.assertEqual(self.service.purge_expired(), 1)

    def test_purged_fixture_lands_in_the_trash(self) -> None:
        self._add_and_expire("Kazajistán (F) | Kazygurt - Zhetysu")

        trash = self.service.list_trash(CHAT_ID)
        self.assertEqual(len(trash), 1)
        self.assertEqual(trash[0].home, "Kazygurt")
        self.assertEqual(trash[0].away, "Zhetysu")
        self.assertEqual(trash[0].reason, "expired")
        self.assertEqual(trash[0].league_hint, "Kazajistán (F)")

    def test_sheet_import_skips_a_fixture_in_the_trash(self) -> None:
        self._add_and_expire("Kazajistán (F) | Kazygurt - Zhetysu")

        added = self.service.add_fixture_lines(
            CHAT_ID,
            ["Kazajistán (F) | Kazygurt - Zhetysu"],
            skip_recently_removed=True,
        )

        self.assertEqual(added, [])
        self.assertEqual(self.service.list_watches(CHAT_ID), [])

    def test_manual_paste_ignores_the_trash(self) -> None:
        """Si el usuario re-pega el partido a mano, lo quiere: no se filtra."""

        self._add_and_expire("Kazajistán (F) | Kazygurt - Zhetysu")

        added = self.service.add_fixture_lines(CHAT_ID, ["Kazygurt - Zhetysu"])

        self.assertEqual(len(added), 1)

    def test_trash_only_blocks_the_same_fixture(self) -> None:
        self._add_and_expire("Kazajistán (F) | Kazygurt - Zhetysu")

        added = self.service.add_fixture_lines(
            CHAT_ID,
            [
                "Kazajistán (F) | Caspiy - Kairat",  # otro partido
                "Kazajistán (F) | Zhetysu - Kazygurt",  # mismos equipos, invertidos
            ],
            skip_recently_removed=True,
        )

        self.assertEqual(len(added), 2)

    def test_trash_expires_after_the_retention_window(self) -> None:
        self._add_and_expire("Kazajistán (F) | Kazygurt - Zhetysu")
        stale = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        with open_connection() as conn:
            conn.execute("UPDATE live_watch_tombstones SET expires_at = ?", (stale,))

        self.assertEqual(self.service.list_trash(CHAT_ID), [])
        added = self.service.add_fixture_lines(
            CHAT_ID,
            ["Kazajistán (F) | Kazygurt - Zhetysu"],
            skip_recently_removed=True,
        )
        self.assertEqual(len(added), 1)

    def test_expired_tombstones_are_swept_by_the_purge_cycle(self) -> None:
        self._add_and_expire("Kazajistán (F) | Kazygurt - Zhetysu")
        stale = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        with open_connection() as conn:
            conn.execute("UPDATE live_watch_tombstones SET expires_at = ?", (stale,))

        self.service.purge_expired()

        with open_connection() as conn:
            remaining = conn.execute(
                "SELECT COUNT(*) AS n FROM live_watch_tombstones"
            ).fetchone()["n"]
        self.assertEqual(remaining, 0)

    def test_manual_removal_also_fills_the_trash(self) -> None:
        added = self.service.add_fixture_lines(CHAT_ID, ["Kazygurt - Zhetysu"])
        self.assertTrue(
            self.service.remove_watch_by_local_id(CHAT_ID, added[0].chat_local_id)
        )

        trash = self.service.list_trash(CHAT_ID)
        self.assertEqual(len(trash), 1)
        self.assertEqual(trash[0].reason, "removed")

    def test_trash_is_per_chat(self) -> None:
        self._add_and_expire("Kazajistán (F) | Kazygurt - Zhetysu")

        added = self.service.add_fixture_lines(
            999,
            ["Kazajistán (F) | Kazygurt - Zhetysu"],
            skip_recently_removed=True,
        )

        self.assertEqual(len(added), 1)


if __name__ == "__main__":
    unittest.main()

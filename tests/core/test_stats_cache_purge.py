from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

tracking_repository_module = importlib.import_module("storage.tracking_repository")


class StatsCachePurgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_db_path = tracking_repository_module.DB_FILE_PATH
        self.tmp = tempfile.TemporaryDirectory()
        tracking_repository_module.DB_FILE_PATH = Path(self.tmp.name) / "tracking.sqlite3"
        self.repo = tracking_repository_module.SqliteTrackingRepository()

    def tearDown(self) -> None:
        tracking_repository_module.DB_FILE_PATH = self.old_db_path
        self.tmp.cleanup()

    def test_purge_removes_only_expired(self) -> None:
        self.repo.set_cached_stats_payload("fresh", {"v": 1}, ttl_seconds=3600)
        self.repo.set_cached_stats_payload("stale", {"v": 2}, ttl_seconds=3600)
        # Backdate the "stale" row past its TTL.
        with tracking_repository_module._connect() as c:
            c.execute(
                "UPDATE stats_payload_cache SET expires_at = ? WHERE cache_key = ?",
                ("2000-01-01T00:00:00+00:00", "stale"),
            )

        removed = self.repo.purge_expired_stats_payloads()

        self.assertEqual(removed, 1)
        self.assertIsNotNone(self.repo.get_cached_stats_payload("fresh"))
        self.assertIsNone(self.repo.get_cached_stats_payload("stale"))

    def test_set_cached_stats_payload_enforces_fifo_row_limit(self) -> None:
        for index in range(tracking_repository_module.STATS_PAYLOAD_CACHE_MAX_ROWS + 5):
            self.repo.set_cached_stats_payload(f"key_{index:03d}", {"v": index}, ttl_seconds=3600)

        with tracking_repository_module._connect() as connection:
            rows = connection.execute(
                "SELECT cache_key FROM stats_payload_cache ORDER BY fetched_at ASC, cache_key ASC"
            ).fetchall()

        keys = [str(row["cache_key"]) for row in rows]
        self.assertEqual(len(keys), tracking_repository_module.STATS_PAYLOAD_CACHE_MAX_ROWS)
        self.assertEqual(keys[0], "key_005")
        self.assertNotIn("key_000", keys)
        self.assertNotIn("key_004", keys)
        self.assertIn("key_204", keys)


if __name__ == "__main__":
    unittest.main()

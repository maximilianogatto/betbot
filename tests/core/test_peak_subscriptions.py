from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

tracking_repository_module = importlib.import_module("storage.tracking_repository")
SqliteTrackingRepository = tracking_repository_module.SqliteTrackingRepository


class PeakDigestSubscriptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_db_path = tracking_repository_module.DB_FILE_PATH
        self.old_data_dir = tracking_repository_module.DATA_DIR
        self.tmp_dir = tempfile.TemporaryDirectory()
        tracking_repository_module.DATA_DIR = Path(self.tmp_dir.name)
        tracking_repository_module.DB_FILE_PATH = Path(self.tmp_dir.name) / "tracking.sqlite3"
        self.repository = SqliteTrackingRepository()

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        tracking_repository_module.DB_FILE_PATH = self.old_db_path
        tracking_repository_module.DATA_DIR = self.old_data_dir

    def test_subscribe_and_list(self) -> None:
        self.assertEqual(self.repository.list_peak_digest_chats(), [])
        self.assertFalse(self.repository.is_peak_digest_enabled(101))

        self.repository.set_peak_digest_subscription(101, True)
        self.repository.set_peak_digest_subscription(202, True)
        self.assertTrue(self.repository.is_peak_digest_enabled(101))
        self.assertEqual(sorted(self.repository.list_peak_digest_chats()), [101, 202])

    def test_unsubscribe(self) -> None:
        self.repository.set_peak_digest_subscription(303, True)
        self.assertIn(303, self.repository.list_peak_digest_chats())

        self.repository.set_peak_digest_subscription(303, False)
        self.assertFalse(self.repository.is_peak_digest_enabled(303))
        self.assertEqual(self.repository.list_peak_digest_chats(), [])

    def test_idempotent_upsert(self) -> None:
        self.repository.set_peak_digest_subscription(404, True)
        self.repository.set_peak_digest_subscription(404, True)
        self.assertEqual(self.repository.list_peak_digest_chats(), [404])


if __name__ == "__main__":
    unittest.main()

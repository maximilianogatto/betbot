from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema


class PeakDigestSubscriptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp_dir.name) / "tracking.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.repository = SqliteStorage()

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        if self.old_db_path is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self.old_db_path

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

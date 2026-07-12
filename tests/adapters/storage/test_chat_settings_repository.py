import unittest
import os
import tempfile
from pathlib import Path

from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from adapters.storage.chat_settings import SQLiteChatSettingsAdapter


class ChatSettingsRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "test_db.sqlite3"
        self._prev_db_path = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(db_path)

        self.adapter = SQLiteChatSettingsAdapter()
        with open_connection() as conn:
            initialize_schema(conn)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        if self._prev_db_path is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db_path

    def test_default_is_none(self) -> None:
        self.assertIsNone(self.adapter.get_chat_timezone(123))

    def test_set_and_get(self) -> None:
        self.adapter.set_chat_timezone(123, "America/Argentina/Buenos_Aires")
        self.assertEqual(
            self.adapter.get_chat_timezone(123),
            "America/Argentina/Buenos_Aires",
        )

    def test_set_is_idempotent_upsert(self) -> None:
        self.adapter.set_chat_timezone(123, "UTC")
        self.adapter.set_chat_timezone(123, "Europe/Madrid")
        self.assertEqual(self.adapter.get_chat_timezone(123), "Europe/Madrid")

    def test_clear_reverts_to_default(self) -> None:
        self.adapter.set_chat_timezone(123, "UTC")
        self.adapter.clear_chat_timezone(123)
        self.assertIsNone(self.adapter.get_chat_timezone(123))

    def test_clear_on_unknown_chat_is_noop(self) -> None:
        self.adapter.clear_chat_timezone(999)  # must not raise
        self.assertIsNone(self.adapter.get_chat_timezone(999))


if __name__ == "__main__":
    unittest.main()

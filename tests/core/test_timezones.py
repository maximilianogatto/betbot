from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.alerts import format_display_datetime
from core.timezones import (
    current_display_timezone,
    default_timezone,
    get_zoneinfo,
    resolve_chat_timezone,
    tz_offset_label,
    use_timezone,
)



class TimezoneHelpersTests(unittest.TestCase):
    def test_get_zoneinfo_valid_and_invalid(self) -> None:
        self.assertIsInstance(get_zoneinfo("America/Sao_Paulo"), ZoneInfo)
        self.assertIsNone(get_zoneinfo("Not/AZone"))
        self.assertIsNone(get_zoneinfo(""))
        self.assertIsNone(get_zoneinfo(None))

    def test_default_timezone_is_argentina(self) -> None:
        self.assertEqual(str(default_timezone()), "America/Argentina/Buenos_Aires")

    def test_offset_label(self) -> None:
        self.assertEqual(
            tz_offset_label(ZoneInfo("America/Argentina/Buenos_Aires")), "UTC-03"
        )
        self.assertEqual(tz_offset_label(ZoneInfo("UTC")), "UTC+00")
        # Half-hour offset shows minutes.
        self.assertEqual(tz_offset_label(ZoneInfo("Asia/Kolkata")), "UTC+05:30")

    def test_use_timezone_context_resets(self) -> None:
        self.assertEqual(str(current_display_timezone()), "America/Argentina/Buenos_Aires")
        with use_timezone(ZoneInfo("Europe/Madrid")):
            self.assertEqual(str(current_display_timezone()), "Europe/Madrid")
        self.assertEqual(str(current_display_timezone()), "America/Argentina/Buenos_Aires")

    def test_format_display_datetime_follows_active_tz(self) -> None:
        # 22:00 UTC: 19:00 Argentina vs 23:00 Madrid (CET, UTC+1, winter).
        iso = "2026-01-13T22:00:00+00:00"
        self.assertEqual(format_display_datetime(iso), "Mar 13/01 19:00")
        with use_timezone(ZoneInfo("Europe/Madrid")):
            self.assertEqual(format_display_datetime(iso), "Mar 13/01 23:00")


class ChatTimezonePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        # resolve_chat_timezone() lee vía el facade greenfield (get_storage()), así
        # que el test escribe/lee por el MISMO facade sobre una DB greenfield temporal.
        from adapters.storage import SqliteStorage
        from adapters.storage.connection import open_connection
        from adapters.storage.schema import initialize_schema

        self.tmp = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp.name) / "tz.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.repo = SqliteStorage()

    def tearDown(self) -> None:
        if self._prev_db is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db
        self.tmp.cleanup()

    def test_set_get_clear_roundtrip(self) -> None:
        chat = 1234
        self.assertIsNone(self.repo.get_chat_timezone(chat))
        # Unset chat resolves to default.
        self.assertEqual(str(resolve_chat_timezone(chat)), "America/Argentina/Buenos_Aires")

        self.repo.set_chat_timezone(chat, "Europe/Madrid")
        self.assertEqual(self.repo.get_chat_timezone(chat), "Europe/Madrid")
        self.assertEqual(str(resolve_chat_timezone(chat)), "Europe/Madrid")

        # Overwrite, then reset back to default.
        self.repo.set_chat_timezone(chat, "America/Sao_Paulo")
        self.assertEqual(self.repo.get_chat_timezone(chat), "America/Sao_Paulo")
        self.repo.clear_chat_timezone(chat)
        self.assertIsNone(self.repo.get_chat_timezone(chat))
        self.assertEqual(str(resolve_chat_timezone(chat)), "America/Argentina/Buenos_Aires")


if __name__ == "__main__":
    unittest.main()

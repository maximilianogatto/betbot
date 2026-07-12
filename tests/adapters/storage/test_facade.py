import unittest
import inspect
import os
import tempfile
from pathlib import Path

from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from core.ports import (
    competitions,
    events,
    subscriptions,
    baselines,
    stats_links,
    live_watch,
    maintenance,
    chat_settings,
)

PORT_MODULES = [
    competitions, events, subscriptions, baselines,
    stats_links, live_watch, maintenance, chat_settings,
]


class FacadeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "test_db.sqlite3"
        self._prev = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(db_path)
        with open_connection() as conn:
            initialize_schema(conn)
        self.storage = SqliteStorage()

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        if self._prev is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev

    def test_facade_implements_all_port_methods(self) -> None:
        """El facade expone todos los métodos de todos los ports de storage."""
        for mod in PORT_MODULES:
            for name, obj in inspect.getmembers(mod, inspect.isclass):
                if name.endswith("Port") and obj.__module__ == mod.__name__:
                    for meth, _ in inspect.getmembers(obj, callable):
                        if not meth.startswith("_"):
                            self.assertTrue(
                                hasattr(self.storage, meth),
                                f"Facade no expone {name}.{meth}",
                            )

    def test_facade_delegates_end_to_end(self) -> None:
        """Métodos de distintos agregados funcionan a través del mismo objeto facade."""
        self.storage.set_chat_timezone(42, "UTC")
        self.assertEqual(self.storage.get_chat_timezone(42), "UTC")
        self.storage.clear_chat_timezone(42)
        self.assertIsNone(self.storage.get_chat_timezone(42))


if __name__ == "__main__":
    unittest.main()

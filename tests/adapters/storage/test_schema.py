from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from adapters.storage.connection import (
    open_connection,
    resolve_database_path,
    transaction,
)
from adapters.storage.schema import (
    EXPECTED_TABLES,
    FORBIDDEN_LEGACY_TABLES,
    get_schema_version,
    initialize_schema,
    list_tables,
)

class StorageSchemaTests(unittest.TestCase):
    def test_open_connection_initializes_greenfield_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "greenfield.sqlite3"

            with open_connection(db_path) as connection:
                tables = list_tables(connection)
                self.assertTrue(set(EXPECTED_TABLES).issubset(tables))
                self.assertTrue(set(FORBIDDEN_LEGACY_TABLES).isdisjoint(tables))
                self.assertEqual(get_schema_version(connection), 5)

                row = connection.execute("SELECT 1 AS value").fetchone()
                self.assertIsInstance(row, sqlite3.Row)
                self.assertEqual(row["value"], 1)
                self.assertEqual(
                    connection.execute("PRAGMA foreign_keys").fetchone()[0],
                    1,
                )
                self.assertGreater(
                    connection.execute("PRAGMA busy_timeout").fetchone()[0],
                    0,
                )

            self.assertTrue(db_path.exists())

    def test_schema_is_idempotent_and_preserves_data(self) -> None:
        with open_connection(":memory:") as connection:
            competition_id = connection.execute(
                """
                INSERT INTO competitions(platform, external_id, name, source_url, created_at, updated_at)
                VALUES ('test', 'league-1', 'Test League', 'http://url', '2026-06-29', '2026-06-29')
                """
            ).lastrowid
            connection.commit()

            initialize_schema(connection)

            row = connection.execute(
                "SELECT name FROM competitions WHERE id = ?",
                (competition_id,),
            ).fetchone()
            self.assertEqual(row["name"], "Test League")

    def test_cascade_from_competition_removes_dependent_rows(self) -> None:
        with open_connection(":memory:") as connection:
            competition_id = connection.execute(
                """
                INSERT INTO competitions(platform, external_id, name, source_url, created_at, updated_at)
                VALUES ('test', 'league-1', 'Test League', 'http://url', '2026-06-29', '2026-06-29')
                """
            ).lastrowid
            event_id = connection.execute(
                """
                INSERT INTO events(
                    competition_id, platform, external_event_id, home, away,
                    first_seen_at, last_seen_at, created_at, updated_at
                )
                VALUES (?, 'test', 'event-1', 'Home', 'Away', '2026', '2026', '2026', '2026')
                """,
                (competition_id,),
            ).lastrowid
            connection.execute(
                """
                INSERT INTO subscriptions(chat_id, competition_id, created_at, updated_at)
                VALUES (123, ?, '2026', '2026')
                """,
                (competition_id,),
            )
            connection.execute(
                """
                INSERT INTO baselines(chat_id, event_id, set_at, updated_at)
                VALUES (123, ?, '2026', '2026')
                """,
                (event_id,),
            )
            connection.execute(
                """
                INSERT INTO sent_alerts(chat_id, event_id, alert_type, sent_at)
                VALUES (123, ?, 'new_match', '2026')
                """,
                (event_id,),
            )
            connection.execute(
                """
                INSERT INTO stats_match_links(event_id, provider, match_id, method, created_at, updated_at)
                VALUES (?, 'stats', 'match-1', 'manual', '2026', '2026')
                """,
                (event_id,),
            )
            connection.commit()

            connection.execute("DELETE FROM competitions WHERE id = ?", (competition_id,))
            connection.commit()

            for table in (
                "events",
                "subscriptions",
                "baselines",
                "sent_alerts",
                "stats_match_links",
            ):
                self.assertEqual(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                    0,
                    table,
                )

    def test_transaction_rolls_back_on_error(self) -> None:
        with open_connection(":memory:") as connection:
            with self.assertRaises(RuntimeError):
                with transaction(connection) as tx:
                    tx.execute(
                        """
                        INSERT INTO competitions(platform, external_id, name, source_url, created_at, updated_at)
                        VALUES ('test', 'league-1', 'Test League', 'http://url', '2026-06-29', '2026-06-29')
                        """
                    )
                    raise RuntimeError("boom")

            count = connection.execute("SELECT COUNT(*) FROM competitions").fetchone()[0]
            self.assertEqual(count, 0)

    def test_resolve_database_path_uses_env_relative_to_project_root(self) -> None:
        previous = os.environ.get("BETBOT_DB_PATH")
        try:
            os.environ["BETBOT_DB_PATH"] = "data/custom-test.sqlite3"
            resolved = resolve_database_path()
            self.assertTrue(str(resolved).endswith("data/custom-test.sqlite3"))
            self.assertTrue(resolved.is_absolute())
        finally:
            if previous is None:
                os.environ.pop("BETBOT_DB_PATH", None)
            else:
                os.environ["BETBOT_DB_PATH"] = previous

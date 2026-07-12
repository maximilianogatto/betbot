from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path

from adapters.storage.connection import open_connection, resolve_database_path
from adapters.storage.schema import initialize_schema
from storage import league_seed


def _sample_seed() -> dict:
    return {
        "version": 1,
        "exported_at": "2026-01-01T00:00:00Z",
        "unified_competitions": ["Premier League", "Serie A"],
        "tracked_competitions": [
            {
                "platform": "1xbet_http",
                "competition_external_id": "PL-1X",
                "competition_name": "Inglaterra. Premier League",
                "source_url": "1xbet:league:PL-1X",
                "metadata_json": None,
                "needs_name_resolution": 0,
                "enabled": 1,
                "reminders_enabled": 1,
                "unified_name": "Premier League",
            },
            {
                "platform": "betovo_http",
                "competition_external_id": "PL-BV",
                "competition_name": "England Premier League",
                "source_url": "betovo:league:PL-BV",
                "metadata_json": "{\"k\": 1}",
                "needs_name_resolution": 0,
                "enabled": 1,
                "reminders_enabled": 0,
                "unified_name": "Premier League",
            },
            {
                "platform": "1xbet_http",
                "competition_external_id": "SA-1X",
                "competition_name": "Italia. Serie A",
                "source_url": "1xbet:league:SA-1X",
                "metadata_json": None,
                "needs_name_resolution": 0,
                "enabled": 1,
                "reminders_enabled": 0,
                "unified_name": "Serie A",
            },
        ],
        "stats_league_links": [
            {
                "platform": "1xbet_http",
                "competition_external_id": "PL-1X",
                "stats_provider": "sofascore_http",
                "stats_league_id": "17",
                "stats_league_name": "Premier League",
                "stats_country_name": "England",
                "confidence": 1.0,
                "payload_json": None,
            },
        ],
    }


class LeagueSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp.name) / "tracking.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.seed_path = Path(self.tmp.name) / "leagues.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()
        if self.old_db_path is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self.old_db_path

    def _counts(self) -> dict[str, int]:
        with open_connection() as c:
            return {
                t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in (
                    "unified_competitions",
                    "competitions",
                    "stats_league_links",
                    "subscriptions",
                    "events",
                )
            }

    def test_import_then_export_roundtrip(self) -> None:
        counts = league_seed.import_league_seed(_sample_seed(), overwrite=False)
        self.assertEqual(counts["unified_created"], 2)
        self.assertEqual(counts["tracked_inserted"], 3)
        self.assertEqual(counts["stats_inserted"], 1)

        db = self._counts()
        self.assertEqual(db["unified_competitions"], 2)
        self.assertEqual(db["competitions"], 3)
        self.assertEqual(db["stats_league_links"], 1)
        # User tables are never populated by a seed import.
        self.assertEqual(db["subscriptions"], 0)
        self.assertEqual(db["events"], 0)

        # Export is registry-centric (v2): one entry per league with its
        # platform links + league-level stats links.
        exported = league_seed.export_league_seed()
        self.assertEqual(exported["version"], 2)
        by_name = {league["name"]: league for league in exported["leagues"]}
        self.assertEqual(set(by_name), {"Premier League", "Serie A"})
        pl = by_name["Premier League"]
        self.assertEqual(
            {(p["platform"], p["competition_external_id"]) for p in pl["platforms"]},
            {("1xbet_http", "PL-1X"), ("betovo_http", "PL-BV")},
        )
        self.assertEqual(pl["public_id"], "premier-league")
        self.assertEqual(len(pl["stats_links"]), 1)
        self.assertEqual(pl["stats_links"][0]["stats_provider"], "sofascore_http")
        self.assertEqual(exported["unlinked_platforms"], [])

        # And a v2 export imports cleanly into a fresh DB (full roundtrip).
        with tempfile.TemporaryDirectory() as tmp2:
            os.environ["BETBOT_DB_PATH"] = str(Path(tmp2) / "fresh.sqlite3")
            with open_connection() as conn:
                initialize_schema(conn)
            counts2 = league_seed.import_league_seed(exported, overwrite=False)
            self.assertEqual(counts2["unified_created"], 2)
            self.assertEqual(counts2["tracked_inserted"], 3)
            self.assertEqual(counts2["stats_inserted"], 1)
            with open_connection() as c:
                row = c.execute(
                    "SELECT public_id FROM unified_competitions WHERE name = 'Premier League'"
                ).fetchone()
                self.assertEqual(row["public_id"], "premier-league")
                link = c.execute(
                    "SELECT c.unified_competition_id FROM stats_league_links s JOIN competitions c ON c.id = s.competition_id"
                ).fetchone()
                self.assertIsNotNone(link["unified_competition_id"])
            os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp.name) / "tracking.sqlite3")

    def test_import_is_idempotent(self) -> None:
        league_seed.import_league_seed(_sample_seed(), overwrite=False)
        counts = league_seed.import_league_seed(_sample_seed(), overwrite=False)
        self.assertEqual(counts["tracked_inserted"], 0)
        self.assertEqual(counts["tracked_skipped"], 3)
        self.assertEqual(counts["stats_inserted"], 0)
        self.assertEqual(self._counts()["competitions"], 3)

    def test_overwrite_updates_existing(self) -> None:
        league_seed.import_league_seed(_sample_seed(), overwrite=False)
        data = _sample_seed()
        data["tracked_competitions"][0]["competition_name"] = "NEW NAME"
        counts = league_seed.import_league_seed(data, overwrite=True)
        self.assertEqual(counts["tracked_updated"], 3)
        with open_connection() as c:
            row = c.execute(
                "SELECT name FROM competitions WHERE platform=? AND external_id=?",
                ("1xbet_http", "PL-1X"),
            ).fetchone()
        self.assertEqual(row["name"], "NEW NAME")

    def test_seed_if_empty_bootstraps_then_noop(self) -> None:
        self.seed_path.write_text(json.dumps(_sample_seed()), encoding="utf-8")
        first = league_seed.seed_if_empty(self.seed_path)
        self.assertIsNotNone(first)
        self.assertEqual(first["tracked_inserted"], 3)
        # DB now has data -> second call is a no-op.
        self.assertIsNone(league_seed.seed_if_empty(self.seed_path))

    def test_seed_if_empty_without_file_is_noop(self) -> None:
        self.assertIsNone(league_seed.seed_if_empty(self.seed_path))
        self.assertEqual(self._counts()["competitions"], 0)


if __name__ == "__main__":
    unittest.main()

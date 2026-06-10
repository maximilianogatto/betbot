from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from pathlib import Path

tracking_repository_module = importlib.import_module("storage.tracking_repository")
from storage import league_seed  # noqa: E402


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
        self.old_db_path = tracking_repository_module.DB_FILE_PATH
        self.tmp = tempfile.TemporaryDirectory()
        tracking_repository_module.DB_FILE_PATH = Path(self.tmp.name) / "tracking.sqlite3"
        self.seed_path = Path(self.tmp.name) / "leagues.json"

    def tearDown(self) -> None:
        tracking_repository_module.DB_FILE_PATH = self.old_db_path
        self.tmp.cleanup()

    def _counts(self) -> dict[str, int]:
        with tracking_repository_module._connect() as c:
            return {
                t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in (
                    "unified_competitions",
                    "tracked_competitions",
                    "stats_league_links",
                    "competition_subscriptions",
                    "active_events",
                )
            }

    def test_import_then_export_roundtrip(self) -> None:
        counts = league_seed.import_league_seed(_sample_seed(), overwrite=False)
        self.assertEqual(counts["unified_created"], 2)
        self.assertEqual(counts["tracked_inserted"], 3)
        self.assertEqual(counts["stats_inserted"], 1)

        db = self._counts()
        self.assertEqual(db["unified_competitions"], 2)
        self.assertEqual(db["tracked_competitions"], 3)
        self.assertEqual(db["stats_league_links"], 1)
        # User tables are never populated by a seed import.
        self.assertEqual(db["competition_subscriptions"], 0)
        self.assertEqual(db["active_events"], 0)

        exported = league_seed.export_league_seed()
        self.assertEqual(set(exported["unified_competitions"]), {"Premier League", "Serie A"})
        keys = {(t["platform"], t["competition_external_id"]) for t in exported["tracked_competitions"]}
        self.assertEqual(keys, {("1xbet_http", "PL-1X"), ("betovo_http", "PL-BV"), ("1xbet_http", "SA-1X")})
        # The two Premier League platforms share one unified group.
        pl = [t for t in exported["tracked_competitions"] if t["unified_name"] == "Premier League"]
        self.assertEqual(len(pl), 2)
        self.assertEqual(len(exported["stats_league_links"]), 1)

    def test_import_is_idempotent(self) -> None:
        league_seed.import_league_seed(_sample_seed(), overwrite=False)
        counts = league_seed.import_league_seed(_sample_seed(), overwrite=False)
        self.assertEqual(counts["tracked_inserted"], 0)
        self.assertEqual(counts["tracked_skipped"], 3)
        self.assertEqual(counts["stats_inserted"], 0)
        self.assertEqual(self._counts()["tracked_competitions"], 3)

    def test_overwrite_updates_existing(self) -> None:
        league_seed.import_league_seed(_sample_seed(), overwrite=False)
        data = _sample_seed()
        data["tracked_competitions"][0]["competition_name"] = "NEW NAME"
        counts = league_seed.import_league_seed(data, overwrite=True)
        self.assertEqual(counts["tracked_updated"], 3)
        with tracking_repository_module._connect() as c:
            row = c.execute(
                "SELECT competition_name FROM tracked_competitions WHERE platform=? AND competition_external_id=?",
                ("1xbet_http", "PL-1X"),
            ).fetchone()
        self.assertEqual(row["competition_name"], "NEW NAME")

    def test_seed_if_empty_bootstraps_then_noop(self) -> None:
        self.seed_path.write_text(json.dumps(_sample_seed()), encoding="utf-8")
        first = league_seed.seed_if_empty(self.seed_path)
        self.assertIsNotNone(first)
        self.assertEqual(first["tracked_inserted"], 3)
        # DB now has data -> second call is a no-op.
        self.assertIsNone(league_seed.seed_if_empty(self.seed_path))

    def test_seed_if_empty_without_file_is_noop(self) -> None:
        self.assertIsNone(league_seed.seed_if_empty(self.seed_path))
        self.assertEqual(self._counts()["tracked_competitions"], 0)


if __name__ == "__main__":
    unittest.main()

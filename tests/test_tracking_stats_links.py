from __future__ import annotations

import importlib
from pathlib import Path
import tempfile
import unittest

from storage.tracking_repository import ActiveEventUpsert, SqliteTrackingRepository

tracking_repository_module = importlib.import_module("storage.tracking_repository")


class TrackingStatsLinksTests(unittest.TestCase):
    def test_upserts_stats_league_and_match_links(self) -> None:
        old_db_path = tracking_repository_module.DB_FILE_PATH
        old_data_dir = tracking_repository_module.DATA_DIR

        with tempfile.TemporaryDirectory() as tmp_dir:
            tracking_repository_module.DATA_DIR = Path(tmp_dir)
            tracking_repository_module.DB_FILE_PATH = Path(tmp_dir) / "tracking.sqlite3"
            try:
                repository = SqliteTrackingRepository()
                chat_id = 10
                repository.create_pending_competition_request(
                    chat_id,
                    platform="bet365",
                    source_url="https://example.test/league",
                    competition_external_id="league-1",
                    competition_name="Spanish Primera",
                )
                confirmed = repository.confirm_pending_competition_request(chat_id)
                self.assertIsNotNone(confirmed)
                tracked_id = confirmed.tracked_competition.id

                league_link = repository.upsert_stats_league_link(
                    tracked_id,
                    stats_provider="sportradar_statshub",
                    stats_league_id="8",
                    stats_league_name="LaLiga",
                    stats_country_name="Spain",
                    confidence=0.98,
                    payload={"source": "test"},
                )

                loaded_league_link = repository.get_stats_league_link(tracked_id)
                self.assertEqual(loaded_league_link, league_link)
                self.assertEqual(league_link.stats_provider, "sportradar_statshub")
                self.assertEqual(league_link.stats_league_id, "8")

                repository.upsert_active_events(
                    tracked_id,
                    [
                        ActiveEventUpsert(
                            external_event_id="fixture-1",
                            home="Sevilla",
                            away="Real Madrid",
                            scheduled_label_date="Dom 24/05",
                            scheduled_label_time="17:00",
                            scheduled_at="2026-05-24T17:00:00+00:00",
                            odds_home=3.2,
                            odds_draw=3.5,
                            odds_away=2.1,
                        )
                    ],
                )
                event = repository.get_active_events(tracked_id, only_future=False)[0]

                match_link = repository.upsert_stats_match_link(
                    event.id,
                    stats_provider="sportradar_statshub",
                    stats_match_id="61624678",
                    stats_url="https://statshub.sportradar.com/bet365/en/match/61624678",
                    confidence=0.95,
                    method="league_fixture_similarity",
                    payload={"score": 0.95},
                )
                loaded_match_link = repository.get_stats_match_link(event.id)

                self.assertEqual(loaded_match_link, match_link)
                self.assertEqual(match_link.stats_match_id, "61624678")
                self.assertEqual(match_link.method, "league_fixture_similarity")
            finally:
                tracking_repository_module.DB_FILE_PATH = old_db_path
                tracking_repository_module.DATA_DIR = old_data_dir


if __name__ == "__main__":
    unittest.main()

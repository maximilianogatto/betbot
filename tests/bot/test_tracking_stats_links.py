from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from core.models import ActiveEventUpsert
from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema


class TrackingStatsLinksTests(unittest.TestCase):
    def test_upserts_stats_league_and_match_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            old_db = os.environ.get("BETBOT_DB_PATH")
            os.environ["BETBOT_DB_PATH"] = str(Path(tmp_dir) / "tracking.sqlite3")
            with open_connection() as conn:
                initialize_schema(conn)
            try:
                repository = SqliteStorage()
                chat_id = 10
                repository.create_pending_competition_request(
                    chat_id,
                    platform="bet365",
                    source_url="https://example.test/league",
                    competition_external_id="league-1",
                    competition_name="Spanish Primera",
                    requires_empty_confirmation=False,
                    needs_name_resolution=False,
                )
                confirmed = repository.confirm_pending_competition_request(chat_id)
                self.assertIsNotNone(confirmed)
                tracked_id = confirmed.id

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
                self.assertEqual(loaded_league_link.stats_league_id, league_link.stats_league_id)
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

                self.assertEqual(loaded_match_link.stats_match_id, match_link.stats_match_id)
                self.assertEqual(match_link.stats_match_id, "61624678")
                self.assertEqual(match_link.method, "league_fixture_similarity")
            finally:
                if old_db is None:
                    os.environ.pop("BETBOT_DB_PATH", None)
                else:
                    os.environ["BETBOT_DB_PATH"] = old_db

    def test_tracks_stats_league_without_sportsbook_competition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            old_db = os.environ.get("BETBOT_DB_PATH")
            os.environ["BETBOT_DB_PATH"] = str(Path(tmp_dir) / "tracking.sqlite3")
            with open_connection() as conn:
                initialize_schema(conn)
            try:
                repository = SqliteStorage()
                subscription = repository.upsert_stats_league_subscription(
                    10,
                    stats_provider="footystats_http",
                    stats_league_id="australia/northern-nsw-npl",
                    stats_league_name="Northern NSW NPL",
                    stats_country_name="Australia",
                    source_url="https://footystats.org/australia/northern-nsw-npl",
                    payload={"source": "public_html"},
                )

                loaded = repository.list_stats_league_subscriptions(10)
                global_loaded = repository.list_globally_active_stats_leagues()

                self.assertEqual(loaded[0].stats_league_id, subscription.stats_league_id)
                self.assertEqual(global_loaded[0].stats_league_id, subscription.stats_league_id)
                self.assertTrue(
                    repository.delete_stats_league_subscription(
                        10,
                        stats_provider="footystats_http",
                        stats_league_id="australia/northern-nsw-npl",
                    )
                )
                self.assertEqual(repository.list_stats_league_subscriptions(10), [])
            finally:
                if old_db is None:
                    os.environ.pop("BETBOT_DB_PATH", None)
                else:
                    os.environ["BETBOT_DB_PATH"] = old_db


if __name__ == "__main__":
    unittest.main()

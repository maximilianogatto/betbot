import unittest
import os
import tempfile
from pathlib import Path

from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from adapters.storage.stats_links import SQLiteStatsLinksAdapter
from core.models import StatsLeagueLink, StatsMatchLinkRecord

class StatsLinksRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "test_db.sqlite3"
        self._prev_db_path = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(db_path)

        self.adapter = SQLiteStatsLinksAdapter()
        with open_connection() as conn:
            initialize_schema(conn)
            
            # Setup dummy competition
            conn.execute(
                """
                INSERT INTO competitions(id, platform, external_id, name, source_url, created_at, updated_at)
                VALUES (1, 'bet365', 'comp-1', 'La Liga', 'http://url', '2026', '2026')
                """
            )
            # Setup events
            conn.execute(
                """
                INSERT INTO events(id, competition_id, platform, external_event_id, home, away, is_active, first_seen_at, last_seen_at, created_at, updated_at)
                VALUES (100, 1, 'bet365', 'evt-100', 'Real Madrid', 'Barcelona', 1, '2026', '2026', '2026', '2026')
                """
            )

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        if self._prev_db_path is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db_path

    def test_stats_league_links_both_signatures(self) -> None:
        # 1. Port signature
        self.adapter.upsert_stats_league_link(
            1, # tracked_competition_id
            "sportradar", # stats_provider
            "sr-league-1", # stats_league_id
            "La Liga stats", # stats_league_name
            "Spain", # stats_country_name
            0.95, # confidence
            '{"details": true}' # payload_json
        )
        
        links = self.adapter.list_stats_league_links(1)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].stats_league_id, "sr-league-1")
        self.assertEqual(links[0].stats_provider, "sportradar")
        
        # 2. Legacy signature (using kwargs)
        self.adapter.upsert_stats_league_link(
            1,
            stats_provider="sportradar",
            stats_league_id="sr-league-updated",
            stats_league_name="La Liga stats updated",
            stats_country_name="Spain",
            confidence=1.0,
            payload={"updated": True}
        )
        
        link = self.adapter.get_stats_league_link(1, "sportradar")
        self.assertIsNotNone(link)
        self.assertEqual(link.stats_league_id, "sr-league-updated")
        self.assertEqual(link.confidence, 1.0)
        
        # Test delete
        deleted = self.adapter.delete_stats_league_link(1, "sportradar")
        self.assertTrue(deleted)
        self.assertIsNone(self.adapter.get_stats_league_link(1, "sportradar"))

    def test_stats_match_links_both_signatures(self) -> None:
        # 1. Port signature
        self.adapter.upsert_stats_match_link(
            100, # active_event_id
            "sportradar", # stats_provider
            "sr-match-1", # stats_match_id
            "http://sr-url", # stats_url
            0.9, # confidence
            "auto", # method
            '{"meta": 1}' # payload_json
        )
        
        link = self.adapter.get_stats_match_link(100, "sportradar")
        self.assertIsNotNone(link)
        self.assertEqual(link.stats_match_id, "sr-match-1")
        self.assertEqual(link.method, "auto")
        
        # 2. Legacy signature (using kwargs)
        self.adapter.upsert_stats_match_link(
            100,
            stats_provider="sportradar",
            stats_match_id="sr-match-updated",
            stats_url="http://sr-url-updated",
            confidence=0.99,
            method="manual",
            payload={"meta": 2}
        )
        
        links = self.adapter.list_stats_match_links(100)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].stats_match_id, "sr-match-updated")
        self.assertEqual(links[0].method, "manual")
        self.assertEqual(links[0].confidence, 0.99)

import unittest
import sqlite3
import json
import os
import tempfile
from pathlib import Path

from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from adapters.storage.subscriptions import SQLiteSubscriptionsAdapter

class SubscriptionsRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "test_db.sqlite3"
        self._prev_db_path = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(db_path)

        self.adapter = SQLiteSubscriptionsAdapter()
        with open_connection() as conn:
            initialize_schema(conn)
            
            # Setup dummy competitions
            conn.execute(
                """
                INSERT INTO competitions(id, platform, external_id, name, source_url, created_at, updated_at)
                VALUES (1, 'bet365', 'comp-1', 'La Liga', 'http://url', '2026', '2026')
                """
            )
            conn.execute(
                """
                INSERT INTO competitions(id, platform, external_id, name, source_url, created_at, updated_at)
                VALUES (2, 'betsson', 'comp-2', 'Serie A', 'http://url2', '2026', '2026')
                """
            )
            # Setup unified competition
            conn.execute(
                """
                INSERT INTO unified_competitions(id, public_id, name, created_at, updated_at)
                VALUES (10, 'la-liga', 'La Liga Canonical', '2026', '2026')
                """
            )
            conn.execute("UPDATE competitions SET unified_competition_id = 10 WHERE id = 1")
            
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

    def test_competition_subscriptions(self) -> None:
        chat_id = 123
        # Create subscription (via set_competition_reminders which inserts if missing)
        self.adapter.set_competition_reminders(chat_id, 1, True)
        
        # Test get_tracked_competition_subscription
        sub = self.adapter.get_tracked_competition_subscription(chat_id, 1)
        self.assertIsNotNone(sub)
        self.assertEqual(sub.telegram_chat_id, chat_id)
        self.assertEqual(sub.tracked_competition_id, 1)
        self.assertTrue(sub.enabled)
        
        # Test get_tracked_competition_subscription_by_identity
        combined = self.adapter.get_tracked_competition_subscription_by_identity(chat_id, "bet365", "comp-1")
        self.assertIsNotNone(combined)
        self.assertEqual(combined.tracked_competition.competition_name, "La Liga")
        self.assertEqual(combined.subscription.telegram_chat_id, chat_id)
        
        # Test get_subscriptions_for_competition
        subs = self.adapter.get_subscriptions_for_competition(1)
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].telegram_chat_id, chat_id)
        
        # Test get_enabled_subscription_count
        self.assertEqual(self.adapter.get_enabled_subscription_count(), 1)
        self.assertEqual(self.adapter.get_enabled_subscription_count(1), 1)
        self.assertEqual(self.adapter.get_enabled_subscription_count(2), 0)
        
        # Test modification methods
        self.adapter.set_change_percent_threshold(chat_id, 1, 15.0)
        self.adapter.set_odds_notifications(chat_id, 1, False)
        
        updated_sub = self.adapter.get_tracked_competition_subscription(chat_id, 1)
        self.assertEqual(updated_sub.change_percent_threshold, 15.0)
        self.assertFalse(updated_sub.notify_odds_changes)
        
        # Test remove_tracked_competition_subscription
        removed = self.adapter.remove_tracked_competition_subscription(chat_id, 1)
        self.assertTrue(removed)
        self.assertIsNone(self.adapter.get_tracked_competition_subscription(chat_id, 1))

    def test_remove_unified_subscription(self) -> None:
        chat_id = 456
        self.adapter.set_competition_reminders(chat_id, 1, True)
        
        # Remove unified subscription (which deletes subscriptions to child tracker competition 1)
        removed = self.adapter.remove_unified_subscription(chat_id, 10)
        self.assertTrue(removed)
        self.assertIsNone(self.adapter.get_tracked_competition_subscription(chat_id, 1))

    def test_legacy_global_reminders(self) -> None:
        # Legacy signature for set_competition_reminders/competition_reminders_enabled
        self.adapter.set_competition_reminders(1, True)
        self.assertTrue(self.adapter.competition_reminders_enabled(1))
        
        self.adapter.set_competition_reminders(1, False)
        self.assertFalse(self.adapter.competition_reminders_enabled(1))

    def test_event_reminders_both_signatures(self) -> None:
        # 1. Legacy signature: (competition_id, external_event_id, enabled)
        self.adapter.set_event_reminder(1, "evt-100", True)
        enabled_ext_ids = self.adapter.event_reminder_enabled_ids(1)
        self.assertEqual(enabled_ext_ids, {"evt-100"})
        
        self.adapter.set_event_reminder(1, "evt-100", False)
        enabled_ext_ids = self.adapter.event_reminder_enabled_ids(1)
        self.assertEqual(enabled_ext_ids, set())
        
        # 2. Port signature: (chat_id, event_id, enabled)
        chat_id = 789
        self.adapter.set_event_reminder(chat_id, 100, True)
        enabled_event_ids = self.adapter.event_reminder_enabled_ids(chat_id)
        self.assertEqual(enabled_event_ids, {100})
        
        self.adapter.set_event_reminder(chat_id, 100, False)
        enabled_event_ids = self.adapter.event_reminder_enabled_ids(chat_id)
        self.assertEqual(enabled_event_ids, set())

    def test_stats_league_subscriptions(self) -> None:
        chat_id = 111
        self.adapter.upsert_stats_league_subscription(
            chat_id=chat_id,
            provider="sportradar",
            stats_league_id="sr-1",
            stats_league_name="EPL Stats",
            stats_country_name="England",
            source_url="http://stats-epl"
        )
        
        subs = self.adapter.list_stats_league_subscriptions(chat_id)
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].stats_league_name, "EPL Stats")
        self.assertEqual(subs[0].stats_country_name, "England")
        
        # Update
        self.adapter.upsert_stats_league_subscription(
            chat_id=chat_id,
            provider="sportradar",
            stats_league_id="sr-1",
            stats_league_name="EPL Stats Updated"
        )
        subs_updated = self.adapter.list_stats_league_subscriptions(chat_id)
        self.assertEqual(subs_updated[0].stats_league_name, "EPL Stats Updated")

    def test_peak_digest_subscriptions(self) -> None:
        self.adapter.set_peak_digest_subscription(222, True)
        self.adapter.set_peak_digest_subscription(333, True)
        
        chats = self.adapter.list_peak_digest_chats()
        self.assertEqual(set(chats), {222, 333})
        
        self.adapter.set_peak_digest_subscription(222, False)
        chats_after = self.adapter.list_peak_digest_chats()
        self.assertEqual(chats_after, [333])

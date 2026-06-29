import unittest
import sqlite3
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from adapters.storage.competitions import SQLiteCompetitionsAdapter
from core.models import TrackedCompetition, PendingCompetitionTrackRequest

class CompetitionsRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "test_db.sqlite3"
        self._prev_db_path = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(db_path)
        
        self.adapter = SQLiteCompetitionsAdapter()
        with open_connection() as conn:
            initialize_schema(conn)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        if self._prev_db_path is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db_path

    def test_pending_competition_request_flow(self) -> None:
        chat_id = 999
        req = self.adapter.create_pending_competition_request(
            chat_id=chat_id,
            platform="bet365",
            source_url="http://example.com/league",
            competition_external_id="league-123",
            competition_name="La Liga",
            requires_empty_confirmation=True,
            needs_name_resolution=True,
            payload_json='{"some": "data"}'
        )
        
        self.assertEqual(req.telegram_chat_id, chat_id)
        self.assertEqual(req.platform, "bet365")
        self.assertEqual(req.competition_external_id, "league-123")
        self.assertEqual(req.competition_name, "La Liga")
        self.assertTrue(req.requires_empty_confirmation)
        self.assertTrue(req.needs_name_resolution)
        
        latest = self.adapter.get_latest_pending_competition_request(chat_id)
        self.assertIsNotNone(latest)
        self.assertEqual(latest.competition_name, "La Liga")
        
        deleted = self.adapter.delete_pending_competition_request(chat_id)
        self.assertTrue(deleted)
        
        latest_after_delete = self.adapter.get_latest_pending_competition_request(chat_id)
        self.assertIsNone(latest_after_delete)

    def test_confirm_pending_competition_request(self) -> None:
        chat_id = 888
        self.adapter.create_pending_competition_request(
            chat_id=chat_id,
            platform="bet365",
            source_url="http://example.com/league",
            competition_external_id="league-123",
            competition_name="La Liga",
            requires_empty_confirmation=False,
            needs_name_resolution=False
        )
        
        comp = self.adapter.confirm_pending_competition_request(chat_id)
        
        self.assertEqual(comp.platform, "bet365")
        self.assertEqual(comp.competition_external_id, "league-123")
        self.assertEqual(comp.competition_name, "La Liga")
        self.assertTrue(comp.enabled)
        
        # Confirming should delete the pending request
        self.assertIsNone(self.adapter.get_latest_pending_competition_request(chat_id))
        
        # Tracked competition lookup
        comp_by_id = self.adapter.get_tracked_competition(comp.id)
        self.assertEqual(comp_by_id.competition_name, "La Liga")
        
        comp_by_identity = self.adapter.get_tracked_competition_by_identity("bet365", "league-123")
        self.assertEqual(comp_by_identity.id, comp.id)
        
        # Listing tracked & globally active
        all_tracked = self.adapter.list_tracked_competitions()
        self.assertEqual(len(all_tracked), 1)
        self.assertEqual(all_tracked[0].id, comp.id)
        
        active = self.adapter.list_globally_active_competitions()
        self.assertEqual(len(active), 1)

    def test_update_tracked_competition(self) -> None:
        chat_id = 777
        self.adapter.create_pending_competition_request(
            chat_id=chat_id,
            platform="bet365",
            source_url="http://example.com/league",
            competition_external_id="league-abc",
            competition_name="Serie A",
            requires_empty_confirmation=False,
            needs_name_resolution=False
        )
        comp = self.adapter.confirm_pending_competition_request(chat_id)
        
        updated = self.adapter.update_tracked_competition(
            comp.id,
            enabled=False,
            last_synced_at="2026-06-29T12:00:00Z"
        )
        self.assertFalse(updated.enabled)
        self.assertEqual(updated.last_synced_at, "2026-06-29T12:00:00Z")
        
        self.adapter.update_tracked_competition_source(comp.id, "http://new-url.com")
        comp_after_src = self.adapter.get_tracked_competition(comp.id)
        self.assertEqual(comp_after_src.source_url, "http://new-url.com")

    def test_auto_track_live_detected_league(self) -> None:
        comp = self.adapter.auto_track_live_detected_league(
            platform="betsson",
            external_id="league-xyz",
            name="Eredivisie",
            source_url="http://eredivisie.nl"
        )
        self.assertIsNotNone(comp)
        self.assertEqual(comp.platform, "betsson")
        self.assertEqual(comp.competition_external_id, "league-xyz")
        self.assertEqual(comp.competition_name, "Eredivisie")
        
        all_tracked = self.adapter.list_tracked_competitions()
        self.assertEqual(len(all_tracked), 1)

    def test_record_unavailable_refresh_and_warnings(self) -> None:
        chat_id = 666
        self.adapter.create_pending_competition_request(
            chat_id=chat_id,
            platform="bet365",
            source_url="http://example.com/league",
            competition_external_id="league-123",
            competition_name="La Liga",
            requires_empty_confirmation=False,
            needs_name_resolution=False
        )
        comp = self.adapter.confirm_pending_competition_request(chat_id)
        
        self.assertFalse(self.adapter.should_send_unavailable_refresh_warning(comp.id, minimum_failures=3))
        
        # 1 failure
        comp = self.adapter.record_unavailable_refresh(comp.id, reason="Network timeout")
        self.assertEqual(comp.consecutive_unavailable_refreshes, 1)
        self.assertEqual(comp.last_unavailable_reason, "Network timeout")
        
        # 2 failures
        comp = self.adapter.record_unavailable_refresh(comp.id, reason="Bad gateway")
        # 3 failures
        comp = self.adapter.record_unavailable_refresh(comp.id, reason="HTTP 500")
        
        self.assertTrue(self.adapter.should_send_unavailable_refresh_warning(comp.id, minimum_failures=3))
        
        # Mark sent
        self.adapter.mark_unavailable_refresh_warning_sent(comp.id)
        
        # Now it shouldn't warn due to cooldown
        self.assertFalse(self.adapter.should_send_unavailable_refresh_warning(comp.id, minimum_failures=3, cooldown_seconds=60))

    def test_unified_competitions_operations(self) -> None:
        # Create unified league
        uc_id = self.adapter.create_unified_competition("Premier League")
        self.assertGreater(uc_id, 0)
        
        # Check auto-track links to unified
        comp = self.adapter.auto_track_live_detected_league(
            platform="bet365",
            external_id="pl-123",
            name="Premier League",
            source_url="http://pl.com"
        )
        self.assertEqual(comp.unified_competition_id, uc_id)
        
        # Merge unified
        target_uc_id = self.adapter.create_unified_competition("English Premier League")
        self.adapter.merge_unified_competitions(uc_id, target_uc_id)
        
        comp_after_merge = self.adapter.get_tracked_competition(comp.id)
        self.assertIsNotNone(comp_after_merge)
        self.assertEqual(comp_after_merge.unified_competition_id, target_uc_id)
        
        # relink by normalized name
        comp2 = self.adapter.auto_track_live_detected_league(
            platform="betsson",
            external_id="pl-xyz",
            name="English Premier League (relink test)",
            source_url="http://pl-xyz.com"
        )
        uc_id_2 = self.adapter.create_unified_competition("English Premier League (relink test)")
        self.adapter.link_tracked_competition_to_unified(comp2.id, uc_id_2)
        
        # relink
        moved = self.adapter.relink_unified_by_normalized_name()
        self.assertGreaterEqual(moved, 0)

    def test_suggestions_and_subscribed_unified(self) -> None:
        uc_id = self.adapter.create_unified_competition("Copa Libertadores")
        
        suggestions = self.adapter.suggest_similar_unified("Copa Libertadores de America")
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["id"], uc_id)
        
        # Subscribed unified leagues
        chat_id = 555
        self.adapter.create_pending_competition_request(
            chat_id=chat_id,
            platform="bet365",
            source_url="http://example.com/league",
            competition_external_id="lib-123",
            competition_name="Copa Libertadores",
            requires_empty_confirmation=False,
            needs_name_resolution=False
        )
        comp = self.adapter.confirm_pending_competition_request(chat_id)
        
        subscribed = self.adapter.list_subscribed_unified_competitions(chat_id)
        self.assertEqual(len(subscribed), 1)
        self.assertEqual(subscribed[0]["id"], comp.unified_competition_id)
        
        tracked_for_unified = self.adapter.list_tracked_competitions_for_unified(comp.unified_competition_id)
        self.assertEqual(len(tracked_for_unified), 1)
        self.assertEqual(tracked_for_unified[0].id, comp.id)

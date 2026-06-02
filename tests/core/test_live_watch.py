from __future__ import annotations

import importlib
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.models import LiveEventSnapshot
from monitors.live_watch import (
    LiveWatchService,
    _name_similarity,
    match_score,
    parse_fixture_line,
    render_live_hit,
)
from storage.tracking_repository import SqliteTrackingRepository

tracking_repository_module = importlib.import_module("storage.tracking_repository")


class LiveWatchUnitTests(unittest.TestCase):
    def test_parse_fixture_line(self) -> None:
        self.assertIsNone(parse_fixture_line(""))
        self.assertIsNone(parse_fixture_line("   "))
        self.assertIsNone(parse_fixture_line("SingleTeamNameNoSeparator"))

        # Simple hyphen (4-tuple: league_hint, home, away, kickoff_utc)
        p1 = parse_fixture_line("Murdoch - East Perth")
        self.assertEqual(p1, (None, "Murdoch", "East Perth", None))

        # VS separator
        p2 = parse_fixture_line("Poli Iasi vs Otelul")
        self.assertEqual(p2, (None, "Poli Iasi", "Otelul", None))

        # League hint with pipe
        p3 = parse_fixture_line("Australia Occidental | Subiaco - UWA")
        self.assertEqual(p3, ("Australia Occidental", "Subiaco", "UWA", None))

        # Extra whitespace
        p4 = parse_fixture_line("  League A  |   Team X   vs.   Team Y  ")
        self.assertEqual(p4, ("League A", "Team X", "Team Y", None))

        # Leading Argentina time -> kickoff captured (UTC ISO), stripped from names
        p5 = parse_fixture_line("21:00 Olympia - Ballard")
        self.assertEqual(p5[:3], (None, "Olympia", "Ballard"))
        self.assertIsNotNone(p5[3])

    def test_name_similarity(self) -> None:
        # High similarity for exact names (case-insensitive, normalized)
        self.assertGreaterEqual(_name_similarity("Murdoch FC", "murdoch"), 0.8)
        self.assertGreaterEqual(_name_similarity("Sevilla", "Sevilla FC"), 0.8)

        # stopwords removal
        self.assertGreaterEqual(_name_similarity("Poli Iasi AC", "Poli Iasi"), 0.9)

        # Low similarity
        self.assertLess(_name_similarity("Murdoch", "East Perth"), 0.4)

    def test_match_score(self) -> None:
        # Create a watch entry
        entry = SimpleNamespace(
            home="Murdoch FC",
            away="East Perth SC",
        )

        # Match (should be high)
        event_match = LiveEventSnapshot(
            platform="kambi",
            external_event_id="1",
            is_soccer=True,
            home="murdoch",
            away="east perth",
            country_name="Australia",
            competition_name="NPL",
            minute="12'",
            home_score=0,
            away_score=0,
        )
        score_ok = match_score(entry, event_match)
        self.assertGreaterEqual(score_ok, 0.70)

        # Mismatch (different away team)
        event_mismatch = LiveEventSnapshot(
            platform="kambi",
            external_event_id="2",
            is_soccer=True,
            home="murdoch",
            away="UWA",
            country_name="Australia",
            competition_name="NPL",
            minute="12'",
            home_score=0,
            away_score=0,
        )
        score_fail = match_score(entry, event_mismatch)
        self.assertEqual(score_fail, 0.0)


class LiveWatchRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_db_path = tracking_repository_module.DB_FILE_PATH
        self.old_data_dir = tracking_repository_module.DATA_DIR
        self.tmp_dir = tempfile.TemporaryDirectory()
        tracking_repository_module.DATA_DIR = Path(self.tmp_dir.name)
        tracking_repository_module.DB_FILE_PATH = Path(self.tmp_dir.name) / "tracking.sqlite3"
        self.repository = SqliteTrackingRepository()

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        tracking_repository_module.DB_FILE_PATH = self.old_db_path
        tracking_repository_module.DATA_DIR = self.old_data_dir

    def test_live_watch_crud(self) -> None:
        chat_id = 999
        # Add live watch
        w1 = self.repository.add_live_watch(
            chat_id,
            home="Banyule",
            away="Bundoora",
            league_hint="Australia Victorian",
            note="Visitantes +3/4",
        )
        self.assertEqual(w1.chat_id, chat_id)
        self.assertEqual(w1.home, "Banyule")
        self.assertEqual(w1.away, "Bundoora")
        self.assertEqual(w1.status, "watching")

        # List watch
        watches = self.repository.list_live_watches(chat_id)
        self.assertEqual(len(watches), 1)
        self.assertEqual(watches[0].id, w1.id)

        # List active all
        active = self.repository.list_all_active_live_watches()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].id, w1.id)

        # Mark fired
        self.repository.mark_live_watch_fired(
            w1.id, platform="betovo", event_id="ev-123", minute="45'"
        )
        watches_after = self.repository.list_live_watches(chat_id)
        self.assertEqual(watches_after[0].status, "fired")
        self.assertEqual(watches_after[0].matched_platform, "betovo")
        self.assertEqual(watches_after[0].matched_event_id, "ev-123")
        self.assertEqual(watches_after[0].matched_minute, "45'")

        # Ensure no longer in active list
        active_after = self.repository.list_all_active_live_watches()
        self.assertEqual(len(active_after), 0)

        # Clear watches
        removed = self.repository.clear_live_watches(chat_id)
        self.assertEqual(removed, 1)
        self.assertEqual(len(self.repository.list_live_watches(chat_id)), 0)


class LiveWatchServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.old_db_path = tracking_repository_module.DB_FILE_PATH
        self.old_data_dir = tracking_repository_module.DATA_DIR
        self.tmp_dir = tempfile.TemporaryDirectory()
        tracking_repository_module.DATA_DIR = Path(self.tmp_dir.name)
        tracking_repository_module.DB_FILE_PATH = Path(self.tmp_dir.name) / "tracking.sqlite3"
        self.repository = SqliteTrackingRepository()

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        tracking_repository_module.DB_FILE_PATH = self.old_db_path
        tracking_repository_module.DATA_DIR = self.old_data_dir

    async def test_live_watch_poller_matches_and_fires_alerts(self) -> None:
        service = LiveWatchService(repository=self.repository)

        # Load watch lines
        chat_id = 888
        lines = [
            "Australia Victorian | Banyule - Bundoora",
            "Poli Iasi vs Otelul",
        ]
        added = service.add_fixture_lines(chat_id, lines)
        self.assertEqual(len(added), 2)

        # Mock an extractor registry and live events
        mock_extractor = SimpleNamespace(
            name="betovo",
            display_name="Betovo",
            supports_live_detection=True,
            list_live_events=AsyncMock(
                return_value=[
                    LiveEventSnapshot(
                        platform="betovo",
                        external_event_id="ev-99",
                        is_soccer=True,
                        home="Banyule City",
                        away="Bundoora FC",
                        country_name="Australia",
                        competition_name="Victorian State League",
                        minute="5'",
                        home_score=1,
                        away_score=0,
                        odds_1x2=SimpleNamespace(home=1.85, draw=3.40, away=3.80),
                    )
                ]
            ),
        )
        service.extractor_registry = SimpleNamespace(
            list_registered=lambda: [mock_extractor]
        )

        # Poll once
        hits = await service.poll_once()
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual(hit.entry.home, "Banyule")
        self.assertEqual(hit.event.home, "Banyule City")
        self.assertEqual(hit.event.minute, "5'")

        # Verify it has been marked as fired in repository
        active = self.repository.list_all_active_live_watches()
        self.assertEqual(len(active), 1)  # Only Poli Iasi vs Otelul remains
        self.assertEqual(active[0].home, "Poli Iasi")

        # Test render_live_hit helper
        alert_msg = render_live_hit(hit)
        self.assertIn("🔴 EN VIVO — salió tu partido", alert_msg)
        self.assertIn("Banyule City vs Bundoora FC", alert_msg)
        self.assertIn("Victorian State League", alert_msg)
        self.assertIn("5'  |  1-0", alert_msg)
        self.assertIn("1.85 / 3.4 / 3.8", alert_msg)
        self.assertIn("betovo", alert_msg)


class LiveWatchPrematchAndExpiryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.old_db_path = tracking_repository_module.DB_FILE_PATH
        self.old_data_dir = tracking_repository_module.DATA_DIR
        self.tmp_dir = tempfile.TemporaryDirectory()
        tracking_repository_module.DATA_DIR = Path(self.tmp_dir.name)
        tracking_repository_module.DB_FILE_PATH = Path(self.tmp_dir.name) / "tracking.sqlite3"
        self.repository = SqliteTrackingRepository()

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()
        tracking_repository_module.DB_FILE_PATH = self.old_db_path
        tracking_repository_module.DATA_DIR = self.old_data_dir

    async def test_prematch_listing_fires_pre_once_and_keeps_watching(self) -> None:
        service = LiveWatchService(repository=self.repository)
        service.add_fixture_lines(7, ["USL League Two | Olympia - Ballard"])

        pre_extractor = SimpleNamespace(
            name="solcasino_http",
            supports_live_detection=False,
            supports_prematch_listing=True,
            list_live_events=AsyncMock(return_value=[]),
            list_prematch_events=AsyncMock(
                return_value=[
                    LiveEventSnapshot(
                        platform="solcasino_http", external_event_id="p1", is_soccer=True,
                        home="Olympia FC", away="Ballard FC SC", country_name="USA",
                        competition_name="USL League Two", minute=None,
                    )
                ]
            ),
        )
        service.extractor_registry = SimpleNamespace(list_registered=lambda: [pre_extractor])

        hits = await service.poll_once()
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].phase, "pre")
        msg = render_live_hit(hits[0])
        self.assertIn("LISTADO EN PRE", msg)
        # one-shot: still watching, not re-alerted
        active = self.repository.list_all_active_live_watches()
        self.assertEqual(len(active), 1)
        self.assertIsNotNone(active[0].prematch_seen_at)
        self.assertEqual(len(await service.poll_once()), 0)

    def test_purge_expired_removes_past_kickoff_and_stale(self) -> None:
        import datetime as _dt

        chat = 5
        # Past kickoff -> purged
        past = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=5)).isoformat()
        self.repository.add_live_watch(chat, home="A", away="B", kickoff_at=past)
        # Future kickoff -> kept
        future = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=5)).isoformat()
        keep = self.repository.add_live_watch(chat, home="C", away="D", kickoff_at=future)

        removed = self.repository.purge_expired_live_watches()
        self.assertEqual(removed, 1)
        remaining = self.repository.list_live_watches(chat)
        self.assertEqual([w.id for w in remaining], [keep.id])

    def test_chat_local_id_generation_and_deletion(self) -> None:
        chat_a = 111
        chat_b = 222
        
        # Add to chat A
        w1 = self.repository.add_live_watch(chat_a, home="A1", away="A2")
        w2 = self.repository.add_live_watch(chat_a, home="B1", away="B2")
        self.assertEqual(w1.chat_local_id, 1)
        self.assertEqual(w2.chat_local_id, 2)
        
        # Add to chat B
        w3 = self.repository.add_live_watch(chat_b, home="C1", away="C2")
        self.assertEqual(w3.chat_local_id, 1)
        
        # Remove by local ID in chat A
        ok = self.repository.remove_live_watch_by_local_id(chat_a, 1)
        self.assertTrue(ok)
        
        # Remaining in chat A
        remaining = self.repository.list_live_watches(chat_a)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].id, w2.id)
        self.assertEqual(remaining[0].chat_local_id, 2)
        
        # Ensure Chat B's watch wasn't affected
        self.assertEqual(len(self.repository.list_live_watches(chat_b)), 1)

    def test_purge_expired_default_grace_period_is_2_hours(self) -> None:
        import datetime as _dt
        chat = 777
        # Kickoff 2.5 hours ago -> should be purged because 2.5 > 2.0 default grace
        past = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=2.5)).isoformat()
        self.repository.add_live_watch(chat, home="A", away="B", kickoff_at=past)
        
        # Kickoff 1.5 hours ago -> should be kept because 1.5 < 2.0 default grace
        future = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=1.5)).isoformat()
        keep = self.repository.add_live_watch(chat, home="C", away="D", kickoff_at=future)
        
        removed = self.repository.purge_expired_live_watches()
        self.assertEqual(removed, 1)
        remaining = self.repository.list_live_watches(chat)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].id, keep.id)

    def test_kickoff_from_arg_time_tomorrow_shifting(self) -> None:
        from monitors.live_watch import _kickoff_from_arg_time, _ARG_TZ
        import datetime as _dt
        
        # Current Argentina local time (with clean seconds/microseconds for exact comparisons)
        now_arg = _dt.datetime.now(_ARG_TZ).replace(second=0, microsecond=0)
        
        # Test case 1: Kickoff is 1 hour in the past compared to now
        # It should stay today (timedelta <= 2.5 hours)
        target_time1 = now_arg - _dt.timedelta(hours=1)
        ko_str1 = _kickoff_from_arg_time(target_time1.hour, target_time1.minute)
        self.assertIsNotNone(ko_str1)
        ko_dt1 = _dt.datetime.fromisoformat(ko_str1)
        diff1 = now_arg - ko_dt1.astimezone(_ARG_TZ)
        self.assertLessEqual(abs(diff1.total_seconds() - 3600), 15)
        
        # Test case 2: Kickoff is 5 hours in the past compared to now
        # Since 5 > 2.5 hours, it must shift to tomorrow (+1 day)
        target_time2 = now_arg - _dt.timedelta(hours=5)
        ko_str2 = _kickoff_from_arg_time(target_time2.hour, target_time2.minute)
        self.assertIsNotNone(ko_str2)
        ko_dt2 = _dt.datetime.fromisoformat(ko_str2)
        diff2 = ko_dt2.astimezone(_ARG_TZ) - now_arg
        # Difference should be tomorrow minus 5 hours = +19 hours in the future
        self.assertLessEqual(abs(diff2.total_seconds() - 19 * 3600), 15)

        # Test case 3: Kickoff is 2 hours in the future compared to now
        # It should stay today (future)
        target_time3 = now_arg + _dt.timedelta(hours=2)
        ko_str3 = _kickoff_from_arg_time(target_time3.hour, target_time3.minute)
        self.assertIsNotNone(ko_str3)
        ko_dt3 = _dt.datetime.fromisoformat(ko_str3)
        diff3 = ko_dt3.astimezone(_ARG_TZ) - now_arg
        self.assertLessEqual(abs(diff3.total_seconds() - 2 * 3600), 15)

    def test_get_recommended_poll_interval(self) -> None:
        import datetime as _dt
        from datetime import timezone
        service = LiveWatchService(repository=self.repository)
        
        # 1. No active watches -> should return normal interval (60s)
        self.assertEqual(service.get_recommended_poll_interval(), 60.0)
        
        # 2. Has watch, but kickoff is far in the future (e.g. 5 hours) -> should return normal (60s)
        far_future = (_dt.datetime.now(timezone.utc) + _dt.timedelta(hours=5)).isoformat()
        self.repository.add_live_watch(123, home="A", away="B", kickoff_at=far_future)
        self.assertEqual(service.get_recommended_poll_interval(), 60.0)
        
        # 3. Has watch starting in 1 minute (within the 2-minute fast-polling window) -> should return fast (15s)
        near_future = (_dt.datetime.now(timezone.utc) + _dt.timedelta(minutes=1)).isoformat()
        self.repository.add_live_watch(123, home="C", away="D", kickoff_at=near_future)
        self.assertEqual(service.get_recommended_poll_interval(), 15.0)




if __name__ == "__main__":
    unittest.main()

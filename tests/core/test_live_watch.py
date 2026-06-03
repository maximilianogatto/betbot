from __future__ import annotations

import asyncio
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
        self.assertEqual(watches_after[0].status, "watching")
        self.assertEqual(watches_after[0].fired_platforms, "betovo")
        self.assertEqual(watches_after[0].matched_platform, "betovo")
        self.assertEqual(watches_after[0].matched_event_id, "ev-123")
        self.assertEqual(watches_after[0].matched_minute, "45'")

        # Under the new multi-platform alert flow, the entry remains active until expiry
        active_after = self.repository.list_all_active_live_watches()
        self.assertEqual(len(active_after), 1)

        # Last observed live state is persisted per platform.
        self.repository.update_live_watch_platform_state(
            w1.id,
            platform="betovo",
            state={"event_id": "ev-123", "home_score": 1, "away_score": 0},
        )
        state_after = self.repository.list_live_watches(chat_id)[0].live_state
        self.assertEqual(state_after["betovo"]["event_id"], "ev-123")
        self.assertEqual(state_after["betovo"]["home_score"], 1)

        # Per-chat alert settings default to goals+reds on and yellows off.
        defaults = self.repository.get_live_watch_settings(chat_id)
        self.assertTrue(defaults.alert_goals)
        self.assertTrue(defaults.alert_red_cards)
        self.assertFalse(defaults.alert_yellow_cards)
        updated = self.repository.set_live_watch_settings(chat_id, alert_goals=False, alert_yellow_cards=True)
        self.assertFalse(updated.alert_goals)
        self.assertTrue(updated.alert_red_cards)
        self.assertTrue(updated.alert_yellow_cards)

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

        # Verify it has been marked as fired on betovo in repository but remains active
        active = self.repository.list_all_active_live_watches()
        self.assertEqual(len(active), 2)
        fired_ones = [w for w in active if w.fired_platforms == "betovo"]
        self.assertEqual(len(fired_ones), 1)
        self.assertEqual(fired_ones[0].home, "Banyule")

        # Test render_live_hit helper
        alert_msg = render_live_hit(hit)
        self.assertIn("🔴 EN VIVO", alert_msg)
        self.assertIn("Banyule City vs Bundoora FC", alert_msg)
        self.assertIn("Victorian State League", alert_msg)
        self.assertIn("5'  |  1-0", alert_msg)
        self.assertIn("1.85 / 3.4 / 3.8", alert_msg)
        self.assertIn("betovo", alert_msg)

    async def test_live_watch_poller_fires_per_casino(self) -> None:
        service = LiveWatchService(repository=self.repository)
        chat_id = 888
        added = service.add_fixture_lines(chat_id, ["Banyule - Bundoora"])
        self.assertEqual(len(added), 1)

        # Mock first platform (betovo)
        mock_betovo = SimpleNamespace(
            name="betovo",
            display_name="Betovo",
            supports_live_detection=True,
            list_live_events=AsyncMock(
                return_value=[
                    LiveEventSnapshot(
                        platform="betovo",
                        external_event_id="ev-1",
                        is_soccer=True,
                        home="Banyule",
                        away="Bundoora",
                        minute="5'",
                        home_score=1,
                        away_score=0,
                    )
                ]
            ),
        )
        # Mock second platform (bz_http)
        mock_bz = SimpleNamespace(
            name="bz_http",
            display_name="BZ",
            supports_live_detection=True,
            list_live_events=AsyncMock(
                return_value=[
                    LiveEventSnapshot(
                        platform="bz_http",
                        external_event_id="ev-2",
                        is_soccer=True,
                        home="Banyule",
                        away="Bundoora",
                        minute="6'",
                        home_score=1,
                        away_score=0,
                    )
                ]
            ),
        )
        service.extractor_registry = SimpleNamespace(
            list_registered=lambda: [mock_betovo, mock_bz]
        )

        # Poll once -> matches betovo
        hits1 = await service.poll_once()
        self.assertEqual(len(hits1), 1)
        self.assertEqual(hits1[0].event.platform, "betovo")

        # Verify entry is still active but marked with betovo in fired_platforms
        watches = self.repository.list_all_active_live_watches()
        self.assertEqual(len(watches), 1)
        self.assertEqual(watches[0].fired_platforms, "betovo")

        # Poll twice -> betovo is already fired, should match bz_http
        hits2 = await service.poll_once()
        self.assertEqual(len(hits2), 1)
        self.assertEqual(hits2[0].event.platform, "bz_http")

        # Verify entry is still active and marked with both
        watches2 = self.repository.list_all_active_live_watches()
        self.assertEqual(len(watches2), 1)
        self.assertIn("betovo", watches2[0].fired_platforms_list)
        self.assertIn("bz_http", watches2[0].fired_platforms_list)

        # Poll thrice -> both are fired, should not alert again
        hits3 = await service.poll_once()
        self.assertEqual(len(hits3), 0)

    async def test_goal_alert_is_deduplicated_across_platforms(self) -> None:
        service = LiveWatchService(repository=self.repository)
        chat_id = 889
        service.add_fixture_lines(chat_id, ["Banyule - Bundoora"])

        score_state = {"home": 0, "away": 0}

        def event(platform: str, event_id: str) -> LiveEventSnapshot:
            return LiveEventSnapshot(
                platform=platform,
                external_event_id=event_id,
                home="Banyule",
                away="Bundoora",
                minute="10'",
                home_score=score_state["home"],
                away_score=score_state["away"],
            )

        service.extractor_registry = SimpleNamespace(
            list_registered=lambda: [
                SimpleNamespace(
                    name="betovo",
                    supports_live_detection=True,
                    list_live_events=AsyncMock(side_effect=lambda: [event("betovo", "ev-1")]),
                ),
                SimpleNamespace(
                    name="bz_http",
                    supports_live_detection=True,
                    list_live_events=AsyncMock(side_effect=lambda: [event("bz_http", "ev-2")]),
                ),
            ]
        )

        self.assertEqual([hit.phase for hit in await service.poll_once()], ["live"])
        self.assertEqual([hit.phase for hit in await service.poll_once()], ["live"])

        score_state["home"] = 1
        hits = await service.poll_once()
        self.assertEqual([hit.phase for hit in hits], ["goal"])

    async def test_collect_live_events_fetches_platforms_in_parallel(self) -> None:
        service = LiveWatchService(repository=self.repository)
        started = 0
        release = asyncio.Event()

        async def fetch(platform: str) -> list[LiveEventSnapshot]:
            nonlocal started
            started += 1
            if started == 2:
                release.set()
            await release.wait()
            return [
                LiveEventSnapshot(
                    platform=platform,
                    external_event_id=f"{platform}-1",
                    home="A",
                    away="B",
                )
            ]

        service.extractor_registry = SimpleNamespace(
            list_registered=lambda: [
                SimpleNamespace(name="one", supports_live_detection=True, list_live_events=lambda: fetch("one")),
                SimpleNamespace(name="two", supports_live_detection=True, list_live_events=lambda: fetch("two")),
            ]
        )

        events = await asyncio.wait_for(service.collect_live_events(), timeout=1.0)
        self.assertEqual({event.platform for event in events}, {"one", "two"})

    async def test_live_watch_detects_goal_and_red_card_after_live_match(self) -> None:
        service = LiveWatchService(repository=self.repository)
        chat_id = 777
        service.add_fixture_lines(chat_id, ["Banyule - Bundoora"])

        current_events = [
            LiveEventSnapshot(
                platform="betovo",
                external_event_id="ev-1",
                home="Banyule",
                away="Bundoora",
                minute="1'",
                home_score=0,
                away_score=0,
                home_red_cards=0,
                away_red_cards=0,
                home_yellow_cards=0,
                away_yellow_cards=0,
            )
        ]
        extractor = SimpleNamespace(
            name="betovo",
            supports_live_detection=True,
            list_live_events=AsyncMock(side_effect=lambda: list(current_events)),
        )
        service.extractor_registry = SimpleNamespace(list_registered=lambda: [extractor])

        hits1 = await service.poll_once()
        self.assertEqual([hit.phase for hit in hits1], ["live"])

        current_events[0] = LiveEventSnapshot(
            platform="betovo",
            external_event_id="ev-1",
            home="Banyule",
            away="Bundoora",
            minute="9'",
            home_score=1,
            away_score=0,
            home_red_cards=0,
            away_red_cards=0,
            home_yellow_cards=0,
            away_yellow_cards=0,
        )
        hits2 = await service.poll_once()
        self.assertEqual([hit.phase for hit in hits2], ["goal"])
        self.assertIn("GOL DETECTADO", render_live_hit(hits2[0]))
        self.assertIn("Banyule", render_live_hit(hits2[0]))

        current_events[0] = LiveEventSnapshot(
            platform="betovo",
            external_event_id="ev-1",
            home="Banyule",
            away="Bundoora",
            minute="18'",
            home_score=1,
            away_score=0,
            home_red_cards=0,
            away_red_cards=1,
            home_yellow_cards=0,
            away_yellow_cards=0,
        )
        hits3 = await service.poll_once()
        self.assertEqual([hit.phase for hit in hits3], ["red_card"])
        self.assertIn("TARJETA ROJA", render_live_hit(hits3[0]))
        self.assertIn("Bundoora", render_live_hit(hits3[0]))

        self.repository.set_live_watch_settings(chat_id, alert_yellow_cards=True)
        current_events[0] = LiveEventSnapshot(
            platform="betovo",
            external_event_id="ev-1",
            home="Banyule",
            away="Bundoora",
            minute="23'",
            home_score=1,
            away_score=0,
            home_red_cards=0,
            away_red_cards=1,
            home_yellow_cards=0,
            away_yellow_cards=1,
        )
        hits4 = await service.poll_once()
        self.assertEqual([hit.phase for hit in hits4], ["yellow_card"])
        self.assertIn("TARJETA AMARILLA", render_live_hit(hits4[0]))

    async def test_live_watch_settings_suppress_goal_alerts(self) -> None:
        service = LiveWatchService(repository=self.repository)
        chat_id = 778
        service.add_fixture_lines(chat_id, ["Banyule - Bundoora"])
        self.repository.set_live_watch_settings(chat_id, alert_goals=False)

        current_events = [
            LiveEventSnapshot(
                platform="betovo",
                external_event_id="ev-1",
                home="Banyule",
                away="Bundoora",
                minute="1'",
                home_score=0,
                away_score=0,
            )
        ]
        service.extractor_registry = SimpleNamespace(
            list_registered=lambda: [
                SimpleNamespace(
                    name="betovo",
                    supports_live_detection=True,
                    list_live_events=AsyncMock(side_effect=lambda: list(current_events)),
                )
            ]
        )
        self.assertEqual([hit.phase for hit in await service.poll_once()], ["live"])

        current_events[0] = LiveEventSnapshot(
            platform="betovo",
            external_event_id="ev-1",
            home="Banyule",
            away="Bundoora",
            minute="5'",
            home_score=1,
            away_score=0,
        )
        self.assertEqual(await service.poll_once(), [])


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
        
        # 1. No active watches -> should return normal interval (30s)
        self.assertEqual(service.get_recommended_poll_interval(), 30.0)
        
        # 2. Has watch, but kickoff is far in the future (e.g. 5 hours) -> should return normal (30s)
        far_future = (_dt.datetime.now(timezone.utc) + _dt.timedelta(hours=5)).isoformat()
        self.repository.add_live_watch(123, home="A", away="B", kickoff_at=far_future)
        self.assertEqual(service.get_recommended_poll_interval(), 30.0)
        
        # 3. Has watch starting in 1 minute (within the 2-minute fast-polling window) -> should return fast (10s)
        near_future = (_dt.datetime.now(timezone.utc) + _dt.timedelta(minutes=1)).isoformat()
        self.repository.add_live_watch(123, home="C", away="D", kickoff_at=near_future)
        self.assertEqual(service.get_recommended_poll_interval(), 10.0)

    def test_spanish_name_similarity_normalization(self) -> None:
        # Femenino normalization
        self.assertGreaterEqual(_name_similarity("AC Connecticut Femenino", "AC Connecticut Women"), 0.8)
        self.assertGreaterEqual(_name_similarity("Vermont (Femenil)", "Vermont FC"), 0.8)
        # Sub-20 normalization
        self.assertGreaterEqual(_name_similarity("Texoma Sub 20", "Texoma U20"), 0.8)
        self.assertGreaterEqual(_name_similarity("Banyule sub-23", "Banyule U23"), 0.8)
        # Reserva normalization
        self.assertGreaterEqual(_name_similarity("Belconnen United Reserva", "Belconnen United Reserves"), 0.8)

    async def test_per_casino_prematch_alerting(self) -> None:
        service = LiveWatchService(repository=self.repository)
        chat_id = 999
        entry = service.add_fixture_lines(chat_id, ["Texoma - Fort Worth"])[0]

        # First poll: event listed on betovo
        ev_betovo = LiveEventSnapshot(
            platform="betovo", external_event_id="ev1", home="Texoma FC", away="Fort Worth Vaqueros",
            country_name="USA", competition_name="USL Two",
        )
        service.extractor_registry = SimpleNamespace(
            list_registered=lambda: [
                SimpleNamespace(name="betovo", supports_live_detection=False, supports_prematch_listing=True,
                                list_prematch_events=AsyncMock(return_value=[ev_betovo]), list_live_events=AsyncMock(return_value=[]))
            ]
        )

        hits1 = await service.poll_once()
        self.assertEqual(len(hits1), 1)
        self.assertEqual(hits1[0].event.platform, "betovo")
        self.assertEqual(hits1[0].phase, "pre")

        # Reload watch entry
        entry = self.repository.list_live_watches(chat_id)[0]
        self.assertEqual(entry.prematch_fired_platforms, "betovo")

        # Second poll: event listed on solcasino too
        ev_sol = LiveEventSnapshot(
            platform="solcasino_http", external_event_id="ev2", home="Texoma FC", away="Fort Worth Vaqueros",
            country_name="USA", competition_name="USL Two",
        )
        service.extractor_registry = SimpleNamespace(
            list_registered=lambda: [
                SimpleNamespace(name="betovo", supports_live_detection=False, supports_prematch_listing=True,
                                list_prematch_events=AsyncMock(return_value=[ev_betovo]), list_live_events=AsyncMock(return_value=[])),
                SimpleNamespace(name="solcasino_http", supports_live_detection=False, supports_prematch_listing=True,
                                list_prematch_events=AsyncMock(return_value=[ev_sol]), list_live_events=AsyncMock(return_value=[]))
            ]
        )

        service._prematch_cache = None
        hits2 = await service.poll_once()
        self.assertEqual(len(hits2), 1)
        self.assertEqual(hits2[0].event.platform, "solcasino_http")
        self.assertEqual(hits2[0].phase, "pre")

        # Reload watch entry
        entry = self.repository.list_live_watches(chat_id)[0]
        self.assertIn("betovo", entry.prematch_fired_platforms_list)
        self.assertIn("solcasino_http", entry.prematch_fired_platforms_list)

        # Third poll: both are already fired, no new alerts
        service._prematch_cache = None
        hits3 = await service.poll_once()
        self.assertEqual(len(hits3), 0)

    async def test_kickoff_countdown_alert(self) -> None:
        import datetime as _dt
        from datetime import timezone
        from unittest.mock import patch
        
        service = LiveWatchService(repository=self.repository)
        chat_id = 999
        
        # Add a watch with kickoff 5 minutes in the future
        ko_time = (_dt.datetime.now(timezone.utc) + _dt.timedelta(minutes=5)).isoformat()
        entry = self.repository.add_live_watch(chat_id, home="Texoma FC", away="Fort Worth Vaqueros", kickoff_at=ko_time)
        
        # Populate repository mock active events
        active_event = SimpleNamespace(
            id=1,
            tracked_competition_id=10,
            platform="betovo",
            competition_external_id="ext1",
            external_event_id="ev1",
            home="Texoma FC",
            away="Fort Worth Vaqueros FC",
            scheduled_label_date="2026-06-03",
            scheduled_label_time="12:00",
            scheduled_at=ko_time,
            event_url=None,
            odds_home=1.85,
            odds_draw=3.40,
            odds_away=3.80,
            markets_json='{"asian_handicap": {"selections": [{"selection": "Texoma FC", "line": "-0.5", "odds": 1.85}, {"selection": "Fort Worth Vaqueros FC", "line": "+0.5", "odds": 1.90}]}}',
            raw_payload_json=None,
            reminder_sent_at=None,
            is_active=1,
            first_seen_at=ko_time,
            last_seen_at=ko_time,
            created_at=ko_time,
            updated_at=ko_time,
            league_name="USA USL League Two"
        )
        
        with patch.object(self.repository, "get_all_active_events_with_league", return_value=[active_event]):
            # Set extractors to return empty so we only focus on countdown
            service.extractor_registry = SimpleNamespace(list_registered=lambda: [])
            
            hits = await service.poll_once()
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].phase, "countdown")
            msg = render_live_hit(hits[0])
            self.assertIn("⏰ PRÓXIMO INICIO (5 min)", msg)
            self.assertIn("USA USL League Two", msg)
            self.assertIn("1.85 / 3.40 / 3.80", msg)
            self.assertIn("📐 AH L(-0.5):1.85 | V(+0.5):1.90", msg)
            
            # Verify countdown is marked as fired in database
            entry_after = self.repository.list_live_watches(chat_id)[0]
            self.assertIsNotNone(entry_after.countdown_fired_at)
            
            # Second poll: should not fire again
            hits2 = await service.poll_once()
            self.assertEqual(len(hits2), 0)

    def test_add_fixture_lines_filters_duplicates_and_past_kickoffs(self) -> None:
        from unittest.mock import patch
        from datetime import datetime, timezone, timedelta
        service = LiveWatchService(repository=self.repository)
        chat_id = 111

        past_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        future_iso = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        # 1. Past kickoff filter
        with patch("monitors.live_watch.parse_fixture_line", return_value=(None, "Past", "Match", past_iso)):
            added_past = service.add_fixture_lines(chat_id, ["some line"])
            self.assertEqual(len(added_past), 0)

        # 2. Future kickoff filter (should succeed)
        with patch("monitors.live_watch.parse_fixture_line", return_value=(None, "Future", "Match", future_iso)):
            added_future = service.add_fixture_lines(chat_id, ["some line"])
            self.assertEqual(len(added_future), 1)

        # 3. Duplicate check (same fixture name "Future" vs "Match")
        with patch("monitors.live_watch.parse_fixture_line", return_value=(None, "Future", "Match", future_iso)):
            added_dup = service.add_fixture_lines(chat_id, ["some line"])
            self.assertEqual(len(added_dup), 0)

        # 4. Batch duplicates check (two identical mock events in the same call)
        with patch("monitors.live_watch.parse_fixture_line", return_value=(None, "Another", "Match", future_iso)):
            added_batch = service.add_fixture_lines(chat_id, ["line1", "line2"])
            self.assertEqual(len(added_batch), 1)


if __name__ == "__main__":
    unittest.main()

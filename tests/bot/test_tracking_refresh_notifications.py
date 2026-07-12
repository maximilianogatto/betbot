from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from core.extractor_base import CompetitionUnavailableError
from monitors.models import RefreshSummary, UnavailableCompetitionRefresh
from monitors.tracking import TrackingService, format_duration
from core.models import TrackedCompetition


def _tracked_competition() -> TrackedCompetition:
    return TrackedCompetition(
        id=1,
        platform="bet365",
        source_url="https://example.test/league",
        competition_external_id="#topic#",
        competition_name="Spanish Primera",
        metadata_json=None,
        needs_name_resolution=False,
        enabled=True,
        last_synced_at=None,
        consecutive_unavailable_refreshes=0,
        last_unavailable_refresh_at=None,
        last_unavailable_reason=None,
        last_unavailable_notification_at=None,
        created_at="2026-05-13T00:00:00+00:00",
        updated_at="2026-05-13T00:00:00+00:00",
    )


class _UnavailableExtractor:
    async def extract_league(self, url: str):
        raise CompetitionUnavailableError(
            "Bet365 league payload was not captured.",
            platform="bet365",
            source_url=url,
            reason_code="competition_unavailable",
        )


class _ExtractorRegistryStub:
    def get_for_url(self, url: str):
        return _UnavailableExtractor()


class _RepositoryStub:
    def __init__(self) -> None:
        self.tracked = _tracked_competition()
        self.remove_missing_called = False

    def get_tracked_competition(self, tracked_league_id: int):
        return self.tracked if tracked_league_id == self.tracked.id else None

    def record_unavailable_refresh(self, tracked_league_id: int, *, reason: str):
        assert tracked_league_id == self.tracked.id
        return self.tracked

    def remove_missing_events(self, *args, **kwargs):
        self.remove_missing_called = True
        raise AssertionError("remove_missing_events should not be called on failed extraction")


class TrackingRefreshNotificationTests(unittest.IsolatedAsyncioTestCase):
    def test_format_duration_formats_seconds_minutes_and_hours(self) -> None:
        self.assertEqual(format_duration(42.9), "42s")
        self.assertEqual(format_duration(68.0), "1m 08s")
        self.assertEqual(format_duration(3730.0), "1h 02m 10s")

    async def test_automatic_refresh_skips_when_manual_refresh_holds_lock(self) -> None:
        service = TrackingService()
        service.refresh_all_active_leagues = AsyncMock()
        service.dispatch_notifications = AsyncMock()

        await service.try_start_refresh("manual")
        try:
            with self.assertLogs("monitors.tracking", level="INFO") as captured_logs:
                summary = await service.monitor_once(bot=object())
        finally:
            await service.finish_refresh("manual")

        self.assertEqual(summary.tracks_requested, 0)
        self.assertEqual(summary.tracks_refreshed, 0)
        service.refresh_all_active_leagues.assert_not_awaited()
        service.dispatch_notifications.assert_not_awaited()
        self.assertTrue(
            any("Skipping automatic refresh because another refresh is already running" in line
                for line in captured_logs.output)
        )

    async def test_automatic_refresh_does_not_notify_unavailable_competitions(self) -> None:
        service = TrackingService()
        service.notify_for_refresh_result = AsyncMock()
        service.notify_for_unavailable_competition = AsyncMock()

        summary = RefreshSummary(
            tracks_requested=1,
            tracks_refreshed=0,
            active_matches=0,
            new_events=0,
            odds_changes=0,
            failed_leagues=["Spanish Primera"],
            degraded_leagues=[],
            league_results=[],
            unavailable_competitions=[
                UnavailableCompetitionRefresh(
                    tracked_league=_tracked_competition(),
                    reason="Bet365 league payload was not captured.",
                )
            ],
            elapsed_seconds=12.0,
        )

        await service.dispatch_notifications(
            bot=object(),
            summary=summary,
            notify_failures=False,
        )

        service.notify_for_unavailable_competition.assert_not_awaited()

    async def test_manual_refresh_notifies_unavailable_competitions(self) -> None:
        service = TrackingService()
        service.notify_for_refresh_result = AsyncMock()
        service.notify_for_unavailable_competition = AsyncMock()

        summary = RefreshSummary(
            tracks_requested=1,
            tracks_refreshed=0,
            active_matches=0,
            new_events=0,
            odds_changes=0,
            failed_leagues=["Spanish Primera"],
            degraded_leagues=[],
            league_results=[],
            unavailable_competitions=[
                UnavailableCompetitionRefresh(
                    tracked_league=_tracked_competition(),
                    reason="Bet365 league payload was not captured.",
                )
            ],
            elapsed_seconds=12.0,
        )

        await service.dispatch_notifications(
            bot=object(),
            summary=summary,
            notify_failures=True,
            force_unavailable_warnings=True,
            unavailable_warning_chat_id=123,
        )

        service.notify_for_unavailable_competition.assert_awaited_once()

    async def test_failed_extraction_does_not_remove_existing_matches(self) -> None:
        repository = _RepositoryStub()
        service = TrackingService(
            extractor_registry=_ExtractorRegistryStub(),
            repository=repository,
        )

        summary = await service._refresh_leagues([repository.tracked.id])

        self.assertFalse(repository.remove_missing_called)
        self.assertEqual(summary.tracks_refreshed, 0)
        self.assertEqual(summary.failed_leagues, ["Spanish Primera"])
        self.assertEqual(len(summary.unavailable_competitions), 1)
        self.assertGreaterEqual(summary.elapsed_seconds, 0.0)


if __name__ == "__main__":
    unittest.main()

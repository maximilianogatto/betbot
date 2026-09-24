from __future__ import annotations

import dataclasses
import logging
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from core.extractor_base import CompetitionUnavailableError
from services.models import RefreshSummary, UnavailableCompetitionRefresh
from services.tracking import TrackingService, format_duration
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
    def __init__(self, extractor=None) -> None:
        self.extractor = extractor or _UnavailableExtractor()

    def get_for_url(self, url: str):
        return self.extractor


class _NetworkErrorExtractor:
    async def extract_league(self, url: str):
        raise httpx.ConnectError("proxy unreachable")


class _RepositoryStub:
    def __init__(self, streak: int = 0) -> None:
        self.tracked = dataclasses.replace(_tracked_competition(), consecutive_unavailable_refreshes=streak)
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

        await service.try_start_refresh("manual")
        try:
            with self.assertLogs("services.tracking", level="INFO") as captured_logs:
                summary, _merges = await service.monitor_once()
        finally:
            await service.finish_refresh("manual")

        self.assertEqual(summary.tracks_requested, 0)
        self.assertEqual(summary.tracks_refreshed, 0)
        service.refresh_all_active_leagues.assert_not_awaited()
        self.assertTrue(
            any("Skipping automatic refresh because another refresh is already running" in line
                for line in captured_logs.output)
        )

    @patch("interfaces.telegram.notifications.notify_for_unavailable_competition", new_callable=AsyncMock)
    async def test_unforced_warnings_delegate_the_decision_to_the_repository(
        self, mock_notify_unavailable
    ) -> None:
        from interfaces.telegram.notifications import notify_unavailable_competitions
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

        # El ciclo automático ya no llama a esta función en absoluto: la
        # garantía de no spamear advertencias es estructural, no un flag.
        await notify_unavailable_competitions(
            bot=object(),
            summary=summary,
            repository=object(),
        )

        # Sin forzar, la decisión de avisar queda en manos del repositorio
        # (umbral de fallos + cooldown), que acá no autoriza nada.
        mock_notify_unavailable.assert_awaited_once()
        self.assertFalse(mock_notify_unavailable.await_args.kwargs["force_notify"])

    @patch("interfaces.telegram.notifications.notify_for_unavailable_competition", new_callable=AsyncMock)
    async def test_manual_refresh_notifies_unavailable_competitions(
        self, mock_notify_unavailable
    ) -> None:
        from interfaces.telegram.notifications import notify_unavailable_competitions
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

        await notify_unavailable_competitions(
            bot=object(),
            summary=summary,
            repository=object(),
            force_unavailable_warnings=True,
            unavailable_warning_chat_id=123,
        )

        mock_notify_unavailable.assert_awaited_once()

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

    async def test_empty_league_warns_only_when_the_streak_starts(self) -> None:
        """Una liga en receso vuelve vacía cada ciclo: avisar una vez, no 78 por día."""

        first = TrackingService(extractor_registry=_ExtractorRegistryStub(), repository=_RepositoryStub(streak=1))
        with self.assertLogs("services.tracking", level="WARNING") as captured:
            await first._refresh_leagues([1])
        self.assertTrue(any("Competition refresh unavailable id=1" in line for line in captured.output))

        repeat = TrackingService(extractor_registry=_ExtractorRegistryStub(), repository=_RepositoryStub(streak=4))
        with self.assertNoLogs("services.tracking", level="WARNING"):
            summary = await repeat._refresh_leagues([1])
        # Sigue contando como no disponible aunque no se loguee en WARNING.
        self.assertEqual(len(summary.unavailable_competitions), 1)

    async def test_leagues_of_a_disabled_platform_are_skipped_quietly(self) -> None:
        class _NoExtractorRegistry:
            def get_for_url(self, url: str):
                raise ValueError(f"No registered extractor can handle URL: {url}")

        service = TrackingService(extractor_registry=_NoExtractorRegistry(), repository=_RepositoryStub())

        with self.assertNoLogs("services.tracking", level="WARNING"):
            summary = await service._refresh_leagues([1])

        self.assertEqual(summary.tracks_requested, 0)
        self.assertEqual(summary.failed_leagues, [])

    async def test_network_error_is_one_line_without_traceback(self) -> None:
        service = TrackingService(
            extractor_registry=_ExtractorRegistryStub(_NetworkErrorExtractor()),
            repository=_RepositoryStub(),
        )

        with self.assertLogs("services.tracking", level="WARNING") as captured:
            summary = await service._refresh_leagues([1])

        [record] = [r for r in captured.records if "network error" in r.getMessage()]
        self.assertEqual(record.levelno, logging.WARNING)
        self.assertIsNone(record.exc_info)
        self.assertIn("ConnectError", record.getMessage())
        self.assertEqual(summary.failed_leagues, ["Spanish Primera"])
        self.assertEqual(summary.unavailable_competitions, [])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from bot.handlers import (
    LINK_STATS_SELECTED_PROVIDER_CONTEXT_KEY,
    MATCHES_ACTIVE_CONTEXT_KEY,
    MATCHES_SELECTED_TRACK_CONTEXT_KEY,
    SELECT_LEAGUE_FOR_STATS,
    SELECT_LEAGUE_FOR_LINK_STATS,
    STATS_ACTIVE_CONTEXT_KEY,
    STATS_SELECTED_TRACK_CONTEXT_KEY,
    link_stats_enter_country,
    stats_select_match,
    stats_command,
)
from core.stats_models import StatsLeagueOption, StatsProviderCapabilities, StatsProviderDescriptor
from monitors.models import CommandResult
from storage.tracking_repository import (
    ActiveEventRecord,
    CompetitionSubscription,
    TrackedCompetition,
    TrackedCompetitionSubscription,
)


class StatsCommandHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_stats_without_args_starts_interactive_league_selection(self) -> None:
        tracked_subscription = _tracked_subscription()
        tracking_service = SimpleNamespace(list_confirmed_tracks=lambda chat_id: [tracked_subscription])
        message = SimpleNamespace(text="1", reply_text=AsyncMock())
        context = SimpleNamespace(args=[], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with patch("bot.handlers.get_tracking_service", return_value=tracking_service):
            state = await stats_command(update, context)

        self.assertEqual(state, SELECT_LEAGUE_FOR_STATS)
        self.assertIn("stats_tracks", context.user_data)
        self.assertIn("De qué liga", message.reply_text.await_args.args[0])

    async def test_stats_command_uses_stats_service_report(self) -> None:
        match = _active_event()
        tracked_subscription = _tracked_subscription()
        stats_service = SimpleNamespace(
            build_match_stats_report=AsyncMock(
                return_value=CommandResult(ok=True, message="Reporte stats listo")
            )
        )
        message = SimpleNamespace(text="1", reply_text=AsyncMock())
        context = SimpleNamespace(
            args=["2"],
            user_data={
                MATCHES_ACTIVE_CONTEXT_KEY: [match],
                MATCHES_SELECTED_TRACK_CONTEXT_KEY: tracked_subscription,
            },
        )
        update = SimpleNamespace(message=message)

        with patch("bot.handlers.get_stats_service", return_value=stats_service):
            await stats_command(update, context)

        stats_service.build_match_stats_report.assert_awaited_once_with(
            tracked_subscription=tracked_subscription,
            matches=[match],
            event_number=1,
        )
        self.assertEqual(message.reply_text.await_args_list[0].args, ("Generando reporte de stats...",))
        self.assertEqual(message.reply_text.await_args_list[1].args, ("Reporte stats listo",))

    async def test_stats_select_match_generates_report(self) -> None:
        match = _active_event()
        tracked_subscription = _tracked_subscription()
        stats_service = SimpleNamespace(
            build_match_stats_report=AsyncMock(
                return_value=CommandResult(ok=True, message="Reporte interactivo")
            )
        )
        message = SimpleNamespace(text="1", reply_text=AsyncMock())
        context = SimpleNamespace(
            user_data={
                STATS_ACTIVE_CONTEXT_KEY: [match],
                STATS_SELECTED_TRACK_CONTEXT_KEY: tracked_subscription,
            },
        )
        update = SimpleNamespace(message=message)

        with patch("bot.handlers.get_stats_service", return_value=stats_service):
            state = await stats_select_match(update, context)

        self.assertEqual(state, -1)
        stats_service.build_match_stats_report.assert_awaited_once_with(
            tracked_subscription=tracked_subscription,
            matches=[match],
            event_number=1,
        )
        self.assertEqual(message.reply_text.await_args_list[1].args, ("Reporte interactivo",))

    async def test_link_stats_country_reports_sportradar_bootstrap_failure(self) -> None:
        stats_service = SimpleNamespace(
            search_leagues=AsyncMock(
                side_effect=RuntimeError("Sportradar bootstrap failed mode=headless")
            )
        )
        provider = StatsProviderDescriptor(
            key="sportradar_statshub",
            display_name="Sportradar Statshub",
            capabilities=StatsProviderCapabilities(supports_league_discovery=True),
        )
        message = SimpleNamespace(text="Australia", reply_text=AsyncMock())
        context = SimpleNamespace(
            user_data={
                LINK_STATS_SELECTED_PROVIDER_CONTEXT_KEY: provider,
            },
        )
        update = SimpleNamespace(message=message)

        with patch("bot.handlers.get_stats_service", return_value=stats_service):
            state = await link_stats_enter_country(update, context)

        self.assertEqual(state, -1)
        self.assertIn("SPORTRADAR_BOOTSTRAP_MODE=auto", message.reply_text.await_args.args[0])

    async def test_link_stats_country_splits_large_league_list(self) -> None:
        options = [
            StatsLeagueOption(
                provider="sportradar_statshub",
                provider_display_name="Sportradar Statshub",
                country_name="Australia",
                league_id=str(index),
                league_name=f"Australia Very Long Stats League Name {index} With Extra Context",
                season_id=f"season-{index}",
            )
            for index in range(80)
        ]
        stats_service = SimpleNamespace(search_leagues=AsyncMock(return_value=options))
        provider = StatsProviderDescriptor(
            key="sportradar_statshub",
            display_name="Sportradar Statshub",
            capabilities=StatsProviderCapabilities(supports_league_discovery=True),
        )
        message = SimpleNamespace(text="Australia", reply_text=AsyncMock())
        context = SimpleNamespace(
            user_data={
                LINK_STATS_SELECTED_PROVIDER_CONTEXT_KEY: provider,
            },
        )
        update = SimpleNamespace(message=message)

        with patch("bot.handlers.get_stats_service", return_value=stats_service):
            state = await link_stats_enter_country(update, context)

        self.assertEqual(state, SELECT_LEAGUE_FOR_LINK_STATS)
        self.assertGreater(message.reply_text.await_count, 1)
        for call in message.reply_text.await_args_list:
            self.assertLessEqual(len(call.args[0]), 3900)


def _active_event() -> ActiveEventRecord:
    return ActiveEventRecord(
        id=1,
        tracked_competition_id=10,
        platform="bet365",
        competition_external_id="league-1",
        external_event_id="event-1",
        home="Sevilla",
        away="Real Madrid",
        scheduled_label_date="Dom 24/05",
        scheduled_label_time="17:00",
        scheduled_at="2026-05-24T17:00:00+00:00",
        event_url=None,
        odds_home=3.2,
        odds_draw=3.5,
        odds_away=2.1,
        markets_json=None,
        raw_payload_json=None,
        alerted=False,
        is_active=True,
        first_seen_at="2026-05-20T00:00:00+00:00",
        last_seen_at="2026-05-20T00:00:00+00:00",
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:00+00:00",
    )


def _tracked_subscription() -> TrackedCompetitionSubscription:
    tracked = TrackedCompetition(
        id=10,
        platform="bet365",
        source_url="https://example.test",
        competition_external_id="league-1",
        competition_name="Spanish Primera",
        metadata_json=None,
        needs_name_resolution=False,
        enabled=True,
        last_synced_at=None,
        consecutive_unavailable_refreshes=0,
        last_unavailable_refresh_at=None,
        last_unavailable_reason=None,
        last_unavailable_notification_at=None,
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:00+00:00",
    )
    subscription = CompetitionSubscription(
        telegram_chat_id=123,
        tracked_competition_id=10,
        notify_new_events=True,
        notify_odds_changes=True,
        change_percent_threshold=20.0,
        enabled=True,
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:00+00:00",
    )
    return TrackedCompetitionSubscription(tracked_competition=tracked, subscription=subscription)


if __name__ == "__main__":
    unittest.main()

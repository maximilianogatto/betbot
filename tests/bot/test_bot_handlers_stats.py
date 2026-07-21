from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from interfaces.telegram.handlers import (
    EXPLORE_FIXTURES_CONTEXT_KEY,
    EXPLORE_MENU,
    EXPLORE_SELECTED_LEAGUE_CONTEXT_KEY,
    SELECT_LEAGUE_FOR_TRACK_STATS,
    LINK_STATS_SELECTED_PROVIDER_CONTEXT_KEY,
    LINK_STATS_SELECTED_TRACK_CONTEXT_KEY,
    MATCHES_ACTIVE_CONTEXT_KEY,
    MATCHES_SELECTED_TRACK_CONTEXT_KEY,
    SELECT_LEAGUE_FOR_STATS,
    SELECT_LEAGUE_FOR_LINK_STATS,
    STATS_ACTIVE_CONTEXT_KEY,
    STATS_SELECTED_TRACK_CONTEXT_KEY,
    _extract_statshub_tournament_id,
    explore_select_fixture,
    link_stats_enter_country,
    stats_select_match,
    stats_command,
    track_stats_enter_country,
    track_stats_select_league,
)
from core.stats_models import StatsFixture, StatsLeagueOption, StatsProviderCapabilities, StatsProviderDescriptor
from services.models import CommandResult
from services.stats import ExplorableStatsLeague, StatsResolution
from core.models import (
    ActiveEventRecord,
    CompetitionSubscription,
    TrackedCompetition,
    TrackedCompetitionSubscription,
)


class StatsCommandHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_stats_without_args_starts_interactive_league_selection(self) -> None:
        unified = {"id": 1, "name": "USA League Two"}
        repository = SimpleNamespace(
            list_subscribed_unified_competitions=lambda chat_id: [unified]
        )
        tracking_service = SimpleNamespace(repository=repository)
        message = SimpleNamespace(text="1", reply_text=AsyncMock())
        context = SimpleNamespace(args=[], user_data={})
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with patch("interfaces.telegram.handlers.commands.get_tracking_service", return_value=tracking_service):
            state = await stats_command(update, context)

        self.assertEqual(state, SELECT_LEAGUE_FOR_STATS)
        self.assertIn("stats_tracks", context.user_data)
        self.assertIn("De qué liga", message.reply_text.await_args.args[0])

    async def test_stats_command_uses_unified_report_from_matches(self) -> None:
        # /stats 2 after /matches: grouped matches (cross-book) + unified league dict.
        match = _active_event()
        unified = {"id": 1, "name": "USA League Two"}
        stats_service = SimpleNamespace(
            build_unified_match_stats_report=AsyncMock(
                return_value=CommandResult(ok=True, message="Reporte stats listo")
            )
        )
        message = SimpleNamespace(text="2", reply_text=AsyncMock())
        context = SimpleNamespace(
            args=["2"],
            user_data={
                MATCHES_ACTIVE_CONTEXT_KEY: [[match]],
                MATCHES_SELECTED_TRACK_CONTEXT_KEY: unified,
            },
        )
        update = SimpleNamespace(message=message)

        with patch("interfaces.telegram.handlers.commands.get_stats_service", return_value=stats_service), patch(
            "interfaces.telegram.renderers.build_comparison_match_card_message", return_value=""
        ):
            await stats_command(update, context)

        stats_service.build_unified_match_stats_report.assert_awaited_once_with(
            league_name="USA League Two",
            match_group=[match],
            provider_filter=None,
        )
        self.assertEqual(message.reply_text.await_args_list[0].args, ("Generando reporte de stats...",))
        self.assertEqual(message.reply_text.await_args_list[1].args, ("Reporte stats listo",))

    async def test_stats_select_match_generates_unified_report(self) -> None:
        match = _active_event()
        unified = {"id": 1, "name": "USA League Two"}
        stats_service = SimpleNamespace(
            resolve_unified_event=AsyncMock(
                return_value=(
                    StatsResolution(
                        kind="report",
                        result=CommandResult(ok=True, message="Reporte interactivo"),
                    ),
                    match,
                )
            )
        )
        message = SimpleNamespace(text="1", reply_text=AsyncMock())
        context = SimpleNamespace(
            user_data={
                STATS_ACTIVE_CONTEXT_KEY: [[match]],
                STATS_SELECTED_TRACK_CONTEXT_KEY: unified,
            },
        )
        update = SimpleNamespace(message=message)

        with patch("interfaces.telegram.handlers.commands.get_stats_service", return_value=stats_service), patch(
            "interfaces.telegram.renderers.build_comparison_match_card_message", return_value=""
        ):
            state = await stats_select_match(update, context)

        self.assertEqual(state, -1)
        stats_service.resolve_unified_event.assert_awaited_once_with(
            league_name="USA League Two",
            match_group=[match],
        )
        self.assertEqual(message.reply_text.await_args_list[1].args, ("Reporte interactivo",))

    def test_extract_statshub_tournament_id(self) -> None:
        url = "https://statshub.sportradar.com/bet365/es/sport/1/tournament/28743"
        self.assertEqual(_extract_statshub_tournament_id(url), "28743")
        self.assertIsNone(_extract_statshub_tournament_id("Estados Unidos"))
        self.assertIsNone(_extract_statshub_tournament_id("https://statshub.sportradar.com/bet365/en/match/70673280"))

    async def test_link_stats_links_by_statshub_url(self) -> None:
        option = StatsLeagueOption(
            provider="sportradar_statshub",
            provider_display_name="Sportradar Statshub",
            country_name="USA",
            league_id="28743",
            league_name="USL, League Two",
        )
        stats_service = SimpleNamespace(
            describe_league=AsyncMock(return_value=option),
            link_league=Mock(return_value=CommandResult(ok=True, message="✅ Liga de stats vinculada.")),
        )
        provider = StatsProviderDescriptor(
            key="sportradar_statshub",
            display_name="Sportradar Statshub",
            capabilities=StatsProviderCapabilities(supports_league_discovery=True),
        )
        message = SimpleNamespace(
            text="https://statshub.sportradar.com/bet365/es/sport/1/tournament/28743",
            reply_text=AsyncMock(),
        )
        context = SimpleNamespace(
            user_data={
                LINK_STATS_SELECTED_PROVIDER_CONTEXT_KEY: provider,
                LINK_STATS_SELECTED_TRACK_CONTEXT_KEY: _tracked_subscription(),
            },
        )
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with patch("interfaces.telegram.handlers.commands.get_stats_service", return_value=stats_service):
            state = await link_stats_enter_country(update, context)

        self.assertEqual(state, -1)
        stats_service.describe_league.assert_awaited_once_with(
            provider_key="sportradar_statshub", league_id="28743"
        )
        stats_service.link_league.assert_called_once()
        self.assertIn("vinculada", message.reply_text.await_args.args[0])

    async def test_link_stats_links_by_provider_url(self) -> None:
        sofa_url = (
            "https://www.sofascore.com/es-la/football/tournament/australia/"
            "northern-territory-premier-league-women/33650#id:91941"
        )
        option = StatsLeagueOption(
            provider="sofascore_http",
            provider_display_name="SofaScore",
            country_name="Australia",
            league_id="33650:91941",
            league_name="Northern Territory Premier League, Women",
            season_id="91941",
            source_url=sofa_url,
        )
        stats_service = SimpleNamespace(
            describe_league=AsyncMock(return_value=option),
            link_league=Mock(return_value=CommandResult(ok=True, message="✅ Liga de stats vinculada.")),
        )
        provider = StatsProviderDescriptor(
            key="sofascore_http",
            display_name="SofaScore",
            capabilities=StatsProviderCapabilities(supports_league_discovery=True),
        )
        message = SimpleNamespace(text=sofa_url, reply_text=AsyncMock())
        context = SimpleNamespace(
            user_data={
                LINK_STATS_SELECTED_PROVIDER_CONTEXT_KEY: provider,
                LINK_STATS_SELECTED_TRACK_CONTEXT_KEY: _tracked_subscription(),
            },
        )
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with patch("interfaces.telegram.handlers.commands.get_stats_service", return_value=stats_service):
            state = await link_stats_enter_country(update, context)

        self.assertEqual(state, -1)
        stats_service.describe_league.assert_awaited_once_with(provider_key="sofascore_http", league_id=sofa_url)
        stats_service.link_league.assert_called_once()
        self.assertIn("vinculada", message.reply_text.await_args.args[0])

    async def test_link_stats_country_reports_sportradar_bootstrap_failure(self) -> None:
        stats_service = SimpleNamespace(
            search_and_rank_leagues=AsyncMock(
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

        with patch("interfaces.telegram.handlers.commands.get_stats_service", return_value=stats_service):
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
        stats_service = SimpleNamespace(search_and_rank_leagues=AsyncMock(return_value=options))
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

        with patch("interfaces.telegram.handlers.commands.get_stats_service", return_value=stats_service):
            state = await link_stats_enter_country(update, context)

        self.assertEqual(state, SELECT_LEAGUE_FOR_LINK_STATS)
        self.assertGreater(message.reply_text.await_count, 1)
        for call in message.reply_text.await_args_list:
            self.assertLessEqual(len(call.args[0]), 3900)

    async def test_track_stats_discovers_and_persists_standalone_league(self) -> None:
        option = StatsLeagueOption(
            provider="footystats_http",
            provider_display_name="FootyStats",
            country_name="Australia",
            league_id="australia/northern-nsw-npl",
            league_name="Northern NSW NPL",
        )
        stats_service = SimpleNamespace(
            search_leagues=AsyncMock(return_value=[option]),
            track_stats_league=Mock(return_value=CommandResult(ok=True, message="✅ Liga agregada")),
        )
        provider = StatsProviderDescriptor(
            key="footystats_http",
            display_name="FootyStats",
            capabilities=StatsProviderCapabilities(supports_league_discovery=True),
        )
        message = SimpleNamespace(text="Australia", reply_text=AsyncMock())
        context = SimpleNamespace(
            user_data={"track_stats_selected_provider": provider},
        )
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=123))

        with patch("interfaces.telegram.handlers.commands.get_stats_service", return_value=stats_service):
            state = await track_stats_enter_country(update, context)

        self.assertEqual(state, SELECT_LEAGUE_FOR_TRACK_STATS)
        self.assertIn("track_stats_options", context.user_data)

        message.text = "1"
        with patch("interfaces.telegram.handlers.commands.get_stats_service", return_value=stats_service):
            state = await track_stats_select_league(update, context)

        self.assertEqual(state, -1)
        stats_service.track_stats_league.assert_called_once_with(chat_id=123, option=option)

    async def test_explore_fixture_builds_direct_report(self) -> None:
        fixture = StatsFixture(
            provider="footystats_http",
            league_id="australia/northern-nsw-npl",
            match_id="8439330",
            home="Valentine",
            away="Maitland",
            scheduled_at="2026-06-20T03:50:00+00:00",
        )
        stats_service = SimpleNamespace(
            build_direct_match_report=AsyncMock(return_value=CommandResult(ok=True, message="Reporte directo"))
        )
        message = SimpleNamespace(text="1", reply_text=AsyncMock())
        context = SimpleNamespace(
            user_data={
                EXPLORE_FIXTURES_CONTEXT_KEY: [fixture],
                EXPLORE_SELECTED_LEAGUE_CONTEXT_KEY: ExplorableStatsLeague(
                    provider_key="footystats_http",
                    league_id="australia/northern-nsw-npl",
                    league_name="Northern NSW NPL",
                    country_name="Australia",
                    label="Northern NSW NPL",
                ),
                "explore_overview": {"league_name": "Northern NSW NPL"},
            }
        )
        update = SimpleNamespace(message=message)

        with patch("interfaces.telegram.handlers.commands.get_stats_service", return_value=stats_service):
            state = await explore_select_fixture(update, context)

        self.assertEqual(state, EXPLORE_MENU)
        stats_service.build_direct_match_report.assert_awaited_once_with(
            provider_key="footystats_http",
            stats_match_id="8439330",
        )
        self.assertIn("Reporte directo", message.reply_text.await_args_list[1].args[0])


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

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
import tempfile
import unittest

from core.stats_models import (
    MatchIdentityCandidate,
    MatchStatsReport,
    StatsFixture,
    StatsLeagueOption,
    StatsMatchLink,
    StatsProviderCapabilities,
)
from core.stats_provider_base import StatsProvider, StatsProviderRegistry
from services.stats import (
    StatsService,
    render_league_fixtures,
    render_league_table,
    render_team_row,
    render_top_scorers,
)
import os
from core.models import ActiveEventUpsert
from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema


class FakeStatsProvider(StatsProvider):
    name = "sportradar_statshub"
    display_name = "Sportradar Statshub"
    capabilities = StatsProviderCapabilities(supports_league_discovery=True, supports_fixture_discovery=True)

    async def search_leagues(self, *, country_name: str, query: str | None = None, limit: int = 80):
        del query
        return [
            StatsLeagueOption(
                provider=self.name,
                provider_display_name=self.display_name,
                country_name=country_name,
                league_id="8",
                league_name="LaLiga",
            )
        ][:limit]

    async def list_fixtures(self, league_id: str, *, limit: int | None = None):
        del limit
        return [
            StatsFixture(
                provider=self.name,
                league_id=league_id,
                match_id="61624678",
                home="Sevilla",
                away="Real Madrid",
                scheduled_at="2026-05-24T17:00:00+00:00",
            )
        ]

    async def resolve_match(self, candidate: MatchIdentityCandidate, *, league_id: str | None = None):
        if candidate.stats_url:
            return StatsMatchLink(
                provider=self.name,
                stats_match_id="61624678",
                stats_url=candidate.stats_url,
                confidence=1.0,
                method="direct_stats_url",
            )
        if league_id == "8":
            return StatsMatchLink(
                provider=self.name,
                stats_match_id="61624678",
                stats_url="https://statshub.sportradar.com/bet365/en/match/61624678",
                confidence=0.96,
                method="league_fixture_similarity",
            )
        return None

    async def build_match_report(self, stats_match_id: str):
        return MatchStatsReport(
            provider=self.name,
            match_id=stats_match_id,
            title="Sevilla vs Real Madrid",
            markdown="Sevilla vs Real Madrid\n\n- Form: 7.5 vs 5.2",
            data={},
            generated_at="2026-05-27T00:00:00+00:00",
        )


class StatsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp.name) / "stats_service.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.repository = SqliteStorage()
        registry = StatsProviderRegistry()
        registry.register(FakeStatsProvider())
        self.service = StatsService(provider_registry=registry, repository=self.repository)
        self.subscription = self._create_track()

    def tearDown(self) -> None:
        if self._prev_db is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db
        self.tmp.cleanup()

    def test_warm_tracked_leagues_prefetches_and_links(self) -> None:
        options = asyncio.run(
            self.service.search_leagues(provider_key="sportradar_statshub", country_name="Spain")
        )
        self.service.link_league(
            tracked_competition_id=self.subscription.tracked_league.id, option=options[0]
        )
        self.repository.upsert_active_events(
            self.subscription.tracked_league.id,
            [
                ActiveEventUpsert(
                    external_event_id="fx-future",
                    home="Sevilla",
                    away="Real Madrid",
                    scheduled_label_date="07/06",
                    scheduled_label_time="03:00",
                    scheduled_at="2099-06-07T03:00:00+00:00",
                    odds_home=2.0,
                    odds_draw=3.0,
                    odds_away=3.0,
                    raw_payload={},
                )
            ],
        )
        event = self.repository.get_active_events(self.subscription.tracked_league.id, only_future=True)[0]

        summary = asyncio.run(self.service.warm_tracked_leagues(ttl_seconds=1000))

        self.assertGreaterEqual(summary["leagues"], 1)
        self.assertGreaterEqual(summary["reports"], 1)
        # The resolved stats match link was persisted during prefetch.
        self.assertIsNotNone(self.repository.get_stats_match_link(event.id))

    def test_link_league_persists_option(self) -> None:
        options = asyncio.run(
            self.service.search_leagues(provider_key="sportradar_statshub", country_name="Spain")
        )

        result = self.service.link_league(
            tracked_competition_id=self.subscription.tracked_league.id,
            option=options[0],
        )

        self.assertTrue(result.ok)
        link = self.repository.get_stats_league_link(self.subscription.tracked_league.id)
        self.assertIsNotNone(link)
        self.assertEqual(link.stats_league_id, "8")

    def test_tracks_and_lists_standalone_stats_league(self) -> None:
        option = asyncio.run(
            self.service.search_leagues(provider_key="sportradar_statshub", country_name="Spain")
        )[0]

        result = self.service.track_stats_league(chat_id=123, option=option)
        message = self.service.build_stats_tracks_message(chat_id=123)
        explorable = self.service.list_explorable_leagues(
            chat_id=123,
            tracked_subscriptions=[self.subscription],
        )

        self.assertTrue(result.ok)
        self.assertIn("cache diario", result.message)
        self.assertIn("LaLiga", message.message)
        self.assertEqual(explorable[0].league_id, "8")
        self.assertIn("solo stats", explorable[0].label)

    def test_builds_direct_provider_native_report(self) -> None:
        result = asyncio.run(
            self.service.build_direct_match_report(
                provider_key="sportradar_statshub",
                stats_match_id="61624678",
            )
        )

        self.assertTrue(result.ok)
        self.assertIn("Sevilla vs Real Madrid", result.message)

    def test_search_and_rank_promotes_league_holding_the_teams(self) -> None:
        # Two leagues share a name; only one actually contains the tracked teams.
        class DuplicateLeagueProvider(FakeStatsProvider):
            async def search_leagues(self, *, country_name, query=None, limit=80):
                del query, limit
                return [
                    StatsLeagueOption(
                        provider=self.name,
                        provider_display_name=self.display_name,
                        country_name=country_name,
                        league_id="wrong",
                        league_name="Northern NSW NPL",
                    ),
                    StatsLeagueOption(
                        provider=self.name,
                        provider_display_name=self.display_name,
                        country_name=country_name,
                        league_id="right",
                        league_name="Northern NSW NPL",
                    ),
                ]

            async def list_fixtures(self, league_id, *, limit=None):
                del limit
                if league_id != "right":
                    return []
                return [
                    StatsFixture(
                        provider=self.name,
                        league_id=league_id,
                        match_id="1",
                        home="Maitland",
                        away="Belmont Swansea",
                        scheduled_at="2026-05-30T06:30:00+00:00",
                    )
                ]

            async def count_matching_events(self, league_id, candidates):
                fixtures = await self.list_fixtures(league_id)
                return len(fixtures) and len(candidates) and 1 or 0

        registry = StatsProviderRegistry()
        registry.register(DuplicateLeagueProvider())
        service = StatsService(provider_registry=registry, repository=self.repository)

        ordered = asyncio.run(
            service.search_and_rank_leagues(
                provider_key="sportradar_statshub",
                country_name="Australia",
                odds_league_name="Australia. NPL Northern NSW",
                sample_events=[
                    MatchIdentityCandidate(
                        home="Maitland",
                        away="Belmont Swansea United",
                        scheduled_at="2026-05-30T06:30:00+00:00",
                    )
                ],
            )
        )

        self.assertEqual(ordered[0].league_id, "right")

    def test_build_report_uses_direct_stats_url(self) -> None:
        event = self._create_event(raw_payload={"stats_url": "https://s5.sir.sportradar.com/bet365/en/match/61624678"})

        result = asyncio.run(
            self.service.build_match_stats_report(
                tracked_subscription=self.subscription,
                matches=[event],
                event_number=1,
            )
        )

        self.assertTrue(result.ok)
        self.assertIn("Sevilla vs Real Madrid", result.message)
        self.assertIn("direct_stats_url", result.message)

    def test_build_report_uses_linked_league_when_no_direct_url(self) -> None:
        options = asyncio.run(
            self.service.search_leagues(provider_key="sportradar_statshub", country_name="Spain")
        )
        self.service.link_league(tracked_competition_id=self.subscription.tracked_league.id, option=options[0])
        event = self._create_event(raw_payload={})

        result = asyncio.run(
            self.service.build_match_stats_report(
                tracked_subscription=self.subscription,
                matches=[event],
                event_number=1,
            )
        )

        self.assertTrue(result.ok)
        self.assertIn("league_fixture_similarity", result.message)
        cached = self.repository.get_stats_match_link(event.id)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.stats_match_id, "61624678")

    def test_link_multiple_providers_and_build_consolidated_report(self) -> None:
        # Create a second fake provider
        class SecondFakeProvider(StatsProvider):
            name = "footystats_http"
            display_name = "FootyStats"
            capabilities = StatsProviderCapabilities(supports_league_discovery=True, supports_fixture_discovery=True)

            async def search_leagues(self, *, country_name: str, query: str | None = None, limit: int = 80):
                return []

            async def list_fixtures(self, league_id: str, *, limit: int | None = None):
                return []

            async def resolve_match(self, candidate: MatchIdentityCandidate, *, league_id: str | None = None):
                if league_id == "fs-123":
                    return StatsMatchLink(
                        provider=self.name,
                        stats_match_id="fs-match-1",
                        stats_url="https://footystats.org/fs-match-1",
                        confidence=0.98,
                        method="league_fixture_similarity",
                    )
                return None

            async def build_match_report(self, stats_match_id: str):
                return MatchStatsReport(
                    provider=self.name,
                    match_id=stats_match_id,
                    title="Sevilla vs Real Madrid",
                    markdown="Sevilla vs Real Madrid (FootyStats)\n\n- Goals avg: 3.5",
                    data={},
                    generated_at="2026-05-27T00:00:00+00:00",
                )

        self.service.provider_registry.register(SecondFakeProvider())

        # Link LaLiga to BOTH FakeStatsProvider ("sportradar_statshub") and SecondFakeProvider ("footystats_http")
        # 1. Link FakeStatsProvider
        option1 = StatsLeagueOption(
            provider="sportradar_statshub",
            provider_display_name="Sportradar Statshub",
            country_name="Spain",
            league_id="8",
            league_name="LaLiga",
        )
        self.service.link_league(tracked_competition_id=self.subscription.tracked_league.id, option=option1)

        # 2. Link SecondFakeProvider
        option2 = StatsLeagueOption(
            provider="footystats_http",
            provider_display_name="FootyStats",
            country_name="Spain",
            league_id="fs-123",
            league_name="LaLiga FS",
        )
        self.service.link_league(tracked_competition_id=self.subscription.tracked_league.id, option=option2)

        # Let's verify we have both links in the database
        links = self.repository.list_stats_league_links(self.subscription.tracked_league.id)
        self.assertEqual(len(links), 2)
        
        # Verify get_stats_league_link supports stats_provider filtering
        link_sr = self.repository.get_stats_league_link(self.subscription.tracked_league.id, stats_provider="sportradar_statshub")
        self.assertIsNotNone(link_sr)
        self.assertEqual(link_sr.stats_league_id, "8")
        
        link_fs = self.repository.get_stats_league_link(self.subscription.tracked_league.id, stats_provider="footystats_http")
        self.assertIsNotNone(link_fs)
        self.assertEqual(link_fs.stats_league_id, "fs-123")

        # Let's create an event to resolve
        event = self._create_event(raw_payload={})

        # Build stats report (should query and merge both!)
        result = asyncio.run(
            self.service.build_match_stats_report(
                tracked_subscription=self.subscription,
                matches=[event],
                event_number=1,
            )
        )

        self.assertTrue(result.ok)
        self.assertIn("Form: 7.5 vs 5.2", result.message)
        self.assertIn("Goals avg: 3.5", result.message)
        self.assertIn("━━━━━━━━━━━━━━━━━━━━", result.message)

        # Check match links are stored for both
        match_links = self.repository.list_stats_match_links(event.id)
        self.assertEqual(len(match_links), 2)
        
        # Test get_stats_match_link with stats_provider filtering
        match_link_sr = self.repository.get_stats_match_link(event.id, stats_provider="sportradar_statshub")
        self.assertIsNotNone(match_link_sr)
        self.assertEqual(match_link_sr.stats_match_id, "61624678")

        match_link_fs = self.repository.get_stats_match_link(event.id, stats_provider="footystats_http")
        self.assertIsNotNone(match_link_fs)
        self.assertEqual(match_link_fs.stats_match_id, "fs-match-1")

        # --- Provider selector (/stats <n> <provider>) ---
        # Filtering to one provider returns ONLY that provider's report.
        only_fs = asyncio.run(
            self.service.build_match_stats_report(
                tracked_subscription=self.subscription,
                matches=[event],
                event_number=1,
                provider_filter="footystats",
            )
        )
        self.assertTrue(only_fs.ok)
        self.assertIn("Goals avg: 3.5", only_fs.message)
        self.assertNotIn("Form: 7.5 vs 5.2", only_fs.message)

        # Unknown provider -> helpful error listing the available ones.
        unknown = asyncio.run(
            self.service.build_match_stats_report(
                tracked_subscription=self.subscription,
                matches=[event],
                event_number=1,
                provider_filter="noexiste",
            )
        )
        self.assertFalse(unknown.ok)
        self.assertIn("Providers disponibles", unknown.message)

    def _create_track(self):
        chat_id = 123
        self.repository.create_pending_competition_request(
            chat_id,
            platform="bet365",
            source_url="https://example.test/laliga",
            competition_external_id="laliga",
            competition_name="Spanish Primera",
            requires_empty_confirmation=False,
            needs_name_resolution=False,
        )
        confirmed = self.repository.confirm_pending_competition_request(chat_id)
        return self.repository.get_tracked_competition_subscription_by_identity(
            chat_id, "bet365", "laliga"
        )

    def _create_event(self, *, raw_payload: dict):
        self.repository.upsert_active_events(
            self.subscription.tracked_league.id,
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
                    raw_payload=raw_payload,
                )
            ],
        )
        return self.repository.get_active_events(self.subscription.tracked_league.id, only_future=False)[0]


def _overview_fixture() -> dict:
    return {
        "league_id": "28743",
        "season_id": "139904",
        "league_name": "USL, League Two",
        "source_url": "https://statshub.sportradar.com/bet365/en/sport/1/tournament/28743",
        "standings": {
            "tables": [
                {
                    "name": "Chesapeake Division",
                    "rows": [
                        {
                            "position": 1,
                            "team": {"name": "Virginia Beach United"},
                            "played": 4,
                            "points": 8,
                            "wins": 2,
                            "draws": 2,
                            "losses": 0,
                            "goals_for": 9,
                            "goals_against": 3,
                            "goal_difference": 6,
                            "home": {"points": 4, "goals_for": 5, "goals_against": 1},
                            "away": {"points": 4, "goals_for": 4, "goals_against": 2},
                        }
                    ],
                }
            ]
        },
        "fixtures": [
            {
                "time": {"date": "07/06/26", "time": "03:00", "iso_utc": "2099-06-07T03:00:00+00:00"},
                "home": {"name": "Charlestown"},
                "away": {"name": "Cooks Hill United"},
            },
            {
                "time": {"date": "01/01/20", "time": "00:00", "iso_utc": "2020-01-01T00:00:00+00:00"},
                "home": {"name": "Old"},
                "away": {"name": "Past"},
            },
        ],
        "teams": [],
        "top_goals": [],
    }


class StatsExploreRenderTests(unittest.TestCase):
    def test_table_lists_team_and_link(self) -> None:
        out = render_league_table(_overview_fixture())
        self.assertIn("Chesapeake Division", out)
        self.assertIn("Virginia Beach", out)  # name is column-truncated in the table
        self.assertIn("statshub.sportradar.com", out)

    def test_fixtures_show_only_future(self) -> None:
        out = render_league_fixtures(_overview_fixture())
        self.assertIn("Charlestown vs Cooks Hill United", out)
        self.assertNotIn("Old vs Past", out)  # past fixture filtered out

    def test_team_row_found_by_fuzzy_name(self) -> None:
        out = render_team_row(_overview_fixture(), "virginia beach")
        self.assertIn("Virginia Beach United", out)
        self.assertIn("8 pts", out)

    def test_team_row_not_found(self) -> None:
        out = render_team_row(_overview_fixture(), "zzz nonexistent")
        self.assertIn("No encontré", out)

    def test_top_scorers_empty_is_graceful(self) -> None:
        out = render_top_scorers(_overview_fixture())
        self.assertIn("Sin datos de goleadores", out)


class PickRepresentativeEventTests(unittest.TestCase):
    def test_prefers_event_with_stats_url(self) -> None:
        from types import SimpleNamespace

        from services.stats import _pick_representative_event

        no_url = SimpleNamespace(stats_url=None, home="A", away="B")
        with_url = SimpleNamespace(stats_url="https://x/match/1", home="A", away="B")
        self.assertIs(_pick_representative_event([no_url, with_url]), with_url)
        # Falls back to the first when none carries a stats URL.
        self.assertIs(_pick_representative_event([no_url]), no_url)
        with self.assertRaises(ValueError):
            _pick_representative_event([])


if __name__ == "__main__":
    unittest.main()

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
from monitors.stats import StatsService
from storage.tracking_repository import ActiveEventUpsert, SqliteTrackingRepository

tracking_repository_module = importlib.import_module("storage.tracking_repository")


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
        self.old_db_path = tracking_repository_module.DB_FILE_PATH
        self.old_data_dir = tracking_repository_module.DATA_DIR
        self.tmp = tempfile.TemporaryDirectory()
        tracking_repository_module.DATA_DIR = Path(self.tmp.name)
        tracking_repository_module.DB_FILE_PATH = Path(self.tmp.name) / "tracking.sqlite3"
        self.repository = SqliteTrackingRepository()
        registry = StatsProviderRegistry()
        registry.register(FakeStatsProvider())
        self.service = StatsService(provider_registry=registry, repository=self.repository)
        self.subscription = self._create_track()

    def tearDown(self) -> None:
        tracking_repository_module.DB_FILE_PATH = self.old_db_path
        tracking_repository_module.DATA_DIR = self.old_data_dir
        self.tmp.cleanup()

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

    def _create_track(self):
        chat_id = 123
        self.repository.create_pending_competition_request(
            chat_id,
            platform="bet365",
            source_url="https://example.test/laliga",
            competition_external_id="laliga",
            competition_name="Spanish Primera",
        )
        confirmed = self.repository.confirm_pending_competition_request(chat_id)
        self.assertIsNotNone(confirmed)
        return self.repository.list_tracked_competitions(chat_id)[0]

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


if __name__ == "__main__":
    unittest.main()

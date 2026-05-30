from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from core.stats_models import MatchIdentityCandidate
from stats_providers.sportradar_http import SportradarHttpStatsProvider


class FakeSportradarRuntime:
    def __init__(self) -> None:
        self.leagues = [
            {
                "country_name": "Spain",
                "name": "LaLiga",
                "unique_tournament_id": 8,
                "season_id": 130805,
            }
        ]
        self.fixtures = [
            {
                "match_id": 61624678,
                "home": {"name": "Sevilla"},
                "away": {"name": "Real Madrid"},
                "time": {"iso_utc": "2026-05-24T17:00:00+00:00"},
                "status": {"in_livescore": False},
            }
        ]

    def search_leagues(self, *, country_name: str, query: str | None, limit: int):
        del query
        return [item for item in self.leagues if item["country_name"] == country_name][:limit]

    def get_tournament_navigation(self, request):
        self.last_tournament_request = request
        return {"fixtures": self.fixtures}

    def get_match_report(self, request):
        return {
            "snapshot": {
                "metadata": {
                    "home": {"name": "Sevilla"},
                    "away": {"name": "Real Madrid"},
                }
            },
            "intelligence": {},
            "intelligence_markdown": "Sevilla vs Real Madrid\n\n- Form: test",
        }


class SportradarHttpStatsProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = FakeSportradarRuntime()
        self.provider = SportradarHttpStatsProvider(runtime=self.runtime)

    def test_search_leagues_maps_provider_options(self) -> None:
        options = asyncio.run(self.provider.search_leagues(country_name="Spain", limit=10))

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].provider, "sportradar_statshub")
        self.assertEqual(options[0].league_id, "8")
        self.assertEqual(options[0].season_id, "130805")

    def test_list_fixtures_maps_navigation_fixture(self) -> None:
        fixtures = asyncio.run(self.provider.list_fixtures("8"))

        self.assertEqual(len(fixtures), 1)
        self.assertEqual(fixtures[0].match_id, "61624678")
        self.assertEqual(fixtures[0].home, "Sevilla")
        self.assertIn("/match/61624678", fixtures[0].stats_url or "")

    def test_resolve_match_uses_direct_stats_url(self) -> None:
        link = asyncio.run(
            self.provider.resolve_match(
                MatchIdentityCandidate(
                    home="Any",
                    away="Any",
                    scheduled_at=None,
                    stats_url="https://statshub.sportradar.com/bet365/en/match/61624678",
                )
            )
        )

        self.assertIsNotNone(link)
        self.assertEqual(link.stats_match_id, "61624678")
        self.assertEqual(link.method, "direct_stats_url")

    def test_resolve_match_scores_fixture_similarity(self) -> None:
        link = asyncio.run(
            self.provider.resolve_match(
                MatchIdentityCandidate(
                    home="Sevilla FC",
                    away="Real Madrid",
                    scheduled_at="2026-05-24T17:00:00+00:00",
                    league_name="LaLiga",
                ),
                league_id="8",
            )
        )

        self.assertIsNotNone(link)
        self.assertEqual(link.stats_match_id, "61624678")
        self.assertEqual(link.method, "league_fixture_similarity")
        self.assertGreaterEqual(link.confidence, 0.9)

    def test_resolve_match_links_abbreviated_provider_name(self) -> None:
        # Sportradar shortens names; the sportsbook pads them. Per-side token
        # containment must still link "Sevilla Olympic Warriors" -> "Sevilla".
        link = asyncio.run(
            self.provider.resolve_match(
                MatchIdentityCandidate(
                    home="Sevilla Olympic Warriors",
                    away="Real Madrid Reserves",
                    scheduled_at="2026-05-24T17:00:00+00:00",
                    league_name="LaLiga",
                ),
                league_id="8",
            )
        )

        self.assertIsNotNone(link)
        self.assertEqual(link.stats_match_id, "61624678")

    def test_resolve_match_defers_when_candidates_are_ambiguous(self) -> None:
        # Two fixtures share the home team and kickoff; the away name decides.
        self.runtime.fixtures = [
            {
                "match_id": 1,
                "home": {"name": "Newcastle"},
                "away": {"name": "Sydney"},
                "time": {"iso_utc": "2026-05-24T17:00:00+00:00"},
                "status": {"in_livescore": False},
            },
            {
                "match_id": 2,
                "home": {"name": "Newcastle"},
                "away": {"name": "Sidney"},
                "time": {"iso_utc": "2026-05-24T17:00:00+00:00"},
                "status": {"in_livescore": False},
            },
        ]
        candidate = MatchIdentityCandidate(
            home="Newcastle United",
            away="Sydney FC",
            scheduled_at="2026-05-24T17:00:00+00:00",
            league_name="LaLiga",
        )

        link = asyncio.run(self.provider.resolve_match(candidate, league_id="8"))
        ranked = asyncio.run(self.provider.rank_match_candidates(candidate, league_id="8"))

        self.assertIsNone(link)
        self.assertGreaterEqual(len(ranked), 2)

    def test_build_match_report_returns_compact_report(self) -> None:
        report = asyncio.run(self.provider.build_match_report("61624678"))

        self.assertEqual(report.provider, "sportradar_statshub")
        self.assertEqual(report.title, "Sevilla vs Real Madrid")
        self.assertIn("Form", report.markdown)

    def test_default_runtime_config_honors_bootstrap_mode_env(self) -> None:
        with patch.dict("os.environ", {"SPORTRADAR_BOOTSTRAP_MODE": "auto"}):
            provider = SportradarHttpStatsProvider(runtime=FakeSportradarRuntime())

        self.assertEqual(provider._runtime_config.bootstrap_mode, "auto")


if __name__ == "__main__":
    unittest.main()

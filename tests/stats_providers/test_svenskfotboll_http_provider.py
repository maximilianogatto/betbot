from __future__ import annotations

import unittest

from core.stats_models import MatchIdentityCandidate
from stats_providers.svenskfotboll_http import SvenskfotbollHttpStatsProvider


class FakeSvenskfotbollClient:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def search_leagues(self, query: str | None = None, *, association_id: str | int | None = None, limit: int = 80):
        del association_id
        leagues = [
            {
                "competition_id": "133348",
                "name": "Allsvenskan 2026",
                "source_url": "/go-to/?ftid=133348",
                "categories": ["Allsvenskan herrar"],
            },
            {
                "competition_id": "32363",
                "name": "Northern NSW NPL 2026",
                "source_url": "/go-to/?ftid=32363",
                "categories": ["Australia"],
            },
        ]
        if query:
            query_norm = query.casefold()
            leagues = [league for league in leagues if query_norm in league["name"].casefold()]
        return leagues[:limit]

    def get_upcoming_matches(self, competition_id: str | int, *, limit: int = 40):
        return {
            "competition_id": str(competition_id),
            "title": "Allsvenskan 2026: Kommande matcher",
            "matches": [
                {
                    "match_id": "6529914",
                    "start_time_local": "2026-07-03 19:00",
                    "home": "IK Sirius FK",
                    "away": "Mjällby AIF",
                },
                {
                    "match_id": "6529920",
                    "start_time_local": "2026-07-04 17:30",
                    "home": "Hammarby IF",
                    "away": "AIK",
                },
            ][:limit],
        }

    def get_latest_results(self, competition_id: str | int, *, limit: int = 40):
        return {
            "competition_id": str(competition_id),
            "title": "Allsvenskan 2026: Senaste resultat",
            "matches": [
                {
                    "match_id": "6529800",
                    "start_time_local": "2026-06-28 15:00",
                    "home": "IK Sirius FK",
                    "away": "AIK",
                    "score": "2 - 1",
                },
                {
                    "match_id": "6529801",
                    "start_time_local": "2026-06-27 19:00",
                    "home": "Mjällby AIF",
                    "away": "Hammarby IF",
                    "score": "1 - 1",
                },
            ][:limit],
        }

    def get_standings(self, competition_id: str | int):
        return {
            "competition_id": str(competition_id),
            "title": "Allsvenskan 2026",
            "teams": [
                {
                    "position": 2,
                    "team": "IK Sirius FK",
                    "played": 10,
                    "goal_difference": 12,
                    "points": 23,
                    "team_id": "108445",
                },
                {
                    "position": 6,
                    "team": "Mjällby AIF",
                    "played": 10,
                    "goal_difference": 3,
                    "points": 17,
                    "team_id": "108441",
                },
            ],
        }

    def get_live_game_info(self, match_id: str | int):
        return {
            "match_id": str(match_id),
            "home": {"name": "IK Sirius FK"},
            "away": {"name": "Mjällby AIF"},
            "status": {"desc": "HALFTIME"},
            "score": {"home-team": "2", "away-team": "1"},
            "stats": {
                "home-corners": "3",
                "away-corners": "2",
                "home-shots-on-goal": "5",
                "away-shots-on-goal": "2",
                "home-red-cards": "0",
                "away-red-cards": "1",
            },
            "event_summary": {
                "goals": 3,
                "red_cards": 1,
                "corners": 5,
                "latest_event": {"game-minute-for-web": "45+1", "type-desc": "Goal"},
            },
        }


class SvenskfotbollHttpStatsProviderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = FakeSvenskfotbollClient()
        self.provider = SvenskfotbollHttpStatsProvider(client=self.client, payload_cache=None)

    async def asyncTearDown(self) -> None:
        await self.provider.stop()

    async def test_provider_metadata_matches_stats_contract(self) -> None:
        self.assertEqual(self.provider.name, "svenskfotboll_http")
        self.assertIn("Svenskfotboll", self.provider.display_name)
        self.assertTrue(self.provider.capabilities.supports_league_discovery)
        self.assertTrue(self.provider.capabilities.supports_fixture_discovery)
        self.assertTrue(self.provider.capabilities.supports_live)
        self.assertFalse(self.provider.capabilities.requires_browser_bootstrap)

    async def test_search_leagues_is_country_gated_to_sweden(self) -> None:
        self.assertEqual(await self.provider.search_leagues(country_name="Argentina", query="Allsvenskan"), [])

        options = await self.provider.search_leagues(country_name="Suecia", query="Allsvenskan")

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].provider, "svenskfotboll_http")
        self.assertEqual(options[0].league_id, "133348")
        self.assertEqual(options[0].country_name, "Sweden")
        self.assertEqual(options[0].season_id, "2026")

    async def test_describe_league_accepts_direct_ftid_url(self) -> None:
        option = await self.provider.describe_league(
            "https://www.svenskfotboll.se/widget-go-to/?scr=table&ftid=133348"
        )

        self.assertIsNotNone(option)
        self.assertEqual(option.league_id, "133348")
        self.assertIn("Allsvenskan", option.league_name)

    async def test_list_fixtures_builds_compound_match_ids(self) -> None:
        fixtures = await self.provider.list_fixtures(
            "https://www.svenskfotboll.se/widget-go-to/?scr=table&ftid=133348",
            limit=1,
        )

        self.assertEqual(len(fixtures), 1)
        self.assertEqual(fixtures[0].provider, "svenskfotboll_http")
        self.assertEqual(fixtures[0].league_id, "133348")
        self.assertEqual(fixtures[0].match_id, "133348:6529914")
        self.assertEqual(fixtures[0].scheduled_at, "2026-07-03T19:00:00+02:00")

    async def test_resolve_match_from_direct_url(self) -> None:
        candidate = MatchIdentityCandidate(
            home="IK Sirius FK",
            away="Mjällby AIF",
            scheduled_at=None,
            stats_url="https://www.svenskfotboll.se/widget-go-to/?scr=result&ftid=133348&fmid=6529914",
        )

        link = await self.provider.resolve_match(candidate)

        self.assertIsNotNone(link)
        self.assertEqual(link.stats_match_id, "133348:6529914")
        self.assertEqual(link.method, "direct_stats_url")
        self.assertEqual(link.confidence, 1.0)

    async def test_resolve_match_by_fixture_similarity(self) -> None:
        candidate = MatchIdentityCandidate(
            home="IK Sirius",
            away="Mjallby",
            scheduled_at="2026-07-03T19:00:00+02:00",
        )

        link = await self.provider.resolve_match(candidate, league_id="133348")

        self.assertIsNotNone(link)
        self.assertEqual(link.stats_match_id, "133348:6529914")
        self.assertEqual(link.method, "league_fixture_similarity")
        self.assertGreaterEqual(link.confidence, 0.78)

    async def test_build_match_report_includes_live_table_and_recent_results(self) -> None:
        report = await self.provider.build_match_report("133348:6529914")

        self.assertEqual(report.provider, "svenskfotboll_http")
        self.assertEqual(report.match_id, "133348:6529914")
        self.assertEqual(report.title, "IK Sirius FK vs Mjällby AIF")
        self.assertIn("Estado live: HALFTIME", report.markdown)
        self.assertIn("Marcador: 2 - 1", report.markdown)
        self.assertIn("Tabla:", report.markdown)
        self.assertIn("Resultados recientes:", report.markdown)


if __name__ == "__main__":
    unittest.main()

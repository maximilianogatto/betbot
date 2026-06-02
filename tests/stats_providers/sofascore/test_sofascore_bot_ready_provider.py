from __future__ import annotations

import asyncio
import json
import unittest

from core.stats_models import MatchIdentityCandidate
from stats_providers.sofascore_http import SofaScoreBotReadyStatsProvider
from stats_providers.sofascore_http.reporting import render_match_report
from stats_providers.sofascore_http.validate_bot_ready import run_validation


class FakeSofaScoreClient:
    def __init__(self) -> None:
        self.closed = False
        self.season_event_calls = 0

    def close(self) -> None:
        self.closed = True

    def get_categories(self):
        return [
            {"id": 34, "name": "Australia"},
            {"id": 1, "name": "England"},
        ]

    def get_category_tournaments(self, category_id: int):
        self.last_category_id = category_id
        return [
            {
                "id": 1638,
                "name": "NPL Northern New South Wales",
                "slug": "npl-northern-new-south-wales",
                "category": {"id": 34, "name": "Australia", "sport": {"slug": "football"}},
            },
            {
                "id": 1894,
                "name": "A-League Women",
                "category": {"id": 34, "name": "Australia", "sport": {"slug": "football"}},
            },
        ]

    def get_public_html(self, url: str) -> str:
        self.last_public_url = url
        next_data = {
            "props": {
                "pageProps": {
                    "initialProps": {
                        "uniqueTournament": {
                            "id": 33650,
                            "name": "Northern Territory Premier League, Women",
                            "slug": "northern-territory-premier-league-women",
                            "category": {
                                "name": "Australia",
                                "slug": "australia",
                                "country": {"name": "Australia"},
                            },
                        },
                        "info": {"season": {"id": 91941, "name": "2026", "year": "2026"}},
                        "seasons": [{"id": 91941, "name": "2026", "year": "2026"}],
                        "hasEvents": True,
                    }
                }
            }
        }
        return (
            '<html><head><script id="__NEXT_DATA__" type="application/json">'
            f"{json.dumps(next_data)}"
            "</script></head></html>"
        )

    def get_unique_tournament_seasons(self, tournament_id: int):
        self.last_tournament_id = tournament_id
        return [{"id": 88647, "name": "Northern NSW NPL 2026", "year": "2026"}]

    def get_season_events(self, tournament_id: int, season_id: int, *, direction: str, page: int):
        self.season_event_calls += 1
        self.last_season_args = (tournament_id, season_id, direction, page)
        fixture = {
            "id": 15981197,
            "slug": "cooks-hill-united-charlestown-azzurri",
            "startTimestamp": 1780801200,
            "status": {"type": "notstarted", "description": "Not started"},
            "homeTeam": {"id": 409081, "name": "Cooks Hill United"},
            "awayTeam": {"id": 136220, "name": "Charlestown Azzurri"},
            "season": {"id": 88647},
            "tournament": {
                "uniqueTournament": {"id": 1638, "name": "NPL Northern New South Wales"}
            },
        }
        return [fixture]

    def get_season_standings(self, tournament_id: int, season_id: int):
        return [
            {
                "name": "Northern NSW NPL 2026",
                "type": "total",
                "rows": [
                    {
                        "position": 1,
                        "matches": 10,
                        "points": 24,
                        "scoreDiffFormatted": "+12",
                        "scoresFor": 22,
                        "scoresAgainst": 10,
                        "wins": 8,
                        "draws": 0,
                        "losses": 2,
                        "team": {"id": 409081, "name": "Cooks Hill United"},
                    }
                ],
            }
        ]

    def get_event(self, event_id: int):
        return {
            "id": event_id,
            "startTimestamp": 1780801200,
            "status": {"type": "inprogress", "description": "2nd half"},
            "homeTeam": {"id": 409081, "name": "Cooks Hill United"},
            "awayTeam": {"id": 136220, "name": "Charlestown Azzurri"},
            "homeScore": {"current": 2},
            "awayScore": {"current": 1},
            "season": {"id": 88647},
            "tournament": {"uniqueTournament": {"id": 1638, "name": "NPL Northern New South Wales"}},
        }

    def get_event_statistics(self, event_id: int):
        return [
            {
                "period": "ALL",
                "groups": [
                    {
                        "statisticsItems": [
                            {"name": "Corner kicks", "home": "4", "away": "2"},
                            {"name": "Shots on target", "home": "6", "away": "3"},
                        ]
                    }
                ],
            }
        ]

    def get_event_incidents(self, event_id: int):
        return [
            {
                "incidentType": "goal",
                "time": 55,
                "isHome": True,
                "homeScore": 2,
                "awayScore": 1,
                "player": {"id": 1, "name": "Scorer"},
            }
        ]

    def get_event_lineups(self, event_id: int):
        return {"confirmed": True, "home": {"players": [{}] * 11}, "away": {"players": [{}] * 11}}

    def get_event_h2h(self, event_id: int):
        return {"teamDuel": {"homeWins": 3, "draws": 1, "awayWins": 2}}

    def get_event_win_probability(self, event_id: int):
        return {"winProbability": {"homeWin": 60, "draw": 25, "awayWin": 15}}

    def get_event_odds(self, event_id: int):
        return {
            "markets": [
                {
                    "marketGroup": "1X2",
                    "choices": [
                        {"name": "1", "fractionalValue": "1/2"},
                        {"name": "X", "fractionalValue": "5/2"},
                        {"name": "2", "fractionalValue": "9/2"},
                    ],
                }
            ]
        }


class SofaScoreBotReadyProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeSofaScoreClient()
        self.provider = SofaScoreBotReadyStatsProvider(client=self.client)

    def test_capabilities_are_http_only(self) -> None:
        capabilities = self.provider.capabilities

        self.assertTrue(capabilities.supports_live)
        self.assertTrue(capabilities.supports_lineups)
        self.assertFalse(capabilities.requires_browser_bootstrap)

    def test_search_leagues_filters_country_and_query(self) -> None:
        leagues = asyncio.run(self.provider.search_leagues(country_name="Australia", query="Northern"))

        self.assertEqual(len(leagues), 1)
        self.assertEqual(leagues[0].league_id, "1638")
        self.assertEqual(leagues[0].provider, "sofascore_http")

    def test_describe_league_from_public_tournament_url(self) -> None:
        option = asyncio.run(
            self.provider.describe_league(
                "https://www.sofascore.com/es-la/football/tournament/australia/"
                "northern-territory-premier-league-women/33650#id:91941"
            )
        )

        self.assertIsNotNone(option)
        assert option is not None
        self.assertEqual(option.provider, "sofascore_http")
        self.assertEqual(option.league_id, "33650:91941")
        self.assertEqual(option.season_id, "91941")
        self.assertEqual(option.country_name, "Australia")
        self.assertEqual(option.league_name, "Northern Territory Premier League, Women")
        self.assertEqual(self.client.last_public_url, option.source_url)

    def test_list_fixtures_deduplicates_next_and_last_pages(self) -> None:
        fixtures = asyncio.run(self.provider.list_fixtures("1638"))

        self.assertEqual(len(fixtures), 1)
        self.assertEqual(fixtures[0].match_id, "15981197")
        self.assertEqual(self.client.season_event_calls, 2)

    def test_list_fixtures_accepts_explicit_season_league_id(self) -> None:
        fixtures = asyncio.run(self.provider.list_fixtures("1638:88647"))

        self.assertEqual(len(fixtures), 1)
        self.assertEqual(self.client.last_season_args, (1638, 88647, "last", 0))

    def test_resolve_match_scores_similar_names(self) -> None:
        link = asyncio.run(
            self.provider.resolve_match(
                MatchIdentityCandidate(
                    home="Cooks Hill United FC",
                    away="Charlestown Azzurri",
                    scheduled_at="2026-06-07T03:00:00+00:00",
                ),
                league_id="1638",
            )
        )

        self.assertIsNotNone(link)
        self.assertEqual(link.stats_match_id, "15981197")
        self.assertGreaterEqual(link.confidence, 0.9)

    def test_league_overview_normalizes_standings(self) -> None:
        overview = asyncio.run(self.provider.get_league_overview("1638"))

        rows = overview["standings"]["tables"][0]["rows"]
        self.assertEqual(rows[0]["team"]["name"], "Cooks Hill United")
        self.assertEqual(rows[0]["goal_difference"], "+12")

    def test_build_match_report_is_compact(self) -> None:
        report = asyncio.run(self.provider.build_match_report("15981197"))

        self.assertEqual(report.provider, "sofascore_http")
        self.assertIn("Odds 1X2", report.markdown)
        self.assertIn("Corner kicks: 4 | 2", report.markdown)
        self.assertIn("55' Gol local: Scorer (2-1)", report.markdown)

    def test_stop_closes_client(self) -> None:
        asyncio.run(self.provider.stop())

        self.assertTrue(self.client.closed)

    def test_validation_payload_is_json_serializable(self) -> None:
        payload = asyncio.run(
            run_validation(
                self.provider,
                country="Australia",
                query="Northern",
                league_id="1638",
                event_id="15981197",
            )
        )

        self.assertIn('"requires_browser_bootstrap": false', json.dumps(payload))


class SofaScoreReportTests(unittest.TestCase):
    def test_empty_snapshot_renders_without_crashing(self) -> None:
        markdown = render_match_report({})

        self.assertIn("Local vs Visitante", markdown)
        self.assertIn("unknown", markdown)


if __name__ == "__main__":
    unittest.main()

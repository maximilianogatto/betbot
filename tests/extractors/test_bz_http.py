from __future__ import annotations

import unittest

from extractors.bz_http import discovery as discovery_module
from extractors.bz_http.extractor import BzHttpExtractor, _tournament_id_from_url
from extractors.bz_http.parser import build_competition_extraction, find_tournament
from extractors.bz_http.settings import BzHttpSettings


def _search_data() -> list[dict]:
    return [
        {
            "id": "sr:tournament:325",
            "name": "Brasileiro Serie A",
            "categoryId": "sr:category:25",
            "categoryName": "Brazil",
            "currentSeasonId": "sr:season:1",
            "matchCount": 1,
            "matches": [
                {
                    "id": "sr:match:66886828",
                    "name": "Cruzeiro vs. Fluminense",
                    "homeName": "Cruzeiro EC MG",
                    "awayName": "Fluminense FC RJ",
                    "homeId": "sr:competitor:1",
                    "awayId": "sr:competitor:2",
                    "seasonId": "sr:season:1",
                    "scheduledTime": 1780270200000,
                }
            ],
        },
        {
            "id": "sr:tournament:1347",
            "name": "Primera B",
            "categoryId": "sr:category:41",
            "categoryName": "Argentina",
            "matchCount": 0,
            "matches": [],
        },
    ]


def _odds_tabs() -> list[dict]:
    return [
        {
            "tabId": "MAIN",
            "tabName": "Main",
            "markets": [
                {
                    "marketId": "1",
                    "marketName": "1X2",
                    "marketSpecifierList": [
                        {
                            "specifiers": "",
                            "status": 1,
                            "outcomes": [
                                {"outcomeId": "1", "displayName": "{#competitor1}", "odds": 1.93},
                                {"outcomeId": "2", "displayName": "Draw", "odds": 3.45},
                                {"outcomeId": "3", "displayName": "{#competitor2}", "odds": 4.10},
                            ],
                        }
                    ],
                },
                {
                    "marketId": "16",
                    "marketName": "Handicap",
                    "colNameList": ["{#competitor1}", "{#competitor2}"],
                    "marketSpecifierList": [
                        {
                            "specifiers": "hcp=0",
                            "status": 1,
                            "outcomes": [
                                {"outcomeId": "1714", "displayName": "0", "odds": 1.41},
                                {"outcomeId": "1715", "displayName": "0", "odds": 2.80},
                            ],
                        },
                        {
                            "specifiers": "hcp=0.25",
                            "status": 1,
                            "outcomes": [
                                {"outcomeId": "1714", "displayName": "-0.25", "odds": 1.66},
                                {"outcomeId": "1715", "displayName": "+0.25", "odds": 2.20},
                            ],
                        },
                    ],
                },
                {
                    "marketId": "18",
                    "marketName": "Total",
                    "marketSpecifierList": [
                        {
                            "specifiers": "total=2.5",
                            "status": 1,
                            "outcomes": [
                                {"outcomeId": "12", "displayName": "2.5", "odds": 2.18},
                                {"outcomeId": "13", "displayName": "2.5", "odds": 1.69},
                            ],
                        },
                        {
                            "specifiers": "total=3.5",
                            "status": 1,
                            "outcomes": [
                                {"outcomeId": "12", "displayName": "3.5", "odds": 3.80},
                                {"outcomeId": "13", "displayName": "3.5", "odds": 1.25},
                            ],
                        },
                    ],
                },
            ],
        }
    ]


class BzParserTests(unittest.TestCase):
    def test_build_competition_maps_all_markets(self) -> None:
        tournament = find_tournament(_search_data(), "325")
        extraction = build_competition_extraction(
            tournament_id="325",
            tournament=tournament,
            odds_by_match={"sr:match:66886828": _odds_tabs()},
            source_url="bz:tournament:325",
        )
        self.assertEqual(extraction.platform, "bz_http")
        self.assertEqual(extraction.competition_name, "Brazil · Brasileiro Serie A")
        self.assertEqual(extraction.competition_external_id, "325")
        self.assertEqual(len(extraction.events), 1)

        event = extraction.events[0]
        self.assertEqual(event.home, "Cruzeiro EC MG")
        self.assertEqual(event.away, "Fluminense FC RJ")
        self.assertEqual(event.odds_1x2.home, 1.93)
        self.assertEqual(event.odds_1x2.draw, 3.45)
        self.assertEqual(event.odds_1x2.away, 4.10)
        self.assertEqual(event.metadata["sr_match_id"], "sr:match:66886828")
        self.assertTrue(event.scheduled_at.startswith("2026"))

        ah = event.markets_payload["asian_handicap"]["selections"]
        names = {s["selection"] for s in ah}
        self.assertEqual(names, {"Cruzeiro EC MG", "Fluminense FC RJ"})
        # main line (closest to 0) first for the home side
        self.assertEqual(ah[0]["selection"], "Cruzeiro EC MG")
        self.assertEqual(ah[0]["line"], "0")

        gl = event.markets_payload["goal_line"]["selections"]
        self.assertEqual(gl[0]["selection"], "Over")
        self.assertEqual(gl[0]["line"], "2.5")
        self.assertEqual(gl[0]["odds"], 2.18)

    def test_missing_tournament_is_empty(self) -> None:
        extraction = build_competition_extraction(
            tournament_id="999",
            tournament={"name": None, "matches": []},
            odds_by_match={},
            source_url="bz:tournament:999",
        )
        self.assertTrue(extraction.is_empty)


class BzDiscoveryTests(unittest.TestCase):
    def test_build_league_options_by_country(self) -> None:
        options = discovery_module.build_league_options(
            _search_data(),
            platform="bz_http",
            platform_display_name="BZ",
            country_name="brazil",
        )
        self.assertEqual(len(options), 1)
        opt = options[0]
        self.assertEqual(opt.league_name, "Brasileiro Serie A")
        self.assertEqual(opt.source_url, "bz:tournament:325")
        self.assertEqual(opt.games_count, 1)

    def test_unknown_country_empty(self) -> None:
        options = discovery_module.build_league_options(
            _search_data(),
            platform="bz_http",
            platform_display_name="BZ",
            country_name="Narnia",
        )
        self.assertEqual(options, [])


class BzUrlTests(unittest.TestCase):
    def test_tournament_id_from_scheme(self) -> None:
        self.assertEqual(_tournament_id_from_url("bz:tournament:325"), "325")
        self.assertEqual(_tournament_id_from_url("bz:tournament:sr:tournament:325"), "325")

    def test_tournament_id_from_sr_in_url(self) -> None:
        self.assertEqual(
            _tournament_id_from_url("https://m.bz.com/sports?id=sr:tournament:231"), "231"
        )

    def test_tournament_id_missing(self) -> None:
        self.assertIsNone(_tournament_id_from_url("https://m.bz.com/"))

    def test_can_handle_url(self) -> None:
        self.assertTrue(BzHttpExtractor.can_handle_url("bz:tournament:325"))
        self.assertTrue(BzHttpExtractor.can_handle_url("https://m.bz.com/sports"))
        self.assertFalse(BzHttpExtractor.can_handle_url("https://rainbet.com/x"))

    def test_api_base(self) -> None:
        self.assertEqual(BzHttpSettings(base_url="https://m.bz.com").api_base, "https://m.bz.com/api")


if __name__ == "__main__":
    unittest.main()

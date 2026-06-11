from __future__ import annotations

import unittest

from extractors.solcasino_http import discovery as discovery_module
from extractors.solcasino_http.extractor import SolcasinoHttpExtractor, _tournament_id_from_url
from extractors.solcasino_http.parser import build_competition_extraction
from extractors.solcasino_http.settings import SolcasinoHttpSettings


def _snapshot() -> dict:
    return {
        "sports": {"1": {"name": "Soccer"}, "5": {"name": "Tennis"}},
        "categories": {"10": {"name": "Brazil"}, "20": {"name": "Spain"}},
        "tournaments": {
            "100": {"name": "Brasileiro Serie A", "category_id": "10"},
            "200": {"name": "ATP Madrid", "category_id": "20"},  # tennis -> excluded
            "300": {"name": "Empty League", "category_id": "10"},  # no events -> excluded
        },
        "events": {
            "e1": {
                "desc": {
                    "type": "match",
                    "sport": "1",
                    "tournament": "100",
                    "scheduled": 1780250000,
                    "competitors": [{"name": "Palmeiras", "id": "a"}, {"name": "Santos", "id": "b"}],
                },
                "markets": {
                    "1": {"": {"1": {"k": "1.40"}, "2": {"k": "4.70"}, "3": {"k": "7.80"}}},
                    "18": {
                        "total=2.5": {"12": {"k": "1.72"}, "13": {"k": "2.12"}},
                        "total=1.5": {"12": {"k": "1.20"}, "13": {"k": "4.10"}},
                    },
                },
            },
            "e2": {
                "desc": {
                    "type": "match",
                    "sport": "5",  # tennis
                    "tournament": "200",
                    "scheduled": 1780260000,
                    "competitors": [{"name": "Alcaraz"}, {"name": "Sinner"}],
                },
                "markets": {"1": {"": {"1": {"k": "1.5"}, "3": {"k": "2.4"}}}},
            },
        },
    }


class SolcasinoParserTests(unittest.TestCase):
    def test_build_competition_maps_1x2_and_goal_line(self) -> None:
        extraction = build_competition_extraction(
            tournament_id="100", snapshot=_snapshot(), source_url="solcasino:tournament:100"
        )
        self.assertEqual(extraction.platform, "solcasino_http")
        self.assertEqual(extraction.competition_name, "Brazil · Brasileiro Serie A")
        self.assertEqual(len(extraction.events), 1)
        event = extraction.events[0]
        self.assertEqual(event.home, "Palmeiras")
        self.assertEqual(event.away, "Santos")
        self.assertEqual(event.odds_1x2.home, 1.40)
        self.assertEqual(event.odds_1x2.draw, 4.70)
        self.assertEqual(event.odds_1x2.away, 7.80)
        gl = event.markets_payload["goal_line"]["selections"]
        # main line (closest to 2.5) first
        self.assertEqual(gl[0]["selection"], "Over")
        self.assertEqual(gl[0]["line"], "2.5")
        self.assertEqual(gl[0]["odds"], 1.72)
        self.assertTrue(event.scheduled_at.startswith("2026"))

    def test_empty_for_unknown_tournament(self) -> None:
        extraction = build_competition_extraction(
            tournament_id="999", snapshot=_snapshot(), source_url="solcasino:tournament:999"
        )
        self.assertTrue(extraction.is_empty)


class SolcasinoDiscoveryTests(unittest.TestCase):
    def test_build_league_options_soccer_only_by_country(self) -> None:
        options = discovery_module.build_league_options(
            _snapshot(),
            platform="solcasino_http",
            platform_display_name="Solcasino HTTP",
            sport_id="1",
            country_name="brazil",
        )
        # Tennis (200) and event-less league (300) excluded; only Serie A remains.
        self.assertEqual(len(options), 1)
        opt = options[0]
        self.assertEqual(opt.league_name, "Brazil · Brasileiro Serie A")
        self.assertEqual(opt.country_name, "Brazil")
        self.assertEqual(opt.source_url, "solcasino:tournament:100")
        self.assertEqual(opt.games_count, 1)

    def test_unknown_country_returns_empty(self) -> None:
        options = discovery_module.build_league_options(
            _snapshot(),
            platform="solcasino_http",
            platform_display_name="Solcasino HTTP",
            sport_id="1",
            country_name="Marte",
        )
        self.assertEqual(options, [])


class SolcasinoUrlTests(unittest.TestCase):
    def test_tournament_id_from_scheme(self) -> None:
        self.assertEqual(_tournament_id_from_url("solcasino:tournament:1669818812230406144"), "1669818812230406144")

    def test_tournament_id_from_bt_path(self) -> None:
        url = "https://solcasino.io/sports?bt-path=%2Fsoccer%2Fbrazil%2Fbrasileiro-serie-a-1669818812230406144"
        self.assertEqual(_tournament_id_from_url(url), "1669818812230406144")

    def test_tournament_id_missing(self) -> None:
        self.assertIsNone(_tournament_id_from_url("https://solcasino.io/sports"))

    def test_can_handle_url(self) -> None:
        self.assertTrue(SolcasinoHttpExtractor.can_handle_url("solcasino:tournament:1669818812230406144"))
        self.assertTrue(SolcasinoHttpExtractor.can_handle_url("https://solcasino.io/sports?bt-path=%2Fsoccer"))
        self.assertFalse(SolcasinoHttpExtractor.can_handle_url("https://mystake.bet/x"))

    def test_feed_url_shape(self) -> None:
        settings = SolcasinoHttpSettings(api_host="h.sptpub.com", brand_id="123", language="en")
        self.assertEqual(settings.feed_url(0), "https://h.sptpub.com/api/v4/prematch/brand/123/en/0")


if __name__ == "__main__":
    unittest.main()

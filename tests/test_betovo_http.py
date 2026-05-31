from __future__ import annotations

import unittest

from extractors.betovo_http import discovery as discovery_module
from extractors.betovo_http.extractor import BetovoHttpExtractor, _champ_id_from_url
from extractors.betovo_http.parser import build_competition_extraction
from extractors.betovo_http.settings import BetovoHttpSettings


def _events_payload() -> dict:
    return {
        "champs": [
            {"id": 11318, "name": "Brasileiro Serie A"},
            {"id": 3951, "name": "J.League"},
        ],
        "categories": [
            {"id": 593, "name": "Brazil", "iso": "BRA", "champIds": [11318]},
            {"id": 600, "name": "Japan", "iso": "JPN", "champIds": [3951]},
        ],
        "events": [
            {
                "id": 15457817,
                "name": "Cruzeiro vs. Fluminense",
                "champId": 11318,
                "catId": 593,
                "startDate": "2026-05-31T23:30:00Z",
                "extId": "fp32_ar:match:554495",
                "competitorIds": [51666, 47398],
            },
            {"id": 999, "name": "Kashima vs. Urawa", "champId": 3951, "catId": 600, "startDate": "2026-06-01T10:00:00Z"},
        ],
    }


def _detail() -> dict:
    return {
        "competitors": [{"id": 51666, "name": "Cruzeiro"}, {"id": 47398, "name": "Fluminense"}],
        "markets": [
            {"typeId": 1, "name": "1x2", "desktopOddIds": [[1], [2], [3]]},
            {"typeId": 16, "name": "Handicap", "sv": "-0.5", "desktopOddIds": [[10], [11], [12], [13]]},
            {"typeId": 18, "name": "Goal Line", "sv": "2.5", "desktopOddIds": [[20], [21]]},
        ],
        "odds": [
            {"id": 1, "name": "1", "price": 1.90, "competitorId": 51666},
            {"id": 2, "name": "X", "price": 3.40},
            {"id": 3, "name": "2", "price": 4.30, "competitorId": 47398},
            {"id": 10, "name": "Cruzeiro (0)", "price": 1.38, "competitorId": 51666},
            {"id": 11, "name": "Cruzeiro (-0.5)", "price": 1.88, "competitorId": 51666},
            {"id": 12, "name": "Fluminense (0)", "price": 3.00, "competitorId": 47398},
            {"id": 13, "name": "Fluminense (+0.5)", "price": 1.92, "competitorId": 47398},
            {"id": 20, "name": "Over 2.5", "price": 2.05},
            {"id": 21, "name": "Under 2.5", "price": 1.78},
        ],
    }


class BetovoParserTests(unittest.TestCase):
    def test_build_competition_maps_all_markets(self) -> None:
        extraction = build_competition_extraction(
            champ_id="11318",
            events_payload=_events_payload(),
            details_by_event={"15457817": _detail()},
            source_url="betovo:champ:11318",
        )
        self.assertEqual(extraction.platform, "betovo_http")
        self.assertEqual(extraction.competition_name, "Brazil · Brasileiro Serie A")
        self.assertEqual(len(extraction.events), 1)

        event = extraction.events[0]
        self.assertEqual(event.home, "Cruzeiro")
        self.assertEqual(event.away, "Fluminense")
        self.assertEqual(event.odds_1x2.home, 1.90)
        self.assertEqual(event.odds_1x2.draw, 3.40)
        self.assertEqual(event.odds_1x2.away, 4.30)
        self.assertEqual(event.metadata["sr_match_id"], "ar:match:554495")
        self.assertTrue(event.scheduled_at.startswith("2026-05-31"))

        ah = event.markets_payload["asian_handicap"]["selections"]
        self.assertEqual({s["selection"] for s in ah}, {"Cruzeiro", "Fluminense"})
        self.assertEqual(ah[0]["selection"], "Cruzeiro")
        self.assertEqual(ah[0]["line"], "0")  # main line (closest to 0) first

        gl = event.markets_payload["goal_line"]["selections"]
        self.assertEqual(gl[0], {"selection": "Over", "line": "2.5", "odds": 2.05})
        self.assertEqual(gl[1], {"selection": "Under", "line": "2.5", "odds": 1.78})

    def test_missing_champ_is_empty(self) -> None:
        extraction = build_competition_extraction(
            champ_id="424242",
            events_payload=_events_payload(),
            details_by_event={},
            source_url="betovo:champ:424242",
        )
        self.assertTrue(extraction.is_empty)


class BetovoDiscoveryTests(unittest.TestCase):
    def test_build_league_options_by_country(self) -> None:
        options = discovery_module.build_league_options(
            _events_payload(),
            platform="betovo_http",
            platform_display_name="Betovo HTTP",
            country_name="brazil",
        )
        self.assertEqual(len(options), 1)
        opt = options[0]
        self.assertEqual(opt.league_name, "Brasileiro Serie A")
        self.assertEqual(opt.source_url, "betovo:champ:11318")
        self.assertEqual(opt.games_count, 1)

    def test_unknown_country_empty(self) -> None:
        options = discovery_module.build_league_options(
            _events_payload(),
            platform="betovo_http",
            platform_display_name="Betovo HTTP",
            country_name="Atlantis",
        )
        self.assertEqual(options, [])


class BetovoUrlTests(unittest.TestCase):
    def test_champ_id_from_scheme(self) -> None:
        self.assertEqual(_champ_id_from_url("betovo:champ:11318"), "11318")

    def test_champ_id_from_query(self) -> None:
        self.assertEqual(_champ_id_from_url("https://www.betovo848425.com/sports?champids=11318"), "11318")

    def test_champ_id_missing(self) -> None:
        self.assertIsNone(_champ_id_from_url("https://www.betovo848425.com/"))

    def test_can_handle_url(self) -> None:
        self.assertTrue(BetovoHttpExtractor.can_handle_url("betovo:champ:11318"))
        self.assertTrue(BetovoHttpExtractor.can_handle_url("https://www.betovo848425.com/sports"))
        self.assertFalse(BetovoHttpExtractor.can_handle_url("https://m.bz.com/x"))

    def test_common_params(self) -> None:
        params = BetovoHttpSettings().common_params
        self.assertEqual(params["integration"], "betovo")
        self.assertEqual(params["culture"], "en-GB")


if __name__ == "__main__":
    unittest.main()

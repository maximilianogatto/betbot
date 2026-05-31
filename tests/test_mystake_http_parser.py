from __future__ import annotations

import json
import unittest

from extractors.mystake_http.extractor import MystakeHttpExtractor, _region_id_from_url
from extractors.mystake_http.parser import build_competition_extraction


def _raw_response() -> dict:
    games = [
        {
            "id": 71,
            "t1": 1,
            "t2": 2,
            "st": "2026-06-01T20:00:00+00:00",
            "sport": 1,
            "region": 100,
            "ev": {
                "448": {
                    "a": {"pos": 1, "coef": 2.10},
                    "b": {"pos": 2, "coef": 3.20},
                    "c": {"pos": 3, "coef": 3.50},
                },
                "537": {
                    "x": {"pos": 81, "h": 2.5, "coef": 1.90},
                    "y": {"pos": 82, "h": 2.5, "coef": 1.95},
                },
            },
        },
        {  # different league -> must be filtered out
            "id": 72,
            "t1": 1,
            "t2": 3,
            "st": "2026-06-02T20:00:00+00:00",
            "region": 999,
            "ev": {"448": {"a": {"pos": 1, "coef": 1.5}}},
        },
    ]
    teams = [{"ID": 1, "Name": "Team A"}, {"ID": 2, "Name": "Team B"}, {"ID": 3, "Name": "Team C"}]
    return {"game": json.dumps(games), "teams": json.dumps(teams), "outrights": "[]"}


class MystakeParserTests(unittest.TestCase):
    def test_build_competition_filters_region_and_maps_odds(self) -> None:
        extraction = build_competition_extraction(
            region_id="100",
            raw_response=_raw_response(),
            source_url="mystake:region:100",
        )

        self.assertEqual(extraction.competition_external_id, "100")
        self.assertEqual(extraction.platform, "mystake_http")
        self.assertFalse(extraction.is_empty)
        self.assertEqual(len(extraction.events), 1)  # the region=999 game is excluded

        event = extraction.events[0]
        self.assertEqual(event.home, "Team A")
        self.assertEqual(event.away, "Team B")
        self.assertEqual(event.external_event_id, "71")
        self.assertEqual(event.odds_1x2.home, 2.10)
        self.assertEqual(event.odds_1x2.draw, 3.20)
        self.assertEqual(event.odds_1x2.away, 3.50)
        self.assertEqual(event.markets_payload["over_under"]["line"], 2.5)
        self.assertEqual(event.markets_payload["over_under"]["over"], 1.90)

    def test_empty_when_no_games_for_region(self) -> None:
        extraction = build_competition_extraction(
            region_id="555",
            raw_response=_raw_response(),
            source_url="mystake:region:555",
        )
        self.assertTrue(extraction.is_empty)
        self.assertEqual(extraction.events, [])


class MystakeExtractorUrlTests(unittest.TestCase):
    def test_can_handle_scheme_and_domain(self) -> None:
        self.assertTrue(MystakeHttpExtractor.can_handle_url("mystake:region:100"))
        self.assertTrue(MystakeHttpExtractor.can_handle_url("https://mystake.bet/as/sportsbook/prematch?region=100"))
        self.assertFalse(MystakeHttpExtractor.can_handle_url("https://spinbetter.com/x"))

    def test_region_id_extraction(self) -> None:
        self.assertEqual(_region_id_from_url("mystake:region:100"), "100")
        self.assertEqual(_region_id_from_url("https://mystake.bet/x?region=2829182"), "2829182")
        self.assertIsNone(_region_id_from_url("https://mystake.bet/x"))


if __name__ == "__main__":
    unittest.main()

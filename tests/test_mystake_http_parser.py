from __future__ import annotations

import json
import unittest

from extractors.mystake_http.extractor import (
    MystakeHttpExtractor,
    _champ_id_from_url,
    _game_ids_for_champ,
)
from extractors.mystake_http.parser import build_competition_extraction


def _gameall_response() -> dict:
    games = [
        {
            "id": 72119374,
            "ch": 258,
            "t1": 1,
            "t2": 2,
            "st": "2026-06-01T20:00:00",
            "ev": {
                "448": {
                    "a": {"pos": 1, "coef": 1.20},
                    "b": {"pos": 2, "coef": 7.20},
                    "c": {"pos": 3, "coef": 13.11},
                },
                "537": {
                    "x": {"pos": 81, "h": 2.5, "coef": 1.42},
                    "y": {"pos": 82, "h": 2.5, "coef": 2.80},
                },
            },
        },
        {  # different championship -> excluded
            "id": 71549853,
            "ch": 15268,
            "t1": 1,
            "t2": 3,
            "st": "2026-06-02T20:00:00",
            "ev": {"448": {"a": {"pos": 1, "coef": 1.5}}},
        },
    ]
    teams = [{"ID": 1, "Name": "Japan"}, {"ID": 2, "Name": "Iceland"}, {"ID": 3, "Name": "X"}]
    return {"game": json.dumps(games), "teams": json.dumps(teams), "outrights": "[]"}


def _topgames() -> list:
    return [
        {
            "id": 1,
            "kn": "Soccer",
            "gms": [72119374, 71549853],
            "gmsi": [
                {"id": 72119374, "ch": 258, "rg": 15},
                {"id": 71549853, "ch": 15268, "rg": 15},
            ],
        },
        {"id": 3, "kn": "Baseball", "gms": [70000293], "gmsi": [{"id": 70000293, "ch": 661, "rg": 15}]},
    ]


class MystakeParserTests(unittest.TestCase):
    def test_build_competition_filters_by_championship_and_maps_odds(self) -> None:
        extraction = build_competition_extraction(
            champ_id="258", raw_response=_gameall_response(), source_url="mystake:champ:258"
        )
        self.assertEqual(extraction.competition_external_id, "258")
        self.assertEqual(extraction.platform, "mystake_http")
        self.assertEqual(len(extraction.events), 1)  # ch=15268 excluded
        event = extraction.events[0]
        self.assertEqual(event.home, "Japan")
        self.assertEqual(event.away, "Iceland")
        self.assertEqual(event.odds_1x2.home, 1.20)
        self.assertEqual(event.odds_1x2.away, 13.11)
        self.assertEqual(event.markets_payload["over_under"]["line"], 2.5)

    def test_empty_for_unknown_championship(self) -> None:
        extraction = build_competition_extraction(
            champ_id="999", raw_response=_gameall_response(), source_url="mystake:champ:999"
        )
        self.assertTrue(extraction.is_empty)


class MystakeExtractorTests(unittest.TestCase):
    def test_can_handle_url(self) -> None:
        self.assertTrue(MystakeHttpExtractor.can_handle_url("mystake:champ:258"))
        self.assertTrue(MystakeHttpExtractor.can_handle_url("https://mystake.bet/as/sportsbook/prematch?ch=258"))
        self.assertFalse(MystakeHttpExtractor.can_handle_url("https://spinbetter.com/x"))

    def test_champ_id_extraction(self) -> None:
        self.assertEqual(_champ_id_from_url("mystake:champ:258"), "258")
        self.assertEqual(_champ_id_from_url("https://mystake.bet/x?ch=15268"), "15268")
        self.assertIsNone(_champ_id_from_url("https://mystake.bet/x"))

    def test_game_ids_for_champ_from_topgames(self) -> None:
        self.assertEqual(_game_ids_for_champ(_topgames(), sport_id=1, champ_id="258"), [72119374])
        self.assertEqual(_game_ids_for_champ(_topgames(), sport_id=1, champ_id="15268"), [71549853])
        self.assertEqual(_game_ids_for_champ(_topgames(), sport_id=1, champ_id="661"), [])  # baseball, not soccer


if __name__ == "__main__":
    unittest.main()

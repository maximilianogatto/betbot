from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from extractors.mystake_http.extractor import (
    MystakeHttpExtractor,
    _champ_id_from_url,
    _dominant_champ_id,
    _game_ids_from_update_cache,
    _game_ids_for_champ,
    _game_ids_from_gameall_url,
)
from extractors.mystake_http.client import _decode_cache_payload
from extractors.mystake_http.parser import (
    build_competition_extraction,
    live_events_from_mobile_header,
    live_event_from_game,
    parse_teams,
    prematch_event_from_game,
)


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
                "451": {
                    "a": {"pos": 70, "h": -0.5, "coef": 1.90},
                    "b": {"pos": 71, "h": 0.5, "coef": 1.95},
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


def _header_tree() -> dict:
    return {
        "AS": {
            "Sports": {
                "1": {
                    "Name": "Fútbol",
                    "Regions": {
                        "15": {
                            "Name": "International",
                            "Champs": {
                                "258": {
                                    "Name": "Friendlies",
                                    "GameSmallItems": {"72119374": {"ID": 72119374}},
                                }
                            },
                        }
                    },
                }
            }
        }
    }


def _live_mobile_header() -> dict:
    return {
        "Games": [
            {
                "ID": 74160920,
                "Sport": 1,
                "Region": 222,
                "Champ": 128773,
                "StartTime": "2026-08-03T21:30:00",
                "Team1": 112427,
                "Team2": 17601,
                "MatchStatusID": 3,
                "MatchTime": "28",
                "Score": "1:1",
                "LiveBetStatus": True,
                "rct1": 1,
                "rct2": 0,
                "hprs": [
                    {"mid": 602, "kname": "1", "posn": 1, "v": 3.45},
                    {"mid": 602, "kname": "x", "posn": 2, "v": 2.80},
                    {"mid": 602, "kname": "2", "posn": 3, "v": 2.30},
                    {"mid": 603, "kname": "o", "posn": 1, "h": 3.5, "v": 1.70},
                    {"mid": 603, "kname": "u", "posn": 2, "h": 3.5, "v": 2.05},
                ],
            },
            {
                "ID": 74568059,
                "Sport": 1,
                "Region": 1626,
                "Champ": 69553,
                "StartTime": "2026-08-03T21:50:00",
                "Team1": 357824,
                "Team2": 397041,
                "MatchStatusID": 4,
                "MatchTime": "8",
                "Score": "6:2",
                "LiveBetStatus": True,
            },
            {"ID": 900, "Sport": 2, "Team1": 1, "Team2": 2, "Score": "10:9"},
        ],
        "Teams": [
            {"ID": 112427, "Name": "CD Recoleta"},
            {"ID": 17601, "Name": "Nacional Asuncion"},
            {"ID": 357824, "Name": "Paris Saint-Germain (Felix)"},
            {"ID": 397041, "Name": "Manchester City FC (Sebastian)"},
        ],
        "Championats": [
            {"ID": 128773, "Name": "Paraguay. Division Intermedia"},
            {"ID": 69553, "Name": "eAdriatic League"},
        ],
        "Regions": [
            {"ID": 222, "Name": "Paraguay"},
            {"ID": 1626, "Name": "eAdriatic League"},
        ],
    }


class FakeMystakeClient:
    def __init__(
        self,
        raw_response: dict,
        *,
        updates: dict | None = None,
        live_header: dict | None = None,
    ) -> None:
        self.raw_response = raw_response
        self.updates = updates or {}
        self.live_header = live_header or {}
        self.closed = False

    async def fetch_header(self) -> dict:
        return _header_tree()

    async def fetch_games(self, game_ids: list[int]) -> dict:
        self.requested_game_ids = game_ids
        return self.raw_response

    async def fetch_live_game_updates(self) -> dict:
        return self.updates

    async def fetch_live_header_mobile(self) -> dict:
        return self.live_header

    async def aclose(self) -> None:
        self.closed = True


class MystakeParserTests(unittest.TestCase):
    def test_decode_cache_payload_accepts_base64_gzip_json(self) -> None:
        import base64
        import gzip

        payload = {"Games": [{"ID": 1, "Score": "1:0"}]}
        encoded = base64.b64encode(gzip.compress(json.dumps(payload).encode("utf-8"))).decode("ascii")

        self.assertEqual(_decode_cache_payload(encoded), payload)

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
        # Goal line (market 537) and Asian handicap (market 451) in the bot's shape.
        gl = event.markets_payload["goal_line"]["selections"]
        self.assertEqual(gl[0]["selection"], "Over")
        self.assertEqual(gl[0]["line"], "2.5")
        ah = event.markets_payload["asian_handicap"]["selections"]
        sel_names = {s["selection"] for s in ah}
        self.assertEqual(sel_names, {"Japan", "Iceland"})

    def test_empty_for_unknown_championship(self) -> None:
        extraction = build_competition_extraction(
            champ_id="999", raw_response=_gameall_response(), source_url="mystake:champ:999"
        )
        self.assertTrue(extraction.is_empty)

    def test_prematch_event_maps_to_live_watch_shape_without_firing_live_state(self) -> None:
        raw = _gameall_response()
        game = json.loads(raw["game"])[0]
        teams = parse_teams(raw["teams"])

        event = prematch_event_from_game(
            game,
            teams,
            competition_external_id="258",
            competition_name="International Friendlies",
            country_name="International",
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.platform, "mystake_http")
        self.assertEqual(event.source_url, "mystake:champ:258")
        self.assertEqual((event.home, event.away), ("Japan", "Iceland"))
        self.assertIsNone(event.minute)
        self.assertIsNone(event.home_score)
        self.assertEqual(event.odds_1x2.home, 1.20)

    def test_live_event_requires_live_signal_and_maps_score_cards(self) -> None:
        raw = _gameall_response()
        game = json.loads(raw["game"])[0]
        teams = parse_teams(raw["teams"])

        self.assertIsNone(
            live_event_from_game(
                game,
                teams,
                competition_external_id="258",
                competition_name="International Friendlies",
                country_name="International",
            )
        )

        game = {
            **game,
            "s": 1,
            "minute": "37'",
            "score": {"home": 2, "away": 1},
            "cards": {"home": {"red": 1, "yellow": 2}, "away": {"red": 0, "yellow": 3}},
        }
        event = live_event_from_game(
            game,
            teams,
            competition_external_id="258",
            competition_name="International Friendlies",
            country_name="International",
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.minute, "37'")
        self.assertEqual((event.home_score, event.away_score), (2, 1))
        self.assertEqual((event.home_red_cards, event.away_red_cards), (1, 0))
        self.assertEqual((event.home_yellow_cards, event.away_yellow_cards), (2, 3))

    def test_live_events_from_mobile_header_maps_soccer_score_cards_and_odds(self) -> None:
        events = live_events_from_mobile_header(_live_mobile_header())

        self.assertEqual(len(events), 2)  # basketball is ignored; virtual soccer is flagged, not dropped
        event = events[0]
        self.assertEqual(event.external_event_id, "74160920")
        self.assertEqual((event.home, event.away), ("CD Recoleta", "Nacional Asuncion"))
        self.assertEqual(event.competition_name, "Paraguay. Division Intermedia")
        self.assertEqual(event.country_name, "Paraguay")
        self.assertEqual(event.minute, "28'")
        self.assertEqual((event.home_score, event.away_score), (1, 1))
        self.assertEqual((event.home_red_cards, event.away_red_cards), (1, 0))
        self.assertEqual(event.odds_1x2.home, 3.45)
        self.assertEqual(event.odds_1x2.draw, 2.8)
        self.assertEqual(event.odds_1x2.away, 2.3)
        self.assertEqual(event.markets_payload["goal_line"]["selections"][0]["line"], "3.5")
        self.assertTrue(event.is_soccer)
        self.assertFalse(events[1].is_soccer)


class MystakeExtractorTests(unittest.TestCase):
    def test_can_handle_url(self) -> None:
        self.assertTrue(MystakeHttpExtractor.can_handle_url("mystake:champ:258"))
        self.assertTrue(MystakeHttpExtractor.can_handle_url("https://mystake.bet/as/sportsbook/prematch?ch=258"))
        self.assertTrue(
            MystakeHttpExtractor.can_handle_url(
                "https://analytics-sp.googleserv.tech/api/prematch/getprematchgameall/as/28/?games=,72219517"
            )
        )
        self.assertFalse(MystakeHttpExtractor.can_handle_url("https://spinbetter.com/x"))

    def test_game_ids_from_gameall_url(self) -> None:
        url = "https://analytics-sp.googleserv.tech/api/prematch/getprematchgameall/as/28/?games=,72219517,71336881"
        self.assertEqual(_game_ids_from_gameall_url(url), [72219517, 71336881])
        self.assertEqual(_game_ids_from_gameall_url("mystake:champ:258"), [])

    def test_dominant_champ_id(self) -> None:
        self.assertEqual(_dominant_champ_id(_gameall_response()), "258")  # 1 ch=258, 1 ch=15268 -> tie, first
        single = {"game": json.dumps([{"id": 1, "ch": 10304, "t1": 1, "t2": 2, "ev": {}}]), "teams": "[]"}
        self.assertEqual(_dominant_champ_id(single), "10304")

    def test_champ_id_extraction(self) -> None:
        self.assertEqual(_champ_id_from_url("mystake:champ:258"), "258")
        self.assertEqual(_champ_id_from_url("https://mystake.bet/x?ch=15268"), "15268")
        self.assertIsNone(_champ_id_from_url("https://mystake.bet/x"))

    def test_game_ids_for_champ_from_topgames(self) -> None:
        self.assertEqual(_game_ids_for_champ(_topgames(), sport_id=1, champ_id="258"), [72119374])
        self.assertEqual(_game_ids_for_champ(_topgames(), sport_id=1, champ_id="15268"), [71549853])
        self.assertEqual(_game_ids_for_champ(_topgames(), sport_id=1, champ_id="661"), [])  # baseball, not soccer

    def test_game_ids_from_update_cache_ignores_deleted_ids(self) -> None:
        payload = {
            "UpdateList": [{"GameId": 100}, {"GameId": "101"}, {"GameId": "x"}],
            "DeleteList": [{"GameId": 101}],
        }
        self.assertEqual(_game_ids_from_update_cache(payload), [100])


class MystakeExtractorAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_live_events_uses_live_cache_ids_and_filters_prematch_details(self) -> None:
        extractor = MystakeHttpExtractor()
        extractor._client = FakeMystakeClient(
            _gameall_response(),
            updates={"UpdateList": [{"GameId": 72119374}], "DeleteList": []},
        )

        self.assertEqual(await extractor.list_live_events(), [])

    async def test_list_live_events_maps_live_details_when_status_is_live(self) -> None:
        raw = _gameall_response()
        games = json.loads(raw["game"])
        games[0] = {**games[0], "s": 1, "minute": "12'", "score": {"home": 1, "away": 0}}
        raw = {**raw, "game": json.dumps(games)}
        extractor = MystakeHttpExtractor()
        extractor._client = FakeMystakeClient(
            raw,
            updates={"UpdateList": [{"GameId": 72119374}], "DeleteList": []},
        )

        events = await extractor.list_live_events()

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual((event.home, event.away), ("Japan", "Iceland"))
        self.assertEqual(event.competition_name, "International · Friendlies")
        self.assertEqual(event.minute, "12'")
        self.assertEqual((event.home_score, event.away_score), (1, 0))

    async def test_list_live_events_prefers_mobile_header_snapshot(self) -> None:
        extractor = MystakeHttpExtractor()
        extractor._client = FakeMystakeClient(_gameall_response(), live_header=_live_mobile_header())

        events = await extractor.list_live_events()

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].external_event_id, "74160920")
        self.assertEqual((events[0].home_score, events[0].away_score), (1, 1))

    async def test_list_prematch_events_reads_active_tracked_champs(self) -> None:
        extractor = MystakeHttpExtractor()
        extractor._client = FakeMystakeClient(_gameall_response())

        with patch("extractors.mystake_http.extractor._active_mystake_champ_ids", return_value=["258"]):
            events = await extractor.list_prematch_events()

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual((event.home, event.away), ("Japan", "Iceland"))
        self.assertEqual(event.source_url, "mystake:champ:258")


if __name__ == "__main__":
    unittest.main()

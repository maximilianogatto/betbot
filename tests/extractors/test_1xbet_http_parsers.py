from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

SANDBOX_DIR = Path(__file__).resolve().parents[1] / "sandbox" / "1xbet_http"
if str(SANDBOX_DIR) not in sys.path:
    sys.path.insert(0, str(SANDBOX_DIR))

import xbet_parsing
import extract_1xbet_league


SPORTS_SHORT_PAYLOAD = {
    "Id": 0,
    "Success": True,
    "Error": "",
    "ErrorCode": 0,
    "Guid": "",
    "Value": [
        {
            "IT": 1,
            "N": "Fútbol",
            "E": "Football",
            "C": 2074,
            "CC": 411,
            "CID": 14,
            "L": [
                {
                    "LI": 118587,
                    "L": "Liga de Campeones de la UEFA",
                    "LE": "UEFA Champions League",
                    "CN": "Europa",
                    "CI": 223,
                    "GC": 1,
                }
            ],
        }
    ],
}

CHAMP_PAYLOAD = {
    "Id": 0,
    "Success": True,
    "Error": "",
    "ErrorCode": 0,
    "Guid": "",
    "Value": {
        "SI": 1,
        "SN": "Fútbol",
        "L": "Liga de Campeones de la UEFA",
        "LI": 118587,
        "G": [
            {
                "I": 718933777,
                "O1": "Paris Saint-Germain",
                "O2": "Arsenal",
                "O1I": 1,
                "O2I": 2,
                "S": 1780156800,
                "CI": 330725078,
                "N": 192527,
                "B": 15005,
                "SS": 2,
                "SST": 2,
                "TN": "Mitad",
                "TNS": "Mitades",
                "MIO": {
                    "TSt": "Ronda 10",
                    "Loc": "O'Connor Enclosed (Canberra)",
                },
                "MIS": [
                    {"K": 9, "V": "+15ºC"},
                    {"K": 21, "V": "Bruma"},
                    {"K": 27, "V": "65"},
                ],
                "SG": [
                    {"I": 718933778, "N": 192528, "EC": 247, "P": 1, "PN": "1.ª mitad", "MG": 718933777},
                ],
            }
        ],
    },
}

GAME_PAYLOAD = {
    "Id": 0,
    "Success": True,
    "Error": "",
    "ErrorCode": 0,
    "Guid": "",
    "Value": {
        "I": 718933777,
        "O1": "Paris Saint-Germain",
        "O2": "Arsenal",
        "O1I": 1,
        "O2I": 2,
        "L": "Liga de Campeones de la UEFA",
        "LI": 118587,
        "SI": 1,
        "CN": "Europa",
        "S": 1780156800,
        "MEC": [
            {"MT": 2, "EC": 3, "N": "Populares"},
            {"MT": 3, "EC": 2, "N": "Total"},
            {"MT": 4, "EC": 2, "N": "Hándicap"},
        ],
        "E": [
            {"T": 1, "G": 1, "C": 2.357},
            {"T": 2, "G": 1, "C": 3.39},
            {"T": 3, "G": 1, "C": 3.37},
            {"T": 7, "G": 2, "P": -1, "C": 3.48},
            {"T": 8, "G": 2, "P": 1, "C": 1.25},
            {"T": 9, "G": 17, "P": 2.5, "C": 2.05},
            {"T": 10, "G": 17, "P": 2.5, "C": 1.896},
        ],
    },
}


class OneXBetParsingTests(unittest.TestCase):
    def test_detect_endpoint_name(self) -> None:
        url = "https://1xbetarge.com/service-api/LineFeed/GetGameZip?id=718933777&lng=es"
        self.assertEqual(xbet_parsing.detect_endpoint_name(url), "GetGameZip")

    def test_parse_sports_short_value(self) -> None:
        parsed = xbet_parsing.parse_sports_short_value(SPORTS_SHORT_PAYLOAD["Value"])
        self.assertEqual(parsed[0]["sport_id"], "1")
        self.assertEqual(parsed[0]["leagues"][0]["league_id"], "118587")

    def test_parse_champ_games_value(self) -> None:
        games = xbet_parsing.parse_champ_games_value(CHAMP_PAYLOAD["Value"])
        self.assertEqual(games[0]["external_event_id"], "718933777")
        self.assertEqual(games[0]["home"], "Paris Saint-Germain")
        self.assertEqual(games[0]["subgames"][0]["market_count"], 247)
        self.assertEqual(games[0]["metadata"]["round"], "Ronda 10")
        self.assertEqual(games[0]["metadata"]["venue"], "O'Connor Enclosed (Canberra)")
        self.assertEqual(games[0]["metadata"]["weather"]["temperature"], "+15ºC")

    def test_build_compact_markets_from_game_detail(self) -> None:
        markets = xbet_parsing.build_compact_markets_from_game_detail(GAME_PAYLOAD["Value"])
        self.assertEqual(markets["1x2"]["1"], 2.357)
        self.assertEqual(markets["1x2"]["X"], 3.39)
        self.assertEqual(markets["1x2"]["2"], 3.37)
        self.assertEqual(markets["handicap"][0]["line"], -1.0)
        self.assertEqual(markets["handicap"][0]["home"], 3.48)
        self.assertEqual(markets["handicap"][0]["away"], 1.25)
        self.assertEqual(markets["totals"][0]["line"], 2.5)
        self.assertEqual(markets["totals"][0]["over"], 2.05)
        self.assertEqual(markets["totals"][0]["under"], 1.896)

    def test_build_compact_game_record_is_json_serializable(self) -> None:
        game_stub = xbet_parsing.parse_champ_games_value(CHAMP_PAYLOAD["Value"])[0]
        record = xbet_parsing.build_compact_game_record(game_stub, detail_value=GAME_PAYLOAD["Value"])
        self.assertEqual(record["external_event_id"], "718933777")
        self.assertEqual(record["league"], "Liga de Campeones de la UEFA")
        self.assertTrue(record["odds_1x2"])
        self.assertTrue(record["has_game_detail"])
        json.dumps(record, ensure_ascii=False)

    def test_build_fixture_only_record_keeps_fixture_metadata(self) -> None:
        game_stub = xbet_parsing.parse_champ_games_value(CHAMP_PAYLOAD["Value"])[0]
        record = xbet_parsing.build_compact_game_record(game_stub, detail_value=None)
        self.assertEqual(record["external_event_id"], "718933777")
        self.assertFalse(record["has_game_detail"])
        self.assertEqual(record["metadata"]["round"], "Ronda 10")
        self.assertEqual(record["subgames"][0]["period_name"], "1.ª mitad")
        self.assertEqual(record["markets_json"]["raw_market_count"], 0)

    def test_build_tracking_odds_payload_is_minimal_and_serializable(self) -> None:
        game_stub = xbet_parsing.parse_champ_games_value(CHAMP_PAYLOAD["Value"])[0]
        record = xbet_parsing.build_compact_game_record(game_stub, detail_value=GAME_PAYLOAD["Value"])
        payload = xbet_parsing.build_tracking_odds_payload(
            [record],
            source={"bookmaker": "spinbetter"},
            generated_at_utc="2026-05-22T00:00:00+00:00",
        )

        match = payload["matches"][0]
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(match["home"], "Paris Saint-Germain")
        self.assertEqual(match["away"], "Arsenal")
        self.assertEqual(match["kickoff"]["date_utc"], "2026-05-30")
        self.assertEqual(match["kickoff"]["time_utc"], "16:00")
        self.assertEqual(match["odds_1x2"], {"1": 2.357, "X": 3.39, "2": 3.37})
        self.assertTrue(match["handicap"])
        self.assertTrue(match["totals"])
        self.assertEqual(match["market_status"]["missing"], [])
        self.assertEqual(payload["summary"]["matches_with_all_required_markets"], 1)
        json.dumps(payload, ensure_ascii=False)

    def test_build_tracking_odds_payload_marks_missing_markets(self) -> None:
        game_stub = xbet_parsing.parse_champ_games_value(CHAMP_PAYLOAD["Value"])[0]
        fixture_only_record = xbet_parsing.build_compact_game_record(game_stub, detail_value=None)
        payload = xbet_parsing.build_tracking_odds_payload([fixture_only_record])
        match = payload["matches"][0]

        self.assertEqual(match["market_status"]["missing"], ["1x2", "handicap", "totals"])
        self.assertEqual(payload["summary"]["matches_with_all_required_markets"], 0)

    def test_build_probe_index(self) -> None:
        index = xbet_parsing.build_probe_index(
            [
                {
                    "endpoint_name": "GetSportsShortZip",
                    "client": "httpx",
                    "status": 200,
                    "url": "https://1xbetarge.com/service-api/LineFeed/GetSportsShortZip?sports=1",
                    "value_shape": {"type": "list"},
                },
                {
                    "endpoint_name": "GetSportsShortZip",
                    "client": "curl_cffi",
                    "status": 200,
                    "url": "https://1xbetarge.com/service-api/LineFeed/GetSportsShortZip?sports=1",
                    "value_shape": {"type": "list"},
                },
            ]
        )
        self.assertEqual(index["GetSportsShortZip"]["count"], 2)
        self.assertEqual(index["GetSportsShortZip"]["example_url"], "https://1xbetarge.com/service-api/LineFeed/GetSportsShortZip?sports=1")

    def test_spinbetter_champ_url_can_omit_sport_param(self) -> None:
        url = extract_1xbet_league.build_champ_url(
            base_url="spinbetter.com",
            sport_id="1",
            champ_id="2872359",
            lng="es",
            include_sport=False,
        )
        self.assertEqual(
            url,
            "https://spinbetter.com/service-api/LineFeed/GetChampZip?champ=2872359&lng=es",
        )


if __name__ == "__main__":
    unittest.main()

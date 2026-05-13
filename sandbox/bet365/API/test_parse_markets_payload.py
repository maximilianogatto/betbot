from __future__ import annotations

import unittest
from pathlib import Path

from parse_markets_payload import (
    build_league_1x2_projection,
    build_event_url,
    detect_payload_kind,
    extract_sportradar_url,
    flatten_markets,
    looks_like_coupon_payload,
    looks_like_markets_payload,
    parse_bet365_payload_file,
    parse_coupon_payload_file,
    parse_markets_payload_file,
    parse_markets_payload_text,
)

SMALL_FIXTURE = (
    "F|CL;ID=1;IT=#AC#B1#C1#D1002#E120757998#G40#;PV=matchmarketscontentapi_0;"
    "|EV;ID=E1;L3=SPANISH-PRIMERA;TB=Fútbol,#AS#B1#¬Spanish Primera ,#ABM#B1#C1#D1002#E120757998#G40#;"
    "|MG;ID=40;SY=cmx;"
    "|MA;MA=40;ID=M40;NA= ;FI=193003384;"
    "|PA;ID=PC193003384;NA=Elche;N2=CD Alaves;FI=193003384;BC=20260509130000;PD=#AC#B1#C1#D8#E193003384#F3#I1#;"
    "|MA;MA=40;ID=M40;NA=1;FI=193003384;"
    "|PA;ID=193003384-1;FI=193003384;OD=23/20;"
    "|MA;MA=40;ID=M40;NA=X;FI=193003384;"
    "|PA;ID=193003384-X;FI=193003384;OD=2/1;"
    "|MA;MA=40;ID=M40;NA=2;FI=193003384;"
    "|PA;ID=193003384-2;FI=193003384;DO=3.2;OD=11/5;"
    "|MG;ID=LMAB;CC=Spanish Primera;ED=Spain La Liga ;|"
)


class ParseMarketsPayloadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.base_dir = Path(__file__).resolve().parent

    def test_parse_small_fixture(self) -> None:
        parsed = parse_markets_payload_text(SMALL_FIXTURE, host="www.bet365.es")

        self.assertEqual(parsed["competition"]["topic"], "#AC#B1#C1#D1002#E120757998#G40#")
        self.assertEqual(parsed["competition"]["name"], "Spanish Primera")
        self.assertEqual(len(parsed["matches"]), 1)

        match = parsed["matches"][0]
        self.assertEqual(match["fixture_id"], "193003384")
        self.assertEqual(match["home"], "Elche")
        self.assertEqual(match["away"], "CD Alaves")
        self.assertEqual(match["start_raw"], "20260509130000")
        self.assertEqual(match["event_pd"], "#AC#B1#C1#D8#E193003384#F3#I1#")
        self.assertEqual(
            match["event_url"],
            "https://www.bet365.es/#/AC/B1/C1/D8/E193003384/F3/I1/",
        )
        self.assertEqual(
            match["odds_1x2"],
            {"1": 2.15, "X": 3.0, "2": 3.2},
        )
        self.assertEqual(
            match["odds_1x2_fractional"],
            {"1": "23/20", "X": "2/1", "2": "11/5"},
        )

    def test_detects_markets_payload_shape(self) -> None:
        self.assertTrue(looks_like_markets_payload(SMALL_FIXTURE))
        self.assertEqual(detect_payload_kind(SMALL_FIXTURE), "markets")

    def test_parse_real_output_market_fixture(self) -> None:
        fixture_path = self.base_dir / "output_market.txt"
        parsed = parse_markets_payload_file(fixture_path, host="www.bet365.es")

        self.assertEqual(parsed["competition"]["name"], "Spanish Primera")
        self.assertEqual(parsed["competition"]["topic"], "#AC#B1#C1#D1002#E120757998#G40#")
        self.assertGreaterEqual(len(parsed["events"]), 10)
        self.assertGreaterEqual(len(parsed["matches"]), 10)

        target = next(
            (event for event in parsed["events"] if event["fixture_id"] == "193003384"),
            None,
        )
        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target["home"], "Elche")
        self.assertEqual(target["away"], "CD Alaves")
        self.assertEqual(target["name"], "Elche v CD Alaves")
        self.assertEqual(target["event_token"], "E193003384")
        self.assertEqual(target["event_it"], "ACB1D8E193003384F3I0")
        self.assertEqual(target["event_pd"], "#AC#B1#C1#D8#E193003384#F3#I1#")
        self.assertEqual(target["markets"][0]["market_id"], "40")
        full_time = {selection["participant_code"]: selection for selection in target["markets"][0]["selections"]}
        self.assertEqual(full_time["1"]["odds_fractional"], "23/20")
        self.assertEqual(full_time["1"]["odds_decimal"], 2.15)
        self.assertEqual(full_time["X"]["odds_fractional"], "2/1")
        self.assertEqual(full_time["X"]["odds_decimal"], 3.0)
        self.assertEqual(full_time["2"]["odds_fractional"], "11/5")
        self.assertEqual(full_time["2"]["odds_decimal"], 3.2)
        self.assertEqual(
            target["sportradar_url"],
            "https://s5.sir.sportradar.com/bet365/en/match/61624628",
        )
        self.assertEqual(
            target["event_url"],
            "https://www.bet365.es/#/AC/B1/C1/D8/E193003384/F3/I1/",
        )
        self.assertEqual(target["stats_identifier"], "1502-1")
        self.assertEqual(target["source_meta"]["league_lt"], "#LT#B1#C1#D1002#E120757998#F0")

        projection = build_league_1x2_projection(
            parsed,
            league_url="https://www.bet365.es/#/AC/B1/C1/D1002/E120757998/G40/",
        )
        self.assertGreaterEqual(len(projection["events"]), 10)
        projected_target = next(
            (event for event in projection["events"] if event["fixture_id"] == "193003384"),
            None,
        )
        self.assertIsNotNone(projected_target)
        assert projected_target is not None
        self.assertEqual(projected_target["home"], "Elche")
        self.assertEqual(projected_target["away"], "CD Alaves")
        self.assertEqual(
            projected_target["full_time_result"],
            [
                {"name": "Elche", "odds": "23/20"},
                {"name": "Draw", "odds": "2/1"},
                {"name": "CD Alaves", "odds": "11/5"},
            ],
        )

    def test_parse_real_output_coupon_fixture(self) -> None:
        fixture_path = self.base_dir / "output_coupon.txt"
        parsed = parse_coupon_payload_file(fixture_path, host="www.bet365.es")

        self.assertTrue(looks_like_coupon_payload(fixture_path.read_text(encoding="utf-8")))
        self.assertEqual(detect_payload_kind(fixture_path.read_text(encoding="utf-8")), "coupon")
        self.assertEqual(parsed["competition"]["name"], "Spanish Primera")
        self.assertEqual(parsed["competition"]["topic"], "#AC#B1#C1#D8#E193003384#F3#I1#")
        self.assertEqual(len(parsed["events"]), 1)

        event = parsed["events"][0]
        self.assertEqual(event["fixture_id"], "193003384")
        self.assertEqual(event["event_id"], "193003384")
        self.assertEqual(event["event_token"], "E193003384")
        self.assertEqual(event["home"], "Elche")
        self.assertEqual(event["away"], "CD Alaves")
        self.assertEqual(event["event_url"], "https://www.bet365.es/#/AC/B1/C1/D8/E193003384/F3/I1/")

        markets = {market["market_id"]: market for market in event["markets"]}
        self.assertIn("40", markets)
        self.assertIn("981", markets)
        self.assertIn("10150", markets)

        full_time = {selection["name"]: selection for selection in markets["40"]["selections"]}
        self.assertEqual(full_time["Elche"]["odds_fractional"], "23/20")
        self.assertEqual(full_time["Elche"]["odds_decimal"], 2.15)
        self.assertEqual(full_time["Draw"]["odds_fractional"], "2/1")
        self.assertEqual(full_time["CD Alaves"]["odds_fractional"], "11/5")

        goals = {selection["name"]: selection for selection in markets["981"]["selections"]}
        self.assertEqual(goals["Over 2.5"]["odds_fractional"], "10/11")
        self.assertEqual(goals["Under 2.5"]["odds_fractional"], "10/11")

        btts = {selection["name"]: selection for selection in markets["10150"]["selections"]}
        self.assertEqual(btts["Yes"]["odds_fractional"], "7/10")
        self.assertEqual(btts["No"]["odds_fractional"], "21/20")

        flattened = flatten_markets(parsed["events"])
        self.assertGreaterEqual(len(flattened), 3)

    def test_auto_parse_real_output_coupon_fixture(self) -> None:
        fixture_path = self.base_dir / "output_coupon.txt"
        parsed = parse_bet365_payload_file(fixture_path, host="www.bet365.es")
        self.assertEqual(parsed["payload_type"], "coupon")
        self.assertEqual(parsed["events"][0]["fixture_id"], "193003384")

    def test_helpers(self) -> None:
        self.assertEqual(
            build_event_url("#AC#B1#C1#D8#E193003384#F3#I1#", host="www.bet365.es"),
            "https://www.bet365.es/#/AC/B1/C1/D8/E193003384/F3/I1/",
        )
        self.assertEqual(
            extract_sportradar_url(
                "puw~https://s5.sir.sportradar.com/bet365/en/match/61624628~Bet365Stats~Height=700"
            ),
            "https://s5.sir.sportradar.com/bet365/en/match/61624628",
        )


if __name__ == "__main__":
    unittest.main()

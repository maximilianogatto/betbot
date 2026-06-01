from __future__ import annotations

import unittest
from pathlib import Path

from extractors.bet365.playwright_asian import (
    extract_sportradar_url,
    parse_datetime,
    parse_asian_payload,
    parse_league_payload,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEAGUE_FIXTURE = PROJECT_ROOT / "sandbox" / "bet365" / "bet365_capture_20260512-122415" / "raw_league.txt"
ASIAN_FIXTURE = (
    PROJECT_ROOT / "sandbox" / "bet365" / "bet365_capture_20260512-122415" / "raw_asian_193003460.txt"
)


class Bet365PlaywrightAsianParserTests(unittest.TestCase):
    def test_parse_league_payload_extracts_matches_and_1x2(self) -> None:
        parsed = parse_league_payload(
            LEAGUE_FIXTURE.read_text(encoding="utf-8"),
            host="www.bet365.bet.ar",
        )

        self.assertEqual(parsed["league_name"], "Spanish Primera")
        self.assertGreaterEqual(len(parsed["matches"]), 20)

        real_madrid_match = next(
            match for match in parsed["matches"] if match["fixture_id"] == "193003460"
        )
        self.assertEqual(real_madrid_match["home"], "Real Madrid")
        self.assertEqual(real_madrid_match["away"], "Real Oviedo")
        self.assertEqual(
            real_madrid_match["event_url"],
            "https://www.bet365.bet.ar/#/AC/B1/C1/D8/E193003460/F3/I1/",
        )
        self.assertAlmostEqual(real_madrid_match["markets_payload"]["1x2"]["home"], 1.222222)
        self.assertAlmostEqual(real_madrid_match["markets_payload"]["1x2"]["draw"], 7.0)
        self.assertAlmostEqual(real_madrid_match["markets_payload"]["1x2"]["away"], 11.0)

    def test_parse_league_payload_extracts_stats_url(self) -> None:
        parsed = parse_league_payload(
            LEAGUE_FIXTURE.read_text(encoding="utf-8"),
            host="www.bet365.bet.ar",
        )

        atletico_match = next(
            match for match in parsed["matches"] if match["fixture_id"] == "193003456"
        )
        self.assertEqual(
            atletico_match["stats_url"],
            "https://s5.sir.sportradar.com/bet365/es/match/61624650",
        )

    def test_extract_sportradar_url_handles_present_and_missing_values(self) -> None:
        self.assertEqual(
            extract_sportradar_url(
                "puw~https://s5.sir.sportradar.com/bet365/en/match/61624650~Bet365Stats~Height=700"
            ),
            "https://s5.sir.sportradar.com/bet365/en/match/61624650",
        )
        self.assertIsNone(extract_sportradar_url(None))
        self.assertIsNone(extract_sportradar_url("puw~https://example.com/foo~OtherStats~Height=700"))

    def test_parse_datetime_uses_bet365_site_timezone(self) -> None:
        date_label, time_label, scheduled_at = parse_datetime(
            "20260512190000",
            host="www.bet365.bet.ar",
        )

        self.assertEqual(date_label, "2026-05-12")
        self.assertEqual(time_label, "19:00")
        self.assertEqual(scheduled_at, "2026-05-12T22:00:00+00:00")

    def test_parse_asian_payload_extracts_primary_markets(self) -> None:
        parsed = parse_asian_payload(
            ASIAN_FIXTURE.read_text(encoding="utf-8"),
            "193003460",
            include_alternative_markets=False,
        )

        self.assertEqual(parsed["event"]["event_id"], "193003460")
        self.assertEqual(parsed["event"]["home"], "Real Madrid")
        self.assertEqual(parsed["event"]["away"], "Real Oviedo")

        asian_handicap = parsed["markets_payload"]["asian_handicap"]
        self.assertEqual(asian_handicap["market_id"], "938")
        self.assertEqual(asian_handicap["market_name"], "Asian Handicap")
        self.assertEqual(
            asian_handicap["selections"],
            [
                {"selection": "Real Madrid", "line": "-1.5, -2.0", "odds": 1.875},
                {"selection": "Real Oviedo", "line": "1.5, 2.0", "odds": 1.975},
            ],
        )

        goal_line = parsed["markets_payload"]["goal_line"]
        self.assertEqual(goal_line["market_id"], "10143")
        self.assertEqual(goal_line["market_name"], "Goal Line")
        self.assertEqual(
            goal_line["selections"],
            [
                {"selection": "Over", "line": "3.0, 3.5", "odds": 1.85},
                {"selection": "Under", "line": "3.0, 3.5", "odds": 2.0},
            ],
        )


if __name__ == "__main__":
    unittest.main()

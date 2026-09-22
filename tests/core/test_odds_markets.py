"""Explotar el markets_payload archivado a filas por mercado/línea/lado."""
from __future__ import annotations

import unittest

from core.odds_markets import find_market, flatten_markets, market_period, market_type, selection_side

MARKETS = {
    "1x2": {"home": 1.25, "draw": 6.0, "away": 11.0},
    "asian_handicap": {"market_name": "Asian Handicap", "selections": [
        {"selection": "Darwin Olympic W", "line": "-2.5", "odds": 1.66},
        {"selection": "Palmerston Rovers W", "line": "+2.5", "odds": 2.10}]},
    "goal_line": {"market_name": "Goal Line", "selections": [
        {"selection": "Over", "line": "4.5", "odds": 1.90},
        {"selection": "Under", "line": "4.5", "odds": 1.85}]},
    "alternative_markets": [
        {"market_name": "1st Half Asian Handicap", "selections": [
            {"selection": "Darwin Olympic W", "line": "-1.5", "odds": 1.70},
            {"selection": "Palmerston Rovers W", "line": "1.5", "odds": 2.05}]}],
}


class FlattenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = flatten_markets(MARKETS, home="Darwin Olympic W", away="Palmerston Rovers W")

    def test_every_market_family(self) -> None:
        index = {(r["market_type"], r["market_period"], r["line"], r["side"]): r["odds"] for r in self.rows}
        self.assertEqual(index[("1x2", "FT", None, "draw")], 6.0)
        self.assertEqual(index[("asian_handicap", "FT", -2.5, "home")], 1.66)
        self.assertEqual(index[("goal_line", "FT", 4.5, "over")], 1.90)
        # Los de primer tiempo llegan como alternativos y deben quedar en HT.
        self.assertEqual(index[("asian_handicap", "HT", -1.5, "home")], 1.70)

    def test_overround_pairs_handicap_by_inverted_line(self) -> None:
        home = find_market(self.rows, market_type="asian_handicap", side="home", line=-2.5)
        self.assertAlmostEqual(home["overround"], 1 / 1.66 + 1 / 2.10, places=4)
        one_x_two = find_market(self.rows, market_type="1x2", side="home")
        self.assertAlmostEqual(one_x_two["overround"], 1 / 1.25 + 1 / 6.0 + 1 / 11.0, places=4)

    def test_garbage_is_ignored(self) -> None:
        self.assertEqual(flatten_markets(None, home="a", away="b"), [])
        self.assertEqual(flatten_markets({"asian_handicap": "x"}, home="a", away="b"), [])


class NamingTests(unittest.TestCase):
    def test_period_and_type(self) -> None:
        self.assertEqual(market_period("1st Half Goal Line"), "HT")
        self.assertEqual(market_period("Hándicap 1ª parte"), "HT")
        self.assertEqual(market_period("Asian Handicap"), "FT")
        self.assertEqual(market_type("goal_line"), "goal_line")
        self.assertEqual(market_type("Asian Handicap"), "asian_handicap")

    def test_sides(self) -> None:
        self.assertEqual(selection_side("Darwin", home="Darwin", away="Palmerston"), "home")
        self.assertEqual(selection_side("Palmerston", home="Darwin", away="Palmerston"), "away")
        for text, side in (("Over", "over"), ("Menos", "under"), ("X", "draw"), ("Sí", "yes")):
            self.assertEqual(selection_side(text, home="Darwin", away="Palmerston"), side)


if __name__ == "__main__":
    unittest.main()

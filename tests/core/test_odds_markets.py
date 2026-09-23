"""Explotar el markets_payload archivado a filas por mercado/línea/lado."""
from __future__ import annotations

import unittest

from core.odds_markets import (
    attach_overround, find_market, flatten_markets, market_period, market_type, selection_side,
)

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


class InvalidOddsTests(unittest.TestCase):
    """Algunos extractores guardan cuota 0 con el mercado suspendido (VPS, 2026-09-23)."""

    SUSPENDED = {
        "1x2": {"home": 0, "draw": 6.0, "away": 11.0},
        "asian_handicap": {"market_name": "Asian Handicap", "selections": [
            {"selection": "Darwin Olympic W", "line": "-2.5", "odds": 0.0},
            {"selection": "Palmerston Rovers W", "line": "+2.5", "odds": 2.10},
            {"selection": "Darwin Olympic W", "line": "0", "odds": 1.30},
            {"selection": "Palmerston Rovers W", "line": "0", "odds": 3.40}]},
        "goal_line": {"market_name": "Goal Line", "selections": [
            {"selection": "Over", "line": "4.5", "odds": "-"},
            {"selection": "Under", "line": "4.5", "odds": 1.0}]},
        "alternative_markets": [
            {"market_name": "1st Half Asian Handicap", "selections": [
                {"selection": "Darwin Olympic W", "line": "-1.5", "odds": "0"},
                {"selection": "Palmerston Rovers W", "line": "1.5", "odds": 2.05}]}],
    }

    def setUp(self) -> None:
        self.rows = flatten_markets(self.SUSPENDED, home="Darwin Olympic W", away="Palmerston Rovers W")
        self.index = {(r["market_type"], r["market_period"], r["line"], r["side"]): r for r in self.rows}

    def test_zero_prices_are_dropped_and_valid_ones_kept(self) -> None:
        self.assertNotIn(("1x2", "FT", None, "home"), self.index)
        self.assertEqual(self.index[("1x2", "FT", None, "draw")]["odds"], 6.0)
        self.assertNotIn(("asian_handicap", "FT", -2.5, "home"), self.index)
        self.assertEqual(self.index[("asian_handicap", "FT", 2.5, "away")]["odds"], 2.10)
        self.assertNotIn(("asian_handicap", "HT", -1.5, "home"), self.index)
        self.assertEqual(self.index[("asian_handicap", "HT", 1.5, "away")]["odds"], 2.05)

    def test_non_numeric_and_even_prices_are_dropped(self) -> None:
        self.assertFalse(any(r["market_type"] == "goal_line" for r in self.rows))

    def test_zero_line_is_still_a_line(self) -> None:
        home = self.index[("asian_handicap", "FT", 0.0, "home")]
        self.assertEqual(home["odds"], 1.30)
        self.assertAlmostEqual(home["overround"], 1 / 1.30 + 1 / 3.40, places=4)

    def test_incomplete_markets_get_no_overround(self) -> None:
        self.assertNotIn("overround", self.index[("1x2", "FT", None, "draw")])
        self.assertNotIn("overround", self.index[("asian_handicap", "FT", 2.5, "away")])

    def test_attach_overround_tolerates_non_positive_odds(self) -> None:
        rows = [{"market_type": "1x2", "market_period": "FT", "line": None, "side": s, "odds": o}
                for s, o in (("home", 0.0), ("draw", 3.5), ("away", 2.2))]
        attach_overround(rows)
        self.assertFalse(any("overround" in r for r in rows))


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

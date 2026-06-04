from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from monitors.peak_model import (
    LeagueModel,
    PastMatch,
    PeakParams,
    TeamStats,
    data_gate,
    expected_supremacy,
    h2h_signal,
    league_rates,
    logistic,
    position_signal,
    score_prematch,
    transitivity_signal,
)

_NOW = datetime(2026, 6, 4, tzinfo=timezone.utc)


def _team(tid, pos, gfh, gah, gfa, gaa, ph=5, pa=5):
    return TeamStats(
        team_id=tid, name=tid, position=pos,
        played=ph + pa, played_home=ph, played_away=pa,
        gf_home=gfh, ga_home=gah, gf_away=gfa, ga_away=gaa,
    )


def _league(matches=None):
    teams = {
        "H": _team("H", 1, 15, 5, 10, 8),   # strong: scores at home, solid away
        "A": _team("A", 4, 5, 15, 2, 18),   # weak: barely scores away, leaks goals
        "M1": _team("M1", 2, 10, 10, 7, 10),
        "M2": _team("M2", 3, 8, 8, 6, 9),
    }
    return LeagueModel(name="Test", teams=teams, matches=matches or [])


class HelperTests(unittest.TestCase):
    def test_logistic_gate(self) -> None:
        self.assertLess(logistic(2, midpoint=5), 0.1)
        self.assertGreater(logistic(8, midpoint=5), 0.9)
        self.assertAlmostEqual(logistic(5, midpoint=5), 0.5, places=6)

    def test_data_gate_suppresses_small_sample(self) -> None:
        params = PeakParams()
        few = _team("x", 1, 1, 1, 1, 1, ph=1, pa=1)   # played=2
        many = _team("y", 1, 1, 1, 1, 1, ph=8, pa=8)  # played=16
        self.assertLess(data_gate(few, few, params), 0.2)
        self.assertGreater(data_gate(many, many, params), 0.9)


class FactorTests(unittest.TestCase):
    def test_position_signal_direction(self) -> None:
        league = _league()
        # Home pos 1, away pos 4 -> positive (home favoured).
        self.assertGreater(position_signal(league.teams["H"], league.teams["A"], 4), 0)
        self.assertLess(position_signal(league.teams["A"], league.teams["H"], 4), 0)

    def test_expected_supremacy_favours_strong_home(self) -> None:
        league = _league()
        rates = league_rates(league)
        s = expected_supremacy(league.teams["H"], league.teams["A"], rates, PeakParams())
        self.assertGreater(s, 0)
        # Reverse fixture: weak home vs strong away -> negative supremacy.
        s_rev = expected_supremacy(league.teams["A"], league.teams["H"], rates, PeakParams())
        self.assertLess(s_rev, 0)

    def test_h2h_recency_and_direction(self) -> None:
        recent = (_NOW - timedelta(days=10)).strftime("%Y-%m-%d")
        old = (_NOW - timedelta(days=900)).strftime("%Y-%m-%d")
        matches = [
            PastMatch(date=recent, home_id="H", away_id="A", gh=4, ga=0),
            PastMatch(date=old, home_id="A", away_id="H", gh=3, ga=0),  # old A win, decayed
        ]
        signal, n = h2h_signal("H", "A", matches, _NOW, PeakParams())
        self.assertEqual(n, 2)
        self.assertGreater(signal, 0)  # recent home blowout dominates

    def test_h2h_red_card_discount(self) -> None:
        d = (_NOW - timedelta(days=10)).strftime("%Y-%m-%d")
        base = [PastMatch(date=d, home_id="H", away_id="A", gh=3, ga=0)]
        with_red = [PastMatch(date=d, home_id="H", away_id="A", gh=3, ga=0, away_red=True, has_red_info=True)]
        s_base, _ = h2h_signal("H", "A", base, _NOW, PeakParams())
        s_red, _ = h2h_signal("H", "A", with_red, _NOW, PeakParams())
        # Single match: ratio identical, but the weighted contribution is downscaled
        # only relative to other games. Here verify red flag does not flip the sign
        # and the function stays bounded.
        self.assertGreaterEqual(s_base, s_red - 1e-9)
        self.assertTrue(-1.0 <= s_red <= 1.0)

    def test_transitivity_common_opponent(self) -> None:
        d = (_NOW - timedelta(days=20)).strftime("%Y-%m-%d")
        matches = [
            PastMatch(date=d, home_id="H", away_id="M1", gh=3, ga=0),   # H crushed M1
            PastMatch(date=d, home_id="M1", away_id="A", gh=3, ga=0),   # M1 crushed A
        ]
        signal, n = transitivity_signal("H", "A", matches, _NOW, PeakParams())
        self.assertEqual(n, 1)
        self.assertGreater(signal, 0)  # H >> M1 >> A


class ScoreTests(unittest.TestCase):
    def test_clear_mismatch_high_score(self) -> None:
        recent = (_NOW - timedelta(days=15)).strftime("%Y-%m-%d")
        matches = [
            PastMatch(date=recent, home_id="H", away_id="A", gh=4, ga=0),
            PastMatch(date=recent, home_id="H", away_id="M1", gh=2, ga=0),
            PastMatch(date=recent, home_id="M1", away_id="A", gh=3, ga=1),
        ]
        league = _league(matches)
        result = score_prematch("H", "A", league, now=_NOW)
        self.assertEqual(result.favorite_id, "H")
        self.assertGreater(result.score, 6.0)
        self.assertTrue(1.0 <= result.score <= 10.0)

    def test_even_match_low_score(self) -> None:
        league = _league()
        # M1 vs M2 are near league average and have no history -> low magnitude.
        result = score_prematch("M1", "M2", league, now=_NOW)
        self.assertLess(result.score, 4.0)

    def test_score_bounds_and_components(self) -> None:
        league = _league()
        result = score_prematch("H", "A", league, now=_NOW)
        self.assertTrue(1.0 <= result.score <= 10.0)
        for key in ("data_gate", "supremacy", "position", "h2h", "transitivity", "edge"):
            self.assertIn(key, result.components)

    def test_missing_team_is_safe(self) -> None:
        league = _league()
        result = score_prematch("UNKNOWN1", "UNKNOWN2", league, now=_NOW)
        self.assertTrue(1.0 <= result.score <= 10.0)
        self.assertIsNone(result.favorite_id)


if __name__ == "__main__":
    unittest.main()

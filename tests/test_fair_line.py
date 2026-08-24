"""Tests de core.fair_line — matemática pura de la línea justa.

Corre en el venv del bot (sin numpy). Los valores de referencia se cruzaron
contra la matemática de research (score_matrix/probs_1x2 con ρ=0, maxg=10).
"""

from __future__ import annotations

import unittest

from core.fair_line import fair_line, _side_pmf


class FairLineTests(unittest.TestCase):
    def test_cross_check_research_values(self) -> None:
        fl = fair_line(1.4, 0.9)
        self.assertAlmostEqual(fl.p_home, 0.4859, places=4)
        self.assertAlmostEqual(fl.p_draw, 0.2724, places=4)
        self.assertAlmostEqual(fl.p_away, 0.2417, places=4)
        self.assertAlmostEqual(fl.p_over25, 0.4040, places=4)
        self.assertAlmostEqual(fl.p_btts, 0.4471, places=4)

    def test_probabilities_sum_to_one(self) -> None:
        for lh, la in [(0.3, 0.3), (2.5, 0.4), (1.0, 1.0), (0.01, 3.0)]:
            fl = fair_line(lh, la)
            self.assertAlmostEqual(fl.p_home + fl.p_draw + fl.p_away, 1.0, places=9)
            self.assertAlmostEqual(fl.p_over25 + fl.p_under25, 1.0, places=9)

    def test_side_pmf_sums_to_one_with_tail(self) -> None:
        for lam in [0.0, 0.5, 1.9, 12.0]:  # 12 > max_goals: la cola absorbe
            self.assertAlmostEqual(sum(_side_pmf(lam)), 1.0, places=9)

    def test_symmetry_equal_lambdas(self) -> None:
        fl = fair_line(1.3, 1.3)
        self.assertAlmostEqual(fl.p_home, fl.p_away, places=9)
        self.assertAlmostEqual(fl.fair_handicap, 0.0, places=9)
        self.assertAlmostEqual(fl.expected_supremacy, 0.0, places=9)

    def test_supremacy_and_totals(self) -> None:
        fl = fair_line(2.0, 0.8)
        self.assertAlmostEqual(fl.expected_supremacy, 1.2, places=9)
        self.assertAlmostEqual(fl.expected_total_goals, 2.8, places=9)
        self.assertGreater(fl.p_home, fl.p_away)          # local mucho más fuerte
        self.assertLessEqual(fl.fair_handicap, 0.0)       # local da hándicap

    def test_over25_monotonic_in_total_intensity(self) -> None:
        lows = fair_line(0.5, 0.5).p_over25
        mids = fair_line(1.3, 1.2).p_over25
        highs = fair_line(2.2, 1.9).p_over25
        self.assertLess(lows, mids)
        self.assertLess(mids, highs)

    def test_degenerate_zero_intensity(self) -> None:
        fl = fair_line(0.0, 0.0)   # sin goles esperados -> 0-0 seguro
        self.assertAlmostEqual(fl.p_draw, 1.0, places=9)
        self.assertAlmostEqual(fl.p_btts, 0.0, places=9)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import itertools
import unittest

from services.peak_backtest import (
    BacktestRow,
    build_model_at,
    run_backtest_on_matches,
    summarize,
)
from services.peak_model import PastMatch


def _gen_season(reps: int = 4) -> list[PastMatch]:
    """Deterministic league where strength A>B>C>D and the stronger side wins 2-0."""

    order = ["A", "B", "C", "D"]
    strength = {t: 4 - i for i, t in enumerate(order)}
    out: list[PastMatch] = []
    day = 1
    for rep in range(reps):
        for i, j in itertools.combinations(range(4), 2):
            h, a = (order[i], order[j]) if rep % 2 == 0 else (order[j], order[i])
            if strength[h] > strength[a]:
                gh, ga = 2, 0
            elif strength[h] < strength[a]:
                gh, ga = 0, 2
            else:
                gh, ga = 1, 1
            out.append(PastMatch(date=f"2026-03-{day:02d}", home_id=h, away_id=a, gh=gh, ga=ga))
            day += 1
    return out


class BuildModelAtTests(unittest.TestCase):
    def test_excludes_future_and_self(self) -> None:
        matches = [
            PastMatch(date="2026-03-01", home_id="A", away_id="B", gh=2, ga=0),
            PastMatch(date="2026-03-05", home_id="A", away_id="C", gh=3, ga=0),
            PastMatch(date="2026-03-10", home_id="B", away_id="C", gh=1, ga=1),  # cutoff
        ]
        model = build_model_at(matches, "2026-03-10")
        # Only the two earlier matches counted.
        self.assertEqual(len(model.matches), 2)
        self.assertEqual(model.teams["A"].played, 2)
        self.assertEqual(model.teams["A"].gf_home, 5)
        # A won twice -> position 1.
        self.assertEqual(model.teams["A"].position, 1)

    def test_positions_from_points(self) -> None:
        matches = [
            PastMatch(date="2026-03-01", home_id="A", away_id="B", gh=3, ga=0),
            PastMatch(date="2026-03-02", home_id="C", away_id="A", gh=0, ga=1),
        ]
        model = build_model_at(matches, "2026-03-09")
        self.assertEqual(model.teams["A"].position, 1)  # 6 pts
        self.assertTrue(model.teams["B"].position in (2, 3))
        self.assertTrue(model.teams["C"].position in (2, 3))


class RunBacktestTests(unittest.TestCase):
    def test_strong_team_predicted_and_wins(self) -> None:
        rows = run_backtest_on_matches(_gen_season(reps=4), min_history=3)
        self.assertGreater(len(rows), 0)
        with_fav = [r for r in rows if r.favorite_id is not None]
        self.assertGreater(len(with_fav), 0)
        # In a strictly ordered league the favourite should win the large majority.
        win_rate = sum(1 for r in with_fav if r.fav_result == "win") / len(with_fav)
        self.assertGreater(win_rate, 0.75)

    def test_min_history_filters_early_matches(self) -> None:
        rows_low = run_backtest_on_matches(_gen_season(reps=4), min_history=1)
        rows_high = run_backtest_on_matches(_gen_season(reps=4), min_history=6)
        self.assertGreater(len(rows_low), len(rows_high))


class SummarizeTests(unittest.TestCase):
    def test_metrics_and_factor_signal(self) -> None:
        rows = run_backtest_on_matches(_gen_season(reps=5), min_history=3)
        summary = summarize(rows)
        self.assertEqual(summary.n_total, len(rows))
        self.assertIsNotNone(summary.favorite_win_rate)
        self.assertGreater(summary.favorite_win_rate, 0.75)
        # Supremacy (home-oriented) should correlate positively with home margin.
        self.assertIsNotNone(summary.factor_corr["supremacy"])
        self.assertGreater(summary.factor_corr["supremacy"], 0.0)
        self.assertTrue(0.0 <= (summary.brier or 0) <= 1.0)

    def test_empty(self) -> None:
        summary = summarize([])
        self.assertEqual(summary.n_total, 0)
        self.assertIsNone(summary.favorite_win_rate)
        self.assertIsNone(summary.brier)


if __name__ == "__main__":
    unittest.main()

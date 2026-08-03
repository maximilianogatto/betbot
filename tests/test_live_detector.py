"""Tests de services.live_detector — Producto B (Python puro, venv del bot)."""

from __future__ import annotations

import unittest

from services.live_detector import (
    DetectorParams, LiveState, evaluate, implied_probs, remaining_intensities,
)


class LiveDetectorTests(unittest.TestCase):
    def test_implied_probs_remove_vig(self) -> None:
        q = implied_probs(2.0, 4.0, 4.0)  # margen presente
        self.assertAlmostEqual(sum(q), 1.0, places=9)
        self.assertGreater(q[0], q[1])    # local más probable

    def test_remaining_shrinks_with_time(self) -> None:
        p = DetectorParams()
        s0 = LiveState(minute=0, current_home=0, current_away=0)
        s60 = LiveState(minute=60, current_home=0, current_away=0)
        lh0, _ = remaining_intensities(2.0, 1.0, s0, p)
        lh60, _ = remaining_intensities(2.0, 1.0, s60, p)
        self.assertAlmostEqual(lh0, 2.0, places=9)
        self.assertAlmostEqual(lh60, 2.0 / 3, places=6)   # queda 1/3

    def test_red_card_shifts_intensity(self) -> None:
        p = DetectorParams()
        base = LiveState(minute=30, current_home=0, current_away=0)
        red = LiveState(minute=30, current_home=0, current_away=0, red_home=1)
        lh_b, la_b = remaining_intensities(1.5, 1.5, base, p)
        lh_r, la_r = remaining_intensities(1.5, 1.5, red, p)
        self.assertLess(lh_r, lh_b)     # local expulsado ataca menos
        self.assertGreater(la_r, la_b)  # visita ataca más

    def test_no_false_positive_on_stale_prematch(self) -> None:
        # local gran favorito pre-match, pero va 0-3 al min 60: NO debe alertar
        # a favor del local (el modelo ya ve que la visita gana).
        state = LiveState(minute=60, current_home=0, current_away=3, state_age_seconds=10)
        res = evaluate(2.6, 0.7, state, book_odds=(1.5, 4.0, 6.0))  # casa aún cree en local
        # el modelo favorece a la visita; si dispara, es a favor de A, no de H
        self.assertNotEqual(res.outcome, "H")
        self.assertGreater(res.live_line.p_away, 0.8)

    def test_fires_on_gross_error_fresh_state(self) -> None:
        # 0-0 al min 10, local fuerte; la casa lo precia como underdog -> grosero
        state = LiveState(minute=10, current_home=0, current_away=0, state_age_seconds=5)
        res = evaluate(2.4, 0.6, state, book_odds=(4.0, 3.8, 1.9), params=DetectorParams())
        self.assertTrue(res.fired)
        self.assertEqual(res.outcome, "H")
        self.assertGreater(res.edge, 0.30)

    def test_stale_state_blocks_alert(self) -> None:
        state = LiveState(minute=10, current_home=0, current_away=0, state_age_seconds=600)
        res = evaluate(2.4, 0.6, state, book_odds=(4.0, 3.8, 1.9))
        self.assertFalse(res.fired)
        self.assertIn("rancio", res.reason)

    def test_small_edge_does_not_fire(self) -> None:
        state = LiveState(minute=10, current_home=0, current_away=0, state_age_seconds=5)
        # cuotas casi coincidentes con el modelo -> sin error grosero
        res = evaluate(1.4, 1.3, state, book_odds=(2.5, 3.3, 2.7))
        self.assertFalse(res.fired)

    def test_near_end_does_not_fire(self) -> None:
        state = LiveState(minute=89, current_home=0, current_away=0, state_age_seconds=5)
        res = evaluate(2.4, 0.6, state, book_odds=(4.0, 3.8, 1.9))
        self.assertFalse(res.fired)
        self.assertIn("quedan", res.reason)


if __name__ == "__main__":
    unittest.main()

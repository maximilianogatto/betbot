"""Tests de services.prediction — el puente modelo→bot (Python puro, venv del bot)."""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from services.prediction import PredictionService, PredictionUnavailable


def _artifact() -> dict:
    return {
        "model_version": "test-v1",
        "trained_through": "2026-07-20",
        "leagues": {
            "XL": {
                "mu": 0.2, "home_adv": 0.25, "rho": 0.0, "n_matches": 100,
                "teams": {
                    "strong": {"atk": 0.4, "def": 0.3, "name": "Strong FC"},
                    "weak": {"atk": -0.3, "def": -0.2, "name": "Weak FC"},
                },
            }
        },
    }


class PredictionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(_artifact(), self.tmp)
        self.tmp.close()
        self.svc = PredictionService(self.tmp.name)

    def tearDown(self) -> None:
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_metadata(self) -> None:
        self.assertEqual(self.svc.model_version, "test-v1")
        self.assertEqual(self.svc.available_leagues(), ["XL"])

    def test_lambda_formula(self) -> None:
        pred, reason = self.svc.predict_or_reason("XL", "strong", "weak")
        self.assertEqual(reason, "")
        exp_lh = math.exp(0.2 + 0.25 + 0.4 - (-0.2))
        exp_la = math.exp(0.2 + (-0.3) - 0.3)
        self.assertAlmostEqual(pred.line.lam_home, exp_lh, places=6)
        self.assertAlmostEqual(pred.line.lam_away, exp_la, places=6)
        self.assertGreater(pred.line.p_home, pred.line.p_away)   # local fuerte
        self.assertLess(pred.line.fair_handicap, 0.0)            # da hándicap
        self.assertEqual(pred.model_version, "test-v1")

    def test_league_not_in_fit(self) -> None:
        pred, reason = self.svc.predict_or_reason("EPL", "strong", "weak")
        self.assertIsNone(pred)
        self.assertIn("EPL", reason)

    def test_team_not_in_fit(self) -> None:
        pred, reason = self.svc.predict_or_reason("XL", "strong", "ghost")
        self.assertIsNone(pred)
        self.assertIn("ghost", reason)

    def test_predict_raises_when_unavailable(self) -> None:
        with self.assertRaises(PredictionUnavailable):
            self.svc.predict("EPL", "strong", "weak")


if __name__ == "__main__":
    unittest.main()

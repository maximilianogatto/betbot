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


class TeamResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        art = {
            "model_version": "test-v1", "trained_through": "2026-07-20",
            "leagues": {"XL": {"mu": 0.2, "home_adv": 0.25, "rho": 0.0, "n_matches": 100,
                "teams": {
                    "1": {"atk": 0.3, "def": 0.2, "name": "Helsingin Jalkapalloklubi HJK"},
                    "2": {"atk": -0.1, "def": 0.0, "name": "Football Club International Turku"},
                    "3": {"atk": 0.0, "def": 0.1, "name": "FC Lahti"},
                }}},
        }
        aliases = {"XL": {"HJK Helsinki": "1", "Inter Turku": "2"}}
        self._af = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(art, self._af); self._af.close()
        self._al = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(aliases, self._al); self._al.close()
        self.svc = PredictionService(self._af.name, self._al.name)

    def tearDown(self) -> None:
        Path(self._af.name).unlink(missing_ok=True)
        Path(self._al.name).unlink(missing_ok=True)

    def test_exact_and_close_match(self) -> None:
        tid, s = self.svc.resolve_team("XL", "FC Lahti")
        self.assertEqual(tid, "3")
        self.assertAlmostEqual(s, 1.0, places=6)
        tid2, _ = self.svc.resolve_team("XL", "Lahti FC")   # orden distinto
        self.assertEqual(tid2, "3")

    def test_alias_bridges_federation_name_gap(self) -> None:
        # 'HJK Helsinki' no matchea 'Helsingin Jalkapalloklubi HJK' por fuzzy solo
        self.assertEqual(self.svc.resolve_team("XL", "HJK Helsinki")[0], "1")
        self.assertEqual(self.svc.resolve_team("XL", "Inter Turku")[0], "2")

    def test_unknown_team_returns_none(self) -> None:
        tid, s = self.svc.resolve_team("XL", "Real Madrid CF")
        self.assertIsNone(tid)
        self.assertLess(s, 0.85)

    def test_predict_by_names_end_to_end(self) -> None:
        pred, reason = self.svc.predict_by_names("XL", "HJK Helsinki", "FC Lahti")
        self.assertEqual(reason, "")
        self.assertIsNotNone(pred)
        self.assertEqual(pred.home_team_id, "1")

    def test_predict_by_names_reports_unresolved(self) -> None:
        pred, reason = self.svc.predict_by_names("XL", "HJK Helsinki", "Equipo Fantasma")
        self.assertIsNone(pred)
        self.assertIn("Fantasma", reason)


class LeagueResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        art = {
            "model_version": "test-v1", "trained_through": "2026-07-20",
            "leagues": {
                "VL": {"mu": 0.2, "home_adv": 0.25, "rho": 0.0, "n_matches": 100,
                       "teams": {"1": {"atk": 0.3, "def": 0.2, "name": "HJK"},
                                 "2": {"atk": -0.1, "def": 0.0, "name": "Inter Turku"}}},
                "SW-EN": {"mu": 0.3, "home_adv": 0.2, "rho": 0.0, "n_matches": 80,
                          "teams": {"9": {"atk": 0.1, "def": 0.1, "name": "Team N"}}},
            },
        }
        lmap = {
            "VL": {"country": "FIN", "gender": "M", "patterns": ["veikkausliiga"]},
            "SW-EN": {"country": "SWE", "gender": "M", "patterns": ["ettan norra"]},
            "SW-ES": {"country": "SWE", "gender": "M", "patterns": ["ettan sodra"]},
        }
        self._af = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(art, self._af); self._af.close()
        self._lm = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(lmap, self._lm); self._lm.close()
        self.svc = PredictionService(self._af.name, None, self._lm.name)

    def tearDown(self) -> None:
        Path(self._af.name).unlink(missing_ok=True)
        Path(self._lm.name).unlink(missing_ok=True)

    def test_resolve_league_by_name(self) -> None:
        self.assertEqual(self.svc.resolve_league("Veikkausliiga"), "VL")
        self.assertEqual(self.svc.resolve_league("Finland - Veikkausliiga"), "VL")
        self.assertEqual(self.svc.resolve_league("Ettan Norra"), "SW-EN")

    def test_resolve_league_unknown_returns_none(self) -> None:
        self.assertIsNone(self.svc.resolve_league("Premier League"))

    def test_resolve_league_ambiguous_returns_none(self) -> None:
        # "Ettan" (sin Norra/Södra) matchea patrones distintos por igual -> None
        self.assertIsNone(self.svc.resolve_league("Ettan"))

    def test_country_gender_disambiguation(self) -> None:
        self.assertEqual(self.svc.resolve_league("Veikkausliiga", country="FIN", gender="M"), "VL")
        self.assertIsNone(self.svc.resolve_league("Veikkausliiga", country="SWE"))

    def test_predict_for_fixture_end_to_end(self) -> None:
        pred, reason = self.svc.predict_for_fixture(
            "Veikkausliiga", "HJK", "Inter Turku", country="FIN", gender="M")
        self.assertEqual(reason, "")
        self.assertEqual(pred.league_code, "VL")

    def test_predict_for_fixture_league_unmapped(self) -> None:
        pred, reason = self.svc.predict_for_fixture("La Liga", "Real", "Barsa")
        self.assertIsNone(pred)
        self.assertIn("no mapea", reason)


if __name__ == "__main__":
    unittest.main()

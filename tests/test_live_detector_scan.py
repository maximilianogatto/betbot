"""Tests de la orquestación viva del detector (services.live_detector_scan)."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.models import LiveEventSnapshot, Odds1X2
from services.live_detector_scan import (
    format_alert, parse_minute, scan_live_events)
from services.prediction import PredictionService

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc)


def _svc() -> tuple[PredictionService, str, str]:
    art = {
        "model_version": "t", "trained_through": "2026-07-20",
        "leagues": {"XL": {"mu": 0.2, "home_adv": 0.25, "rho": 0.0, "n_matches": 100,
            "teams": {
                "strong": {"atk": 0.9, "def": 0.3, "name": "Strong FC"},
                "weak": {"atk": -0.5, "def": -0.3, "name": "Weak FC"},
                "evenA": {"atk": 0.0, "def": 0.0, "name": "Even A"},
                "evenB": {"atk": 0.0, "def": 0.0, "name": "Even B"},
            }}},
    }
    lmap = {"XL": {"country": "FIN", "gender": "M", "patterns": ["liga xl"]}}
    af = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(art, af); af.close()
    lm = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(lmap, lm); lm.close()
    return PredictionService(af.name, None, lm.name), af.name, lm.name


def _snap(home, away, comp="Liga XL", minute="5'", hs=0, as_=0,
          odds=None, extracted=None, country="FIN"):
    return LiveEventSnapshot(
        platform="book1", external_event_id="e1", home=home, away=away,
        competition_name=comp, country_name=country, minute=minute,
        home_score=hs, away_score=as_,
        odds_1x2=Odds1X2(*odds) if odds else None,
        extracted_at=(extracted or NOW.isoformat()),
    )


class ParseMinuteTests(unittest.TestCase):
    def test_variants(self) -> None:
        self.assertEqual(parse_minute("12'"), 12)
        self.assertEqual(parse_minute("HT"), 45)
        self.assertEqual(parse_minute("2ª parte"), 45)
        self.assertEqual(parse_minute("45+2"), 47)
        self.assertEqual(parse_minute("90+5"), 90)   # cap
        self.assertIsNone(parse_minute(None))
        self.assertIsNone(parse_minute("basura"))


class ScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.svc, self._af, self._lm = _svc()

    def tearDown(self) -> None:
        Path(self._af).unlink(missing_ok=True)
        Path(self._lm).unlink(missing_ok=True)

    def test_unavailable_when_league_not_in_model(self) -> None:
        snap = _snap("A", "B", comp="Premier League", country="England")
        [item] = scan_live_events([snap], self.svc, now=NOW)
        self.assertEqual(item.status, "unavailable")
        self.assertIsNone(item.league_code)

    def test_no_state_when_minute_unparseable(self) -> None:
        snap = _snap("Strong FC", "Weak FC", minute="???")
        [item] = scan_live_events([snap], self.svc, now=NOW)
        self.assertEqual(item.status, "no_state")

    def test_fires_on_gross_book_error(self) -> None:
        # modelo: local aplastante (~90% H); casa lo precia barato (cuota alta)
        snap = _snap("Strong FC", "Weak FC", minute="5'", hs=0, as_=0,
                     odds=(2.5, 3.4, 2.7))     # implied H ~0.37 sin vig
        [item] = scan_live_events([snap], self.svc, now=NOW)
        self.assertEqual(item.status, "fired")
        self.assertEqual(item.detection.outcome, "H")
        self.assertGreater(item.detection.edge, 0.30)
        self.assertIn("Strong FC", format_alert(item))

    def test_no_edge_on_fair_even_match(self) -> None:
        snap = _snap("Even A", "Even B", minute="5'", odds=(2.6, 3.2, 3.0))
        [item] = scan_live_events([snap], self.svc, now=NOW)
        self.assertEqual(item.status, "no_edge")
        self.assertFalse(item.detection.fired)

    def test_stale_state_does_not_fire(self) -> None:
        old = (NOW - timedelta(seconds=600)).isoformat()
        snap = _snap("Strong FC", "Weak FC", minute="5'",
                     odds=(2.5, 3.4, 2.7), extracted=old)
        [item] = scan_live_events([snap], self.svc, now=NOW)
        self.assertEqual(item.status, "no_edge")
        self.assertIn("rancio", item.detection.reason)

    def test_non_soccer_skipped(self) -> None:
        snap = _snap("Strong FC", "Weak FC")
        object.__setattr__(snap, "is_soccer", False)
        self.assertEqual(scan_live_events([snap], self.svc, now=NOW), [])

    def test_all_results_returned_for_fp_measurement(self) -> None:
        snaps = [_snap("Strong FC", "Weak FC", odds=(2.5, 3.4, 2.7)),
                 _snap("Even A", "Even B", odds=(2.6, 3.2, 3.0)),
                 _snap("A", "B", comp="Premier League", country="England")]
        items = scan_live_events(snaps, self.svc, now=NOW)
        self.assertEqual(len(items), 3)
        self.assertEqual({i.status for i in items}, {"fired", "no_edge", "unavailable"})


if __name__ == "__main__":
    unittest.main()

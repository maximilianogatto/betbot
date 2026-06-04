from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from monitors.special_peak import (
    RotationResult,
    build_peak_scores,
    compute_rotation_ratio,
    render_peak_digest,
    score_finland_match,
    score_sweden_match,
)

_ARG = ZoneInfo("America/Argentina/Buenos_Aires")
# 09:00 ARG (UTC-3); Helsinki summer (EEST) = ARG + 6h.
_NOW = datetime(2026, 7, 3, 9, 0, tzinfo=_ARG)


def _fin_match(**overrides):
    base = {
        "match_id": "1001",
        "status": "Scheduled",
        "category_id": "VL",
        "category_name": "Veikkausliiga (Tier 1)",
        "home_team_name": "HJK",
        "away_team_name": "KuPS",
        "date": "2026-07-03",
        "time": "19:00",  # Helsinki -> 13:00 ARG, ~4h after _NOW (far)
        "team_A_primary_category_id": "VL",
        "team_B_primary_category_id": "VL",
    }
    base.update(overrides)
    return base


class FinlandScoringTests(unittest.TestCase):
    def test_skips_finished_match(self) -> None:
        self.assertIsNone(score_finland_match(_fin_match(status="Finished"), now=_NOW))

    def test_skips_youth_match(self) -> None:
        youth = _fin_match(category_id="P17", category_name="Poikien U17 SM-sarja")
        self.assertIsNone(score_finland_match(youth, now=_NOW))

    def test_plain_league_match_low_score_not_peak(self) -> None:
        score = score_finland_match(_fin_match(), now=_NOW)
        assert score is not None
        # base(1) + senior(1) = 2
        self.assertEqual(score.score_int, 2)
        self.assertFalse(score.is_peak)
        self.assertIn("Esperá", score.peak_window)
        self.assertEqual(score.kickoff_label, "13:00")

    def test_cup_cross_division_is_peak(self) -> None:
        cup = _fin_match(
            match_id="2002",
            category_id="MSC",
            category_name="Suomen Cup",
            team_A_primary_category_id="VL",
            team_B_primary_category_id="M2",
        )
        score = score_finland_match(cup, now=_NOW)
        assert score is not None
        # base(1) + cup(3) + mismatch(2.5) = 6.5 -> peak threshold
        self.assertEqual(score.score, 6.5)
        self.assertTrue(score.is_peak)

    def test_confirmed_b_team_near_kickoff(self) -> None:
        # Kickoff 60 min after _NOW (within lineup window) -> lookup runs.
        cup = _fin_match(
            match_id="3003",
            category_id="MSC",
            category_name="Suomen Cup",
            time="16:00",  # Helsinki -> 10:00 ARG (60 min after _NOW)
            team_A_primary_category_id="VL",
            team_B_primary_category_id="M2",
        )

        def lookup(_match):
            return RotationResult(0.2, ["7 Reserva"]), RotationResult(0.8)

        score = score_finland_match(cup, now=_NOW, rotation_lookup=lookup)
        assert score is not None
        self.assertEqual(score.rotation_ratio, 0.2)
        self.assertTrue(score.is_peak)
        self.assertIn("AHORA", score.peak_window)
        # base1 + cup3 + mismatch2.5 + massive3.5 = 10
        self.assertEqual(score.score_int, 10)

    def test_lookup_skipped_when_far_from_kickoff(self) -> None:
        calls = []

        def lookup(match):
            calls.append(match)
            return RotationResult(0.2), RotationResult(0.2)

        # Default match kickoff is ~4h away -> outside lineup window.
        score = score_finland_match(_fin_match(), now=_NOW, rotation_lookup=lookup)
        assert score is not None
        self.assertEqual(calls, [])
        self.assertIsNone(score.rotation_ratio)


class RotationDetectorTests(unittest.TestCase):
    def test_returns_none_without_recent_games(self) -> None:
        class _Api:
            def get_matches_by_league(self, *_):
                return []

        result = compute_rotation_ratio(
            _Api(),
            team_id="T1",
            primary_category="VL",
            competition_id="C1",
            starters=[{"player_id": "p1"}],
            target_match_id="999",
        )
        self.assertIsNone(result.ratio)

    def test_detects_massive_rotation(self) -> None:
        # Recent league games where regulars were p1..p11; today none of them start.
        regular_lineup = [
            {"team_id": "T1", "start": "1", "player_id": f"p{i}"} for i in range(1, 12)
        ]
        recent = [
            {"match_id": "m1", "status": "Finished", "team_A_id": "T1", "team_B_id": "X", "date": "2026-06-20"},
            {"match_id": "m2", "status": "Finished", "team_A_id": "T1", "team_B_id": "Y", "date": "2026-06-27"},
        ]

        class _Api:
            def get_matches_by_league(self, *_):
                return recent

            def get_match_details(self, _match_id):
                return {"lineups": regular_lineup}

        today_starters = [{"player_id": f"sub{i}", "shirt_number": i, "player_name": f"Sub {i}"} for i in range(1, 12)]
        result = compute_rotation_ratio(
            _Api(),
            team_id="T1",
            primary_category="VL",
            competition_id="C1",
            starters=today_starters,
            target_match_id="today",
        )
        self.assertEqual(result.ratio, 0.0)
        self.assertEqual(len(result.new_starters), 11)


class SwedenScoringTests(unittest.TestCase):
    def test_basic_score(self) -> None:
        match = {
            "match_id": "55",
            "status": "Scheduled",
            "competition_name": "Allsvenskan 2026",
            "home": "Sirius",
            "away": "Mjällby",
            "start_time_local": "2026-07-03 19:00",
        }
        score = score_sweden_match(match, now=_NOW)
        assert score is not None
        self.assertEqual(score.provider_key, "sweden")
        self.assertEqual(score.score_int, 2)
        self.assertEqual(score.detail_command, "/swe_match 55")

    def test_standings_gap_adds_points(self) -> None:
        match = {
            "match_id": "56",
            "competition_name": "Allsvenskan 2026",
            "home": "A",
            "away": "B",
            "start_time_local": "2026-07-03 19:00",
        }
        score = score_sweden_match(match, now=_NOW, standings_gap=1.0)
        assert score is not None
        # base1 + senior1 + mismatch2.5 = 4.5
        self.assertEqual(score.score, 4.5)


class OrchestrationTests(unittest.TestCase):
    def test_build_and_render(self) -> None:
        class _FinApi:
            def get_matches_by_date(self, _date):
                return [
                    _fin_match(),  # plain league -> 2
                    _fin_match(
                        match_id="2002",
                        category_id="MSC",
                        category_name="Suomen Cup",
                        team_A_primary_category_id="VL",
                        team_B_primary_category_id="M2",
                    ),  # cup mismatch -> 6.5
                    _fin_match(match_id="x", status="Finished"),  # skipped
                ]

            def get_match_details(self, _id):
                return None

        class _SweClient:
            def get_matches_today(self):
                return [{
                    "match_id": "55",
                    "competition_name": "Allsvenskan 2026",
                    "home": "Sirius",
                    "away": "Mjällby",
                    "start_time_local": "2026-07-03 19:00",
                }]

        scores = build_peak_scores(finland_api=_FinApi(), sweden_client=_SweClient(), now=_NOW)
        self.assertEqual(len(scores), 3)
        # Sorted by score desc: cup(6.5) first.
        self.assertEqual(scores[0].match_id, "2002")
        self.assertTrue(scores[0].is_peak)

        digest = render_peak_digest(scores, now=_NOW)
        self.assertIn("Peak del día", digest)
        self.assertIn("PEAKS", digest)
        self.assertIn("Suomen Cup", digest)

    def test_render_empty(self) -> None:
        digest = render_peak_digest([], now=_NOW)
        self.assertIn("No hay partidos", digest)


if __name__ == "__main__":
    unittest.main()

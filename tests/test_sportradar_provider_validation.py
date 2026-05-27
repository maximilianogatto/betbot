from __future__ import annotations

import json
import unittest

from sandbox.sportradar_http.provider_validation import (
    build_validation_result,
    build_validation_summary,
    parse_validation_target,
    render_validation_report,
)


class SportradarProviderValidationTests(unittest.TestCase):
    def test_parse_validation_target(self) -> None:
        target = parse_validation_target("18340:South Australia NPL Women:women")

        self.assertEqual(target.tournament_id, 18340)
        self.assertEqual(target.label, "South Australia NPL Women")
        self.assertEqual(target.category, "women")

    def test_build_validation_result_detects_quality_and_dates(self) -> None:
        result = build_validation_result(
            target=parse_validation_target("18340:Women:women"),
            navigation=_navigation(),
            selected_fixture=_fixture(),
            snapshot=_snapshot(),
            intelligence=_intelligence(),
            package_path="packages/18340.json",
        )

        self.assertTrue(result["quality"]["has_priced_odds"])
        self.assertTrue(result["report_quality"]["h2h_has_dates"])
        self.assertTrue(result["report_quality"]["traceability_has_dates"])
        self.assertEqual(result["warnings"], [])
        json.dumps(result)

    def test_fixture_market_odds_can_satisfy_provider_priced_odds(self) -> None:
        snapshot = _snapshot()
        snapshot["feature_quality"]["has_priced_odds"] = False
        snapshot["odds"] = {"markets": {"1x2": {}, "handicap": [], "totals": []}}

        result = build_validation_result(
            target=parse_validation_target("18340:Women:women"),
            navigation=_navigation(),
            selected_fixture=_fixture(),
            snapshot=snapshot,
            intelligence=_intelligence(),
            fixture_market_odds={
                "source": "unified_sport_matches_markets",
                "markets": {"1x2": {"home": 2.1}, "handicap": [{}], "totals": [], "raw_market_count": 2},
            },
        )

        self.assertTrue(result["quality"]["has_priced_odds"])
        self.assertFalse(result["quality"]["has_match_markets_priced_odds"])
        self.assertTrue(result["quality"]["has_fixture_markets_priced_odds"])
        self.assertEqual(result["odds"]["source"], "unified_sport_matches_markets")
        self.assertNotIn("no_priced_odds", result["warnings"])

    def test_render_validation_report(self) -> None:
        result = build_validation_result(
            target=parse_validation_target("18340:Women:women"),
            navigation=_navigation(),
            selected_fixture=_fixture(),
            snapshot=_snapshot(),
            intelligence=_intelligence(),
        )
        report = render_validation_report([result])
        summary = build_validation_summary([result])

        self.assertIn("Sportradar Provider Validation Report", report)
        self.assertEqual(summary["targets"], 1)
        self.assertEqual(summary["with_priced_odds"], 1)


def _navigation() -> dict:
    return {
        "fixture_count": 10,
        "resolved_tournament": {
            "found": True,
            "requested_tournament_id": 18340,
            "season_id": 138964,
            "match_kind": "unique_tournament_id",
            "primary": {"country_name": "Australia", "name": "South Australia NPL, Women"},
        },
    }


def _fixture() -> dict:
    return {
        "match_id": 1,
        "time": {"iso_utc": "2026-06-01T12:00:00+00:00"},
        "home": {"name": "Team A"},
        "away": {"name": "Team B"},
        "status": {"in_livescore": True},
    }


def _snapshot() -> dict:
    return {
        "feature_quality": {
            "has_metadata": True,
            "has_priced_odds": True,
            "has_odds_endpoint": True,
            "has_table": True,
            "has_team_form": True,
            "has_team_scoring": True,
            "has_h2h": True,
            "has_live_state": True,
            "data_completeness": 1,
            "missing_important_endpoints": [],
        },
        "odds": {"markets": {"1x2": {"home": 1.5}, "handicap": [{}], "totals": [{}]}},
        "live_state": {"raw_event_count": 3, "status": "not_started"},
        "live_delta": {"raw_event_count": 0},
        "live_situation": {"raw_sample_count": 0},
    }


def _intelligence() -> dict:
    return {
        "report_summary": "Team A vs Team B\n- H2H edge: Team A\n  - 22/06/24: Team A 2-0 Team B",
        "h2h": {"recent_matches": [{"date_display": "22/06/24"}]},
        "traceability": {
            "common_opponents": [
                {
                    "home_team_evidence": {"date_display": "22/06/24"},
                    "away_team_evidence": {"date_display": "23/06/24"},
                }
            ]
        },
    }


if __name__ == "__main__":
    unittest.main()

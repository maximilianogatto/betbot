from __future__ import annotations

from datetime import UTC, datetime
import json
import unittest

from sandbox.sportradar_http_research.tournament_match_report import (
    build_tournament_match_package,
    render_tournament_match_report,
    select_fixture,
)


class SportradarTournamentMatchReportTests(unittest.TestCase):
    def test_select_fixture_by_match_id(self) -> None:
        fixture = select_fixture(_fixtures(), match_id=2)

        self.assertEqual(fixture["match_id"], 2)

    def test_select_fixture_prefers_upcoming_unplayed(self) -> None:
        fixture = select_fixture(_fixtures(), now=datetime(2026, 5, 27, tzinfo=UTC))

        self.assertEqual(fixture["match_id"], 2)

    def test_build_package_is_compact_and_serializable(self) -> None:
        package = build_tournament_match_package(
            navigation=_navigation(),
            selected_fixture=_fixtures()[1],
            match_intelligence=_intelligence(),
            client_metrics={"total_requests": 4},
        )
        report = render_tournament_match_report(
            navigation=_navigation(),
            selected_fixture=_fixtures()[1],
            match_intelligence=_intelligence(),
        )

        self.assertEqual(package["kind"], "tournament_match_report")
        self.assertEqual(package["match_id"], 2)
        self.assertIn("Team A vs Team B", package["report_summary"])
        self.assertIn("2026-06-01T12:00:00+00:00", report)
        json.dumps(package)


def _fixtures() -> list[dict]:
    return [
        {
            "match_id": 1,
            "time": {"uts": 1772783100, "iso_utc": "2026-03-06T07:45:00+00:00"},
            "home": {"name": "Old Home"},
            "away": {"name": "Old Away"},
            "result": {"home": 1, "away": 1},
        },
        {
            "match_id": 2,
            "time": {"uts": 1780315200, "iso_utc": "2026-06-01T12:00:00+00:00"},
            "home": {"name": "Team A"},
            "away": {"name": "Team B"},
            "result": {"home": None, "away": None},
        },
    ]


def _navigation() -> dict:
    return {
        "resolved_tournament": {
            "requested_tournament_id": 18340,
            "unique_tournament_id": 18340,
            "concrete_tournament_id": 46533,
            "season_id": 138964,
            "primary": {"name": "South Australia NPL, Women", "country_name": "Australia"},
        }
    }


def _intelligence() -> dict:
    return {
        "match_id": 2,
        "report_summary": "Team A vs Team B\n\n- Form: 7.0/10 vs 5.0/10\n- H2H edge: Team A\n  - 22/06/24: Team A 2-0 Team B",
    }


if __name__ == "__main__":
    unittest.main()

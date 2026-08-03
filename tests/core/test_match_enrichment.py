"""Traducción del reporte de un proveedor a los indicadores de MatchResult."""
from __future__ import annotations

import json
import unittest

from core.stats_models import MatchStatsReport
from services.match_enrichment import normalize_provider_report


def _report(**data) -> MatchStatsReport:
    return MatchStatsReport(
        provider="sofascore_http",
        match_id="12345",
        title="Banyule vs Bundoora",
        markdown="",
        data=data,
        generated_at="2026-08-04T10:00:00+00:00",
    )


def _sofascore(**overrides) -> MatchStatsReport:
    data = {
        "match": {
            "status": "finished",
            "score_home": 2,
            "score_away": 1,
            "start_time_utc": "2026-08-03T18:00:00+00:00",
        },
        "live_state": {
            "statistics": {
                "Expected goals": {"home": "1.87", "away": "0.64"},
                "Shots on target": {"home": 7, "away": 2},
                "Ball possession": {"home": 61, "away": 39},
            },
            "incidents": [
                {"incidentType": "goal", "time": 23, "isHome": True},
                {"incidentType": "goal", "time": 71, "isHome": False},
                {"incidentType": "goal", "time": 90, "addedTime": 3, "isHome": True},
                {"incidentType": "card", "incidentClass": "red", "time": 61, "isHome": False},
                {"incidentType": "card", "incidentClass": "yellow", "time": 30, "isHome": True},
                {"incidentType": "period", "text": "HT", "homeScore": 1, "awayScore": 0},
            ],
        },
    }
    data.update(overrides)
    return _report(**data)


class SofaScoreNormalizationTests(unittest.TestCase):
    def test_extracts_the_level_one_indicators(self) -> None:
        fields = normalize_provider_report(_sofascore())

        self.assertEqual(fields["status"], "FINISHED")
        self.assertEqual((fields["final_home_score"], fields["final_away_score"]), (2, 1))
        self.assertEqual((fields["ht_home_score"], fields["ht_away_score"]), (1, 0))
        self.assertEqual(fields["actual_start_at"], "2026-08-03T18:00:00+00:00")

    def test_extracts_xg_and_shots(self) -> None:
        fields = normalize_provider_report(_sofascore())

        self.assertAlmostEqual(fields["xg_home"], 1.87)
        self.assertAlmostEqual(fields["xg_away"], 0.64)
        self.assertEqual((fields["shots_on_target_home"], fields["shots_on_target_away"]), (7, 2))

    def test_goal_minutes_include_stoppage_time_and_are_ordered(self) -> None:
        """Un gol al 90+3 vale 93: sin el descuento el modelo temporal se rompe."""

        fields = normalize_provider_report(_sofascore())

        self.assertEqual(
            json.loads(fields["goal_minutes_json"]),
            [
                {"minute": 23, "team": "home"},
                {"minute": 71, "team": "away"},
                {"minute": 93, "team": "home"},
            ],
        )

    def test_red_cards_counted_from_the_timeline(self) -> None:
        fields = normalize_provider_report(_sofascore())

        self.assertEqual(json.loads(fields["red_card_minutes_json"]), [{"minute": 61, "team": "away"}])
        self.assertEqual((fields["red_cards_home"], fields["red_cards_away"]), (0, 1))

    def test_a_second_yellow_counts_as_a_sending_off(self) -> None:
        """Deja al equipo con uno menos igual que una roja directa."""

        report = _sofascore()
        report.data["live_state"]["incidents"] = [
            {"incidentType": "card", "incidentClass": "yellowRed", "time": 80, "isHome": True},
        ]

        fields = normalize_provider_report(report)

        self.assertEqual(fields["red_cards_home"], 1)

    def test_possession_stays_out_of_the_columns(self) -> None:
        """La posesión es mal predictor: viaja en el crudo, no como columna."""

        fields = normalize_provider_report(_sofascore())

        self.assertNotIn("possession_home", fields)
        self.assertIn("Ball possession", fields["raw_payload_json"])

    def test_an_unfinished_match_is_not_marked_finished(self) -> None:
        report = _sofascore(match={"status": "inprogress", "score_home": 1, "score_away": 0})

        fields = normalize_provider_report(report)

        self.assertEqual(fields["status"], "UNKNOWN")

    def test_maps_postponed_and_cancelled_distinctly(self) -> None:
        self.assertEqual(
            normalize_provider_report(_sofascore(match={"status": "postponed"}))["status"],
            "POSTPONED",
        )
        self.assertEqual(
            normalize_provider_report(_sofascore(match={"status": "canceled"}))["status"],
            "SUSPENDED",
        )

    def test_missing_data_is_omitted_not_nulled(self) -> None:
        """Enriquecer no puede borrar un dato que ya estaba archivado."""

        fields = normalize_provider_report(_report(match={}, live_state={}))

        for key in ("status", "final_home_score", "xg_home", "goal_minutes_json"):
            self.assertNotIn(key, fields)
        # La trazabilidad sí se informa siempre.
        self.assertEqual(fields["stats_provider"], "sofascore_http")
        self.assertEqual(fields["stats_match_id"], "12345")

    def test_survives_a_payload_with_the_wrong_shape(self) -> None:
        """Un proveedor que cambia de forma no puede tirar el enriquecimiento."""

        report = _report(match="no soy un dict", live_state={"statistics": [], "incidents": "nada"})

        fields = normalize_provider_report(report)

        self.assertEqual(fields["stats_provider"], "sofascore_http")
        self.assertNotIn("final_home_score", fields)


if __name__ == "__main__":
    unittest.main()

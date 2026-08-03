"""Orquestación del enriquecimiento: resolver, completar y guardar."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from core.models import MatchResult
from core.stats_models import MatchStatsReport, StatsMatchLink
from services.match_enrichment import MatchEnrichmentService, merge_into_result


def _archived(**overrides) -> MatchResult:
    payload = dict(
        home="Banyule", away="Bundoora", status="UNKNOWN", source="live_watch",
        recorded_at="2026-08-03T20:00:00+00:00",
        platform="betovo_http", external_event_id="ev-1",
        kickoff_at="2026-08-03T18:00:00+00:00",
        final_home_score=1, final_away_score=0,
    )
    payload.update(overrides)
    return MatchResult(**payload)


def _provider(*, link: StatsMatchLink | None, report: MatchStatsReport | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        resolve_match=AsyncMock(return_value=link),
        build_match_report=AsyncMock(return_value=report),
    )


def _report() -> MatchStatsReport:
    return MatchStatsReport(
        provider="sofascore_http", match_id="999", title="t", markdown="",
        generated_at="2026-08-04T10:00:00+00:00",
        data={
            "match": {"status": "finished", "score_home": 2, "score_away": 1},
            "live_state": {
                "statistics": {"Expected goals": {"home": 1.9, "away": 0.5}},
                "incidents": [{"incidentType": "goal", "time": 23, "isHome": True}],
            },
        },
    )


class MergeTests(unittest.TestCase):
    def test_missing_fields_do_not_erase_what_was_archived(self) -> None:
        """Enriquecer nunca puede empeorar el registro."""

        archived = _archived(red_cards_away=1)

        merged = merge_into_result(archived, {"xg_home": 1.9, "xg_away": None})

        self.assertAlmostEqual(merged.xg_home, 1.9)
        self.assertEqual(merged.red_cards_away, 1)   # se conserva
        self.assertIsNone(merged.xg_away)            # no vino, sigue vacío
        self.assertEqual(merged.final_home_score, 1)


class EnrichmentServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp_dir.name) / "enrich.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.repository = SqliteStorage()

    def tearDown(self) -> None:
        if self._prev_db is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db
        self.tmp_dir.cleanup()

    def _service(self, provider) -> MatchEnrichmentService:
        return MatchEnrichmentService(
            repository=self.repository,
            provider_registry=SimpleNamespace(get=lambda key: provider),
        )

    async def test_enriches_and_persists(self) -> None:
        saved = self.repository.record_match_result(_archived())
        link = StatsMatchLink(
            provider="sofascore_http", stats_match_id="999", stats_url=None,
            confidence=0.95, method="fuzzy",
        )

        result = await self._service(_provider(link=link, report=_report())).enrich_one(
            saved, provider_key="sofascore_http"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.status, "FINISHED")
        self.assertEqual((result.final_home_score, result.final_away_score), (2, 1))
        self.assertAlmostEqual(result.xg_home, 1.9)
        self.assertEqual(result.stats_provider, "sofascore_http")
        # Persistido, y sin duplicar la fila.
        stored = self.repository.list_match_results()
        self.assertEqual(len(stored), 1)
        self.assertTrue(stored[0].is_settled)

    async def test_an_unresolved_match_is_left_untouched_for_a_retry(self) -> None:
        """En ligas menores el proveedor a veces no encuentra el partido."""

        saved = self.repository.record_match_result(_archived())

        result = await self._service(_provider(link=None)).enrich_one(
            saved, provider_key="sofascore_http"
        )

        self.assertIsNone(result)
        stored = self.repository.list_match_results()[0]
        self.assertEqual(stored.status, "UNKNOWN")
        self.assertIsNone(stored.stats_provider)
        # Sigue pendiente: se puede reintentar más adelante.
        self.assertEqual(len(self.repository.list_match_results_pending_enrichment()), 1)

    async def test_pending_query_skips_already_enriched(self) -> None:
        self.repository.record_match_result(_archived(external_event_id="a"))
        self.repository.record_match_result(
            _archived(external_event_id="b", status="FINISHED", xg_home=1.2,
                      stats_provider="sofascore_http", stats_match_id="1")
        )

        pending = self.repository.list_match_results_pending_enrichment()

        self.assertEqual([r.external_event_id for r in pending], ["a"])

    async def test_one_failure_does_not_stop_the_batch(self) -> None:
        self.repository.record_match_result(_archived(external_event_id="a"))
        self.repository.record_match_result(_archived(external_event_id="b"))

        link = StatsMatchLink(
            provider="sofascore_http", stats_match_id="999", stats_url=None,
            confidence=0.9, method="fuzzy",
        )
        provider = _provider(link=link, report=_report())
        provider.build_match_report = AsyncMock(side_effect=[RuntimeError("timeout"), _report()])

        enriched = await self._service(provider).enrich_pending(provider_key="sofascore_http")

        self.assertEqual(enriched, 1)  # uno falló, el otro se completó


if __name__ == "__main__":
    unittest.main()

"""El job que completa los resultados archivados con el proveedor de stats."""
from __future__ import annotations

import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from bot.jobs import MatchEnrichmentJob
from bot.jobs.tasks import _orchestrated_match_enrichment


def _application(provider_key: str = "sofascore_http") -> SimpleNamespace:
    return SimpleNamespace(
        bot_data={"settings": SimpleNamespace(match_enrichment_provider=provider_key)}
    )


class MatchEnrichmentJobTests(unittest.IsolatedAsyncioTestCase):
    def test_waits_before_the_first_run(self) -> None:
        """Recién archivado, el proveedor puede no tener las stats todavía."""

        job = MatchEnrichmentJob()

        self.assertGreater(job.next_run, time.time())
        self.assertEqual(job.name, "match_enrichment")

    async def test_runs_the_enrichment_when_the_provider_is_available(self) -> None:
        registry = SimpleNamespace(
            list_registered=lambda: [SimpleNamespace(name="sofascore_http")]
        )
        enrich = AsyncMock(return_value=2)

        with (
            patch("core.stats_provider_base.stats_provider_registry", registry),
            patch("adapters.storage.get_storage", return_value=SimpleNamespace()),
            patch(
                "services.match_enrichment.MatchEnrichmentService.enrich_pending",
                new=enrich,
            ),
        ):
            await _orchestrated_match_enrichment(_application())

        enrich.assert_awaited_once()
        self.assertEqual(enrich.await_args.kwargs["provider_key"], "sofascore_http")

    async def test_is_skipped_when_the_provider_is_not_registered(self) -> None:
        """Sin el proveedor no se puede enriquecer: se saltea sin romper el ciclo."""

        registry = SimpleNamespace(list_registered=lambda: [SimpleNamespace(name="otro_http")])
        enrich = AsyncMock()

        with (
            patch("core.stats_provider_base.stats_provider_registry", registry),
            patch("adapters.storage.get_storage", return_value=SimpleNamespace()),
            patch(
                "services.match_enrichment.MatchEnrichmentService.enrich_pending",
                new=enrich,
            ),
            self.assertLogs("bot.jobs", level="INFO") as logs,
        ):
            await _orchestrated_match_enrichment(_application())

        enrich.assert_not_awaited()
        self.assertTrue(any("no está registrado" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()

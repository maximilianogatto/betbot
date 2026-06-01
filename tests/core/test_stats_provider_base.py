from __future__ import annotations

import unittest

from core.stats_models import StatsProviderCapabilities, StatsProviderDescriptor
from core.stats_provider_base import StatsProvider, StatsProviderRegistry


class FakeStatsProvider(StatsProvider):
    name = "fake_stats"
    display_name = "Fake Stats"
    capabilities = StatsProviderCapabilities(
        supports_league_discovery=True,
        supports_fixture_discovery=True,
        supports_h2h=True,
    )

    async def search_leagues(self, *, country_name: str, query: str | None = None, limit: int = 80):
        return []

    async def list_fixtures(self, league_id: str, *, limit: int | None = None):
        return []

    async def resolve_match(self, candidate, *, league_id: str | None = None):
        return None

    async def build_match_report(self, stats_match_id: str):
        raise NotImplementedError


class StatsProviderBaseTests(unittest.TestCase):
    def test_registry_registers_and_describes_provider(self) -> None:
        registry = StatsProviderRegistry()
        provider = registry.register(FakeStatsProvider())

        self.assertIs(registry.get("fake_stats"), provider)
        descriptors = registry.list_providers()
        self.assertEqual(
            descriptors,
            [
                StatsProviderDescriptor(
                    key="fake_stats",
                    display_name="Fake Stats",
                    capabilities=FakeStatsProvider.capabilities,
                    implemented=True,
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()

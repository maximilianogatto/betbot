from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from core.stats_provider_base import StatsProviderRegistry
from stats_providers import register_default_stats_providers


class StatsProviderRegistrationTests(unittest.TestCase):
    def test_sofascore_is_registered_but_hidden_by_default(self) -> None:
        with patch.dict(os.environ, {"SPORTRADAR_CACHE_ENABLED": "false"}, clear=False):
            registry = register_default_stats_providers(StatsProviderRegistry(), payload_cache=None)

        provider = registry.get("sofascore_http")
        self.assertFalse(provider.implemented)
        visible_keys = {descriptor.key for descriptor in registry.list_providers() if descriptor.implemented}
        self.assertNotIn("sofascore_http", visible_keys)

    def test_sofascore_can_be_enabled_explicitly(self) -> None:
        with patch.dict(
            os.environ,
            {"SPORTRADAR_CACHE_ENABLED": "false", "SOFASCORE_ENABLED": "true"},
            clear=False,
        ):
            registry = register_default_stats_providers(StatsProviderRegistry(), payload_cache=None)

        provider = registry.get("sofascore_http")
        self.assertTrue(provider.implemented)


if __name__ == "__main__":
    unittest.main()

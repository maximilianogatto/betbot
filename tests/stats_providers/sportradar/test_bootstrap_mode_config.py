from __future__ import annotations

import os
import unittest
from unittest import mock

from stats_providers.sportradar_http.provider import _default_runtime_config

_ENV_KEYS = ("SPORTRADAR_BOOTSTRAP_MODE", "SPORTRADAR_BACKGROUND_BOOTSTRAP_MODE")


def _env(**overrides: str):
    base = {k: v for k, v in os.environ.items() if k not in _ENV_KEYS}
    base.update(overrides)
    return mock.patch.dict(os.environ, base, clear=True)


class BootstrapModeConfigTests(unittest.TestCase):
    def test_default_is_headless_both(self) -> None:
        with _env():
            cfg = _default_runtime_config()
        self.assertEqual(cfg.bootstrap_mode, "headless")
        self.assertEqual(cfg.background_bootstrap_mode, "headless")

    def test_headed_applies_to_background_too(self) -> None:
        with _env(SPORTRADAR_BOOTSTRAP_MODE="headed"):
            cfg = _default_runtime_config()
        self.assertEqual(cfg.bootstrap_mode, "headed")
        self.assertEqual(cfg.background_bootstrap_mode, "headed")

    def test_background_can_be_overridden(self) -> None:
        with _env(
            SPORTRADAR_BOOTSTRAP_MODE="headed",
            SPORTRADAR_BACKGROUND_BOOTSTRAP_MODE="headless",
        ):
            cfg = _default_runtime_config()
        self.assertEqual(cfg.bootstrap_mode, "headed")
        self.assertEqual(cfg.background_bootstrap_mode, "headless")


if __name__ == "__main__":
    unittest.main()

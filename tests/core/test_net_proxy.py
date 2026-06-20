from __future__ import annotations

import os
import unittest
from unittest import mock

from core.net import proxy_for_platform, proxy_platforms

_KEYS = ("BOT_PROXY_URL", "BOT_PROXY_PLATFORMS")


def _env(**overrides: str):
    base = {k: v for k, v in os.environ.items() if k not in _KEYS}
    base.update(overrides)
    return mock.patch.dict(os.environ, base, clear=True)


class ProxyForPlatformTests(unittest.TestCase):
    def test_no_proxy_url_means_direct(self) -> None:
        with _env(BOT_PROXY_PLATFORMS="mrpunter_http"):
            self.assertIsNone(proxy_for_platform("mrpunter_http"))

    def test_legacy_mode_returns_none(self) -> None:
        # No whitelist + proxy url -> ALL_PROXY (set by config) governs; helper None.
        with _env(BOT_PROXY_URL="socks5://127.0.0.1:25344"):
            self.assertIsNone(proxy_for_platform("mrpunter_http"))
            self.assertEqual(proxy_platforms(), set())

    def test_selective_routes_only_whitelisted(self) -> None:
        with _env(
            BOT_PROXY_URL="socks5://127.0.0.1:25344",
            BOT_PROXY_PLATFORMS="mrpunter_http, solcasino_http",
        ):
            self.assertEqual(
                proxy_for_platform("mrpunter_http"), "socks5://127.0.0.1:25344"
            )
            self.assertEqual(
                proxy_for_platform("solcasino_http"), "socks5://127.0.0.1:25344"
            )
            # AR books stay direct (they break through a foreign VPN exit).
            self.assertIsNone(proxy_for_platform("betsson_http"))
            self.assertIsNone(proxy_for_platform("1xbet_http"))


if __name__ == "__main__":
    unittest.main()

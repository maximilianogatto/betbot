from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stats_providers.sportradar_http.engine.bot_ready.provider import (
    BotReadyRuntimeConfig,
    SportradarBotReadyProvider,
)
from stats_providers.sportradar_http.provider import SportradarHttpStatsProvider


def _replay_config(tmp: str) -> BotReadyRuntimeConfig:
    return BotReadyRuntimeConfig(
        session_state_path=Path(tmp) / "state.json",
        bootstrap_profile_dir=Path(tmp) / "profile",
        replay_only=True,
    )


class ReplayOnlyEngineTests(unittest.TestCase):
    def test_ensure_fresh_session_never_bootstraps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = SportradarBotReadyProvider(_replay_config(tmp))
            # No state file + replay-only: must NOT launch a browser, just no-op.
            self.assertFalse(provider.ensure_fresh_session())

    def test_client_raises_instead_of_opening_browser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = SportradarBotReadyProvider(_replay_config(tmp))
            with self.assertRaises(RuntimeError):
                provider._client()


class ImportSessionStateTests(unittest.TestCase):
    def _provider(self, tmp: str) -> SportradarHttpStatsProvider:
        return SportradarHttpStatsProvider(runtime_config=_replay_config(tmp))

    def test_expiration_none_when_no_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(self._provider(tmp).session_token_expiration())

    def test_import_invalid_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                self._provider(tmp).import_session_state(b"not json at all")

    def test_import_json_without_token_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                self._provider(tmp).import_session_state("{}")


if __name__ == "__main__":
    unittest.main()

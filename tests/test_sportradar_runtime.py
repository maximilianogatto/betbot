from __future__ import annotations

from datetime import UTC, datetime, timedelta
import tempfile
import unittest
from pathlib import Path

from sandbox.sportradar_http.runtime import (
    BootstrapSessionManager,
    load_or_refresh_session_state,
    normalize_bootstrap_mode,
)
from sandbox.sportradar_http.session_manager import SignedToken, SportradarSessionState, save_session_state


class SportradarRuntimeTests(unittest.TestCase):
    def test_bootstrap_mode_aliases(self) -> None:
        self.assertEqual(normalize_bootstrap_mode(None), "headless")
        self.assertEqual(normalize_bootstrap_mode("no-gui"), "headless")
        self.assertEqual(normalize_bootstrap_mode("gui"), "headed")
        self.assertEqual(normalize_bootstrap_mode("auto"), "auto")

    def test_bootstrap_mode_sequence(self) -> None:
        self.assertEqual(BootstrapSessionManager(mode="headless")._headed_sequence(), [False])
        self.assertEqual(BootstrapSessionManager(mode="headed")._headed_sequence(), [True])
        self.assertEqual(BootstrapSessionManager(mode="auto")._headed_sequence(), [False, True])

    def test_cached_valid_state_prevents_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session.json"
            state = _valid_state()
            save_session_state(state, path)

            loaded, manager = load_or_refresh_session_state(path, seconds=0.01, bootstrap_mode="headless")

        self.assertEqual(loaded.signed_token.raw, "exp=9999999999~acl=/*~hmac=fake")
        self.assertIs(manager.state, loaded)


def _valid_state() -> SportradarSessionState:
    exp = int((datetime.now(UTC) + timedelta(hours=1)).timestamp())
    return SportradarSessionState(
        generated_at=datetime.now(UTC).isoformat(),
        headed=False,
        headless=True,
        bootstrap_urls=["https://statshub.sportradar.com/bet365/en/sport/1"],
        origin="https://statshub.sportradar.com",
        referer="https://statshub.sportradar.com/",
        replay_headers={"origin": "https://statshub.sportradar.com"},
        cookies={},
        signed_token=SignedToken(
            raw="exp=9999999999~acl=/*~hmac=fake",
            exp=exp,
            expires_at_utc=datetime.fromtimestamp(exp, UTC).isoformat(),
            acl="/*",
            hmac="fake",
        ),
        sample_signed_url="https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/event_get/?T=exp=9999999999~acl=/*~hmac=fake",
    )


if __name__ == "__main__":
    unittest.main()

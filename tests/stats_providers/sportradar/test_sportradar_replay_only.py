"""Tests for Sportradar replay-only mode and token import via Telegram."""

from __future__ import annotations

import json
import time
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from stats_providers.sportradar_http.engine.bot_ready.provider import (
    BotReadyRuntimeConfig,
    SportradarBotReadyProvider,
    _is_replay_only,
)
from stats_providers.sportradar_http.engine.session_manager import (
    SignedToken,
    SportradarSessionState,
    save_session_state,
    utc_now_iso,
)


def _make_token(*, seconds_from_now: float = 86400.0) -> SignedToken:
    """Create a SignedToken that expires in the given seconds from now."""
    exp = int(time.time() + seconds_from_now)
    from datetime import UTC, datetime

    return SignedToken(
        raw=f"acl=/*~exp={exp}~hmac=fakehmac123",
        exp=exp,
        expires_at_utc=datetime.fromtimestamp(exp, tz=UTC).isoformat(),
        acl="/*",
        hmac="fakehmac123",
    )


def _make_state(*, token: SignedToken | None = None) -> SportradarSessionState:
    """Create a minimal SportradarSessionState with the given token."""
    return SportradarSessionState(
        generated_at=utc_now_iso(),
        headed=False,
        headless=False,
        bootstrap_urls=[],
        origin="https://statshub.sportradar.com",
        referer="https://statshub.sportradar.com/",
        replay_headers={
            "accept": "application/json,text/plain,*/*",
            "origin": "https://statshub.sportradar.com",
            "referer": "https://statshub.sportradar.com/",
            "user-agent": "Mozilla/5.0 test",
        },
        cookies={},
        signed_token=token,
        sample_signed_url=None,
    )


def _config_in_tmp(tmp: str) -> BotReadyRuntimeConfig:
    return BotReadyRuntimeConfig(
        session_state_path=Path(tmp) / "state.json",
        bootstrap_profile_dir=Path(tmp) / "profile",
    )


class TestIsReplayOnly(unittest.TestCase):
    """Test the _is_replay_only env var helper."""

    def test_defaults_to_false(self) -> None:
        env = dict(__import__("os").environ)
        env.pop("SPORTRADAR_REPLAY_ONLY", None)
        with patch.dict("os.environ", env, clear=True):
            self.assertFalse(_is_replay_only())

    def test_true_values(self) -> None:
        for value in ("true", "True", "TRUE", "1", "yes", "YES"):
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": value}):
                self.assertTrue(_is_replay_only(), f"Expected True for {value!r}")

    def test_false_values(self) -> None:
        for value in ("false", "0", "no", "nope", ""):
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": value}):
                self.assertFalse(_is_replay_only(), f"Expected False for {value!r}")


class TestReplayOnlyClient(unittest.TestCase):
    """Test that _client() never opens Chrome in replay-only mode."""

    def test_replay_only_with_valid_token_creates_client(self) -> None:
        """Replay-only + valid token -> client works, auto_refresh=False."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            token = _make_token(seconds_from_now=86400)
            state = _make_state(token=token)
            save_session_state(state, config.session_state_path)
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "true"}):
                provider = SportradarBotReadyProvider(config)
            self.assertTrue(provider.replay_only)
            client = provider._client()
            self.assertFalse(client.auto_refresh)
            self.assertIsNone(client.session_manager)
            self.assertIsNotNone(client.state)

    def test_replay_only_without_token_raises(self) -> None:
        """Replay-only + no token -> descriptive RuntimeError (no Chrome)."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "true"}):
                provider = SportradarBotReadyProvider(config)
            with self.assertRaises(RuntimeError) as ctx:
                provider._client()
            self.assertIn("replay-only", str(ctx.exception))
            self.assertIn("/sportradar_token", str(ctx.exception))

    def test_replay_only_with_expired_token_raises(self) -> None:
        """Replay-only + expired token -> error, not Chrome bootstrap."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            token = _make_token(seconds_from_now=-100)  # already expired
            state = _make_state(token=token)
            save_session_state(state, config.session_state_path)
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "true"}):
                provider = SportradarBotReadyProvider(config)
            with self.assertRaises(RuntimeError) as ctx:
                provider._client()
            self.assertIn("replay-only", str(ctx.exception))


class TestReplayOnlyEnsureFreshSession(unittest.TestCase):
    """Test that ensure_fresh_session is a no-op in replay-only mode."""

    def test_ensure_fresh_session_skips_in_replay_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "true"}):
                provider = SportradarBotReadyProvider(config)
            result = provider.ensure_fresh_session(min_ttl_seconds=3600.0)
            self.assertFalse(result)


class TestImportTokenString(unittest.TestCase):
    """Test import_token_string() for raw token pasting."""

    def test_import_valid_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "true"}):
                provider = SportradarBotReadyProvider(config)
            token = _make_token(seconds_from_now=86400)
            result = provider.import_token_string(token.raw)
            self.assertTrue(result["ok"])
            self.assertIn("expires_at_utc", result)
            self.assertGreater(result["seconds_left"], 0)
            # Verify state was persisted.
            self.assertTrue(config.session_state_path.exists())
            loaded = json.loads(config.session_state_path.read_text())
            self.assertEqual(loaded["signed_token"]["raw"], token.raw)

    def test_import_expired_token_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "true"}):
                provider = SportradarBotReadyProvider(config)
            token = _make_token(seconds_from_now=-100)
            result = provider.import_token_string(token.raw)
            self.assertFalse(result["ok"])
            self.assertIn("vencido", result["error"])

    def test_import_garbage_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "true"}):
                provider = SportradarBotReadyProvider(config)
            result = provider.import_token_string("not_a_real_token")
            self.assertFalse(result["ok"])

    def test_import_replaces_existing_token(self) -> None:
        """Importing a new token replaces the old one on disk."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "true"}):
                provider = SportradarBotReadyProvider(config)
            old_token = _make_token(seconds_from_now=3600)
            provider.import_token_string(old_token.raw)
            new_token = _make_token(seconds_from_now=86400)
            result = provider.import_token_string(new_token.raw)
            self.assertTrue(result["ok"])
            loaded = json.loads(config.session_state_path.read_text())
            self.assertEqual(loaded["signed_token"]["raw"], new_token.raw)


class TestImportSessionJson(unittest.TestCase):
    """Test import_session_json() for full JSON file import."""

    def test_import_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "true"}):
                provider = SportradarBotReadyProvider(config)
            token = _make_token(seconds_from_now=86400)
            state = _make_state(token=token)
            json_text = json.dumps(state.to_json_dict())
            result = provider.import_session_json(json_text)
            self.assertTrue(result["ok"])
            self.assertIn("expires_at_utc", result)

    def test_import_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "true"}):
                provider = SportradarBotReadyProvider(config)
            result = provider.import_session_json("{not valid json")
            self.assertFalse(result["ok"])
            self.assertIn("JSON", result["error"])

    def test_import_expired_session_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "true"}):
                provider = SportradarBotReadyProvider(config)
            token = _make_token(seconds_from_now=-100)
            state = _make_state(token=token)
            json_text = json.dumps(state.to_json_dict())
            result = provider.import_session_json(json_text)
            self.assertFalse(result["ok"])
            self.assertIn("usable", result["error"].lower())


class TestGetTokenStatus(unittest.TestCase):
    """Test get_token_status() for status display."""

    def test_no_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "true"}):
                provider = SportradarBotReadyProvider(config)
            status = provider.get_token_status()
            self.assertFalse(status["has_token"])
            self.assertFalse(status["usable"])

    def test_valid_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            token = _make_token(seconds_from_now=86400)
            state = _make_state(token=token)
            save_session_state(state, config.session_state_path)
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "true"}):
                provider = SportradarBotReadyProvider(config)
            status = provider.get_token_status()
            self.assertTrue(status["has_token"])
            self.assertTrue(status["usable"])
            self.assertFalse(status["expired"])
            self.assertGreater(status["hours_left"], 0)
            self.assertTrue(status["replay_only"])

    def test_expired_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            token = _make_token(seconds_from_now=-100)
            state = _make_state(token=token)
            save_session_state(state, config.session_state_path)
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "true"}):
                provider = SportradarBotReadyProvider(config)
            status = provider.get_token_status()
            self.assertTrue(status["has_token"])
            self.assertFalse(status["usable"])
            self.assertTrue(status["expired"])

    def test_no_token_in_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            state = _make_state(token=None)
            save_session_state(state, config.session_state_path)
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "true"}):
                provider = SportradarBotReadyProvider(config)
            status = provider.get_token_status()
            self.assertFalse(status["has_token"])


class TestNormalModeUnaffected(unittest.TestCase):
    """Verify that non-replay-only mode is unaffected by the changes."""

    def test_normal_mode_ensure_fresh_session_refreshes(self) -> None:
        """Without SPORTRADAR_REPLAY_ONLY, ensure_fresh_session still refreshes."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _config_in_tmp(tmp)
            # Write empty state so the path exists but has no token.
            config.session_state_path.write_text("{}")
            with patch.dict("os.environ", {"SPORTRADAR_REPLAY_ONLY": "false"}):
                provider = SportradarBotReadyProvider(config)
            self.assertFalse(provider.replay_only)
            fake_state = SimpleNamespace(
                signed_token=SimpleNamespace(
                    is_expired=lambda: False,
                    seconds_until_expiration=lambda: 99999.0,
                ),
                is_usable=lambda: True,
            )
            with patch.object(provider._background_session_manager, "refresh_session", return_value=fake_state) as mock_refresh, \
                 patch("stats_providers.sportradar_http.engine.bot_ready.provider.save_session_state"):
                refreshed = provider.ensure_fresh_session(min_ttl_seconds=3600.0)
            self.assertTrue(refreshed)
            mock_refresh.assert_called_once()


if __name__ == "__main__":
    unittest.main()

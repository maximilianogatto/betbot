"""Runtime helpers shared by sandbox Sportradar HTTP scripts.

Purpose:
    Keep browser bootstrap policy in one place. Most scripts only need a usable
    `SportradarSessionState`; they should not decide independently whether to
    open a headed browser.

Bootstrap modes:
    `headless`: no graphical browser window. This is the default because it is
        the target for Railway/server usage.
    `headed`: visible Chromium window. Useful for local debugging when headless
        is blocked.
    `auto`: try headless first, then headed only if headless fails.

Environment:
    `SPORTRADAR_BOOTSTRAP_MODE=headless|headed|auto` can override CLI defaults.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Literal

from stats_providers.sportradar_http.engine.session_manager import (
    BootstrapConfig,
    SportradarSessionManager,
    SportradarSessionState,
    load_session_state,
    save_session_state,
)


BootstrapMode = Literal["headless", "headed", "auto"]
DEFAULT_BOOTSTRAP_MODE: BootstrapMode = "headless"
BOOTSTRAP_MODE_ENV = "SPORTRADAR_BOOTSTRAP_MODE"


def normalize_bootstrap_mode(value: str | None) -> BootstrapMode:
    """Normalize CLI/env bootstrap mode aliases.

    Args:
        value: Raw mode, for example `headless`, `headed`, `auto`, `no-gui`.

    Returns:
        One of `headless`, `headed`, or `auto`.

    Raises:
        ValueError: if the value is unknown.
    """

    raw = (value or os.getenv(BOOTSTRAP_MODE_ENV) or DEFAULT_BOOTSTRAP_MODE).strip().lower()
    aliases = {
        "no-gui": "headless",
        "nogui": "headless",
        "server": "headless",
        "gui": "headed",
        "visible": "headed",
    }
    raw = aliases.get(raw, raw)
    if raw not in {"headless", "headed", "auto"}:
        raise ValueError(f"Invalid Sportradar bootstrap mode: {value!r}. Use headless, headed, or auto.")
    return raw  # type: ignore[return-value]


def add_bootstrap_mode_arg(parser: argparse.ArgumentParser) -> None:
    """Add a common `--bootstrap-mode` argument to a script parser."""

    parser.add_argument(
        "--bootstrap-mode",
        choices=("headless", "headed", "auto"),
        default=os.getenv(BOOTSTRAP_MODE_ENV, DEFAULT_BOOTSTRAP_MODE),
        help=(
            "Browser bootstrap mode. headless opens no GUI; headed opens a visible browser; "
            "auto tries headless then headed. Can also be set with SPORTRADAR_BOOTSTRAP_MODE."
        ),
    )


class BootstrapSessionManager:
    """Refreshable session manager with explicit headless/headed/auto policy."""

    def __init__(
        self,
        *,
        mode: str | None = None,
        seconds_per_url: float = 4.0,
        bootstrap_urls: tuple[str, ...] | None = None,
        wait_between_urls: float = 0.5,
        user_data_dir: str | None = None,
        timeout_ms: int = 45000,
        block_heavy_resources: bool = True,
    ) -> None:
        self.mode = normalize_bootstrap_mode(mode)
        self.seconds_per_url = seconds_per_url
        self.bootstrap_urls = bootstrap_urls
        self.wait_between_urls = wait_between_urls
        self.user_data_dir = user_data_dir
        self.timeout_ms = timeout_ms
        self.block_heavy_resources = block_heavy_resources
        self.state: SportradarSessionState | None = None

    def refresh_session(self) -> SportradarSessionState:
        """Bootstrap a new session according to the configured mode.

        In `headless` mode this never opens a graphical browser. In `auto` mode a
        visible browser can be opened only after headless fails.
        """

        attempted = []
        last_state: SportradarSessionState | None = None
        for headed in self._headed_sequence():
            attempted.append("headed" if headed else "headless")
            manager = SportradarSessionManager(self._config(headed=headed))
            state = manager.refresh_session()
            last_state = state
            self.state = state
            if state.is_usable():
                return state
        detail = None
        if last_state is not None:
            detail = {
                "fetch_count": last_state.fetch_count,
                "blocked_count": last_state.blocked_count,
                "expired_count": last_state.expired_count,
                "error": last_state.error,
            }
        raise RuntimeError(
            "Sportradar bootstrap failed "
            f"mode={self.mode} attempted={attempted} detail={detail}. "
            "Use --bootstrap-mode auto or headed only if a visible fallback is acceptable."
        )

    def _headed_sequence(self) -> list[bool]:
        if self.mode == "headless":
            return [False]
        if self.mode == "headed":
            return [True]
        return [False, True]

    def _config(self, *, headed: bool) -> BootstrapConfig:
        kwargs = {
            "headed": headed,
            "seconds_per_url": self.seconds_per_url,
            "wait_between_urls": self.wait_between_urls,
            "user_data_dir": self.user_data_dir,
            "timeout_ms": self.timeout_ms,
            "block_heavy_resources": self.block_heavy_resources,
        }
        if self.bootstrap_urls is not None:
            kwargs["bootstrap_urls"] = self.bootstrap_urls
        return BootstrapConfig(**kwargs)


def load_or_refresh_session_state(
    path: Path,
    *,
    seconds: float,
    bootstrap_mode: str | None = None,
) -> tuple[SportradarSessionState, BootstrapSessionManager]:
    """Load cached state or bootstrap according to `bootstrap_mode`.

    Args:
        path: JSON state file.
        seconds: Wait time per bootstrap URL when a refresh is needed.
        bootstrap_mode: `headless`, `headed`, or `auto`.

    Returns:
        `(state, manager)` where manager can refresh later if the HTTP client
        detects an expired/blocked token.
    """

    manager = BootstrapSessionManager(mode=bootstrap_mode, seconds_per_url=seconds)
    if path.exists():
        state = load_session_state(path)
        if state.signed_token and not state.signed_token.is_expired():
            manager.state = state
            return state, manager
    state = manager.refresh_session()
    save_session_state(state, path)
    return state, manager

"""Per-platform HTTP proxy selection (selective egress routing).

Some books block the VPS datacenter IP (e.g. MrPunter, Solcasino) and need to
egress through a VPN (``BOT_PROXY_URL``, a wireproxy SOCKS). But others —
especially geo-locked Argentine books (Betsson, BetWarrior) — break when routed
through a foreign VPN exit (they 302-redirect to the wrong country site). So
routing must be *selective*, not all-or-nothing.

Two modes, driven by env:

- **Selective** (``BOT_PROXY_PLATFORMS`` set): only the listed platform keys
  egress through ``BOT_PROXY_URL``; everything else (other books, Telegram,
  Sportradar) goes direct. No global ``ALL_PROXY`` is exported.
- **Legacy** (``BOT_PROXY_PLATFORMS`` empty): ``bot.config`` exports
  ``ALL_PROXY`` so every client goes through the proxy (old behaviour). Here
  :func:`proxy_for_platform` returns ``None`` and lets the env var govern.
"""

from __future__ import annotations

import os


def _proxy_url() -> str:
    return (os.getenv("BOT_PROXY_URL") or "").strip()


def proxy_platforms() -> set[str]:
    """Platform keys (e.g. ``mrpunter_http``) that must egress through the proxy."""

    raw = os.getenv("BOT_PROXY_PLATFORMS") or ""
    return {part.strip() for part in raw.split(",") if part.strip()}


def proxy_for_platform(platform: str) -> str | None:
    """Return the proxy URL a platform's HTTP client should use, or None (direct).

    None in legacy mode (no whitelist) — the global ALL_PROXY env handles it — and
    None for platforms outside the whitelist in selective mode.
    """

    url = _proxy_url()
    if not url:
        return None
    whitelist = proxy_platforms()
    if not whitelist:
        return None  # legacy: ALL_PROXY (set by bot.config) governs every client
    return url if platform in whitelist else None

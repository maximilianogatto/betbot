"""Bootstrap helpers for concrete sportsbook extractors."""

from __future__ import annotations

from typing import Any

from core.extractor_base import Extractor
from core.registry import ExtractorRegistry
from extractors.bet365 import Bet365Extractor, Bet365ExtractorSettings
from extractors.xbet_http import XBetHttpExtractor


def register_default_extractors(
    registry: ExtractorRegistry,
    *,
    settings: Any | None = None,
) -> list[Extractor]:
    """Register the built-in extractor set used by the current bot."""

    bet365_extractor = registry.register(
        Bet365Extractor(settings=_build_bet365_settings(settings))
    )
    xbet_http_extractor = registry.register(XBetHttpExtractor())
    return [bet365_extractor, xbet_http_extractor]


def _build_bet365_settings(settings: Any | None) -> Bet365ExtractorSettings | None:
    """Translate generic app settings into the concrete Bet365 extractor config."""

    if settings is None:
        return None

    return Bet365ExtractorSettings(
        max_parallel_competitions=int(getattr(settings, "extractor_max_parallel_competitions")),
        max_parallel_pages=int(getattr(settings, "extractor_max_parallel_pages")),
        max_parallel_event_pages=int(getattr(settings, "extractor_max_parallel_event_pages")),
        page_reuse_enabled=bool(getattr(settings, "extractor_page_reuse_enabled")),
        browser_restart_after_n_refreshes=getattr(
            settings,
            "extractor_browser_restart_after_n_refreshes",
        ),
        browser_restart_idle_ttl_seconds=getattr(
            settings,
            "extractor_browser_restart_idle_ttl_seconds",
        ),
        page_load_timeout_ms=int(getattr(settings, "extractor_page_load_timeout_ms")),
        post_load_wait_ms=int(getattr(settings, "extractor_post_load_wait_ms")),
        headless=bool(getattr(settings, "extractor_headless")),
        capture_wait_timeout_ms=int(getattr(settings, "extractor_capture_wait_timeout_ms")),
        capture_stable_ms=int(getattr(settings, "extractor_capture_stable_ms")),
        capture_attempts=int(getattr(settings, "extractor_capture_attempts")),
        event_capture_wait_timeout_ms=int(
            getattr(settings, "extractor_event_capture_wait_timeout_ms")
        ),
        event_capture_stable_ms=int(getattr(settings, "extractor_event_capture_stable_ms")),
        event_capture_attempts=int(getattr(settings, "extractor_event_capture_attempts")),
        save_debug_payloads=bool(getattr(settings, "extractor_save_debug_payloads")),
        debug_payload_dir=getattr(settings, "extractor_debug_payload_dir"),
        extract_alternative_markets=bool(
            getattr(settings, "extractor_extract_alternative_markets")
        ),
        allow_legacy_fallback=bool(getattr(settings, "bet365_allow_legacy_fallback")),
    )


__all__ = ["Bet365Extractor", "XBetHttpExtractor", "register_default_extractors"]

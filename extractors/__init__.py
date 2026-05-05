"""Bootstrap helpers for concrete sportsbook extractors."""

from __future__ import annotations

from typing import Any

from core.extractor_base import Extractor
from core.registry import ExtractorRegistry
from extractors.bet365 import Bet365Extractor, Bet365ExtractorSettings


def register_default_extractors(
    registry: ExtractorRegistry,
    *,
    settings: Any | None = None,
) -> list[Extractor]:
    """Register the built-in extractor set used by the current bot."""

    bet365_extractor = registry.register(
        Bet365Extractor(settings=_build_bet365_settings(settings))
    )
    return [bet365_extractor]


def _build_bet365_settings(settings: Any | None) -> Bet365ExtractorSettings | None:
    """Translate generic app settings into the concrete Bet365 extractor config."""

    if settings is None:
        return None

    return Bet365ExtractorSettings(
        max_parallel_pages=int(getattr(settings, "extractor_max_parallel_pages")),
        page_load_timeout_ms=int(getattr(settings, "extractor_page_load_timeout_ms")),
        post_load_wait_ms=int(getattr(settings, "extractor_post_load_wait_ms")),
    )


__all__ = ["Bet365Extractor", "register_default_extractors"]

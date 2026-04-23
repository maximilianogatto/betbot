"""Bootstrap helpers for concrete sportsbook extractors."""

from __future__ import annotations

from core.extractor_base import Extractor
from core.registry import ExtractorRegistry
from extractors.bet365 import Bet365Extractor
from services.bet365_extractor import Bet365ExtractorSettings


def register_default_extractors(
    registry: ExtractorRegistry,
    *,
    bet365_settings: Bet365ExtractorSettings | None = None,
) -> list[Extractor]:
    """Register the built-in extractor set used by the current bot."""

    bet365_extractor = registry.register(Bet365Extractor(settings=bet365_settings))
    return [bet365_extractor]


__all__ = ["Bet365Extractor", "register_default_extractors"]

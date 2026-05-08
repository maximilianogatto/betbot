"""Core abstractions shared by concrete betting-site extractors."""

from core.browser_handler import BrowserHandler, BrowserHandlerSettings
from core.extractor_base import Extractor
from core.models import (
    CompetitionExtraction,
    CompetitionKey,
    EventKey,
    EventSnapshot,
    Odds1X2,
    PlatformDescriptor,
    platform_display_name,
)
from core.registry import ExtractorRegistry, extractor_registry

__all__ = [
    "BrowserHandler",
    "BrowserHandlerSettings",
    "CompetitionExtraction",
    "CompetitionKey",
    "EventKey",
    "EventSnapshot",
    "Extractor",
    "ExtractorRegistry",
    "Odds1X2",
    "PlatformDescriptor",
    "extractor_registry",
    "platform_display_name",
]

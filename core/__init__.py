"""Core abstractions shared by concrete betting-site extractors."""

from core.extractor_base import Extractor
from core.models import CompetitionExtraction, CompetitionKey, EventKey, EventSnapshot, Odds1X2
from core.registry import ExtractorRegistry, extractor_registry

__all__ = [
    "CompetitionExtraction",
    "CompetitionKey",
    "EventKey",
    "EventSnapshot",
    "Extractor",
    "ExtractorRegistry",
    "Odds1X2",
    "extractor_registry",
]

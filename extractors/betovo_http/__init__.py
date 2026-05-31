"""Betovo (Altenar) prematch HTTP extractor package."""

from extractors.betovo_http.extractor import BetovoHttpExtractor
from extractors.betovo_http.settings import BetovoHttpSettings, betovo_is_configured

__all__ = ["BetovoHttpExtractor", "BetovoHttpSettings", "betovo_is_configured"]

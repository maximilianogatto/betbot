"""Betsson (OBG) prematch + live HTTP extractor package."""

from extractors.betsson_http.extractor import BetssonHttpExtractor
from extractors.betsson_http.settings import BetssonHttpSettings, betsson_is_configured

__all__ = ["BetssonHttpExtractor", "BetssonHttpSettings", "betsson_is_configured"]

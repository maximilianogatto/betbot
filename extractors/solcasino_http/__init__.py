"""Solcasino (Betby/sptpub) prematch HTTP extractor package."""

from extractors.solcasino_http.extractor import SolcasinoHttpExtractor
from extractors.solcasino_http.settings import SolcasinoHttpSettings, solcasino_is_configured

__all__ = ["SolcasinoHttpExtractor", "SolcasinoHttpSettings", "solcasino_is_configured"]

"""Registry for resolving the right extractor for a sportsbook URL."""

from __future__ import annotations

from collections.abc import Iterable

from core.extractor_base import Extractor
from core.models import PlatformDescriptor


class ExtractorRegistry:
    """Hold concrete extractor instances and resolve them by URL."""

    def __init__(self) -> None:
        self._extractors: list[Extractor] = []

    def register(self, extractor: type[Extractor] | Extractor) -> Extractor:
        """Register one extractor class or instance and return the instance."""

        instance = extractor() if isinstance(extractor, type) else extractor

        if any(existing.name == instance.name for existing in self._extractors):
            self._extractors = [
                existing for existing in self._extractors if existing.name != instance.name
            ]

        self._extractors.append(instance)
        return instance

    def get_for_url(self, url: str) -> Extractor:
        """Return the first registered extractor that can handle the URL."""

        for extractor in self._extractors:
            if extractor.can_handle_url(url):
                return extractor

        raise ValueError(f"No registered extractor can handle URL: {url}")

    def list_registered(self) -> list[Extractor]:
        """Return the currently registered extractor instances."""

        return list(self._extractors)

    def list_platforms(self) -> list[PlatformDescriptor]:
        """Return the platform metadata for every registered extractor."""

        return [extractor.describe_platform() for extractor in self._extractors]

    def replace_all(self, extractors: Iterable[type[Extractor] | Extractor]) -> None:
        """Replace the full registry contents with a new ordered extractor set."""

        self._extractors = []
        for extractor in extractors:
            self.register(extractor)


extractor_registry = ExtractorRegistry()

__all__ = ["ExtractorRegistry", "extractor_registry"]

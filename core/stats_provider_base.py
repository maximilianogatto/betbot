"""Abstract interface for match statistics providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.stats_models import (
    MatchIdentityCandidate,
    MatchStatsReport,
    StatsFixture,
    StatsLeagueOption,
    StatsMatchLink,
    StatsProviderCapabilities,
    StatsProviderDescriptor,
)


class StatsProvider(ABC):
    """Common interface for providers such as Sportradar Statshub.

    The interface is intentionally narrower than sportsbook extractors. A stats
    provider does not own odds tracking. It discovers/link stats fixtures and
    generates reports that Telegram can render.
    """

    name: str
    display_name: str = ""
    capabilities: StatsProviderCapabilities = StatsProviderCapabilities()
    implemented: bool = True

    async def start(self) -> None:
        """Start optional provider resources."""

    async def stop(self) -> None:
        """Stop optional provider resources."""

    @abstractmethod
    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[StatsLeagueOption]:
        """Search provider-native leagues by country/query."""

    @abstractmethod
    async def list_fixtures(self, league_id: str, *, limit: int | None = None) -> list[StatsFixture]:
        """List fixtures for one provider-native league id."""

    @abstractmethod
    async def resolve_match(
        self,
        candidate: MatchIdentityCandidate,
        *,
        league_id: str | None = None,
    ) -> StatsMatchLink | None:
        """Resolve one odds event to a provider-native stats match."""

    @abstractmethod
    async def build_match_report(self, stats_match_id: str) -> MatchStatsReport:
        """Build a compact match report for Telegram or future agents."""

    def build_match_url(self, stats_match_id: str) -> str | None:
        """Return a provider URL for one stats match when available."""

        del stats_match_id
        return None

    def describe_provider(self) -> StatsProviderDescriptor:
        """Return provider metadata for UI flows."""

        return StatsProviderDescriptor(
            key=self.name,
            display_name=self.display_name or self.name.replace("_", " ").title(),
            capabilities=self.capabilities,
            implemented=self.implemented,
        )


class StatsProviderRegistry:
    """Hold stats provider instances and resolve them by provider key."""

    def __init__(self) -> None:
        self._providers: list[StatsProvider] = []

    def register(self, provider: type[StatsProvider] | StatsProvider) -> StatsProvider:
        """Register one provider class or instance and return the instance."""

        instance = provider() if isinstance(provider, type) else provider
        self._providers = [existing for existing in self._providers if existing.name != instance.name]
        self._providers.append(instance)
        return instance

    def get(self, provider_key: str) -> StatsProvider:
        """Return a registered provider by key."""

        normalized_key = provider_key.strip().lower()
        for provider in self._providers:
            if provider.name == normalized_key:
                return provider
        raise ValueError(f"No registered stats provider found for: {provider_key}")

    def list_registered(self) -> list[StatsProvider]:
        """Return registered provider instances."""

        return list(self._providers)

    def list_providers(self) -> list[StatsProviderDescriptor]:
        """Return metadata for registered providers."""

        return [provider.describe_provider() for provider in self._providers]


stats_provider_registry = StatsProviderRegistry()


__all__ = [
    "StatsProvider",
    "StatsProviderRegistry",
    "stats_provider_registry",
]

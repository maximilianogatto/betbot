"""Abstract extractor interface for sportsbook-specific scrapers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from core.models import (
    CompetitionExtraction,
    EventSnapshot,
    LiveEventSnapshot,
    PlatformDescriptor,
    ProviderCapabilities,
    platform_display_name,
)


class CompetitionUnavailableError(RuntimeError):
    """Signal a controlled competition refresh failure from an extractor.

    Extractors should raise this when the source URL is syntactically supported
    but the competition currently cannot be refreshed in a trustworthy way, for
    example because the source is temporarily empty, removed, or still exposing
    an incomplete page/runtime state after retries.
    """

    def __init__(
        self,
        message: str,
        *,
        platform: str | None = None,
        source_url: str | None = None,
        reason_code: str = "competition_unavailable",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.platform = platform
        self.source_url = source_url
        self.reason_code = reason_code
        self.details = details or {}


@dataclass(frozen=True)
class LeagueDiscoveryOption:
    """Represent one platform-native league that can be tracked without pasting a URL."""

    platform: str
    platform_display_name: str
    country_id: str | None
    country_name: str
    league_id: str
    league_name: str
    source_url: str
    games_count: int | None = None
    raw_payload: dict[str, Any] | None = None


class Extractor(ABC):
    """Common interface implemented by each sportsbook extractor.

    A future platform should only need to:

    1. decide whether it can handle a URL
    2. expose a stable platform key plus optional display metadata
    3. return a `CompetitionExtraction` for competition URLs
    4. optionally return an `EventSnapshot` for direct event URLs

    The rest of the tracking stack can then operate on the generic models
    without knowing platform-specific parsing details.
    """

    name: str
    display_name: str = ""
    supported_domains: tuple[str, ...] = ()
    supported_capabilities: tuple[str, ...] = ("ligas",)
    provider_capabilities: ProviderCapabilities = ProviderCapabilities()
    implemented: bool = True
    supports_league_discovery: bool = False
    supports_live_detection: bool = False

    @classmethod
    @abstractmethod
    def can_handle_url(cls, url: str) -> bool:
        """Return whether this extractor can handle the given URL."""

    @abstractmethod
    async def extract_league(self, url: str) -> CompetitionExtraction:
        """Extract one competition payload from a sportsbook URL.

        The returned `CompetitionExtraction` must include a stable
        `platform + competition_external_id` identity plus normalized event
        snapshots for any currently visible events.
        """

    @abstractmethod
    async def extract_match(self, url: str) -> EventSnapshot:
        """Extract one event payload from a sportsbook URL."""

    async def start(self) -> None:
        """Start any optional shared runtime resources for the extractor."""

    async def stop(self) -> None:
        """Stop any optional shared runtime resources for the extractor."""

    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[LeagueDiscoveryOption]:
        """Return trackable leagues discovered by country for platforms that support it."""

        del country_name, query, limit
        raise NotImplementedError(f"{self.name} does not support league discovery.")

    async def list_live_events(self) -> list["LiveEventSnapshot"]:
        """Return the platform's currently in-play soccer events.

        Used by the live-watch poller to detect when a watched fixture goes live.
        Platforms that cannot expose live over plain HTTP leave this unimplemented.
        """

        raise NotImplementedError(f"{self.name} does not support live detection.")

    def build_competition_url(
        self,
        *,
        competition_external_id: str,
        source_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Return a usable competition URL when the platform supports it."""

        del competition_external_id, metadata
        return source_url

    def build_event_url(
        self,
        *,
        competition_external_id: str,
        external_event_id: str,
        source_url: str | None = None,
        event_url: str | None = None,
        competition_metadata: dict[str, Any] | None = None,
        event_metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Return a usable event URL when the platform supports direct event links."""

        del competition_external_id, external_event_id, source_url, competition_metadata, event_metadata
        return event_url

    def describe_platform(self) -> PlatformDescriptor:
        """Return the platform metadata exposed by this extractor."""

        return PlatformDescriptor(
            key=self.name,
            display_name=self.display_name or platform_display_name(self.name),
            domains=self.supported_domains,
            supports=self.supported_capabilities,
            implemented=self.implemented,
            capabilities=self.provider_capabilities,
        )

"""Domain models and provider interfaces for sports event data.

This module defines the event shape expected by the monitoring pipeline and a
very small provider abstraction. It does not implement a real API client yet;
instead, it documents the contract future providers should satisfy.
"""

from dataclasses import dataclass


@dataclass
class SportsEvent:
    """Represent one sports event consumed by the monitoring pipeline.

    Attributes:
        event_id (str): Stable identifier of the event in the upstream data
            source.
        sport (str): Sport category, for example `"football"`.
        league (str): League or competition name or identifier.
        home_team (str): Home-side participant.
        away_team (str): Away-side participant.
        starts_at (str): Start date/time represented as a string for now.

    Notes:
        This dataclass is shared across `services`, `monitors`, and `alerts`,
        which makes the future monitoring pipeline easier to understand.
    """

    event_id: str
    sport: str
    league: str
    home_team: str
    away_team: str
    starts_at: str


class SportsAPIClient:
    """Abstract-style base for future sports data providers.

    Notes:
        Concrete implementations may later call REST APIs, SDKs, or scraping
        code. For now this class only documents the interface expected by
        `jobs.scheduler.run_monitoring_cycle()`.
    """

    async def fetch_events(self) -> list[SportsEvent]:
        """Fetch sports events from the underlying provider.

        Returns:
            list[SportsEvent]: Events available for evaluation in the current
            monitoring cycle.

        Raises:
            NotImplementedError: Always, until a concrete provider implements
            the method.

        Notes:
            The method is async because real providers will almost certainly
            perform network I/O. It is consumed by the monitoring scheduler,
            not by Telegram handlers directly.
        """

        raise NotImplementedError("Implementá fetch_events() en un cliente concreto.")

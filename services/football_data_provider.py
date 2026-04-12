"""Football-data provider abstractions and local mock implementation.

This module is the source of fixtures and standings used by the weekly
watchlist builder. At this stage the project intentionally avoids real APIs,
scraping, or betting integrations, so the default provider is a local mock
dataset.

The design still leaves room for growth:

- today: local mock provider for fixtures and standings
- next: real fixture/statistics API
- later: separate odds provider that consumes the saved watchlist

That separation is important because watchlist generation should answer
"which fixtures look uneven?" before any odds-based filter is introduced.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import asyncio
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Fixture:
    """Represent one upcoming football fixture.

    Attributes:
        fixture_id (str): Stable identifier in the current provider.
        league_code (str): Internal code of the fixture's league.
        league_name (str): Human-readable league name.
        home_team (str): Home team name.
        away_team (str): Away team name.
        kickoff_at (datetime): Scheduled kickoff date/time in UTC.
    """

    fixture_id: str
    league_code: str
    league_name: str
    home_team: str
    away_team: str
    kickoff_at: datetime


@dataclass(frozen=True)
class StandingEntry:
    """Represent one team row in league standings.

    Attributes:
        league_code (str): League identifier shared with tracked targets.
        team_name (str): Team name used to match fixtures and standings.
        position (int): Current position in the table. Lower is better.
        points (int): Current league points total.
        goal_difference (int): Current goal-difference value.
    """

    league_code: str
    team_name: str
    position: int
    points: int
    goal_difference: int


class FootballDataProvider:
    """Abstract interface for providers of fixtures and standings."""

    async def get_upcoming_fixtures(
        self,
        league_code: str,
        days_ahead: int = 7,
    ) -> list[Fixture]:
        """Return upcoming fixtures for one league."""

        raise NotImplementedError("Implementá get_upcoming_fixtures() en un proveedor concreto.")

    async def get_standings(self, league_code: str) -> list[StandingEntry]:
        """Return standings rows for one league."""

        raise NotImplementedError("Implementá get_standings() en un proveedor concreto.")


class MockFootballDataProvider(FootballDataProvider):
    """In-memory provider used to develop the watchlist flow locally.

    The mock data intentionally includes both balanced and imbalanced fixtures
    so the watchlist builder can be tested without relying on external APIs.
    """

    def __init__(self) -> None:
        """Initialize reusable mock standings and league metadata."""

        self._league_names = {
            "premier_league": "Premier League",
            "la_liga": "La Liga",
            "serie_a": "Serie A",
        }
        self._standings = {
            "premier_league": [
                StandingEntry("premier_league", "Arsenal", 1, 74, 42),
                StandingEntry("premier_league", "Liverpool", 2, 71, 39),
                StandingEntry("premier_league", "Chelsea", 5, 58, 14),
                StandingEntry("premier_league", "Everton", 14, 35, -10),
                StandingEntry("premier_league", "Ipswich", 18, 23, -27),
                StandingEntry("premier_league", "Southampton", 20, 18, -34),
            ],
            "la_liga": [
                StandingEntry("la_liga", "Real Madrid", 1, 76, 48),
                StandingEntry("la_liga", "Barcelona", 2, 73, 43),
                StandingEntry("la_liga", "Villarreal", 5, 56, 11),
                StandingEntry("la_liga", "Getafe", 14, 34, -11),
                StandingEntry("la_liga", "Leganes", 19, 22, -29),
                StandingEntry("la_liga", "Las Palmas", 20, 20, -31),
            ],
            "serie_a": [
                StandingEntry("serie_a", "Inter", 1, 79, 44),
                StandingEntry("serie_a", "Napoli", 3, 67, 24),
                StandingEntry("serie_a", "Roma", 6, 57, 10),
                StandingEntry("serie_a", "Empoli", 16, 30, -17),
                StandingEntry("serie_a", "Venezia", 18, 25, -22),
                StandingEntry("serie_a", "Monza", 20, 19, -33),
            ],
        }

    async def get_upcoming_fixtures(
        self,
        league_code: str,
        days_ahead: int = 7,
    ) -> list[Fixture]:
        """Return mock fixtures for the next `days_ahead` days.

        Args:
            league_code (str): League identifier requested by the watchlist
                builder.
            days_ahead (int): Future window inspected for fixtures.

        Returns:
            list[Fixture]: Fixtures scheduled inside the requested time window.

        Raises:
            LookupError: If the mock dataset does not know the requested league.

        Notes:
            The coroutine awaits `asyncio.sleep(0)` to behave like a non-
            blocking provider and to match the future async API shape.
        """

        await asyncio.sleep(0)

        if league_code not in self._league_names:
            raise LookupError(f"No mock fixture data available for league {league_code}.")

        now = datetime.now(timezone.utc)
        window_end = now + timedelta(days=days_ahead)
        fixtures = [
            fixture
            for fixture in self._build_mock_fixtures(now).get(league_code, [])
            if now <= fixture.kickoff_at <= window_end
        ]

        fixtures.sort(key=lambda fixture: fixture.kickoff_at)
        return fixtures

    async def get_standings(self, league_code: str) -> list[StandingEntry]:
        """Return mock standings rows for one league.

        Args:
            league_code (str): League identifier requested by the builder.

        Returns:
            list[StandingEntry]: Current mock standings rows for the league.

        Raises:
            LookupError: If the league is unknown to the mock dataset.
        """

        await asyncio.sleep(0)

        if league_code not in self._standings:
            raise LookupError(f"No mock standings data available for league {league_code}.")

        return list(self._standings[league_code])

    def _build_mock_fixtures(self, now: datetime) -> dict[str, list[Fixture]]:
        """Generate time-relative mock fixtures for all supported leagues."""

        return {
            "premier_league": [
                Fixture(
                    fixture_id="epl-001",
                    league_code="premier_league",
                    league_name=self._league_names["premier_league"],
                    home_team="Arsenal",
                    away_team="Ipswich",
                    kickoff_at=now + timedelta(days=2, hours=4),
                ),
                Fixture(
                    fixture_id="epl-002",
                    league_code="premier_league",
                    league_name=self._league_names["premier_league"],
                    home_team="Chelsea",
                    away_team="Southampton",
                    kickoff_at=now + timedelta(days=4, hours=2),
                ),
                Fixture(
                    fixture_id="epl-003",
                    league_code="premier_league",
                    league_name=self._league_names["premier_league"],
                    home_team="Liverpool",
                    away_team="Everton",
                    kickoff_at=now + timedelta(days=5, hours=1),
                ),
            ],
            "la_liga": [
                Fixture(
                    fixture_id="laliga-001",
                    league_code="la_liga",
                    league_name=self._league_names["la_liga"],
                    home_team="Real Madrid",
                    away_team="Leganes",
                    kickoff_at=now + timedelta(days=1, hours=6),
                ),
                Fixture(
                    fixture_id="laliga-002",
                    league_code="la_liga",
                    league_name=self._league_names["la_liga"],
                    home_team="Barcelona",
                    away_team="Getafe",
                    kickoff_at=now + timedelta(days=3, hours=5),
                ),
                Fixture(
                    fixture_id="laliga-003",
                    league_code="la_liga",
                    league_name=self._league_names["la_liga"],
                    home_team="Villarreal",
                    away_team="Las Palmas",
                    kickoff_at=now + timedelta(days=6, hours=2),
                ),
            ],
            "serie_a": [
                Fixture(
                    fixture_id="seriea-001",
                    league_code="serie_a",
                    league_name=self._league_names["serie_a"],
                    home_team="Inter",
                    away_team="Monza",
                    kickoff_at=now + timedelta(days=2, hours=1),
                ),
                Fixture(
                    fixture_id="seriea-002",
                    league_code="serie_a",
                    league_name=self._league_names["serie_a"],
                    home_team="Napoli",
                    away_team="Empoli",
                    kickoff_at=now + timedelta(days=4, hours=4),
                ),
                Fixture(
                    fixture_id="seriea-003",
                    league_code="serie_a",
                    league_name=self._league_names["serie_a"],
                    home_team="Roma",
                    away_team="Venezia",
                    kickoff_at=now + timedelta(days=6, hours=3),
                ),
            ],
        }


def create_football_data_provider(
    provider_name: str,
    api_key: str | None = None,
) -> FootballDataProvider:
    """Create a football-data provider from configuration.

    Args:
        provider_name (str): Provider identifier from environment settings.
        api_key (str | None): Optional API key reserved for future real
            integrations.

    Returns:
        FootballDataProvider: Provider instance ready to serve fixtures and
        standings.

    Notes:
        Only the mock provider is implemented at this stage. Unknown provider
        names gracefully fall back to the mock implementation so the bot stays
        usable while the architecture grows.
    """

    normalized_name = provider_name.strip().lower()

    if normalized_name == "mock":
        return MockFootballDataProvider()

    logger.warning(
        "Provider '%s' is not implemented yet. Falling back to the mock provider. "
        "Configured API key present: %s",
        normalized_name,
        "yes" if api_key else "no",
    )
    return MockFootballDataProvider()

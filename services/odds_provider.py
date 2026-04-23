"""Future extension point for pre-match odds providers.

The watchlist stage of the project intentionally stops after fixture analysis.
This module marks the next architectural step: a separate odds provider that
can inspect saved watchlist fixtures and decide whether a match is available in
pre-match markets.

Keeping this interface separate from `services.football_data_provider` avoids
mixing two different responsibilities:

- football data: fixtures and standings
- odds data: market availability and price information
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PreMatchOdds:
    """Represent a simplified pre-match odds snapshot for one fixture.

    Attributes:
        fixture_id (str): Identifier used to match a saved watchlist fixture.
        home_win (float | None): Price for the home team to win.
        draw (float | None): Price for the draw.
        away_win (float | None): Price for the away team to win.
    """

    fixture_id: str
    home_win: float | None
    draw: float | None
    away_win: float | None


class OddsProvider:
    """Abstract interface for future odds integrations."""

    async def get_pre_match_odds(self, fixture_id: str) -> PreMatchOdds | None:
        """Return pre-match odds for a fixture when available.

        Args:
            fixture_id (str): Fixture identifier from the watchlist.

        Returns:
            PreMatchOdds | None: Odds snapshot when the fixture is listed,
            otherwise `None`.

        Raises:
            NotImplementedError: Always, until a concrete odds provider is
                implemented.
        """

        raise NotImplementedError("Implementá get_pre_match_odds() en un proveedor concreto.")

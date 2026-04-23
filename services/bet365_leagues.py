"""Static Bet365 league catalog used by the incremental integration.

This module is intentionally small and isolated. It does not scrape Bet365,
talk to Telegram, or touch the database. Its only responsibility is to define
which Bet365 leagues are currently known by the project and expose small read
helpers around that catalog.

Keeping the catalog in code is a good fit for the first integration step:

- it is easy to review and version in Git
- it keeps platform-specific URLs away from bot handlers
- it gives the next scraper step a stable contract
- it lets the persistence layer validate leagues without coupling to Telegram

The next integration step can safely reuse this module to decide which league
URL should be opened by Playwright for a given `(platform, league_key)` pair.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Bet365LeagueConfig:
    """Represent one known league entry in the Bet365 catalog.

    Attributes:
        platform (str): Betting platform identifier. For this initial catalog
            the value is always `"bet365"`.
        country (str): Country associated with the league.
        league_key (str): Stable internal identifier used across the project,
            such as `"la_liga"` or `"premier_league"`.
        league_name (str): Human-readable league name.
        url (str): Direct Bet365 URL that opens the league page.
        enabled (bool): Whether the league is currently active for future
            scraping and monitoring flows.

    Notes:
        This dataclass is shared conceptually by the catalog and the
        persistence bootstrap layer. It gives the project one clear source of
        truth for league metadata before a larger admin or configuration
        system exists.
    """

    platform: str
    country: str
    league_key: str
    league_name: str
    url: str
    enabled: bool = True


_LEAGUE_CATALOG: dict[tuple[str, str], Bet365LeagueConfig] = {
    ("bet365", "la_liga_españa"): Bet365LeagueConfig(
        platform="bet365",
        country="Spain",
        league_key="la_liga",
        league_name="La Liga",
        url="https://www.bet365.es/#/AC/B1/C1/D1002/E120757998/G40/",
        enabled=True,
    ),
    ("bet365", "segunda_division"): Bet365LeagueConfig(
        platform="bet365",
        country="Spain",
        league_key="segunda_division",
        league_name="Segunda Division",
        url="https://www.bet365.es/#/AC/B1/C1/D1002/E120794896/G40/",
        enabled=True,
    ),
    ("bet365", "premier_league"): Bet365LeagueConfig(
        platform="bet365",
        country="England",
        league_key="premier_league",
        league_name="Premier League",
        url="https://www.bet365.es/#/AC/B1/C1/D1002/E91422157/G40/",
        enabled=True,
    ),
}


def get_league_config(platform: str, league_key: str) -> Bet365LeagueConfig | None:
    """Return the catalog entry for one `(platform, league_key)` pair.

    Args:
        platform (str): Platform identifier, for example `"bet365"`.
        league_key (str): Internal league key, for example `"la_liga"`.

    Returns:
        Bet365LeagueConfig | None: Matching catalog entry when known,
        otherwise `None`.

    Notes:
        This function is intended to be the main read entry point for the next
        scraper integration step. A scraper can call it to translate a tracked
        league key into the exact Bet365 URL it must open.
    """

    normalized_platform = _normalize_identifier(platform)
    normalized_league_key = _normalize_identifier(league_key)

    return _LEAGUE_CATALOG.get((normalized_platform, normalized_league_key))


def list_known_leagues(platform: str | None = None) -> list[Bet365LeagueConfig]:
    """List every known league defined in the static catalog.

    Args:
        platform (str | None): Optional platform filter. When omitted, leagues
            from every supported platform are returned.

    Returns:
        list[Bet365LeagueConfig]: Known catalog entries sorted in a stable
        order for predictable reads and database bootstrap operations.

    Notes:
        This helper is mainly used by the persistence layer to register known
        leagues in the database without retyping catalog data.
    """

    normalized_platform = _normalize_identifier(platform) if platform else None

    leagues = [
        config
        for config in _LEAGUE_CATALOG.values()
        if normalized_platform is None or config.platform == normalized_platform
    ]

    return sorted(
        leagues,
        key=lambda config: (config.platform, config.country, config.league_name, config.league_key),
    )


def list_enabled_leagues(platform: str | None = None) -> list[Bet365LeagueConfig]:
    """List enabled league entries for one platform or for the full catalog.

    Args:
        platform (str | None): Optional platform filter. When omitted, enabled
            leagues across every supported platform are returned.

    Returns:
        list[Bet365LeagueConfig]: Enabled catalog entries only.

    Notes:
        The next Bet365 scraping step can use this function to discover which
        leagues are currently allowed to run without touching disabled
        entries.
    """

    return [config for config in list_known_leagues(platform=platform) if config.enabled]


def _normalize_identifier(value: str) -> str:
    """Normalize identifiers before using them as catalog keys.

    Args:
        value (str): Raw identifier received from callers.

    Returns:
        str: Lowercased and trimmed identifier.
    """

    return value.strip().lower()

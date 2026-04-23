"""Watchlist-building logic for the weekly fixture analysis stage.

This module turns tracked leagues into a saved weekly watchlist:

1. Read tracked leagues for one Telegram chat.
2. Ask a football-data provider for upcoming fixtures and standings.
3. Calculate an `imbalance_score` for each fixture.
4. Keep only the fixtures that look uneven enough.
5. Persist the selected fixtures in `storage.watchlist`.

The builder intentionally stops before odds analysis. That separation is
important because it keeps the first-stage watchlist independent from any
betting provider or scraping logic. A future odds provider can later consume
this saved watchlist as a second-stage filter.
"""

from dataclasses import dataclass
from datetime import datetime
import logging

from monitors.imbalance import calculate_imbalance_score
from services.football_data_provider import FootballDataProvider, StandingEntry
from storage.tracks import list_tracks
from storage.watchlist import WatchlistMatch, clear_watchlist, load_watchlist, save_watchlist

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WatchlistBuildResult:
    """Summarize the outcome of one watchlist build operation.

    Attributes:
        tracked_leagues (list[str]): League codes tracked by the current chat
            at the time the build started.
        matches (list[WatchlistMatch]): Fixtures that passed the imbalance
            threshold and were saved to the watchlist.
        inspected_fixtures (int): Number of fixtures that could be evaluated
            with standings data.
        skipped_leagues (list[str]): League codes skipped because the current
            provider had no usable data for them.
    """

    tracked_leagues: list[str]
    matches: list[WatchlistMatch]
    inspected_fixtures: int
    skipped_leagues: list[str]


class WeeklyWatchlistBuilder:
    """Build and load weekly watchlists for Telegram chats.

    The builder acts as an orchestration layer between tracked leagues,
    standings analysis, and watchlist storage. It is used by the
    `/build_watchlist` and `/list_watchlist` Telegram commands.
    """

    def __init__(
        self,
        provider: FootballDataProvider,
        days_ahead: int = 7,
        imbalance_threshold: float = 60.0,
    ) -> None:
        """Initialize the builder with a football-data provider and settings.

        Args:
            provider (FootballDataProvider): Source of fixtures and standings.
            days_ahead (int): Future window inspected when building the
                watchlist.
            imbalance_threshold (float): Minimum score required for a fixture
                to become a saved watchlist candidate.
        """

        self.provider = provider
        self.days_ahead = days_ahead
        self.imbalance_threshold = imbalance_threshold

    async def build_for_chat(self, chat_id: int) -> WatchlistBuildResult:
        """Build and persist the weekly watchlist for one Telegram chat.

        Args:
            chat_id (int): Telegram chat whose tracked leagues should be
                analyzed.

        Returns:
            WatchlistBuildResult: Summary of the build operation, including the
            saved matches.

        Side Effects:
            Reads tracked leagues from local storage and writes the resulting
            watchlist to `storage.watchlist`.

        Notes:
            This function is async because the provider may eventually perform
            network I/O for fixtures and standings, even though the current
            mock provider is local.
        """

        tracked_leagues = sorted(
            track.key for track in list_tracks(chat_id) if track.type == "league"
        )

        if not tracked_leagues:
            clear_watchlist(chat_id)
            return WatchlistBuildResult(
                tracked_leagues=[],
                matches=[],
                inspected_fixtures=0,
                skipped_leagues=[],
            )

        candidates: list[WatchlistMatch] = []
        inspected_fixtures = 0
        skipped_leagues: list[str] = []

        for league_code in tracked_leagues:
            try:
                standings = await self.provider.get_standings(league_code)
                fixtures = await self.provider.get_upcoming_fixtures(
                    league_code,
                    days_ahead=self.days_ahead,
                )
            except LookupError:
                logger.info(
                    "Skipping league %s because the provider has no data for it.",
                    league_code,
                )
                skipped_leagues.append(league_code)
                continue

            standings_index = _index_standings_by_team(standings)

            for fixture in fixtures:
                home_entry = standings_index.get(_normalize_team_name(fixture.home_team))
                away_entry = standings_index.get(_normalize_team_name(fixture.away_team))

                if home_entry is None or away_entry is None:
                    logger.info(
                        "Skipping fixture %s because standings data is incomplete for %s vs %s.",
                        fixture.fixture_id,
                        fixture.home_team,
                        fixture.away_team,
                    )
                    continue

                inspected_fixtures += 1
                assessment = calculate_imbalance_score(home_entry, away_entry)

                if assessment.score < self.imbalance_threshold:
                    continue

                candidates.append(
                    WatchlistMatch(
                        fixture_id=fixture.fixture_id,
                        league_code=fixture.league_code,
                        league_name=fixture.league_name,
                        home_team=fixture.home_team,
                        away_team=fixture.away_team,
                        kickoff_at=fixture.kickoff_at.isoformat(),
                        imbalance_score=assessment.score,
                        reasons=assessment.reasons,
                        odds_seen=False,
                        alert_sent=False,
                    )
                )

        candidates.sort(
            key=lambda match: (-match.imbalance_score, match.kickoff_at, match.league_name)
        )
        save_watchlist(chat_id, candidates)

        return WatchlistBuildResult(
            tracked_leagues=tracked_leagues,
            matches=candidates,
            inspected_fixtures=inspected_fixtures,
            skipped_leagues=skipped_leagues,
        )

    def load_saved_watchlist(self, chat_id: int) -> list[WatchlistMatch]:
        """Load the watchlist currently saved for a Telegram chat.

        Args:
            chat_id (int): Telegram chat whose saved watchlist should be read.

        Returns:
            list[WatchlistMatch]: Saved weekly watchlist entries for the chat.
        """

        return load_watchlist(chat_id)


def _index_standings_by_team(
    standings: list[StandingEntry],
) -> dict[str, StandingEntry]:
    """Create a team-name index for fast standings lookups."""

    return {_normalize_team_name(row.team_name): row for row in standings}


def _normalize_team_name(team_name: str) -> str:
    """Normalize team names before comparing fixtures with standings rows."""

    return team_name.strip().lower()

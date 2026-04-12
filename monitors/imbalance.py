"""Helpers for identifying uneven fixtures from standings data.

This module translates basic league-table signals into a single
`imbalance_score`. The score is intentionally simple and robust:

- table-position gap
- points gap
- goal-difference gap

The purpose of this stage is to identify suspiciously uneven fixtures before
introducing pre-match odds. In other words, this module answers:

"Which fixtures already look one-sided from the league table alone?"
"""

from dataclasses import dataclass

from services.football_data_provider import StandingEntry


@dataclass(frozen=True)
class ImbalanceAssessment:
    """Represent the result of evaluating one fixture for imbalance.

    Attributes:
        score (float): Composite score between 0 and 100. Higher means more
            uneven on paper.
        reasons (list[str]): Human-readable explanations for the score.
        stronger_team (str): Team that looks stronger according to current
            standings signals.
    """

    score: float
    reasons: list[str]
    stronger_team: str


def calculate_imbalance_score(
    home_entry: StandingEntry,
    away_entry: StandingEntry,
) -> ImbalanceAssessment:
    """Calculate an imbalance score between two teams in the standings.

    Args:
        home_entry (StandingEntry): Standings row for the home team.
        away_entry (StandingEntry): Standings row for the away team.

    Returns:
        ImbalanceAssessment: Score and reasons describing how uneven the
        matchup looks from standings data alone.

    Notes:
        This function deliberately ignores betting odds, lineups, injuries, or
        external APIs. Its role is to create an initial watchlist that a later
        odds provider can enrich without mixing both concerns too early.
    """

    stronger_entry, weaker_entry = _order_entries_by_strength(home_entry, away_entry)

    position_gap = abs(home_entry.position - away_entry.position)
    points_gap = abs(home_entry.points - away_entry.points)
    goal_difference_gap = abs(home_entry.goal_difference - away_entry.goal_difference)

    # Each signal contributes a capped component so one extreme difference does
    # not dominate the whole score.
    position_component = min(position_gap / 10, 1.0) * 40
    points_component = min(points_gap / 18, 1.0) * 35
    goal_difference_component = min(goal_difference_gap / 25, 1.0) * 25

    score = round(
        position_component + points_component + goal_difference_component,
        1,
    )

    reasons: list[str] = []

    if position_gap >= 4:
        reasons.append(
            f"{stronger_entry.team_name} is {position_gap} places above "
            f"{weaker_entry.team_name} in the table."
        )

    if points_gap >= 10:
        reasons.append(
            f"{stronger_entry.team_name} leads by {points_gap} points."
        )

    if goal_difference_gap >= 12:
        reasons.append(
            f"{stronger_entry.team_name} has a goal-difference edge of "
            f"{goal_difference_gap}."
        )

    if not reasons and score > 0:
        reasons.append(
            f"{stronger_entry.team_name} still profiles as the stronger side on current standings."
        )

    return ImbalanceAssessment(
        score=score,
        reasons=reasons,
        stronger_team=stronger_entry.team_name,
    )


def _order_entries_by_strength(
    first_entry: StandingEntry,
    second_entry: StandingEntry,
) -> tuple[StandingEntry, StandingEntry]:
    """Order two standings entries from stronger to weaker.

    Args:
        first_entry (StandingEntry): First team to compare.
        second_entry (StandingEntry): Second team to compare.

    Returns:
        tuple[StandingEntry, StandingEntry]: Pair ordered as `(stronger, weaker)`.

    Notes:
        Lower table position is better, while higher points and higher goal
        difference indicate strength. The tiebreakers aim to stay stable and
        predictable for learning purposes.
    """

    first_key = (first_entry.position, -first_entry.points, -first_entry.goal_difference)
    second_key = (second_entry.position, -second_entry.points, -second_entry.goal_difference)

    if first_key <= second_key:
        return first_entry, second_entry

    return second_entry, first_entry

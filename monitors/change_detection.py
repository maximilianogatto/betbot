"""Pure-ish tracking helpers for odds comparisons and reminder selection."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from monitors.models import SubscriptionOddsAlert
from storage.tracking_repository import (
    ActiveEventRecord,
    CompetitionSubscription,
    EventBaseline,
    SqliteTrackingRepository,
    TrackedCompetition,
)


def evaluate_subscription_odds_change(
    repository: SqliteTrackingRepository,
    subscription: CompetitionSubscription,
    tracked_league: TrackedCompetition,
    match: ActiveEventRecord,
) -> SubscriptionOddsAlert | None:
    """Evaluate one global odds change against a specific chat baseline."""

    baseline = repository.get_event_baseline(
        subscription.telegram_chat_id,
        tracked_league.id,
        match.fixture_id,
    )

    if baseline is None:
        repository.initialize_event_baselines(
            subscription.telegram_chat_id,
            tracked_league.id,
            [match],
        )
        return None

    max_percent_change = compute_max_percent_change(baseline, match)

    if max_percent_change is None:
        repository.upsert_event_baseline(
            subscription.telegram_chat_id,
            tracked_league.id,
            match.fixture_id,
            baseline_home=match.odds_home,
            baseline_draw=match.odds_draw,
            baseline_away=match.odds_away,
        )
        repository.resolve_small_change_with_current_baseline(
            subscription.telegram_chat_id,
            tracked_league.id,
            match.fixture_id,
        )
        return None

    should_notify = (
        subscription.notify_odds_changes
        and max_percent_change >= subscription.change_percent_threshold
    )

    if should_notify:
        return SubscriptionOddsAlert(
            match=match,
            baseline=baseline,
            max_percent_change=max_percent_change,
        )

    repository.upsert_small_change(
        subscription.telegram_chat_id,
        tracked_league.id,
        match.fixture_id,
        home=match.home,
        away=match.away,
        scheduled_label_date=match.kickoff_label_date,
        scheduled_label_time=match.kickoff_label_time,
        baseline_home=baseline.baseline_home,
        baseline_draw=baseline.baseline_draw,
        baseline_away=baseline.baseline_away,
        current_home=match.odds_home,
        current_draw=match.odds_draw,
        current_away=match.odds_away,
        max_percent_change=max_percent_change,
        status="pending",
    )
    return None


def compute_max_percent_change(
    baseline: EventBaseline,
    match: ActiveEventRecord,
) -> float | None:
    """Return the maximum valid percent change between baseline and current odds."""

    changes = [
        compute_percent_change(baseline.baseline_home, match.odds_home),
        compute_percent_change(baseline.baseline_draw, match.odds_draw),
        compute_percent_change(baseline.baseline_away, match.odds_away),
    ]
    valid_changes = [change for change in changes if change is not None]

    if not valid_changes:
        return None

    return max(valid_changes)


def compute_percent_change(
    baseline_value: float | None,
    current_value: float | None,
) -> float | None:
    """Compute absolute percent change for one odds selection."""

    if baseline_value is None or current_value is None:
        return None

    if baseline_value <= 0:
        return None

    return abs(current_value - baseline_value) / baseline_value * 100


def select_due_reminders(matches: Sequence[ActiveEventRecord]) -> list[ActiveEventRecord]:
    """Return matches that should trigger the 5-minute reminder now."""

    now = datetime.now(timezone.utc)
    due_matches: list[ActiveEventRecord] = []

    for match in matches:
        if match.alerted:
            continue

        time_label = (match.kickoff_label_time or "").strip()
        if not time_label:
            continue

        kickoff = parse_match_kickoff(match)
        if kickoff is None:
            continue

        reminder_time = kickoff - timedelta(minutes=5)
        if reminder_time <= now <= kickoff:
            due_matches.append(match)

    return due_matches


def parse_match_kickoff(match: ActiveEventRecord) -> datetime | None:
    """Parse the stored kickoff timestamp into an aware UTC datetime."""

    if match.kickoff_at is None:
        return None

    try:
        kickoff = datetime.fromisoformat(match.kickoff_at)
    except ValueError:
        return None

    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)

    return kickoff.astimezone(timezone.utc)


__all__ = [
    "compute_max_percent_change",
    "compute_percent_change",
    "evaluate_subscription_odds_change",
    "parse_match_kickoff",
    "select_due_reminders",
]

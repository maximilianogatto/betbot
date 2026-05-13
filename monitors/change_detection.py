"""Pure-ish tracking helpers for odds comparisons and reminder selection."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
import json
from typing import Any

from monitors.models import MarketChangeDetail, SubscriptionOddsAlert
from storage.tracking_repository import (
    ActiveEventRecord,
    CompetitionSubscription,
    EventBaseline,
    SqliteTrackingRepository,
    TrackedCompetition,
)

MARKET_TYPE_LABELS = {
    "1x2": "1X2",
    "asian_handicap": "Asian Handicap",
    "goal_line": "Goal Line",
    "alternative_markets": "Mercados alternativos",
}


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

    change_details = compute_market_change_details(baseline, match)
    max_percent_change = change_details[0].percent_change if change_details else None

    if max_percent_change is None:
        repository.upsert_event_baseline(
            subscription.telegram_chat_id,
            tracked_league.id,
            match.fixture_id,
            baseline_home=match.odds_home,
            baseline_draw=match.odds_draw,
            baseline_away=match.odds_away,
            baseline_markets_json=match.markets_json,
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
            change_details=tuple(change_details),
            changed_market_types=_collect_changed_market_types(change_details),
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
    )
    return None


def compute_max_percent_change(
    baseline: EventBaseline,
    match: ActiveEventRecord,
) -> float | None:
    """Return the maximum valid percent change between baseline and current odds."""

    details = compute_market_change_details(baseline, match)
    if not details:
        return None

    return details[0].percent_change


def compute_market_change_details(
    baseline: EventBaseline,
    match: ActiveEventRecord,
) -> list[MarketChangeDetail]:
    """Return sorted market change details for every comparable odds entry."""

    baseline_entries = _flatten_market_payload(_effective_baseline_payload(baseline))
    current_entries = _flatten_market_payload(_effective_current_payload(match))

    details: list[MarketChangeDetail] = []

    for entry_key in sorted(set(baseline_entries) & set(current_entries)):
        previous_entry = baseline_entries[entry_key]
        current_entry = current_entries[entry_key]
        before = previous_entry["odds"]
        after = current_entry["odds"]
        percent_change = compute_percent_change(before, after)

        if percent_change is None or percent_change <= 0:
            continue

        details.append(
            MarketChangeDetail(
                market_type=str(current_entry["market_type"]),
                market_name=str(current_entry["market_name"]),
                selection=str(current_entry["selection"]),
                line=_normalize_optional_text(current_entry.get("line")),
                before=before,
                after=after,
                percent_change=percent_change,
            )
        )

    details.sort(
        key=lambda detail: (
            -detail.percent_change,
            detail.market_name,
            detail.selection,
            detail.line or "",
        )
    )
    return details


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


def market_type_display_name(market_type: str) -> str:
    """Return a friendly label for one normalized market type."""

    normalized_market_type = market_type.strip().lower()
    return MARKET_TYPE_LABELS.get(normalized_market_type, normalized_market_type.replace("_", " ").title())


def _collect_changed_market_types(
    change_details: Sequence[MarketChangeDetail],
) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()

    for detail in change_details:
        if detail.market_type in seen:
            continue
        seen.add(detail.market_type)
        ordered.append(detail.market_type)

    return tuple(ordered)


def _effective_baseline_payload(baseline: EventBaseline) -> dict[str, Any]:
    payload = _loads_optional_json_dict(baseline.baseline_markets_json) or {}
    return _merge_1x2_payload(
        payload,
        home=baseline.baseline_home,
        draw=baseline.baseline_draw,
        away=baseline.baseline_away,
    )


def _effective_current_payload(match: ActiveEventRecord) -> dict[str, Any]:
    payload = _loads_optional_json_dict(match.markets_json) or {}
    return _merge_1x2_payload(
        payload,
        home=match.odds_home,
        draw=match.odds_draw,
        away=match.odds_away,
    )


def _merge_1x2_payload(
    payload: dict[str, Any],
    *,
    home: float | None,
    draw: float | None,
    away: float | None,
) -> dict[str, Any]:
    merged_payload = json.loads(json.dumps(payload or {}))

    if home is None and draw is None and away is None:
        return merged_payload

    merged_payload["1x2"] = {
        "home": home,
        "draw": draw,
        "away": away,
    }
    return merged_payload


def _flatten_market_payload(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    flattened: dict[str, dict[str, Any]] = {}

    one_x_two = payload.get("1x2")
    if isinstance(one_x_two, dict):
        for selection_key, selection_label in (("home", "1"), ("draw", "X"), ("away", "2")):
            odds_value = _coerce_float(one_x_two.get(selection_key))
            if odds_value is None:
                continue
            flattened[f"1x2|{selection_key}"] = {
                "market_type": "1x2",
                "market_name": "1X2",
                "selection": selection_label,
                "line": None,
                "odds": odds_value,
            }

    for market_type in ("asian_handicap", "goal_line"):
        market_payload = payload.get(market_type)
        if isinstance(market_payload, dict):
            _flatten_market_object(flattened, market_type, market_payload)

    alternative_markets = payload.get("alternative_markets")
    if isinstance(alternative_markets, list):
        for market_payload in alternative_markets:
            if isinstance(market_payload, dict):
                _flatten_market_object(flattened, "alternative_markets", market_payload)

    return flattened


def _flatten_market_object(
    flattened: dict[str, dict[str, Any]],
    market_type: str,
    market_payload: dict[str, Any],
) -> None:
    market_id = _normalize_optional_text(market_payload.get("market_id"))
    market_name = _normalize_optional_text(market_payload.get("market_name")) or market_type_display_name(
        market_type
    )

    for selection_payload in market_payload.get("selections") or []:
        if not isinstance(selection_payload, dict):
            continue

        odds_value = _coerce_float(selection_payload.get("odds"))
        if odds_value is None:
            continue

        selection = _normalize_optional_text(selection_payload.get("selection")) or "?"
        line = _normalize_optional_text(selection_payload.get("line"))
        entry_key = "|".join(
            [
                market_type,
                market_id or market_name,
                selection,
                line or "",
            ]
        )
        flattened[entry_key] = {
            "market_type": market_type,
            "market_name": market_name,
            "selection": selection,
            "line": line,
            "odds": odds_value,
        }


def _loads_optional_json_dict(raw_value: str | None) -> dict[str, Any] | None:
    normalized_value = (raw_value or "").strip()
    if not normalized_value:
        return None

    try:
        payload = json.loads(normalized_value)
    except json.JSONDecodeError:
        return None

    return payload if isinstance(payload, dict) else None


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized_value = value.strip()
        if not normalized_value:
            return None
        try:
            return float(normalized_value)
        except ValueError:
            return None
    return None


def _normalize_optional_text(value: object) -> str | None:
    normalized_value = str(value).strip() if value is not None else ""
    return normalized_value or None


__all__ = [
    "compute_market_change_details",
    "compute_max_percent_change",
    "compute_percent_change",
    "evaluate_subscription_odds_change",
    "market_type_display_name",
    "parse_match_kickoff",
    "select_due_reminders",
]

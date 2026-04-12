"""Monitoring rule placeholders for sports events.

This module represents the place where business rules will eventually live.
Given one `SportsEvent`, it should decide whether the event matches any
conditions that deserve an alert.

At this stage the implementation is intentionally minimal: it returns no
reasons, which means no alerts are triggered yet. The goal is to preserve the
architecture without introducing real rule complexity too early.
"""

from services.sports_api import SportsEvent


def evaluate_event(event: SportsEvent) -> list[str]:
    """Evaluate a sports event and return alert reasons, if any.

    Args:
        event (SportsEvent): Event under evaluation.

    Returns:
        list[str]: A list of human-readable reasons explaining why the event
        should generate an alert. An empty list means "do not alert".

    Notes:
        This function is called from `jobs.scheduler.run_monitoring_cycle()`.
        It does not query APIs or storage; it only inspects the provided event.
        For now it is a placeholder and therefore always returns an empty list.
    """

    # The parameter is intentionally unused for now because this is only the
    # first placeholder for future business rules.
    del event
    return []

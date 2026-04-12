"""Monitoring job orchestration for future alert workflows.

This module contains a simple orchestration function that demonstrates the
future monitoring pipeline:

1. Fetch events from a data provider.
2. Evaluate monitoring rules for each event.
3. Build alert messages for matching events.
4. Send those alerts through Telegram.

The function here is not yet connected to a periodic scheduler, but it already
shows how `services`, `monitors`, and `alerts` fit together.
"""

from telegram import Bot

from alerts.telegram_alerts import build_alert_message, send_alert
from monitors.rules import evaluate_event
from services.sports_api import SportsAPIClient


async def run_monitoring_cycle(
    provider: SportsAPIClient,
    bot: Bot,
    chat_id: int | str,
) -> None:
    """Run one complete monitoring cycle.

    This function connects the core future subsystems of the alert pipeline.
    It asks a provider for events, evaluates each event with monitoring rules,
    and sends Telegram alerts for the events that match.

    Args:
        provider (SportsAPIClient): Data provider capable of returning sports
            events. In a future version, this may wrap a real API or scraping
            implementation.
        bot (Bot): Telegram bot client used to send alerts.
        chat_id (int | str): Destination chat for alert delivery.

    Returns:
        None: The function processes the cycle and sends alerts as needed.

    Side Effects:
        May make API calls through the provider and may send Telegram messages.

    Notes:
        The function is async because both event fetching and alert delivery
        may involve network I/O. It is designed to be called later by a
        periodic job runner, not directly by Telegram command handlers.
    """

    # Fetching is awaited because future providers may perform HTTP requests or
    # other I/O operations.
    events = await provider.fetch_events()

    for event in events:
        # Rule evaluation is synchronous for now because it only inspects data
        # already loaded into memory.
        reasons = evaluate_event(event)

        if not reasons:
            continue

        message = build_alert_message(event, reasons)
        # Alert delivery uses Telegram's API, so it must be awaited.
        await send_alert(bot=bot, chat_id=chat_id, message=message)

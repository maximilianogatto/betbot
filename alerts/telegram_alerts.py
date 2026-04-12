"""Helpers for building and sending Telegram alert messages.

This module belongs to the alert-delivery side of the architecture. It does
not decide *when* an alert should be triggered; that responsibility belongs to
monitoring logic. Instead, it focuses on transforming alert data into text and
sending it through Telegram.
"""

from telegram import Bot

from services.sports_api import SportsEvent


def build_alert_message(event: SportsEvent, reasons: list[str]) -> str:
    """Build a readable Telegram message for a detected sports alert.

    Args:
        event (SportsEvent): Sports event that triggered the alert flow.
        reasons (list[str]): Human-readable reasons explaining why the event
            deserves attention.

    Returns:
        str: Multiline message ready to be sent through Telegram.

    Notes:
        This function is used by `jobs.scheduler.run_monitoring_cycle()`. It
        does not contact Telegram directly; it only prepares the text payload.
    """

    reasons_text = "\n".join(f"- {reason}" for reason in reasons) or "- Sin detalles"

    return (
        "Alerta deportiva detectada\n\n"
        f"Deporte: {event.sport}\n"
        f"Liga: {event.league}\n"
        f"Partido: {event.home_team} vs {event.away_team}\n"
        f"Inicio: {event.starts_at}\n\n"
        f"Motivos:\n{reasons_text}"
    )


async def send_alert(bot: Bot, chat_id: int | str, message: str) -> None:
    """Send an alert message to a Telegram chat.

    Args:
        bot (Bot): Telegram bot client already authenticated with a bot token.
        chat_id (int | str): Destination chat identifier.
        message (str): Message text that should be delivered.

    Returns:
        None: The function performs the send operation and does not return data.

    Side Effects:
        Sends a network request to Telegram's API.

    Notes:
        The function is async because Telegram messaging is I/O-bound and must
        be awaited inside the bot event loop.
    """

    await bot.send_message(chat_id=chat_id, text=message)

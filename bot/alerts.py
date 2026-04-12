"""Bot-side alert helpers for future watchlist notifications.

This module intentionally stays lightweight for now. The current stage of the
project focuses on building a watchlist of imbalanced fixtures, not on odds
collection or advanced alerting.

The functions defined here provide the interface that future monitoring jobs
can call once a separate odds provider starts enriching the watchlist with
pre-match market data.
"""

from telegram import Bot

from storage.watchlist import WatchlistMatch


def build_watchlist_alert_message(match: WatchlistMatch) -> str:
    """Build a Telegram-ready alert message for a watchlist match.

    Args:
        match (WatchlistMatch): Saved watchlist match that deserves attention.

    Returns:
        str: Message text describing the match and the imbalance reasons.

    Notes:
        The message deliberately avoids quoting odds because this stage of the
        project has not integrated an odds provider yet.
    """

    reasons_text = "\n".join(f"- {reason}" for reason in match.reasons)

    return (
        "Watchlist candidate detected\n\n"
        f"League: {match.league_name}\n"
        f"Match: {match.home_team} vs {match.away_team}\n"
        f"Kickoff: {match.kickoff_at}\n"
        f"Imbalance score: {match.imbalance_score:.1f}\n\n"
        f"Reasons:\n{reasons_text}"
    )


async def send_watchlist_alert_placeholder(
    bot: Bot,
    chat_id: int | str,
    match: WatchlistMatch,
) -> None:
    """Send a placeholder watchlist alert without odds data.

    Args:
        bot (Bot): Telegram bot client used to deliver the message.
        chat_id (int | str): Destination Telegram chat.
        match (WatchlistMatch): Saved watchlist entry that triggered the alert.

    Returns:
        None: The coroutine sends a message and does not return data.

    Side Effects:
        Sends a Telegram message.

    Notes:
        This function is not called automatically yet. It exists to define the
        future interface that monitoring jobs can use once watchlist-based
        notifications are enabled.
    """

    await bot.send_message(
        chat_id=chat_id,
        text=build_watchlist_alert_message(match),
    )

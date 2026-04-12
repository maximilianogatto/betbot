"""Placeholder background jobs for future monitoring features.

This module lives inside the `bot` package because it represents future bot
runtime behavior rather than storage or domain rules. At the moment it only
contains placeholders that log periodically.

It is not wired into the main startup flow yet. Its purpose is educational:
to show where periodic monitoring code will eventually live once tracking data,
watchlist analysis, and external providers are connected together.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def monitoring_loop_placeholder(interval_seconds: int = 60) -> None:
    """Run a placeholder periodic monitoring loop."""

    while True:
        logger.info(
            "Placeholder de monitoreo activo. En el futuro acá correrán los chequeos automáticos."
        )
        await asyncio.sleep(interval_seconds)


async def weekly_watchlist_job_placeholder(
    chat_id: int,
    interval_seconds: int = 7 * 24 * 60 * 60,
) -> None:
    """Run a placeholder weekly watchlist rebuild job.

    Args:
        chat_id (int): Telegram chat identifier whose watchlist would be
            refreshed in a future automated version.
        interval_seconds (int): Wait time between placeholder iterations.

    Returns:
        None: The coroutine is designed to run forever until cancelled.

    Side Effects:
        Emits log messages periodically and yields control back to the event
        loop with `asyncio.sleep()`.

    Notes:
        This function does not rebuild the watchlist yet. It only marks the
        future extension point where `/build_watchlist` can be replaced or
        complemented by a weekly automatic job.
    """

    while True:
        logger.info(
            "Weekly watchlist job placeholder active for chat_id=%s. "
            "A future version will rebuild the watchlist automatically here.",
            chat_id,
        )
        await asyncio.sleep(interval_seconds)

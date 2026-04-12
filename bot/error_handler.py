"""Centralized error handling for Telegram update processing.

This module contains the application's global error handler. The Telegram
framework calls it when an exception escapes from a handler or another update
processing step.

Having a single error handler improves observability and gives the bot a
chance to respond gracefully instead of failing silently.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unexpected exceptions raised during update processing.

    This async function is registered through `Application.add_error_handler()`
    in `bot.application`. It logs the original exception and, when possible,
    notifies the user that something went wrong.

    Args:
        update (object): Raw update object associated with the failure. It may
            or may not be an instance of `telegram.Update`.
        context (ContextTypes.DEFAULT_TYPE): Framework context that contains
            the caught exception in `context.error`.

    Returns:
        None: The function reports the error but does not re-raise it.

    Side Effects:
        Writes error information to the console log and may send a Telegram
        message back to the user.

    Notes:
        The function is async because replying to the user uses Telegram's API,
        which is network-bound and therefore awaited inside the event loop.
    """

    logger.error("Se produjo un error mientras se procesaba un update.", exc_info=context.error)

    # Some framework-level failures may not be associated with a normal
    # Telegram `Update`, so the type is checked before accessing message data.
    if not isinstance(update, Update):
        return

    if update.effective_message is None:
        return

    try:
        # Sending a user-facing error message is also asynchronous because it
        # performs an API request to Telegram.
        await update.effective_message.reply_text(
            "Ocurrió un error inesperado. Probá de nuevo en unos segundos."
        )
    except Exception:
        # If even the fallback reply fails, we still want a detailed log entry.
        logger.exception("No se pudo enviar el mensaje de error al usuario.")

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Se produjo un error mientras se procesaba un update.", exc_info=context.error)

    if not isinstance(update, Update):
        return

    if update.effective_message is None:
        return

    try:
        await update.effective_message.reply_text(
            "Ocurrió un error inesperado. Probá de nuevo en unos segundos."
        )
    except Exception:
        logger.exception("No se pudo enviar el mensaje de error al usuario.")

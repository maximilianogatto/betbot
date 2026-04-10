import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)

HELP_MESSAGE = (
    "Comandos disponibles:\n"
    "/start - Mensaje de bienvenida\n"
    "/help - Lista de comandos\n"
    "/ping - Responde pong\n"
    "/status - Informa si el bot está online\n"
    "/echo <texto> - Devuelve el texto enviado"
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context

    if update.message is None:
        return

    logger.info("Comando /start recibido.")

    first_name = "amigo"
    if update.effective_user and update.effective_user.first_name:
        first_name = update.effective_user.first_name

    welcome_message = (
        f"Hola, {first_name}. Soy tu bot base de Telegram.\n\n"
        "Ya estoy funcionando por polling y listo para crecer como sistema de alertas.\n"
        "Usá /help para ver los comandos disponibles."
    )

    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context

    if update.message is None:
        return

    logger.info("Comando /help recibido.")

    await update.message.reply_text(HELP_MESSAGE)


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context

    if update.message is None:
        return

    logger.info("Comando /ping recibido.")

    await update.message.reply_text("pong")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context

    if update.message is None:
        return

    logger.info("Comando /status recibido.")

    await update.message.reply_text("El bot está online y funcionando correctamente.")


async def echo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    logger.info("Comando /echo recibido.")

    text_to_echo = " ".join(context.args).strip()

    if not text_to_echo:
        await update.message.reply_text(
            "Usá /echo seguido de un texto. Ejemplo: /echo hola mundo"
        )
        return

    await update.message.reply_text(text_to_echo)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context

    if update.message is None:
        return

    logger.info("Comando desconocido recibido.")

    await update.message.reply_text(
        "Todavía no conozco ese comando. Usá /help para ver la lista disponible."
    )


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("echo", echo_command))

    # Este handler va al final para capturar comandos no registrados.
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

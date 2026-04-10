from telegram.ext import Application, ApplicationBuilder

from bot.config import Settings
from bot.error_handler import handle_error
from bot.handlers import register_handlers


def create_application(settings: Settings) -> Application:
    application = ApplicationBuilder().token(settings.telegram_bot_token).build()

    register_handlers(application)
    application.add_error_handler(handle_error)

    return application

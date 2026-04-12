"""Telegram command handlers for the interactive bot interface.

This module contains the async functions that respond to commands such as
`/start`, `/help`, `/track`, `/build_watchlist`, and `/list_watchlist`.
It is the main entry point for user interaction with the bot.

Handlers in this file do not talk directly to JSON files or mock providers.
When a command needs domain logic, it delegates to `TrackerService` or
`WeeklyWatchlistBuilder`. This keeps the Telegram-specific layer focused on
parsing updates and producing responses.
"""

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from monitors.tracker import CommandResult, TrackerService
from monitors.watchlist_builder import WatchlistBuildResult, WeeklyWatchlistBuilder
from storage.watchlist import WatchlistMatch

logger = logging.getLogger(__name__)

HELP_MESSAGE = (
    "Comandos disponibles:\n"
    "/start - Mensaje de bienvenida\n"
    "/help - Lista de comandos\n"
    "/ping - Responde pong\n"
    "/status - Informa si el bot está online\n"
    "/echo <texto> - Devuelve el texto enviado\n"
    "/track <tipo> <valor> - Guarda un objetivo para seguir\n"
    "/list_tracks - Lista tus objetivos guardados\n"
    "/untrack <tipo> <valor> - Elimina un objetivo guardado\n"
    "/build_watchlist - Construye la watchlist semanal\n"
    "/list_watchlist - Lista los partidos guardados en la watchlist"
)

TRACK_USAGE_MESSAGE = (
    "Usá /track <tipo> <valor>.\n"
    "Ejemplos:\n"
    "/track league premier_league\n"
    "/track event arsenal_vs_chelsea"
)

UNTRACK_USAGE_MESSAGE = (
    "Usá /untrack <tipo> <valor>.\n"
    "Ejemplos:\n"
    "/untrack league premier_league\n"
    "/untrack event arsenal_vs_chelsea"
)


def get_tracker_service(context: ContextTypes.DEFAULT_TYPE) -> TrackerService:
    """Retrieve the shared tracking service from the Telegram application.

    Handlers use this helper instead of constructing `TrackerService`
    themselves. The service instance is created once during application startup
    inside `bot.application.create_application()`.

    Args:
        context (ContextTypes.DEFAULT_TYPE): Telegram handler context that
            provides access to the application object and its `bot_data`.

    Returns:
        TrackerService: Shared service used to validate, store, and list
            tracking targets.

    Raises:
        RuntimeError: If the service was not attached during application
            startup.
    """

    tracker_service = context.application.bot_data.get("tracker_service")

    if not isinstance(tracker_service, TrackerService):
        raise RuntimeError("TrackerService no está configurado en la aplicación.")

    return tracker_service


def get_watchlist_builder(context: ContextTypes.DEFAULT_TYPE) -> WeeklyWatchlistBuilder:
    """Retrieve the shared weekly watchlist builder from the application.

    Args:
        context (ContextTypes.DEFAULT_TYPE): Telegram handler context that
            exposes `application.bot_data`.

    Returns:
        WeeklyWatchlistBuilder: Shared builder responsible for reading tracked
            leagues, consulting the data provider, and saving the watchlist.

    Raises:
        RuntimeError: If the builder was not configured during startup.
    """

    watchlist_builder = context.application.bot_data.get("watchlist_builder")

    if not isinstance(watchlist_builder, WeeklyWatchlistBuilder):
        raise RuntimeError("WeeklyWatchlistBuilder no está configurado en la aplicación.")

    return watchlist_builder


async def reply_with_result(update: Update, result: CommandResult) -> None:
    """Send a `CommandResult` message back to the user.

    Several command handlers return a domain-level `CommandResult` object from
    `TrackerService`. This helper converts that result into a Telegram reply,
    keeping response logic consistent across `/track`, `/list_tracks`, and
    `/untrack`.

    Args:
        update (Update): Telegram update associated with the current command.
        result (CommandResult): Result object containing the message that
            should be displayed to the user.

    Returns:
        None: The function only sends a response.

    Side Effects:
        Sends a message through Telegram's API.
    """

    if update.message is None:
        return

    await update.message.reply_text(result.message)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/start` command."""

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
    """Handle the `/help` command."""

    del context

    if update.message is None:
        return

    logger.info("Comando /help recibido.")

    await update.message.reply_text(HELP_MESSAGE)


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/ping` command."""

    del context

    if update.message is None:
        return

    logger.info("Comando /ping recibido.")

    await update.message.reply_text("pong")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/status` command."""

    del context

    if update.message is None:
        return

    logger.info("Comando /status recibido.")

    await update.message.reply_text("El bot está online y funcionando correctamente.")


async def echo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/echo` command."""

    if update.message is None:
        return

    logger.info("Comando /echo recibido.")

    # `context.args` already contains the command arguments split by spaces.
    # Joining them again lets the user echo phrases instead of only one word.
    text_to_echo = " ".join(context.args).strip()

    if not text_to_echo:
        await update.message.reply_text(
            "Usá /echo seguido de un texto. Ejemplo: /echo hola mundo"
        )
        return

    await update.message.reply_text(text_to_echo)


async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/track <type> <value>` command."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /track recibido.")

    if len(context.args) < 2:
        await update.message.reply_text(TRACK_USAGE_MESSAGE)
        return

    # The first argument identifies what is being tracked (`league` or
    # `event`). The remaining text becomes the target key.
    target_type = context.args[0]
    target_key = " ".join(context.args[1:])

    tracker_service = get_tracker_service(context)
    result = tracker_service.add_target(
        chat_id=update.effective_chat.id,
        target_type=target_type,
        target_key=target_key,
    )

    await reply_with_result(update, result)


async def list_tracks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/list_tracks` command."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /list_tracks recibido.")

    tracker_service = get_tracker_service(context)
    result = tracker_service.list_targets(update.effective_chat.id)

    await reply_with_result(update, result)


async def untrack_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/untrack <type> <value>` command."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /untrack recibido.")

    if len(context.args) < 2:
        await update.message.reply_text(UNTRACK_USAGE_MESSAGE)
        return

    # Parsing mirrors `/track` so both commands work with the same internal
    # representation of the target.
    target_type = context.args[0]
    target_key = " ".join(context.args[1:])

    tracker_service = get_tracker_service(context)
    result = tracker_service.remove_target(
        chat_id=update.effective_chat.id,
        target_type=target_type,
        target_key=target_key,
    )

    await reply_with_result(update, result)


async def build_watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/build_watchlist` command.

    The command triggers a full manual rebuild of the weekly watchlist for the
    current chat. It is intentionally separate from automatic jobs so the
    watchlist logic can be tested interactively before scheduling it.
    """

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /build_watchlist recibido.")

    watchlist_builder = get_watchlist_builder(context)
    result = await watchlist_builder.build_for_chat(update.effective_chat.id)

    await update.message.reply_text(_format_watchlist_build_result(result))


async def list_watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/list_watchlist` command.

    This command lists the fixtures currently saved in the local weekly
    watchlist for the current chat.
    """

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /list_watchlist recibido.")

    watchlist_builder = get_watchlist_builder(context)
    matches = watchlist_builder.load_saved_watchlist(update.effective_chat.id)

    if not matches:
        await update.message.reply_text(
            "No hay partidos guardados en la watchlist todavía. Usá /build_watchlist para generarla."
        )
        return

    await update.message.reply_text(_format_watchlist_matches(matches))


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle any unsupported Telegram command."""

    del context

    if update.message is None:
        return

    logger.info("Comando desconocido recibido.")

    await update.message.reply_text(
        "Todavía no conozco ese comando. Usá /help para ver la lista disponible."
    )


def register_handlers(application: Application) -> None:
    """Register all Telegram command handlers in the application."""

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("echo", echo_command))
    application.add_handler(CommandHandler("track", track_command))
    application.add_handler(CommandHandler("list_tracks", list_tracks_command))
    application.add_handler(CommandHandler("untrack", untrack_command))
    application.add_handler(CommandHandler("build_watchlist", build_watchlist_command))
    application.add_handler(CommandHandler("list_watchlist", list_watchlist_command))

    # This fallback must be registered last so it only catches unknown
    # commands that were not handled by the more specific handlers above.
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))


def _format_watchlist_build_result(result: WatchlistBuildResult) -> str:
    """Convert a watchlist build report into a Telegram-friendly message."""

    if not result.tracked_leagues:
        return (
            "No encontré ligas trackeadas para este chat.\n"
            "Primero usá /track league <league_code> y después /build_watchlist."
        )

    lines = [
        "Watchlist semanal construida.",
        f"Ligas analizadas: {', '.join(result.tracked_leagues)}",
        f"Partidos evaluados: {result.inspected_fixtures}",
        f"Candidatos guardados: {len(result.matches)}",
    ]

    if result.skipped_leagues:
        lines.append(f"Ligas omitidas: {', '.join(result.skipped_leagues)}")

    if result.matches:
        lines.append("")
        lines.append("Partidos marcados:")
        for match in result.matches[:5]:
            lines.append(
                f"- {match.league_name}: {match.home_team} vs {match.away_team} "
                f"({match.imbalance_score:.1f})"
            )
    else:
        lines.append("No se detectaron partidos suficientemente desparejos esta semana.")

    return "\n".join(lines)


def _format_watchlist_matches(matches: list[WatchlistMatch]) -> str:
    """Format the saved watchlist as a readable Telegram message."""

    lines = ["Partidos guardados en la watchlist:"]

    for index, match in enumerate(matches, start=1):
        reasons_text = "; ".join(match.reasons)
        flags_text = (
            f"odds_seen={'yes' if match.odds_seen else 'no'}, "
            f"alert_sent={'yes' if match.alert_sent else 'no'}"
        )

        lines.append(
            f"{index}. {match.league_name} | {match.home_team} vs {match.away_team}"
        )
        lines.append(f"   Kickoff: {match.kickoff_at}")
        lines.append(f"   Imbalance score: {match.imbalance_score:.1f}")
        lines.append(f"   Reasons: {reasons_text}")
        lines.append(f"   Flags: {flags_text}")

    return "\n".join(lines)

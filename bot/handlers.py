"""Telegram command handlers for the simplified Bet365-focused bot flow."""

from __future__ import annotations

import logging

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.alerts import build_all_matches_message, build_match_card_message
from monitors.bet365_tracking import Bet365TrackingService, CommandResult
from storage.bet365_tracking import ActiveMatchRecord, TrackedLeagueSubscription

logger = logging.getLogger(__name__)

SELECT_LEAGUE_FOR_MATCHES = 1
SELECT_MATCH_FOR_MATCHES = 2
SELECT_LEAGUE_FOR_UNTRACK = 3
SELECT_LEAGUE_FOR_ODDS = 4

MATCHES_TRACKS_CONTEXT_KEY = "bet365_matches_tracks"
MATCHES_ACTIVE_CONTEXT_KEY = "bet365_matches_active"
MATCHES_SELECTED_TRACK_CONTEXT_KEY = "bet365_matches_selected_track"
UNTRACK_TRACKS_CONTEXT_KEY = "bet365_untrack_tracks"
ODDS_TRACKS_CONTEXT_KEY = "bet365_odds_tracks"
ODDS_ENABLED_CONTEXT_KEY = "bet365_odds_enabled"

HELP_MESSAGE = (
    "Comandos disponibles:\n"
    "/start - Mensaje de bienvenida\n"
    "/help - Lista de comandos\n"
    "/ping - Responde pong\n"
    "/status - Informa si el bot está online\n"
    "/echo <texto> - Devuelve el texto enviado\n"
    "/track_url <url> - Extrae una liga Bet365 y la deja pendiente\n"
    "/confirm_track - Confirma la última liga Bet365 pendiente\n"
    "/list_tracks - Lista las ligas Bet365 trackeadas\n"
    "/refresh_tracks - Actualiza partidos y detecta eventos nuevos\n"
    "/matches - Permite elegir una liga y ver sus partidos\n"
    "/untrack - Permite dejar de trackear una liga\n"
    "/odds_on - Activa notificaciones de cambios de odds para una liga\n"
    "/odds_off - Desactiva notificaciones de cambios de odds para una liga\n"
    "/cancel - Cancela la selección interactiva actual"
)

TRACK_URL_USAGE_MESSAGE = (
    "Usá /track_url <url_de_bet365>.\n"
    "Ejemplo:\n"
    "/track_url https://www.bet365.es/#/AC/B1/C1/D1002/E120757998/G40/"
)


def get_bet365_tracking_service(context: ContextTypes.DEFAULT_TYPE) -> Bet365TrackingService:
    """Retrieve the shared Bet365 tracking service from the application."""

    tracking_service = context.application.bot_data.get("bet365_tracking_service")

    if not isinstance(tracking_service, Bet365TrackingService):
        raise RuntimeError("Bet365TrackingService no está configurado en la aplicación.")

    return tracking_service


async def reply_with_result(update: Update, result: CommandResult) -> None:
    """Send a `CommandResult` message back to the current chat."""

    if update.message is None:
        return

    await update.message.reply_text(result.message)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/start` command."""

    del context

    if update.message is None:
        return

    first_name = "amigo"
    if update.effective_user and update.effective_user.first_name:
        first_name = update.effective_user.first_name

    welcome_message = (
        f"Hola, {first_name}. Soy tu bot de tracking para Bet365.\n\n"
        "Podés registrar ligas con /track_url, confirmarlas con /confirm_track, "
        "verlas con /list_tracks y consultar partidos con /matches."
    )

    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/help` command."""

    del context

    if update.message is None:
        return

    await update.message.reply_text(HELP_MESSAGE)


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/ping` command."""

    del context

    if update.message is None:
        return

    await update.message.reply_text("pong")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/status` command."""

    del context

    if update.message is None:
        return

    await update.message.reply_text("El bot está online y funcionando correctamente.")


async def echo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/echo` command."""

    if update.message is None:
        return

    text_to_echo = " ".join(context.args).strip()

    if not text_to_echo:
        await update.message.reply_text(
            "Usá /echo seguido de un texto. Ejemplo: /echo hola mundo"
        )
        return

    await update.message.reply_text(text_to_echo)


async def track_url_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/track_url <url>` for Bet365 league discovery."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /track_url recibido.")

    if not context.args:
        await update.message.reply_text(TRACK_URL_USAGE_MESSAGE)
        return

    url = " ".join(context.args).strip()
    tracking_service = get_bet365_tracking_service(context)
    result = await tracking_service.create_pending_track_from_url(
        chat_id=update.effective_chat.id,
        url=url,
    )

    await reply_with_result(update, result)


async def confirm_track_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/confirm_track` for the latest pending Bet365 request."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /confirm_track recibido.")

    tracking_service = get_bet365_tracking_service(context)
    result = await tracking_service.confirm_pending_track(update.effective_chat.id)

    await reply_with_result(update, result)


async def list_tracks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/list_tracks` using the Bet365 subscription store."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /list_tracks recibido.")

    tracking_service = get_bet365_tracking_service(context)
    result = tracking_service.build_tracks_list_message(update.effective_chat.id)

    await reply_with_result(update, result)


async def refresh_tracks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/refresh_tracks` and send notifications for the refreshed leagues."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /refresh_tracks recibido.")

    tracking_service = get_bet365_tracking_service(context)

    try:
        summary = await tracking_service.refresh_chat_tracks(update.effective_chat.id)
        await tracking_service.dispatch_notifications(context.bot, summary)
    except (RuntimeError, ValueError) as error:
        logger.exception("Bet365 refresh failed for chat_id=%s.", update.effective_chat.id)
        await update.message.reply_text(
            "No pude actualizar las ligas trackeadas.\n"
            f"Detalle: {error}"
        )
        return

    await reply_with_result(update, tracking_service.build_refresh_summary_message(summary))


async def matches_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the interactive `/matches` flow."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END

    logger.info("Comando /matches recibido.")

    tracking_service = get_bet365_tracking_service(context)
    tracked_leagues = tracking_service.list_confirmed_tracks(update.effective_chat.id)

    if not tracked_leagues:
        await update.message.reply_text(
            "No tenés ligas trackeadas todavía.\n"
            "Usá /track_url <url_de_bet365> y después /confirm_track."
        )
        return ConversationHandler.END

    context.user_data[MATCHES_TRACKS_CONTEXT_KEY] = tracked_leagues
    await update.message.reply_text(
        _build_track_selection_message("Qué liga quiere ver?", tracked_leagues),
        reply_markup=_build_numeric_keyboard(len(tracked_leagues), "Elegí el número de la liga"),
    )
    return SELECT_LEAGUE_FOR_MATCHES


async def matches_select_league(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the league number selected during the `/matches` flow."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END

    tracked_leagues = context.user_data.get(MATCHES_TRACKS_CONTEXT_KEY)
    if not isinstance(tracked_leagues, list) or not tracked_leagues:
        await update.message.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /matches.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = _parse_selection_number(update.message.text, len(tracked_leagues))

    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de la lista.",
            reply_markup=_build_numeric_keyboard(len(tracked_leagues)),
        )
        return SELECT_LEAGUE_FOR_MATCHES

    selected_track = tracked_leagues[selected_index]
    tracking_service = get_bet365_tracking_service(context)

    try:
        tracked_subscription, active_matches = tracking_service.get_matches_for_track(
            update.effective_chat.id,
            selected_track.tracked_league.id,
        )
    except ValueError as error:
        await update.message.reply_text(
            str(error),
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    if not active_matches:
        try:
            await tracking_service.refresh_tracked_league(selected_track.tracked_league.id)
            tracked_subscription, active_matches = tracking_service.get_matches_for_track(
                update.effective_chat.id,
                selected_track.tracked_league.id,
            )
        except (RuntimeError, ValueError) as error:
            logger.exception(
                "Failed to refresh tracked league %s for chat_id=%s.",
                selected_track.tracked_league.id,
                update.effective_chat.id,
            )
            await update.message.reply_text(
                "No pude actualizar esa liga en este momento.\n"
                f"Detalle: {error}",
                reply_markup=ReplyKeyboardRemove(),
            )
            _clear_all_selection_context(context)
            return ConversationHandler.END

    if not active_matches:
        await update.message.reply_text(
            "No encontré partidos activos o futuros para esa liga.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    context.user_data[MATCHES_ACTIVE_CONTEXT_KEY] = active_matches
    context.user_data[MATCHES_SELECTED_TRACK_CONTEXT_KEY] = tracked_subscription

    await update.message.reply_text(
        _build_match_selection_message(tracked_subscription, active_matches),
        reply_markup=_build_numeric_keyboard(
            len(active_matches) + 1,
            "Elegí el número del partido",
        ),
    )

    return SELECT_MATCH_FOR_MATCHES


async def matches_select_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the match number selected during the `/matches` flow."""

    if update.message is None:
        return ConversationHandler.END

    active_matches = context.user_data.get(MATCHES_ACTIVE_CONTEXT_KEY)
    tracked_league = context.user_data.get(MATCHES_SELECTED_TRACK_CONTEXT_KEY)

    if not isinstance(active_matches, list) or not active_matches:
        await update.message.reply_text(
            "No encontré la selección de partidos. Probá de nuevo con /matches.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    if not isinstance(tracked_league, TrackedLeagueSubscription):
        await update.message.reply_text(
            "No encontré la liga seleccionada. Probá de nuevo con /matches.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = _parse_selection_number(update.message.text, len(active_matches) + 1)

    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de la lista.",
            reply_markup=_build_numeric_keyboard(len(active_matches) + 1),
        )
        return SELECT_MATCH_FOR_MATCHES

    if selected_index == 0:
        await update.message.reply_text(
            build_all_matches_message(tracked_league.tracked_league, active_matches),
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.HTML,
        )
    else:
        selected_match = active_matches[selected_index - 1]
        await update.message.reply_text(
            build_match_card_message(tracked_league.tracked_league, selected_match),
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.HTML,
        )

    _clear_all_selection_context(context)
    return ConversationHandler.END


async def untrack_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the interactive `/untrack` flow."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END

    logger.info("Comando /untrack recibido.")

    tracking_service = get_bet365_tracking_service(context)
    tracked_leagues = tracking_service.list_confirmed_tracks(update.effective_chat.id)

    if not tracked_leagues:
        await update.message.reply_text(
            "No tenés ligas trackeadas para eliminar.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    context.user_data[UNTRACK_TRACKS_CONTEXT_KEY] = tracked_leagues
    await update.message.reply_text(
        _build_track_selection_message("Qué liga querés dejar de trackear?", tracked_leagues),
        reply_markup=_build_numeric_keyboard(len(tracked_leagues), "Elegí el número de la liga"),
    )
    return SELECT_LEAGUE_FOR_UNTRACK


async def untrack_select_league(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the league selection during `/untrack`."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END

    tracked_leagues = context.user_data.get(UNTRACK_TRACKS_CONTEXT_KEY)
    if not isinstance(tracked_leagues, list) or not tracked_leagues:
        await update.message.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /untrack.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = _parse_selection_number(update.message.text, len(tracked_leagues))

    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de la lista.",
            reply_markup=_build_numeric_keyboard(len(tracked_leagues)),
        )
        return SELECT_LEAGUE_FOR_UNTRACK

    selected_track = tracked_leagues[selected_index]
    tracking_service = get_bet365_tracking_service(context)
    result = tracking_service.untrack_chat(
        update.effective_chat.id,
        selected_track.tracked_league.id,
    )

    await update.message.reply_text(
        result.message,
        reply_markup=ReplyKeyboardRemove(),
    )
    _clear_all_selection_context(context)
    return ConversationHandler.END


async def odds_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the interactive flow that enables odds-change notifications."""

    return await _start_odds_toggle(update, context, enabled=True)


async def odds_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the interactive flow that disables odds-change notifications."""

    return await _start_odds_toggle(update, context, enabled=False)


async def odds_select_league(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the league selection during `/odds_on` or `/odds_off`."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END

    tracked_leagues = context.user_data.get(ODDS_TRACKS_CONTEXT_KEY)
    enabled = context.user_data.get(ODDS_ENABLED_CONTEXT_KEY)

    if not isinstance(tracked_leagues, list) or not tracked_leagues or not isinstance(enabled, bool):
        await update.message.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /odds_on o /odds_off.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = _parse_selection_number(update.message.text, len(tracked_leagues))

    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de la lista.",
            reply_markup=_build_numeric_keyboard(len(tracked_leagues)),
        )
        return SELECT_LEAGUE_FOR_ODDS

    selected_track = tracked_leagues[selected_index]
    tracking_service = get_bet365_tracking_service(context)
    result = tracking_service.set_odds_change_notifications(
        update.effective_chat.id,
        selected_track.tracked_league.id,
        enabled=enabled,
    )

    await update.message.reply_text(
        result.message,
        reply_markup=ReplyKeyboardRemove(),
    )
    _clear_all_selection_context(context)
    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel any active interactive selection flow."""

    _clear_all_selection_context(context)

    if update.message is not None:
        await update.message.reply_text(
            "Selección cancelada.",
            reply_markup=ReplyKeyboardRemove(),
        )

    return ConversationHandler.END


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unsupported Telegram commands."""

    del context

    if update.message is None:
        return

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
    application.add_handler(CommandHandler("track_url", track_url_command))
    application.add_handler(CommandHandler("confirm_track", confirm_track_command))
    application.add_handler(CommandHandler("list_tracks", list_tracks_command))
    application.add_handler(CommandHandler("refresh_tracks", refresh_tracks_command))

    matches_conversation = ConversationHandler(
        entry_points=[CommandHandler("matches", matches_command)],
        states={
            SELECT_LEAGUE_FOR_MATCHES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, matches_select_league)
            ],
            SELECT_MATCH_FOR_MATCHES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, matches_select_match)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        name="bet365_matches_conversation",
        persistent=False,
    )
    application.add_handler(matches_conversation)

    untrack_conversation = ConversationHandler(
        entry_points=[CommandHandler("untrack", untrack_command)],
        states={
            SELECT_LEAGUE_FOR_UNTRACK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, untrack_select_league)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        name="bet365_untrack_conversation",
        persistent=False,
    )
    application.add_handler(untrack_conversation)

    odds_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("odds_on", odds_on_command),
            CommandHandler("odds_off", odds_off_command),
        ],
        states={
            SELECT_LEAGUE_FOR_ODDS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, odds_select_league)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        name="bet365_odds_conversation",
        persistent=False,
    )
    application.add_handler(odds_conversation)

    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))


async def _start_odds_toggle(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    enabled: bool,
) -> int:
    """Start the interactive odds-notification toggle flow."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END

    tracking_service = get_bet365_tracking_service(context)
    tracked_leagues = tracking_service.list_confirmed_tracks(update.effective_chat.id)

    if not tracked_leagues:
        await update.message.reply_text(
            "No tenés ligas trackeadas para configurar.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    context.user_data[ODDS_TRACKS_CONTEXT_KEY] = tracked_leagues
    context.user_data[ODDS_ENABLED_CONTEXT_KEY] = enabled

    prompt = (
        "Qué liga querés activar para cambios de odds?"
        if enabled
        else "Qué liga querés desactivar para cambios de odds?"
    )
    await update.message.reply_text(
        _build_track_selection_message(prompt, tracked_leagues),
        reply_markup=_build_numeric_keyboard(len(tracked_leagues), "Elegí el número de la liga"),
    )
    return SELECT_LEAGUE_FOR_ODDS


def _build_track_selection_message(prompt: str, tracks: list[TrackedLeagueSubscription]) -> str:
    """Build a league-selection prompt using numbered tracked leagues."""

    lines = [prompt]

    for index, item in enumerate(tracks, start=1):
        lines.append(f"{index} - {item.tracked_league.league_name}")

    return "\n".join(lines)


def _build_match_selection_message(
    tracked_league: TrackedLeagueSubscription,
    matches: list[ActiveMatchRecord],
) -> str:
    """Build the second prompt used by `/matches`."""

    lines = [f"Qué partido quiere ver de {tracked_league.tracked_league.league_name}?"]
    lines.append("1 - Ver todos")

    for index, match in enumerate(matches, start=2):
        lines.append(f"{index} - {match.home} vs {match.away}")

    return "\n".join(lines)


def _build_numeric_keyboard(
    count: int,
    placeholder: str | None = None,
) -> ReplyKeyboardMarkup:
    """Build a one-column numeric keyboard for Telegram selections."""

    keyboard = [[str(index)] for index in range(1, count + 1)]
    return ReplyKeyboardMarkup(
        keyboard,
        one_time_keyboard=True,
        resize_keyboard=True,
        input_field_placeholder=placeholder,
    )


def _parse_selection_number(text: str | None, upper_bound: int) -> int | None:
    """Parse a one-based numeric selection from Telegram text."""

    if text is None:
        return None

    candidate = text.strip()

    if not candidate.isdigit():
        return None

    index = int(candidate) - 1

    if index < 0 or index >= upper_bound:
        return None

    return index


def _clear_all_selection_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove temporary state used by interactive Telegram conversations."""

    context.user_data.pop(MATCHES_TRACKS_CONTEXT_KEY, None)
    context.user_data.pop(MATCHES_ACTIVE_CONTEXT_KEY, None)
    context.user_data.pop(MATCHES_SELECTED_TRACK_CONTEXT_KEY, None)
    context.user_data.pop(UNTRACK_TRACKS_CONTEXT_KEY, None)
    context.user_data.pop(ODDS_TRACKS_CONTEXT_KEY, None)
    context.user_data.pop(ODDS_ENABLED_CONTEXT_KEY, None)

"""Telegram command handlers for the current sportsbook tracking bot flow."""

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

from bot.alerts import (
    build_all_matches_message,
    build_competition_unavailable_warning_message,
    build_little_changes_message,
    build_match_card_message,
)
from core.extractor_base import CompetitionUnavailableError
from monitoring import format_system_metrics_message, get_system_metrics
from monitors.tracking import CommandResult, TrackingService
from storage.tracking_repository import ActiveEventRecord, TrackedCompetitionSubscription

logger = logging.getLogger(__name__)

SELECT_LEAGUE_FOR_MATCHES = 1
SELECT_MATCH_FOR_MATCHES = 2
SELECT_LEAGUE_FOR_UNTRACK = 3
SELECT_LEAGUE_FOR_ODDS = 4
SELECT_LEAGUE_FOR_CHANGE_PERCENT = 5

MATCHES_TRACKS_CONTEXT_KEY = "matches_tracks"
MATCHES_ACTIVE_CONTEXT_KEY = "matches_active"
MATCHES_SELECTED_TRACK_CONTEXT_KEY = "matches_selected_track"
UNTRACK_TRACKS_CONTEXT_KEY = "untrack_tracks"
ODDS_TRACKS_CONTEXT_KEY = "odds_tracks"
ODDS_ENABLED_CONTEXT_KEY = "odds_enabled"
CHANGE_PERCENT_TRACKS_CONTEXT_KEY = "change_percent_tracks"
CHANGE_PERCENT_VALUE_CONTEXT_KEY = "change_percent_value"

HELP_MESSAGE = (
    "Comandos generales\n"
    "/start - Mensaje de bienvenida\n"
    "/help - Lista de comandos\n"
    "/guide - Guía rápida del flujo\n"
    "/platforms - Plataformas soportadas\n"
    "/ping - Responde pong\n"
    "/status - Informa si el bot está online\n"
    "/stats - Muestra métricas simples de recursos\n"
    "/echo <texto> - Devuelve el texto enviado\n\n"
    "Tracking de ligas\n"
    "/track_url <url> - Extrae una liga de una plataforma soportada y la deja pendiente\n"
    "/confirm_track - Confirma la última liga pendiente\n"
    "/confirm_empty_track - Confirma una liga válida pero vacía\n"
    "/list_tracks - Lista las ligas trackeadas\n"
    "/competition_url <n> - Muestra la URL original de una liga trackeada\n"
    "/refresh_tracks - Actualiza partidos y detecta eventos nuevos\n"
    "/update_track_url <n> <url> - Actualiza la URL de una liga usando el número de /list_tracks\n"
    "/untrack - Permite dejar de trackear una liga\n\n"
    "Consulta de partidos\n"
    "/matches - Permite elegir una liga y ver sus partidos\n"
    "/event_url <n> - Muestra la URL directa de un partido de la última lista de /matches\n\n"
    "Configuración de odds\n"
    "/odds_on - Activa notificaciones de cambios de odds para una liga\n"
    "/odds_off - Desactiva notificaciones de cambios de odds para una liga\n"
    "/set_change_percent <n> - Configura el % mínimo de cambio para alertar\n\n"
    "Little changes\n"
    "/check_little_changes - Lista cambios pequeños pendientes\n"
    "/confirm_change <n> - Confirma un little change por número\n"
    "/confirm_all_little_changes - Confirma todos los pendientes\n\n"
    "Flujos interactivos\n"
    "/cancel - Cancela la selección interactiva actual"
)

GUIDE_MESSAGE = (
    "Guía rápida\n\n"
    "1. /platforms\n"
    "2. /track_url <url>\n"
    "3. /confirm_track\n"
    "4. /list_tracks\n"
    "5. /competition_url <n>\n"
    "6. /matches\n"
    "7. /event_url <n>\n"
    "8. /update_track_url <n> <url> si el link cambió\n"
    "9. /odds_on\n"
    "10. /set_change_percent 20\n"
    "11. /check_little_changes\n"
    "12. /confirm_change <n> o /confirm_all_little_changes"
)

TRACK_URL_USAGE_MESSAGE = (
    "Usá /track_url <url_de_plataforma>.\n"
    "Primero podés usar /platforms para ver las plataformas disponibles\n"
    "y después pegar la URL de una competencia."
)

SET_CHANGE_PERCENT_USAGE_MESSAGE = (
    "Usá /set_change_percent <porcentaje>.\n"
    "Ejemplo:\n"
    "/set_change_percent 20"
)

UPDATE_TRACK_URL_USAGE_MESSAGE = (
    "Usá /update_track_url <número_de_/list_tracks> <nuevo_link>.\n"
    "Ejemplo:\n"
    "/update_track_url 2 https://www.bet365.es/#/AC/B1/C1/D1002/E123/G40/"
)

COMPETITION_URL_USAGE_MESSAGE = (
    "Usá /competition_url <número_de_/list_tracks>.\n"
    "Ejemplo:\n"
    "/competition_url 2"
)

EVENT_URL_USAGE_MESSAGE = (
    "Usá /event_url <número_visible_en_/matches>.\n"
    "Primero corré /matches, elegí una liga y después pedí el link del partido.\n"
    "Ejemplo:\n"
    "/event_url 3"
)


def get_tracking_service(context: ContextTypes.DEFAULT_TYPE) -> TrackingService:
    """Retrieve the shared tracking service from the application."""

    tracking_service = context.application.bot_data.get("tracking_service")

    if not isinstance(tracking_service, TrackingService):
        raise RuntimeError("TrackingService no está configurado en la aplicación.")

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
        f"Hola, {first_name}. Soy tu bot de tracking de plataformas de apuestas.\n\n"
        "Podés registrar ligas con /track_url, confirmarlas con /confirm_track, "
        "verlas con /list_tracks, consultar partidos con /matches y ver plataformas con /platforms."
    )

    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/help` command."""

    del context

    if update.message is None:
        return

    await update.message.reply_text(HELP_MESSAGE)


async def guide_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/guide` command."""

    del context

    if update.message is None:
        return

    await update.message.reply_text(GUIDE_MESSAGE)


async def platforms_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/platforms` with the registered extractor list."""

    if update.message is None:
        return

    tracking_service = get_tracking_service(context)
    await reply_with_result(update, tracking_service.build_platforms_message())


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


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/stats` command with runtime resource metrics."""

    del context

    if update.message is None:
        return

    metrics = get_system_metrics()
    await update.message.reply_text(format_system_metrics_message(metrics))


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
    """Handle `/track_url <url>` for competition discovery."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /track_url recibido.")

    if not context.args:
        await update.message.reply_text(TRACK_URL_USAGE_MESSAGE)
        return

    url = " ".join(context.args).strip()
    tracking_service = get_tracking_service(context)
    result = await tracking_service.create_pending_track_from_url(
        chat_id=update.effective_chat.id,
        url=url,
    )

    await reply_with_result(update, result)


async def confirm_track_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/confirm_track` for the latest pending tracking request."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /confirm_track recibido.")

    tracking_service = get_tracking_service(context)
    result = await tracking_service.confirm_pending_track(update.effective_chat.id)

    await reply_with_result(update, result)


async def confirm_empty_track_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/confirm_empty_track` for a valid but currently empty competition."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /confirm_empty_track recibido.")

    tracking_service = get_tracking_service(context)
    result = await tracking_service.confirm_empty_pending_track(update.effective_chat.id)

    await reply_with_result(update, result)


async def list_tracks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/list_tracks` using the tracked subscription store."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /list_tracks recibido.")

    tracking_service = get_tracking_service(context)
    result = tracking_service.build_tracks_list_message(update.effective_chat.id)

    await reply_with_result(update, result)


async def competition_url_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/competition_url <track_number>` for one tracked competition."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /competition_url recibido.")

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text(COMPETITION_URL_USAGE_MESSAGE)
        return

    track_number = int(context.args[0])
    if track_number <= 0:
        await update.message.reply_text(COMPETITION_URL_USAGE_MESSAGE)
        return

    tracking_service = get_tracking_service(context)
    result = tracking_service.build_competition_url_message(
        update.effective_chat.id,
        track_number,
    )

    await update.message.reply_text(result.message, parse_mode=ParseMode.HTML)


async def update_track_url_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/update_track_url <track_number> <new_url>` for one chat subscription."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /update_track_url recibido.")

    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text(UPDATE_TRACK_URL_USAGE_MESSAGE)
        return

    track_number = int(context.args[0])
    new_url = " ".join(context.args[1:]).strip()

    if track_number <= 0 or not new_url:
        await update.message.reply_text(UPDATE_TRACK_URL_USAGE_MESSAGE)
        return

    tracking_service = get_tracking_service(context)
    result = await tracking_service.update_tracked_competition_url(
        update.effective_chat.id,
        track_number=track_number,
        new_url=new_url,
    )

    await reply_with_result(update, result)


async def refresh_tracks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/refresh_tracks` and send notifications for the refreshed leagues."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /refresh_tracks recibido.")

    tracking_service = get_tracking_service(context)

    try:
        summary = await tracking_service.refresh_chat_tracks(update.effective_chat.id)
        await tracking_service.dispatch_notifications(
            context.bot,
            summary,
            force_unavailable_warnings=True,
            unavailable_warning_chat_id=update.effective_chat.id,
        )
    except (RuntimeError, ValueError) as error:
        logger.exception("Tracking refresh failed for chat_id=%s.", update.effective_chat.id)
        await update.message.reply_text(
            "No pude actualizar las ligas trackeadas en este momento.\n\n"
            "Volvé a intentar en unos minutos."
        )
        return

    await reply_with_result(update, tracking_service.build_refresh_summary_message(summary))


async def event_url_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/event_url <event_number>` using the latest `/matches` context."""

    if update.message is None:
        return

    logger.info("Comando /event_url recibido.")

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text(EVENT_URL_USAGE_MESSAGE)
        return

    active_matches = context.user_data.get(MATCHES_ACTIVE_CONTEXT_KEY)
    tracked_subscription = context.user_data.get(MATCHES_SELECTED_TRACK_CONTEXT_KEY)

    if not isinstance(active_matches, list) or not active_matches:
        await update.message.reply_text(
            "No tengo una lista reciente de partidos para este chat.\n\n"
            "Usá /matches, elegí una liga y después /event_url <n>."
        )
        return

    if not isinstance(tracked_subscription, TrackedCompetitionSubscription):
        await update.message.reply_text(
            "No tengo una liga seleccionada recientemente.\n\n"
            "Usá /matches, elegí una liga y después /event_url <n>."
        )
        return

    selected_index = _parse_selection_number(context.args[0], len(active_matches) + 1)
    if selected_index is None:
        await update.message.reply_text(EVENT_URL_USAGE_MESSAGE)
        return

    if selected_index == 0:
        await update.message.reply_text(
            "El número 1 corresponde a \"Ver todos\".\n\n"
            "Elegí el número visible de un partido individual de la última lista de /matches."
        )
        return

    tracking_service = get_tracking_service(context)
    result = tracking_service.build_event_url_message(
        tracked_subscription,
        active_matches,
        selected_index,
    )

    await update.message.reply_text(result.message, parse_mode=ParseMode.HTML)


async def matches_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the interactive `/matches` flow."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END

    logger.info("Comando /matches recibido.")

    tracking_service = get_tracking_service(context)
    tracked_leagues = tracking_service.list_confirmed_tracks(update.effective_chat.id)

    if not tracked_leagues:
        await update.message.reply_text(
            "No tenés ligas trackeadas todavía.\n"
            "Usá /track_url <url_de_plataforma> y después /confirm_track."
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
    tracking_service = get_tracking_service(context)

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
        except CompetitionUnavailableError:
            await update.message.reply_text(
                build_competition_unavailable_warning_message(
                    selected_track.tracked_league,
                    track_number=selected_index + 1,
                    title="⚠️ <b>No pude actualizar esa liga en este momento.</b>",
                ),
                reply_markup=ReplyKeyboardRemove(),
                parse_mode=ParseMode.HTML,
            )
            _clear_all_selection_context(context)
            return ConversationHandler.END
        except (RuntimeError, ValueError) as error:
            logger.exception(
                "Failed to refresh tracked league %s for chat_id=%s.",
                selected_track.tracked_league.id,
                update.effective_chat.id,
            )
            await update.message.reply_text(
                "⚠️ No pude actualizar esa liga en este momento.\n\n"
                "Volvé a intentar en unos minutos.",
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

    if not isinstance(tracked_league, TrackedCompetitionSubscription):
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

    tracking_service = get_tracking_service(context)
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
    tracking_service = get_tracking_service(context)
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
    tracking_service = get_tracking_service(context)
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


async def set_change_percent_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the interactive flow that configures odds-change sensitivity."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END

    if len(context.args) != 1:
        await update.message.reply_text(
            SET_CHANGE_PERCENT_USAGE_MESSAGE,
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    try:
        percent = float(context.args[0].replace(",", "."))
    except ValueError:
        await update.message.reply_text(
            "El porcentaje debe ser un número válido.\n\n"
            f"{SET_CHANGE_PERCENT_USAGE_MESSAGE}",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    if percent <= 0:
        await update.message.reply_text(
            "El porcentaje debe ser mayor a 0.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    tracking_service = get_tracking_service(context)
    tracked_leagues = tracking_service.list_confirmed_tracks(update.effective_chat.id)

    if not tracked_leagues:
        await update.message.reply_text(
            "No tenés ligas trackeadas para configurar.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    context.user_data[CHANGE_PERCENT_TRACKS_CONTEXT_KEY] = tracked_leagues
    context.user_data[CHANGE_PERCENT_VALUE_CONTEXT_KEY] = percent

    await update.message.reply_text(
        _build_track_selection_message(
            f"Qué liga querés configurar con umbral {percent:.1f}%?",
            tracked_leagues,
        ),
        reply_markup=_build_numeric_keyboard(len(tracked_leagues), "Elegí el número de la liga"),
    )
    return SELECT_LEAGUE_FOR_CHANGE_PERCENT


async def set_change_percent_select_league(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Handle the league selection during `/set_change_percent`."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END

    tracked_leagues = context.user_data.get(CHANGE_PERCENT_TRACKS_CONTEXT_KEY)
    percent = context.user_data.get(CHANGE_PERCENT_VALUE_CONTEXT_KEY)

    if not isinstance(tracked_leagues, list) or not tracked_leagues or not isinstance(percent, float):
        await update.message.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /set_change_percent.",
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
        return SELECT_LEAGUE_FOR_CHANGE_PERCENT

    selected_track = tracked_leagues[selected_index]
    tracking_service = get_tracking_service(context)
    result = tracking_service.set_change_percent(
        update.effective_chat.id,
        selected_track.tracked_league.id,
        percent,
    )

    await update.message.reply_text(
        result.message,
        reply_markup=ReplyKeyboardRemove(),
    )
    _clear_all_selection_context(context)
    return ConversationHandler.END


async def check_little_changes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/check_little_changes` for the current chat."""

    if update.message is None or update.effective_chat is None:
        return

    tracking_service = get_tracking_service(context)
    changes = tracking_service.get_pending_little_changes(update.effective_chat.id)

    if not changes:
        await update.message.reply_text("No tenés little changes pendientes.")
        return

    await update.message.reply_text(
        build_little_changes_message(changes),
        parse_mode=ParseMode.HTML,
    )


async def confirm_change_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/confirm_change <n>` using the current pending order."""

    if update.message is None or update.effective_chat is None:
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text(
            "Usá /confirm_change <n>.\n"
            "Primero podés mirar la lista con /check_little_changes."
        )
        return

    index = int(context.args[0]) - 1
    tracking_service = get_tracking_service(context)
    result = tracking_service.confirm_little_change_by_index(update.effective_chat.id, index)

    await reply_with_result(update, result)


async def confirm_all_little_changes_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle `/confirm_all_little_changes` for the current chat."""

    if update.message is None or update.effective_chat is None:
        return

    tracking_service = get_tracking_service(context)
    result = tracking_service.confirm_all_pending_little_changes(update.effective_chat.id)

    await reply_with_result(update, result)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel any active interactive selection flow."""

    _clear_all_selection_context(context)

    if update.effective_chat is not None:
        tracking_service = get_tracking_service(context)
        if tracking_service.cancel_pending_empty_track(update.effective_chat.id):
            if update.message is not None:
                await update.message.reply_text(
                    "Se canceló la liga vacía pendiente.",
                    reply_markup=ReplyKeyboardRemove(),
                )
            return ConversationHandler.END

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
    application.add_handler(CommandHandler("guide", guide_command))
    application.add_handler(CommandHandler("platforms", platforms_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("echo", echo_command))
    application.add_handler(CommandHandler("track_url", track_url_command))
    application.add_handler(CommandHandler("confirm_track", confirm_track_command))
    application.add_handler(CommandHandler("confirm_empty_track", confirm_empty_track_command))
    application.add_handler(CommandHandler("list_tracks", list_tracks_command))
    application.add_handler(CommandHandler("competition_url", competition_url_command))
    application.add_handler(CommandHandler("refresh_tracks", refresh_tracks_command))
    application.add_handler(CommandHandler("update_track_url", update_track_url_command))
    application.add_handler(CommandHandler("event_url", event_url_command))
    application.add_handler(CommandHandler("check_little_changes", check_little_changes_command))
    application.add_handler(CommandHandler("confirm_change", confirm_change_command))
    application.add_handler(
        CommandHandler("confirm_all_little_changes", confirm_all_little_changes_command)
    )

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
        name="matches_conversation",
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
        name="untrack_conversation",
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
        name="odds_conversation",
        persistent=False,
    )
    application.add_handler(odds_conversation)

    change_percent_conversation = ConversationHandler(
        entry_points=[CommandHandler("set_change_percent", set_change_percent_command)],
        states={
            SELECT_LEAGUE_FOR_CHANGE_PERCENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_change_percent_select_league)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        name="change_percent_conversation",
        persistent=False,
    )
    application.add_handler(change_percent_conversation)

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

    tracking_service = get_tracking_service(context)
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


def _build_track_selection_message(prompt: str, tracks: list[TrackedCompetitionSubscription]) -> str:
    """Build a league-selection prompt using numbered tracked leagues."""

    lines = [prompt]

    for index, item in enumerate(tracks, start=1):
        lines.append(
            f"{index} - [{item.tracked_league.platform_display_name}] {item.tracked_league.league_name}"
        )

    return "\n".join(lines)


def _build_match_selection_message(
    tracked_league: TrackedCompetitionSubscription,
    matches: list[ActiveEventRecord],
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
    context.user_data.pop(CHANGE_PERCENT_TRACKS_CONTEXT_KEY, None)
    context.user_data.pop(CHANGE_PERCENT_VALUE_CONTEXT_KEY, None)

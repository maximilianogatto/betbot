"""Telegram command handlers for the current sportsbook tracking bot flow."""

from __future__ import annotations

import asyncio
from datetime import date
import logging
import re
from typing import Any
import unicodedata

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from interfaces.telegram.renderers import (
    build_all_matches_message,
    build_competition_unavailable_warning_message,
    build_little_changes_message,
    build_match_card_message,
    format_kickoff_labels,
    split_telegram_message,
)
from core.extractor_base import CompetitionUnavailableError, LeagueDiscoveryOption
from core.models import PlatformDescriptor
from core.timezones import (
    COMMON_TIMEZONES,
    current_display_timezone,
    get_zoneinfo,
    resolve_chat_timezone,
    set_display_timezone,
    tz_offset_label,
)
from core.stats_models import MatchIdentityCandidate, StatsLeagueOption, StatsProviderDescriptor
from monitoring import format_system_metrics_message, get_system_metrics
from services.stats import (
    ExplorableStatsLeague,
    StatsService,
    render_league_fixtures,
    render_league_table,
    render_team_row,
    render_top_scorers,
)
from services.special_peak import SpecialMatchScore
from services.tracking import CommandResult, TrackingService
from core.models import (
    ActiveEventRecord,
    TrackedCompetitionSubscription,
)
from adapters.storage import get_storage

logger = logging.getLogger(__name__)

from interfaces.telegram.handlers.peak import (  # noqa: F401
    _PEAK_SCORES_CACHE,
    _get_cached_peaks,
    _set_cached_peaks,
    filter_peaks,
    peak_off_command,
    peak_on_command,
    peak_today_command,
    peaks_callback_query_handler,
    peaks_command,
    render_filtered_peak_digest,
)

from interfaces.telegram.handlers.system import (  # noqa: F401
    HELP_LEAGUES_MESSAGE,
    HELP_MATCHES_MESSAGE,
    HELP_MESSAGE,
    _get_sportradar_provider,
    apply_chat_timezone_context,
    cancel_callback,
    cancel_command,
    help_command,
    help_leagues_command,
    help_live_command,
    help_matches_command,
    platforms_command,
    sportradar_token_command,
    start_command,
    timezone_command,
)

from interfaces.telegram.handlers.live_watch import (  # noqa: F401
    _format_live_state_report,
    format_watch_entry_report,
    view_match_command,
    HELP_LIVE_MESSAGE,
    _format_live_settings,
    _parse_live_setting_bool,
    import_sheet_command,
    live_settings_command,
    live_status_command,
    unwatch_command,
    watch_live_command,
    watch_live_photo_handler,
    watching_command,
)

from interfaces.telegram.handlers.stats import (  # noqa: F401
    EXPLORE_MENU,
    EXPLORE_SELECT_FIXTURE,
    EXPLORE_TEAM_INPUT,
    explore_menu,
    explore_select_fixture,
    explore_select_league,
    explore_team_input,
    ENTER_COUNTRY_FOR_LINK_STATS,
    ENTER_COUNTRY_FOR_TRACK_STATS,
    EXPLORE_SELECT_LEAGUE,
    HELP_STATS_MESSAGE,
    SELECT_LEAGUE_FOR_LINK_STATS,
    SELECT_LEAGUE_FOR_STATS,
    SELECT_LEAGUE_FOR_TRACK_STATS,
    SELECT_MATCH_FOR_STATS,
    SELECT_PROVIDER_FOR_LINK_STATS,
    SELECT_PROVIDER_FOR_TRACK_STATS,
    SELECT_STATS_CANDIDATE,
    SELECT_TRACK_FOR_LINK_STATS,
    STATS_URL_USAGE_MESSAGE,
    _EXPLORE_MENU_LABELS,
    _HTTP_URL_RE,
    _STATSHUB_TOURNAMENT_RE,
    _build_stats_league_selection_message,
    _build_stats_match_selection_message,
    _build_stats_provider_input_message,
    _build_stats_provider_selection_message,
    _build_unified_stats_match_selection_message,
    _extract_direct_stats_league_reference,
    _extract_statshub_tournament_id,
    _send_unified_stats_report,
    explore_stats_command,
    help_stats_command,
    link_stats_command,
    link_stats_enter_country,
    link_stats_select_league,
    link_stats_select_provider,
    link_stats_select_track,
    stats_callback_query_handler,
    stats_command,
    stats_help_command,
    stats_leagues_command,
    stats_links_command,
    stats_select_candidate,
    stats_select_league,
    stats_select_match,
    stats_tracks_command,
    track_stats_command,
    track_stats_enter_country,
    track_stats_select_league,
    track_stats_select_provider,
)

from interfaces.telegram.handlers.common import (  # noqa: F401
    CHANGE_PERCENT_TRACKS_CONTEXT_KEY,
    CHANGE_PERCENT_VALUE_CONTEXT_KEY,
    COUNTRIES_MAP,
    EXPLORE_FIXTURES_CONTEXT_KEY,
    EXPLORE_OVERVIEW_CONTEXT_KEY,
    EXPLORE_SELECTED_LEAGUE_CONTEXT_KEY,
    EXPLORE_TRACKS_CONTEXT_KEY,
    LINK_STATS_OPTIONS_CONTEXT_KEY,
    LINK_STATS_PROVIDERS_CONTEXT_KEY,
    LINK_STATS_SELECTED_PROVIDER_CONTEXT_KEY,
    LINK_STATS_SELECTED_TRACK_CONTEXT_KEY,
    LINK_STATS_TRACKS_CONTEXT_KEY,
    MATCHES_ACTIVE_CONTEXT_KEY,
    MATCHES_SELECTED_TRACK_CONTEXT_KEY,
    MATCHES_TRACKS_CONTEXT_KEY,
    ODDS_ENABLED_CONTEXT_KEY,
    ODDS_TRACKS_CONTEXT_KEY,
    STATS_ACTIVE_CONTEXT_KEY,
    STATS_CANDIDATES_CONTEXT_KEY,
    STATS_CANDIDATE_MATCH_CONTEXT_KEY,
    STATS_CANDIDATE_PROVIDER_CONTEXT_KEY,
    STATS_SELECTED_TRACK_CONTEXT_KEY,
    STATS_TRACKS_CONTEXT_KEY,
    TRACK_LEAGUE_OPTIONS_CONTEXT_KEY,
    TRACK_LEAGUE_PLATFORMS_CONTEXT_KEY,
    TRACK_LEAGUE_SELECTED_PLATFORM_CONTEXT_KEY,
    TRACK_STATS_OPTIONS_CONTEXT_KEY,
    TRACK_STATS_PROVIDERS_CONTEXT_KEY,
    TRACK_STATS_SELECTED_PROVIDER_CONTEXT_KEY,
    UNTRACK_TRACKS_CONTEXT_KEY,
    _CANCEL_CALLBACK_DATA,
    _build_choice_keyboard,
    _build_track_selection_message,
    _build_unified_league_selection_message,
    _clear_all_selection_context,
    _get_country_adapter,
    _parse_selection_number,
    _reply_text_chunks,
    _selected_index,
    _selection_target,
    _send_text_chunks,
    _show_country_help,
    _show_league_selector,
    _show_today_matches_selector,
    escape_html,
    get_country_selector_keyboard,
    get_live_watch_service,
    get_stats_service,
    get_tracking_service,
    reply_with_result,
)

from interfaces.telegram.handlers.special_leagues import (  # noqa: F401
    _SWE_LEAGUES,
    _AL_LEAGUE_USAGE,
    _FIN_LEAGUE_USAGE,
    _NO_LEAGUE_USAGE,
    _RO_LEAGUE_USAGE,
    _SK_LEAGUE_USAGE,
    _algeria_adapter,
    _convert_fin_to_arg_datetime,
    _convert_swe_to_arg_datetime,
    _finland_adapter,
    _norway_adapter,
    _resolve_swe_league,
    _romania_adapter,
    _run_special_fixtures,
    _run_special_leagues,
    _run_special_match,
    _run_special_standings,
    _run_special_today,
    _slovakia_adapter,
    _swe_usage_guide,
    _sweden_adapter,
    al_fixtures_command,
    al_help_command,
    al_leagues_command,
    al_match_command,
    al_standings_command,
    al_today_command,
    fin_fixtures_command,
    fin_help_command,
    fin_leagues_command,
    fin_match_command,
    fin_standings_command,
    fin_today_command,
    no_fixtures_command,
    no_help_command,
    no_leagues_command,
    no_match_command,
    no_standings_command,
    no_today_command,
    ro_fixtures_command,
    ro_help_command,
    ro_leagues_command,
    ro_match_command,
    ro_standings_command,
    ro_today_command,
    sk_fixtures_command,
    sk_help_command,
    sk_leagues_command,
    sk_match_command,
    sk_standings_command,
    sk_today_command,
    swe_fixtures_command,
    swe_help_command,
    swe_leagues_command,
    swe_match_command,
    swe_results_command,
    swe_standings_command,
    swe_today_command,
)




SELECT_LEAGUE_FOR_MATCHES = 1
SELECT_MATCH_FOR_MATCHES = 2
SELECT_LEAGUE_FOR_UNTRACK = 3
SELECT_LEAGUE_FOR_ODDS = 4
SELECT_LEAGUE_FOR_CHANGE_PERCENT = 5
SELECT_PLATFORM_FOR_TRACK_LEAGUE = 6
ENTER_COUNTRY_FOR_TRACK_LEAGUE = 7
SELECT_LEAGUE_FOR_TRACK_LEAGUE = 8

MANUAL_REFRESH_TASK_KEY = "manual_refresh_task"






GUIDE_MESSAGE = (
    "🧭 <b>Guía rápida</b>\n\n"
    "<b>1 · Seguir una liga</b>\n"
    "  /track_league <i>(interactivo)</i> o <code>/track_url &lt;url&gt;</code> → /confirm_track\n"
    "  /list_tracks — revisá lo que seguís\n\n"
    "<b>2 · Ver partidos y odds</b>\n"
    "  /matches → <code>/event_url &lt;n&gt;</code> para el link del partido\n\n"
    "<b>3 · Alertas de cuotas</b>\n"
    "  /odds_on · <code>/set_change_percent 20</code>\n"
    "  /check_little_changes → <code>/confirm_change &lt;n&gt;</code> o /confirm_all_little_changes\n\n"
    "<b>4 · Estadísticas</b>\n"
    "  <code>/stats &lt;n&gt;</code> · si la casa no trae stats: /link_stats → /stats_links\n\n"
    "<b>5 · En vivo</b>\n"
    "  /watch_live → /watching\n\n"
    "💡 <i>Si un link cambia:</i> <code>/update_track_url &lt;n&gt; &lt;url&gt;</code>"
)

TRACK_URL_USAGE_MESSAGE = (
    "📌 <b>Seguir una liga por link</b>\n"
    "<code>/track_url &lt;url&gt;</code>\n"
    "<i>Pegá la URL de una competencia · casas en</i> /platforms\n\n"
    "Opcional, nombre al final con <code>|</code> <i>(útil en Mystake)</i>:\n"
    "<code>/track_url &lt;url&gt; | Australia NPL Northern NSW</code>"
)

SET_CHANGE_PERCENT_USAGE_MESSAGE = (
    "📊 <b>% mínimo de variación para alertar</b>\n"
    "<code>/set_change_percent &lt;n&gt;</code>\n"
    "Ejemplo: <code>/set_change_percent 20</code>"
)

UPDATE_TRACK_URL_USAGE_MESSAGE = (
    "🔗 <b>Actualizar el link de una liga</b>\n"
    "<code>/update_track_url &lt;n&gt; &lt;url&gt;</code>  <i>(n de</i> /list_tracks<i>)</i>\n"
    "Ejemplo: <code>/update_track_url 2 https://www.bet365.es/#/AC/B1/C1/D1002/E123/G40/</code>"
)

COMPETITION_URL_USAGE_MESSAGE = (
    "🔗 <b>Link original de una liga</b>\n"
    "<code>/competition_url &lt;n&gt;</code>  <i>(n de</i> /list_tracks<i>)</i>\n"
    "Ejemplo: <code>/competition_url 2</code>"
)

EVENT_URL_USAGE_MESSAGE = (
    "🔗 <b>Link directo de un partido</b>\n"
    "<code>/event_url &lt;n&gt;</code>  <i>(n de</i> /matches<i>)</i>\n"
    "<i>Corré</i> /matches <i>y elegí una liga primero.</i>\n"
    "Ejemplo: <code>/event_url 3</code>"
)













async def photo_guidance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Guide the user when they send a photo without any command."""

    del context
    if update.message is None:
        return

    await update.message.reply_text(
        "📸 Recibí tu imagen.\n\n"
        "Si esta imagen contiene una tabla de fixture y querés que vigile los partidos en vivo, "
        "subila de nuevo agregando como epígrafe/comentario el comando `/watch_live`."
    )








































async def guide_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/guide` command."""

    del context

    if update.message is None:
        return

    await update.message.reply_text(GUIDE_MESSAGE, parse_mode=ParseMode.HTML)












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


async def resources_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/resources` with runtime resource metrics."""

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
        await update.message.reply_text(TRACK_URL_USAGE_MESSAGE, parse_mode=ParseMode.HTML)
        return

    raw = " ".join(context.args).strip()
    # Optional custom name after a '|' (e.g. for Mystake, whose API has no names):
    #   /track_url <url> | Australia NPL Northern NSW
    custom_name: str | None = None
    if "|" in raw:
        url_part, _, name_part = raw.partition("|")
        url = url_part.strip()
        custom_name = name_part.strip() or None
    else:
        url = raw

    tracking_service = get_tracking_service(context)
    result = await tracking_service.create_pending_track_from_url(
        chat_id=update.effective_chat.id,
        url=url,
        custom_name=custom_name,
    )

    if result.ok and getattr(result, "data", None) is not None:
        from interfaces.telegram.renderers import build_pending_confirmation_message, build_empty_pending_confirmation_message
        if result.data.requires_empty_confirmation:
            msg = build_empty_pending_confirmation_message(result.data)
        else:
            msg = build_pending_confirmation_message(result.data)
        await _reply_text_chunks(update.message, msg)
    else:
        await reply_with_result(update, result)


async def bulk_track_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text message starting with 'Ligas:' for bulk tracking."""
    if update.message is None or update.message.text is None or update.effective_chat is None:
        return

    text = update.message.text.strip()
    if not text.lower().startswith("ligas:"):
        return

    logger.info("Bulk track text block received.")
    await update.message.reply_text("Iniciando importación masiva de ligas...")

    tracking_service = get_tracking_service(context)
    try:
        result = await tracking_service.bulk_track_leagues(
            chat_id=update.effective_chat.id,
            leagues_text=text,
        )
        await update.message.reply_text(result.message, parse_mode=ParseMode.HTML)
    except Exception as exc:
        logger.exception("Bulk tracking failed")
        await update.message.reply_text(f"❌ Ocurrió un error en la importación masiva: {exc}")


async def track_league_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start `/track_league` platform/country/league discovery."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END

    logger.info("Comando /track_league recibido.")

    tracking_service = get_tracking_service(context)
    platforms = tracking_service.list_league_discovery_platforms()

    if not platforms:
        await update.message.reply_text(
            "No hay plataformas con discovery de ligas habilitado todavía.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    context.user_data[TRACK_LEAGUE_PLATFORMS_CONTEXT_KEY] = platforms

    await update.message.reply_text(
        _build_discovery_platform_selection_message(platforms),
        reply_markup=_build_choice_keyboard([p.display_name for p in platforms], "tl_platform"),
    )
    return SELECT_PLATFORM_FOR_TRACK_LEAGUE


async def track_league_select_platform(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Handle platform selection for `/track_league`."""

    query = update.callback_query
    msg_obj = query.message if query else update.message
    if msg_obj is None:
        return ConversationHandler.END

    platforms = context.user_data.get(TRACK_LEAGUE_PLATFORMS_CONTEXT_KEY)
    if not isinstance(platforms, list) or not platforms:
        await msg_obj.reply_text(
            "No encontré la selección de plataformas. Probá de nuevo con /track_league.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = None
    if query is not None:
        await query.answer()
        data = query.data
        if data.startswith("tl_platform:"):
            selected_index = int(data.split(":")[1])
    else:
        selected_index = _parse_selection_number(update.message.text, len(platforms))

    if selected_index is None:
        await msg_obj.reply_text(
            "Elegí una plataforma de la lista.",
            reply_markup=_build_choice_keyboard([p.display_name for p in platforms], "tl_platform"),
        )
        return SELECT_PLATFORM_FOR_TRACK_LEAGUE

    selected_platform = platforms[selected_index]
    if not isinstance(selected_platform, PlatformDescriptor):
        await msg_obj.reply_text(
            "La plataforma seleccionada no es válida. Probá de nuevo con /track_league.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    context.user_data[TRACK_LEAGUE_SELECTED_PLATFORM_CONTEXT_KEY] = selected_platform
    await msg_obj.reply_text(
        (
            f"Plataforma elegida: {selected_platform.display_name}\n\n"
            "Escribí el país para buscar ligas.\n"
            "Ejemplos: Australia, Argentina, England"
        ),
        reply_markup=ReplyKeyboardRemove(),
    )
    return ENTER_COUNTRY_FOR_TRACK_LEAGUE


async def track_league_enter_country(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Search platform leagues after the user enters a country."""

    if update.message is None:
        return ConversationHandler.END

    selected_platform = context.user_data.get(TRACK_LEAGUE_SELECTED_PLATFORM_CONTEXT_KEY)
    if not isinstance(selected_platform, PlatformDescriptor):
        await update.message.reply_text(
            "No encontré la plataforma seleccionada. Probá de nuevo con /track_league.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    country_name = (update.message.text or "").strip()
    if not country_name:
        await update.message.reply_text("Escribí un país válido.")
        return ENTER_COUNTRY_FOR_TRACK_LEAGUE

    tracking_service = get_tracking_service(context)
    await update.message.reply_text(f"Buscando ligas en {country_name}...")

    try:
        league_options = await tracking_service.search_discoverable_leagues(
            platform=selected_platform.key,
            country_name=country_name,
            limit=80,
        )
    except Exception:
        logger.exception(
            "League discovery failed platform=%s country=%s",
            selected_platform.key,
            country_name,
        )
        await update.message.reply_text(
            "No pude buscar ligas ahora. Probá de nuevo en unos minutos.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    if not league_options:
        await update.message.reply_text(
            f"No encontré ligas para {country_name} en {selected_platform.display_name}.\n\n"
            "Probá con otro nombre de país o /cancel.",
        )
        return ENTER_COUNTRY_FOR_TRACK_LEAGUE

    context.user_data[TRACK_LEAGUE_OPTIONS_CONTEXT_KEY] = league_options

    await update.message.reply_text(
        _build_discovered_league_selection_message(league_options),
        reply_markup=_build_choice_keyboard(
            [option.league_name for option in league_options[:20]], "tl_league"
        ),
    )
    return SELECT_LEAGUE_FOR_TRACK_LEAGUE


async def track_league_select_league(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Track the league selected during `/track_league`."""

    query = update.callback_query
    msg_obj = query.message if query else update.message
    if msg_obj is None or update.effective_chat is None:
        return ConversationHandler.END

    league_options = context.user_data.get(TRACK_LEAGUE_OPTIONS_CONTEXT_KEY)
    if not isinstance(league_options, list) or not league_options:
        await msg_obj.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /track_league.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = None
    if query is not None:
        await query.answer()
        data = query.data
        if data.startswith("tl_league:"):
            selected_index = int(data.split(":")[1])
    else:
        selected_index = _parse_selection_number(update.message.text, len(league_options))

    if selected_index is None:
        await msg_obj.reply_text(
            "Elegí una liga de la lista.",
            reply_markup=_build_choice_keyboard(
                [option.league_name for option in league_options[:20]], "tl_league"
            ),
        )
        return SELECT_LEAGUE_FOR_TRACK_LEAGUE

    selected_option = league_options[selected_index]
    if not isinstance(selected_option, LeagueDiscoveryOption):
        await msg_obj.reply_text(
            "La liga seleccionada no es válida. Probá de nuevo con /track_league.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    tracking_service = get_tracking_service(context)
    await msg_obj.reply_text(
        f"Guardando tracking de {selected_option.league_name}...",
        reply_markup=ReplyKeyboardRemove(),
    )
    result = await tracking_service.track_discovered_league(
        update.effective_chat.id,
        selected_option,
    )

    await _reply_text_chunks(msg_obj, result.message, reply_markup=ReplyKeyboardRemove())
    _clear_all_selection_context(context)
    return ConversationHandler.END


























async def confirm_track_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/confirm_track` for the latest pending tracking request."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /confirm_track recibido.")

    tracking_service = get_tracking_service(context)
    result = await tracking_service.confirm_pending_track(update.effective_chat.id)

    if result.ok and getattr(result, "data", None) is not None:
        from interfaces.telegram.renderers import build_confirmation_message
        msg = build_confirmation_message(
            result.data["confirmed_request"],
            bootstrap_count=result.data["bootstrap_count"],
            bootstrap_error=result.data["bootstrap_error"],
        )
        await _reply_text_chunks(update.message, msg)
    else:
        await reply_with_result(update, result)


async def confirm_empty_track_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/confirm_empty_track` for a valid but currently empty competition."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /confirm_empty_track recibido.")

    tracking_service = get_tracking_service(context)
    result = await tracking_service.confirm_empty_pending_track(update.effective_chat.id)

    if result.ok and getattr(result, "data", None) is not None:
        from interfaces.telegram.renderers import build_empty_confirmation_message
        msg = build_empty_confirmation_message(result.data["confirmed_request"])
        await _reply_text_chunks(update.message, msg)
    else:
        await reply_with_result(update, result)


async def list_tracks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/list_tracks` using the tracked subscription store."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /list_tracks recibido.")

    tracking_service = get_tracking_service(context)
    tracked_leagues = tracking_service.list_confirmed_tracks(update.effective_chat.id)

    from interfaces.telegram.renderers import build_tracks_list_message
    result = build_tracks_list_message(tracked_leagues)

    await reply_with_result(update, result)
    await update.message.reply_text(
        "🏆 Vista cross-plataforma (qué libros/stats tiene cada liga): <code>/leagues</code>",
        parse_mode=ParseMode.HTML,
    )


def _subscribed_unified(chat_id: int) -> list[dict]:
    # Orden: agrupado por país (bandera alineada) y luego alfabético por nombre.
    # Las sin país detectado van al final. Este orden es la fuente única del índice
    # N que usan /league, /link_league, /unlink_league, etc. → display y selección
    # quedan consistentes.
    from core.league_naming import extract_league_traits

    unified = get_storage().list_subscribed_unified_competitions(chat_id)
    return sorted(
        unified,
        key=lambda u: (
            extract_league_traits(u.get("name")).get("country") or "zzzz",
            (u.get("name") or "").lower(),
        ),
    )


async def leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /leagues: list the cross-platform (unified) leagues for this chat."""
    del context
    if update.message is None or update.effective_chat is None:
        return
    from bot.canonical_leagues import build_league_card, render_leagues_list
    unified = _subscribed_unified(update.effective_chat.id)
    cards = [c for c in (build_league_card(get_storage(), u["id"]) for u in unified) if c]
    await _reply_text_chunks(update.message, render_leagues_list(cards), parse_mode=ParseMode.HTML)


async def league_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /league <N>: show the cross-platform card of the Nth league (from /leagues)."""
    if update.message is None or update.effective_chat is None:
        return
    from bot.canonical_leagues import build_league_card, render_league_card
    unified = _subscribed_unified(update.effective_chat.id)
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Uso: <code>/league [N]</code> (el N sale de /leagues).", parse_mode=ParseMode.HTML)
        return
    idx = int(context.args[0])
    if not (1 <= idx <= len(unified)):
        await update.message.reply_text("Número fuera de rango. Mirá <code>/leagues</code>.", parse_mode=ParseMode.HTML)
        return
    card = build_league_card(get_storage(), unified[idx - 1]["id"])
    if not card:
        await update.message.reply_text("No encontré esa liga.")
        return
    await _reply_text_chunks(update.message, render_league_card(card), parse_mode=ParseMode.HTML)


async def link_league_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /link_league <N> <M>: merge league M into N (same physical league)."""
    if update.message is None or update.effective_chat is None:
        return
    from bot.canonical_leagues import build_league_card, render_league_card
    unified = _subscribed_unified(update.effective_chat.id)
    args = context.args or []
    if len(args) != 2 or not all(a.isdigit() for a in args):
        await update.message.reply_text(
            "Uso: <code>/link_league [N] [M]</code> — fusiona la liga M dentro de la N "
            "(mismos partidos en otra plataforma). Los números salen de <code>/leagues</code>.",
            parse_mode=ParseMode.HTML,
        )
        return
    n, m = int(args[0]), int(args[1])
    if not (1 <= n <= len(unified)) or not (1 <= m <= len(unified)) or n == m:
        await update.message.reply_text("Números inválidos. Mirá <code>/leagues</code>.", parse_mode=ParseMode.HTML)
        return
    into_id, from_id = unified[n - 1]["id"], unified[m - 1]["id"]
    # Override manual: si estas ligas estaban bloqueadas por un /unlink_league previo,
    # el usuario afirma que SÍ son la misma — quitamos el bloqueo y avisamos.
    overridden = get_storage().clear_merge_exceptions_between(into_id, from_id)
    get_storage().merge_unified_competitions(from_id, into_id)
    card = build_league_card(get_storage(), into_id)
    aviso = (
        "⚠️ <b>Ojo:</b> estas ligas las habías separado a mano con "
        "<code>/unlink_league</code>. Las fusioné igual porque me lo pediste y quité "
        "ese bloqueo.\n\n"
        if overridden
        else ""
    )
    msg = aviso + "✅ Ligas fusionadas.\n\n" + (render_league_card(card) if card else "")
    await _reply_text_chunks(update.message, msg, parse_mode=ParseMode.HTML)


async def unlink_league_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /unlink_league <N> <plataforma>: split a platform off league N into its own."""
    if update.message is None or update.effective_chat is None:
        return
    unified = _subscribed_unified(update.effective_chat.id)
    args = context.args or []
    if len(args) < 2 or not args[0].isdigit():
        await update.message.reply_text(
            "Uso: <code>/unlink_league [N] [plataforma]</code> (ej: <code>/unlink_league 3 betovo</code>).",
            parse_mode=ParseMode.HTML,
        )
        return
    n = int(args[0])
    plat_q = args[1].lower()
    extra_q = " ".join(args[2:]).lower()  # id o fragmento del nombre, opcional
    if not (1 <= n <= len(unified)):
        await update.message.reply_text("Número fuera de rango. Mirá <code>/leagues</code>.", parse_mode=ParseMode.HTML)
        return
    comps = get_storage().list_tracked_competitions_for_unified(unified[n - 1]["id"])
    matches = [c for c in comps if plat_q in c.platform.lower()]
    if extra_q:
        matches = [
            c for c in matches
            if extra_q in str(c.competition_external_id).lower() or extra_q in c.competition_name.lower()
        ]
    if not matches:
        await update.message.reply_text(
            f"No encontré la plataforma «{escape_html(plat_q)}» en esa liga. Mirá <code>/league {n}</code>.",
            parse_mode=ParseMode.HTML,
        )
        return
    if len(matches) > 1:
        lines = [f"Esa liga tiene {len(matches)} competencias de «{escape_html(plat_q)}». ¿Cuál separo?"]
        for comp in matches:
            lines.append(
                f"  • <code>{escape_html(str(comp.competition_external_id))}</code> — {escape_html(comp.competition_name)}"
            )
        lines.append(f"\nUsá: <code>/unlink_league {n} {escape_html(plat_q)} [id_o_nombre]</code>")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return
    target = matches[0]
    old_uid = unified[n - 1]["id"]
    # Grabar el bloqueo ANTES de reasignar: un par por cada plataforma que quedaba
    # en la liga, para que el learner no la vuelva a fusionar con ninguna de ellas.
    blocked_pairs = get_storage().block_unlinked_competition(target.id, old_uid)
    new_uid = get_storage().create_unified_competition(target.competition_name)
    get_storage().link_tracked_competition_to_unified(target.id, new_uid)
    nota = (
        f"\n🔒 No la volveré a unificar automáticamente con esa liga "
        f"({blocked_pairs} plataforma/s). Si te equivocaste, usá <code>/link_league</code>."
        if blocked_pairs
        else ""
    )
    await update.message.reply_text(
        f"✅ Saqué <b>{escape_html(target.platform.replace('_http', ''))}</b> "
        f"({escape_html(target.competition_name)}) de la liga; quedó como liga propia."
        + nota,
        parse_mode=ParseMode.HTML,
    )


async def undo_league_merge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Botón «Estuvo mal, separalas» del aviso de unificación automática.

    Deshace el merge que acaba de hacer el learner y graba el bloqueo para que no
    las vuelva a pegar. callback_data: `undomrg:<into_id>:<comp_ids separados por coma>`.
    """
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    try:
        _, into_raw, ids_raw = (query.data or "").split(":", 2)
        into_id = int(into_raw)
        moved_ids = [int(x) for x in ids_raw.split(",") if x.strip()]
    except (ValueError, AttributeError):
        await query.edit_message_text("No pude interpretar ese botón. Usá /unlink_league.")
        return

    tracking_service = context.application.bot_data.get("tracking_service")
    if not isinstance(tracking_service, TrackingService):
        return

    result = await asyncio.to_thread(
        tracking_service.undo_league_merge, moved_ids, into_id, ""
    )
    if not result["moved"]:
        await query.edit_message_text(
            "⚠️ No encontré esas competencias (quizá ya las separaste). Mirá /leagues."
        )
        return

    await query.edit_message_text(
        "↩️ <b>Deshecho.</b> Separé "
        f"<b>{result['moved']}</b> plataforma/s en su propia liga.\n"
        f"🔒 No las voy a volver a unificar automáticamente ({result['blocked']} bloqueo/s).\n\n"
        "Si en realidad iban juntas, unilas a mano con <code>/link_league</code>.",
        parse_mode=ParseMode.HTML,
    )


async def relink_leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /relink_leagues: re-unify split leagues by canonical (normalized) name."""
    del context
    if update.message is None:
        return
    summary = get_storage().relink_unified_by_normalized_name()
    await update.message.reply_text(
        "🔗 <b>Re-unificación por nombre normalizado</b>\n"
        f"• Ligas fusionadas: <b>{summary['groups_merged']}</b>\n"
        f"• Competiciones reasignadas: <b>{summary['competitions_moved']}</b>\n\n"
        "Mirá <code>/leagues</code>.",
        parse_mode=ParseMode.HTML,
    )


def _parse_on_off(value: str) -> bool | None:
    v = (value or "").strip().lower()
    if v in ("on", "si", "sí", "true", "1", "activar"):
        return True
    if v in ("off", "no", "false", "0", "desactivar"):
        return False
    return None


async def reminders_league_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reminders_league <N> on|off: toggle pre-kickoff reminders for a league."""
    if update.message is None or update.effective_chat is None:
        return
    unified = _subscribed_unified(update.effective_chat.id)
    args = context.args or []
    enabled = _parse_on_off(args[1]) if len(args) >= 2 else None
    if len(args) != 2 or not args[0].isdigit() or enabled is None:
        await update.message.reply_text(
            "Uso: <code>/reminders_league [N] on|off</code> (N de <code>/leagues</code>).\n"
            "Activa/desactiva el recordatorio 5 min antes para TODOS los partidos de esa liga. Por defecto está OFF.",
            parse_mode=ParseMode.HTML,
        )
        return
    n = int(args[0])
    if not (1 <= n <= len(unified)):
        await update.message.reply_text("Número fuera de rango. Mirá <code>/leagues</code>.", parse_mode=ParseMode.HTML)
        return
    comps = get_storage().list_tracked_competitions_for_unified(unified[n - 1]["id"])
    for comp in comps:
        get_storage().set_competition_reminders(comp.id, enabled)
    estado = "ACTIVADOS ✅" if enabled else "desactivados ⚪️"
    await update.message.reply_text(
        f"⏰ Recordatorios {estado} para <b>{escape_html(unified[n - 1]['name'])}</b> ({len(comps)} plataforma/s).",
        parse_mode=ParseMode.HTML,
    )


async def reminders_match_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reminders_match <n> on|off: toggle reminder for a match from the last /matches list."""
    if update.message is None:
        return
    active_matches = context.user_data.get(MATCHES_ACTIVE_CONTEXT_KEY)
    args = context.args or []
    enabled = _parse_on_off(args[1]) if len(args) >= 2 else None
    if len(args) != 2 or not args[0].isdigit() or enabled is None:
        await update.message.reply_text(
            "Uso: <code>/reminders_match [n] on|off</code> — el <code>n</code> es el del partido de la última lista de <code>/matches</code>.",
            parse_mode=ParseMode.HTML,
        )
        return
    if not isinstance(active_matches, list) or not active_matches:
        await update.message.reply_text(
            "No tengo una lista reciente de partidos. Corré <code>/matches</code>, elegí una liga y después <code>/reminders_match n on</code>.",
            parse_mode=ParseMode.HTML,
        )
        return
    selected_index = _parse_selection_number(args[0], len(active_matches) + 1)
    if selected_index is None or selected_index == 0 or selected_index > len(active_matches):
        await update.message.reply_text(
            "Elegí el número de un partido individual de la última lista de <code>/matches</code>.",
            parse_mode=ParseMode.HTML,
        )
        return
    group = active_matches[selected_index - 1]
    for ev in group:
        get_storage().set_event_reminder(ev.tracked_competition_id, ev.external_event_id, enabled)
    estado = "ACTIVADO ✅" if enabled else "desactivado ⚪️"
    rep = group[0]
    await update.message.reply_text(
        f"⏰ Recordatorio {estado} para <b>{escape_html(rep.home)} vs {escape_html(rep.away)}</b>.",
        parse_mode=ParseMode.HTML,
    )






async def competition_url_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/competition_url <track_number>` for one tracked competition."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /competition_url recibido.")

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text(COMPETITION_URL_USAGE_MESSAGE, parse_mode=ParseMode.HTML)
        return

    track_number = int(context.args[0])
    if track_number <= 0:
        await update.message.reply_text(COMPETITION_URL_USAGE_MESSAGE, parse_mode=ParseMode.HTML)
        return

    tracking_service = get_tracking_service(context)
    tracked_leagues = tracking_service.list_confirmed_tracks(update.effective_chat.id)
    if track_number > len(tracked_leagues):
        await update.message.reply_text("No encontré ese número de liga en /list_tracks.", parse_mode=ParseMode.HTML)
        return

    tracked_subscription = tracked_leagues[track_number - 1]
    extractor = tracking_service.extractor_registry.get_for_platform(
        tracked_subscription.tracked_league.platform
    )

    import json
    def _loads_json(v):
        try:
            return json.loads(v) if v else None
        except Exception:
            return None

    competition_url = extractor.build_competition_url(
        competition_external_id=tracked_subscription.tracked_league.competition_external_id,
        source_url=tracked_subscription.tracked_league.source_url,
        metadata=_loads_json(tracked_subscription.tracked_league.metadata_json),
    )

    if not competition_url:
        await update.message.reply_text("⚠️ Esta plataforma no soporta links directos a competiciones.", parse_mode=ParseMode.HTML)
        return

    from interfaces.telegram.renderers import build_competition_url_message
    message = build_competition_url_message(
        tracked_subscription.tracked_league,
        competition_url,
    )

    await _reply_text_chunks(update.message, message, parse_mode=ParseMode.HTML)


async def update_track_url_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/update_track_url <track_number> <new_url>` for one chat subscription."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /update_track_url recibido.")

    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text(UPDATE_TRACK_URL_USAGE_MESSAGE, parse_mode=ParseMode.HTML)
        return

    track_number = int(context.args[0])
    new_url = " ".join(context.args[1:]).strip()

    if track_number <= 0 or not new_url:
        await update.message.reply_text(UPDATE_TRACK_URL_USAGE_MESSAGE, parse_mode=ParseMode.HTML)
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
    existing_task = context.application.bot_data.get(MANUAL_REFRESH_TASK_KEY)

    if isinstance(existing_task, asyncio.Task):
        if not existing_task.done():
            await update.message.reply_text("⏳ Ya hay un refresh en curso. Esperá a que termine.")
            return
        context.application.bot_data.pop(MANUAL_REFRESH_TASK_KEY, None)

    if not await tracking_service.try_start_refresh("manual"):
        await update.message.reply_text("⏳ Ya hay un refresh en curso. Esperá a que termine.")
        return

    try:
        await update.message.reply_text("🔄 Refrescando tracks, aguardá un momento...")
    except Exception:
        await tracking_service.finish_refresh("manual")
        raise

    async def run_manual_refresh() -> None:
        try:
            summary = await tracking_service.refresh_chat_tracks(update.effective_chat.id)

            from interfaces.telegram.notifications import dispatch_tracking_notifications
            from adapters.storage import get_storage
            from interfaces.telegram.renderers import build_refresh_summary_message

            repository = get_storage()
            await dispatch_tracking_notifications(
                context.bot,
                summary,
                repository,
                notify_failures=True,
                force_unavailable_warnings=True,
                unavailable_warning_chat_id=update.effective_chat.id,
            )
            summary_result = build_refresh_summary_message(summary)
            await _send_text_chunks(
                context.bot,
                update.effective_chat.id,
                summary_result.message,
            )
        except Exception:
            logger.exception("Tracking refresh failed for chat_id=%s.", update.effective_chat.id)
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ Ocurrió un error refrescando los tracks. Revisá logs.",
                )
            except Exception:
                logger.exception(
                    "Also failed to send manual refresh error message for chat_id=%s.",
                    update.effective_chat.id,
                )
        finally:
            await tracking_service.finish_refresh("manual")

    task = asyncio.create_task(
        run_manual_refresh(),
        name=f"manual-refresh-tracks-{update.effective_chat.id}",
    )
    context.application.bot_data[MANUAL_REFRESH_TASK_KEY] = task

    def _clear_manual_refresh_task(finished_task: asyncio.Task) -> None:
        current_task = context.application.bot_data.get(MANUAL_REFRESH_TASK_KEY)
        if current_task is finished_task:
            context.application.bot_data.pop(MANUAL_REFRESH_TASK_KEY, None)

    task.add_done_callback(_clear_manual_refresh_task)


async def event_url_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/event_url <event_number>` using the latest `/matches` context."""

    if update.message is None:
        return

    logger.info("Comando /event_url recibido.")

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text(EVENT_URL_USAGE_MESSAGE, parse_mode=ParseMode.HTML)
        return

    active_matches = context.user_data.get(MATCHES_ACTIVE_CONTEXT_KEY)
    selected_league = context.user_data.get(MATCHES_SELECTED_TRACK_CONTEXT_KEY)

    if not isinstance(active_matches, list) or not active_matches:
        await update.message.reply_text(
            "No tengo una lista reciente de partidos para este chat.\n\n"
            "Usá /matches, elegí una liga y después /event_url <n>."
        )
        return

    if not isinstance(selected_league, dict) or "id" not in selected_league:
        await update.message.reply_text(
            "No tengo una liga seleccionada recientemente.\n\n"
            "Usá /matches, elegí una liga y después /event_url <n>."
        )
        return

    # `/matches` numbers the list as "1 - Ver todos" then one entry per grouped
    # match, so the displayed number N maps to the group at active_matches[N-2].
    selected_index = _parse_selection_number(context.args[0], len(active_matches) + 1)
    if selected_index is None:
        await update.message.reply_text(EVENT_URL_USAGE_MESSAGE, parse_mode=ParseMode.HTML)
        return

    if selected_index == 0:
        await update.message.reply_text(
            "El número 1 corresponde a \"Ver todos\".\n\n"
            "Elegí el número visible de un partido individual de la última lista de /matches."
        )
        return

    group = active_matches[selected_index - 1]
    from interfaces.telegram.renderers import build_grouped_event_url_message

    message = build_grouped_event_url_message(group)
    if not message:
        await update.message.reply_text("No encontré URLs para ese partido.")
        return

    await _reply_text_chunks(update.message, message, parse_mode=ParseMode.HTML)




def _build_grouped_match_selection_message(
    unified_league_name: str,
    grouped_matches: list[list[ActiveEventRecord]],
) -> str:
    """Build the second prompt used by `/matches` for unified leagues."""

    return f"¿Qué partido querés ver de {unified_league_name}?"




async def matches_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the interactive `/matches` flow."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END

    logger.info("Comando /matches recibido.")

    full_odds = False
    selected_track_num = None
    for arg in context.args:
        normalized_arg = arg.strip().lower()
        if normalized_arg in ("-full_odds", "--full_odds", "-full", "-f"):
            full_odds = True
        elif normalized_arg.isdigit():
            selected_track_num = int(normalized_arg)

    context.user_data["matches_full_odds"] = full_odds

    tracking_service = get_tracking_service(context)
    unified_leagues = tracking_service.repository.list_subscribed_unified_competitions(update.effective_chat.id)

    if not unified_leagues:
        await update.message.reply_text(
            "No tenés ligas trackeadas todavía.\n"
            "Usá /track_url <url_de_plataforma> y después /confirm_track o pegá un bloque 'Ligas:'."
        )
        return ConversationHandler.END

    context.user_data[MATCHES_TRACKS_CONTEXT_KEY] = unified_leagues

    if selected_track_num is not None:
        if 1 <= selected_track_num <= len(unified_leagues):
            selected_index = selected_track_num - 1
            selected_league = unified_leagues[selected_index]
            
            active_events = tracking_service.repository.get_active_events_for_unified_competition(
                selected_league["id"],
                only_future=False,
            )

            if not active_events:
                # Refresh all linked tracked leagues
                tracked_links = tracking_service.repository.list_tracked_competitions_for_unified(selected_league["id"])
                for link in tracked_links:
                    try:
                        await tracking_service.refresh_tracked_league(link.id)
                    except Exception:
                        pass
                active_events = tracking_service.repository.get_active_events_for_unified_competition(
                    selected_league["id"],
                    only_future=False,
                )

            if active_events:
                from interfaces.telegram.renderers import group_events_by_physical_match
                grouped_matches = group_events_by_physical_match(active_events)
                context.user_data[MATCHES_ACTIVE_CONTEXT_KEY] = grouped_matches
                context.user_data[MATCHES_SELECTED_TRACK_CONTEXT_KEY] = selected_league

                await update.message.reply_text(
                    _build_grouped_match_selection_message(selected_league["name"], grouped_matches),
                    reply_markup=_match_choice_keyboard(grouped_matches),
                )
                return SELECT_MATCH_FOR_MATCHES

    await update.message.reply_text(
        _build_unified_league_selection_message("Qué liga quiere ver?", unified_leagues),
        reply_markup=_build_choice_keyboard([lg["name"] for lg in unified_leagues], "mx_league"),
    )
    return SELECT_LEAGUE_FOR_MATCHES


async def matches_select_league(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the league number selected during the `/matches` flow."""

    target = _selection_target(update)
    if target is None or update.effective_chat is None:
        return ConversationHandler.END

    unified_leagues = context.user_data.get(MATCHES_TRACKS_CONTEXT_KEY)
    if not isinstance(unified_leagues, list) or not unified_leagues:
        await target.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /matches.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = await _selected_index(update, prefix="mx_league", count=len(unified_leagues))

    if selected_index is None:
        await target.reply_text(
            "Elegí una liga de la lista.",
            reply_markup=_build_choice_keyboard([lg["name"] for lg in unified_leagues], "mx_league"),
        )
        return SELECT_LEAGUE_FOR_MATCHES

    selected_league = unified_leagues[selected_index]
    tracking_service = get_tracking_service(context)

    active_events = tracking_service.repository.get_active_events_for_unified_competition(
        selected_league["id"],
        only_future=False,
    )

    if not active_events:
        # Try refreshing all linked tracked leagues
        tracked_links = tracking_service.repository.list_tracked_competitions_for_unified(selected_league["id"])
        for link in tracked_links:
            try:
                await tracking_service.refresh_tracked_league(link.id)
            except Exception:
                pass
        active_events = tracking_service.repository.get_active_events_for_unified_competition(
            selected_league["id"],
            only_future=False,
        )

    if not active_events:
        await target.reply_text(
            "No encontré partidos activos o futuros para esa liga.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    from interfaces.telegram.renderers import group_events_by_physical_match
    grouped_matches = group_events_by_physical_match(active_events)
    context.user_data[MATCHES_ACTIVE_CONTEXT_KEY] = grouped_matches
    context.user_data[MATCHES_SELECTED_TRACK_CONTEXT_KEY] = selected_league

    await target.reply_text(
        _build_grouped_match_selection_message(selected_league["name"], grouped_matches),
        reply_markup=_match_choice_keyboard(grouped_matches),
    )

    return SELECT_MATCH_FOR_MATCHES


async def matches_select_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the match number selected during the `/matches` flow."""

    target = _selection_target(update)
    if target is None:
        return ConversationHandler.END

    active_matches = context.user_data.get(MATCHES_ACTIVE_CONTEXT_KEY)
    tracked_league = context.user_data.get(MATCHES_SELECTED_TRACK_CONTEXT_KEY)

    if not isinstance(active_matches, list) or not active_matches:
        await target.reply_text(
            "No encontré la selección de partidos. Probá de nuevo con /matches.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    if not isinstance(tracked_league, dict) or "id" not in tracked_league:
        await target.reply_text(
            "No encontré la liga seleccionada. Probá de nuevo con /matches.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    full_odds = context.user_data.get("matches_full_odds", False)
    if getattr(update, "callback_query", None) is not None:
        selected_index = await _selected_index(
            update, prefix="mx_match", count=len(active_matches) + 1
        )
    else:
        # Text fallback still honours an inline `-full_odds` flag.
        input_text = str(update.message.text).strip()
        for flag in ("-full_odds", "--full_odds", "-full", "-f"):
            if flag in input_text.lower():
                full_odds = True
                input_text = input_text.lower().replace(flag, "").strip()
                break
        selected_index = _parse_selection_number(input_text, len(active_matches) + 1)

    if selected_index is None:
        await target.reply_text(
            "Elegí un partido de la lista.",
            reply_markup=_match_choice_keyboard(active_matches),
        )
        return SELECT_MATCH_FOR_MATCHES

    if selected_index == 0:
        from interfaces.telegram.renderers import build_comparison_match_card_message
        parts = []
        for match_group in active_matches:
            card = build_comparison_match_card_message(match_group, full_odds=full_odds)
            if card:
                parts.append(card)
        all_msg = "\n\n━━━━━━━━━━━━━━━━━━━━\n\n".join(parts)
        await _reply_text_chunks(
            target,
            all_msg,
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.HTML,
        )
    else:
        selected_match_group = active_matches[selected_index - 1]
        from interfaces.telegram.renderers import build_comparison_match_card_message
        await _reply_text_chunks(
            target,
            build_comparison_match_card_message(selected_match_group, full_odds=full_odds),
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
    unified_leagues = tracking_service.repository.list_subscribed_unified_competitions(
        update.effective_chat.id
    )

    if not unified_leagues:
        await update.message.reply_text(
            "No tenés ligas trackeadas para eliminar.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    context.user_data[UNTRACK_TRACKS_CONTEXT_KEY] = unified_leagues
    await update.message.reply_text(
        "¿Qué liga querés dejar de trackear? (se quita de todas sus plataformas)",
        reply_markup=_build_choice_keyboard([lg["name"] for lg in unified_leagues], "un_league"),
    )
    return SELECT_LEAGUE_FOR_UNTRACK


async def untrack_select_league(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the league selection during `/untrack`."""

    target = _selection_target(update)
    if target is None or update.effective_chat is None:
        return ConversationHandler.END

    unified_leagues = context.user_data.get(UNTRACK_TRACKS_CONTEXT_KEY)
    if not isinstance(unified_leagues, list) or not unified_leagues:
        await target.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /untrack.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = await _selected_index(update, prefix="un_league", count=len(unified_leagues))

    if selected_index is None:
        await target.reply_text(
            "Elegí una liga de la lista.",
            reply_markup=_build_choice_keyboard([lg["name"] for lg in unified_leagues], "un_league"),
        )
        return SELECT_LEAGUE_FOR_UNTRACK

    selected_league = unified_leagues[selected_index]
    tracking_service = get_tracking_service(context)
    result = tracking_service.untrack_unified(
        update.effective_chat.id,
        selected_league["id"],
    )

    await target.reply_text(
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

    target = _selection_target(update)
    if target is None or update.effective_chat is None:
        return ConversationHandler.END

    unified_leagues = context.user_data.get(ODDS_TRACKS_CONTEXT_KEY)
    enabled = context.user_data.get(ODDS_ENABLED_CONTEXT_KEY)

    if not isinstance(unified_leagues, list) or not unified_leagues or not isinstance(enabled, bool):
        await target.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /odds_on o /odds_off.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = await _selected_index(update, prefix="odds_league", count=len(unified_leagues))

    if selected_index is None:
        await target.reply_text(
            "Elegí una liga de la lista.",
            reply_markup=_build_choice_keyboard([lg["name"] for lg in unified_leagues], "odds_league"),
        )
        return SELECT_LEAGUE_FOR_ODDS

    selected_league = unified_leagues[selected_index]
    tracking_service = get_tracking_service(context)
    result = tracking_service.set_odds_change_notifications_unified(
        update.effective_chat.id,
        selected_league["id"],
        enabled=enabled,
    )

    await target.reply_text(
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
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    try:
        percent = float(context.args[0].replace(",", "."))
    except ValueError:
        await update.message.reply_text(
            "⚠️ El porcentaje debe ser un número válido.\n\n"
            f"{SET_CHANGE_PERCENT_USAGE_MESSAGE}",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    if percent <= 0:
        await update.message.reply_text(
            "El porcentaje debe ser mayor a 0.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    tracking_service = get_tracking_service(context)
    unified_leagues = tracking_service.repository.list_subscribed_unified_competitions(
        update.effective_chat.id
    )

    if not unified_leagues:
        await update.message.reply_text(
            "No tenés ligas trackeadas para configurar.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    context.user_data[CHANGE_PERCENT_TRACKS_CONTEXT_KEY] = unified_leagues
    context.user_data[CHANGE_PERCENT_VALUE_CONTEXT_KEY] = percent

    await update.message.reply_text(
        f"¿Qué liga querés configurar con umbral {percent:.1f}%?",
        reply_markup=_build_choice_keyboard([lg["name"] for lg in unified_leagues], "chg_league"),
    )
    return SELECT_LEAGUE_FOR_CHANGE_PERCENT


async def set_change_percent_select_league(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Handle the league selection during `/set_change_percent`."""

    target = _selection_target(update)
    if target is None or update.effective_chat is None:
        return ConversationHandler.END

    unified_leagues = context.user_data.get(CHANGE_PERCENT_TRACKS_CONTEXT_KEY)
    percent = context.user_data.get(CHANGE_PERCENT_VALUE_CONTEXT_KEY)

    if not isinstance(unified_leagues, list) or not unified_leagues or not isinstance(percent, float):
        await target.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /set_change_percent.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = await _selected_index(update, prefix="chg_league", count=len(unified_leagues))

    if selected_index is None:
        await target.reply_text(
            "Elegí una liga de la lista.",
            reply_markup=_build_choice_keyboard([lg["name"] for lg in unified_leagues], "chg_league"),
        )
        return SELECT_LEAGUE_FOR_CHANGE_PERCENT

    selected_league = unified_leagues[selected_index]
    tracking_service = get_tracking_service(context)
    result = tracking_service.set_change_percent_unified(
        update.effective_chat.id,
        selected_league["id"],
        percent,
    )

    await target.reply_text(
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

    # Runs before every command (group -1): pins the chat's display timezone so
    # all responses render kickoff times/alerts in the user's configured zone.
    application.add_handler(TypeHandler(Update, apply_chat_timezone_context), group=-1)

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(
        CommandHandler(["timezone", "tz", "zona_horaria"], timezone_command)
    )
    application.add_handler(CommandHandler("help_matches", help_matches_command))
    application.add_handler(CommandHandler("help_live", help_live_command))
    application.add_handler(CommandHandler("help_stats", help_stats_command))
    application.add_handler(CommandHandler("help_leagues", help_leagues_command))
    application.add_handler(CommandHandler("guide", guide_command))
    application.add_handler(CommandHandler("sportradar_token", sportradar_token_command))
    # Also handle .json file uploads with /sportradar_token as the caption.
    application.add_handler(
        MessageHandler(
            filters.Document.FileExtension("json") & filters.CaptionRegex(re.compile(r"^/sportradar_token", re.IGNORECASE)),
            sportradar_token_command,
        )
    )
    application.add_handler(CommandHandler("platforms", platforms_command))
    
    # Generic Stats Commands
    application.add_handler(CommandHandler("stats_help", stats_help_command))
    application.add_handler(CommandHandler("stats_leagues", stats_leagues_command))
    application.add_handler(CommandHandler("standings", standings_command))
    application.add_handler(CommandHandler("fixtures", fixtures_command))
    application.add_handler(CommandHandler("today", today_command))
    application.add_handler(CommandHandler("match", match_command))
    
    # Generic Peaks Command
    application.add_handler(CommandHandler("peaks", peaks_command))
    
    # Callback query handlers for generic stats and peaks
    application.add_handler(CallbackQueryHandler(stats_callback_query_handler, pattern="^(stats_co|stats_le|stats_ma):"))
    application.add_handler(CallbackQueryHandler(peaks_callback_query_handler, pattern="^peaks_filter:"))
    
    # Finnish Football Leagues and stats commands
    application.add_handler(CommandHandler("fin_help", fin_help_command))
    application.add_handler(CommandHandler("fin_leagues", fin_leagues_command))
    application.add_handler(CommandHandler("fin_standings", fin_standings_command))
    application.add_handler(CommandHandler("fin_fixtures", fin_fixtures_command))
    application.add_handler(CommandHandler("fin_today", fin_today_command))
    application.add_handler(CommandHandler("fin_match", fin_match_command))

    # Swedish Football (Svenskfotboll / FOGIS) leagues and stats commands
    application.add_handler(CommandHandler("swe_help", swe_help_command))
    application.add_handler(CommandHandler("swe_leagues", swe_leagues_command))
    application.add_handler(CommandHandler("swe_standings", swe_standings_command))
    application.add_handler(CommandHandler("swe_fixtures", swe_fixtures_command))
    application.add_handler(CommandHandler("swe_results", swe_results_command))
    application.add_handler(CommandHandler("swe_today", swe_today_command))
    application.add_handler(CommandHandler("swe_match", swe_match_command))

    # Romanian Football Leagues and stats commands
    application.add_handler(CommandHandler("ro_help", ro_help_command))
    application.add_handler(CommandHandler("ro_leagues", ro_leagues_command))
    application.add_handler(CommandHandler("ro_standings", ro_standings_command))
    application.add_handler(CommandHandler("ro_fixtures", ro_fixtures_command))
    application.add_handler(CommandHandler("ro_today", ro_today_command))
    application.add_handler(CommandHandler("ro_match", ro_match_command))

    # Slovak Football Leagues and stats commands
    application.add_handler(CommandHandler("sk_help", sk_help_command))
    application.add_handler(CommandHandler("sk_leagues", sk_leagues_command))
    application.add_handler(CommandHandler("sk_standings", sk_standings_command))
    application.add_handler(CommandHandler("sk_fixtures", sk_fixtures_command))
    application.add_handler(CommandHandler("sk_today", sk_today_command))
    application.add_handler(CommandHandler("sk_match", sk_match_command))

    # Algerian Football Leagues and stats commands
    application.add_handler(CommandHandler("al_help", al_help_command))
    application.add_handler(CommandHandler("al_leagues", al_leagues_command))
    application.add_handler(CommandHandler("al_standings", al_standings_command))
    application.add_handler(CommandHandler("al_fixtures", al_fixtures_command))
    application.add_handler(CommandHandler("al_today", al_today_command))
    application.add_handler(CommandHandler("al_match", al_match_command))

    # Norwegian Football Leagues and stats commands
    application.add_handler(CommandHandler("no_help", no_help_command))
    application.add_handler(CommandHandler("no_leagues", no_leagues_command))
    application.add_handler(CommandHandler("no_standings", no_standings_command))
    application.add_handler(CommandHandler("no_fixtures", no_fixtures_command))
    application.add_handler(CommandHandler("no_today", no_today_command))
    application.add_handler(CommandHandler("no_match", no_match_command))

    # Special-league daily peak scoring (Finland + Sweden)
    application.add_handler(CommandHandler("peak_today", peak_today_command))
    application.add_handler(CommandHandler("peak_on", peak_on_command))
    application.add_handler(CommandHandler("peak_off", peak_off_command))

    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("resources", resources_command))
    application.add_handler(CommandHandler("echo", echo_command))
    application.add_handler(CommandHandler("track_url", track_url_command))
    application.add_handler(
        MessageHandler(filters.Regex(re.compile(r'^ligas:', re.IGNORECASE)), bulk_track_message_handler)
    )
    application.add_handler(CommandHandler("confirm_track", confirm_track_command))
    application.add_handler(CommandHandler("confirm_empty_track", confirm_empty_track_command))
    application.add_handler(CommandHandler("list_tracks", list_tracks_command))
    application.add_handler(CommandHandler("leagues", leagues_command))
    application.add_handler(CommandHandler("league", league_command))
    application.add_handler(CommandHandler("link_league", link_league_command))
    application.add_handler(CommandHandler("unlink_league", unlink_league_command))
    application.add_handler(
        CallbackQueryHandler(undo_league_merge_callback, pattern="^undomrg:")
    )
    application.add_handler(CommandHandler("relink_leagues", relink_leagues_command))
    application.add_handler(CommandHandler("reminders_league", reminders_league_command))
    application.add_handler(CommandHandler("reminders_match", reminders_match_command))
    application.add_handler(CommandHandler("stats_links", stats_links_command))
    application.add_handler(CommandHandler("stats_tracks", stats_tracks_command))
    application.add_handler(CommandHandler("competition_url", competition_url_command))
    application.add_handler(CommandHandler("refresh_tracks", refresh_tracks_command))
    application.add_handler(CommandHandler("update_track_url", update_track_url_command))
    application.add_handler(CommandHandler("event_url", event_url_command))
    application.add_handler(CommandHandler("check_little_changes", check_little_changes_command))
    application.add_handler(CommandHandler("confirm_change", confirm_change_command))
    application.add_handler(
        CommandHandler("confirm_all_little_changes", confirm_all_little_changes_command)
    )
    application.add_handler(CommandHandler("watch_live", watch_live_command))
    application.add_handler(CommandHandler("import_sheet", import_sheet_command))
    application.add_handler(CommandHandler("watching", watching_command))
    application.add_handler(CommandHandler("live_status", live_status_command))
    application.add_handler(CommandHandler("live_settings", live_settings_command))
    application.add_handler(CommandHandler("unwatch", unwatch_command))
    application.add_handler(CommandHandler("view_match", view_match_command))
    application.add_handler(CommandHandler("view_live_match", view_match_command))
    application.add_handler(CommandHandler("live_match", view_match_command))

    track_league_conversation = ConversationHandler(
        entry_points=[CommandHandler(["track_league", "tracl_league"], track_league_command)],
        states={
            SELECT_PLATFORM_FOR_TRACK_LEAGUE: [
                CallbackQueryHandler(track_league_select_platform, pattern="^tl_platform:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, track_league_select_platform)
            ],
            ENTER_COUNTRY_FOR_TRACK_LEAGUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, track_league_enter_country)
            ],
            SELECT_LEAGUE_FOR_TRACK_LEAGUE: [
                CallbackQueryHandler(track_league_select_league, pattern="^tl_league:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, track_league_select_league)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CallbackQueryHandler(cancel_callback, pattern="^cxl$"),
        ],
        name="track_league_conversation",
        persistent=False,
    )
    application.add_handler(track_league_conversation)

    link_stats_conversation = ConversationHandler(
        entry_points=[CommandHandler("link_stats", link_stats_command)],
        states={
            SELECT_TRACK_FOR_LINK_STATS: [
                CallbackQueryHandler(link_stats_select_track, pattern="^ls_track:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, link_stats_select_track)
            ],
            SELECT_PROVIDER_FOR_LINK_STATS: [
                CallbackQueryHandler(link_stats_select_provider, pattern="^ls_provider:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, link_stats_select_provider)
            ],
            ENTER_COUNTRY_FOR_LINK_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, link_stats_enter_country)
            ],
            SELECT_LEAGUE_FOR_LINK_STATS: [
                CallbackQueryHandler(link_stats_select_league, pattern="^ls_league:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, link_stats_select_league)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CallbackQueryHandler(cancel_callback, pattern="^cxl$"),
        ],
        name="link_stats_conversation",
        persistent=False,
    )
    application.add_handler(link_stats_conversation)

    track_stats_conversation = ConversationHandler(
        entry_points=[CommandHandler("track_stats", track_stats_command)],
        states={
            SELECT_PROVIDER_FOR_TRACK_STATS: [
                CallbackQueryHandler(track_stats_select_provider, pattern="^ts_provider:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, track_stats_select_provider),
            ],
            ENTER_COUNTRY_FOR_TRACK_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, track_stats_enter_country)
            ],
            SELECT_LEAGUE_FOR_TRACK_STATS: [
                CallbackQueryHandler(track_stats_select_league, pattern="^ts_league:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, track_stats_select_league),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CallbackQueryHandler(cancel_callback, pattern="^cxl$"),
        ],
        name="track_stats_conversation",
        persistent=False,
    )
    application.add_handler(track_stats_conversation)

    matches_conversation = ConversationHandler(
        entry_points=[CommandHandler("matches", matches_command)],
        states={
            SELECT_LEAGUE_FOR_MATCHES: [
                CallbackQueryHandler(matches_select_league, pattern="^mx_league:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, matches_select_league),
            ],
            SELECT_MATCH_FOR_MATCHES: [
                CallbackQueryHandler(matches_select_match, pattern="^mx_match:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, matches_select_match),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CallbackQueryHandler(cancel_callback, pattern="^cxl$"),
        ],
        name="matches_conversation",
        persistent=False,
    )
    application.add_handler(matches_conversation)

    stats_conversation = ConversationHandler(
        entry_points=[CommandHandler("stats", stats_command)],
        states={
            SELECT_LEAGUE_FOR_STATS: [
                CallbackQueryHandler(stats_select_league, pattern="^stx_league:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, stats_select_league),
            ],
            SELECT_MATCH_FOR_STATS: [
                CallbackQueryHandler(stats_select_match, pattern="^stx_match:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, stats_select_match),
            ],
            SELECT_STATS_CANDIDATE: [
                CallbackQueryHandler(stats_select_candidate, pattern="^stx_cand:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, stats_select_candidate),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CallbackQueryHandler(cancel_callback, pattern="^cxl$"),
        ],
        name="stats_conversation",
        persistent=False,
    )
    application.add_handler(stats_conversation)

    explore_stats_conversation = ConversationHandler(
        entry_points=[CommandHandler("explore_stats", explore_stats_command)],
        states={
            EXPLORE_SELECT_LEAGUE: [
                CallbackQueryHandler(explore_select_league, pattern="^exp_league:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, explore_select_league),
            ],
            EXPLORE_MENU: [
                CallbackQueryHandler(explore_menu, pattern="^exp_menu:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, explore_menu),
            ],
            EXPLORE_TEAM_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, explore_team_input)
            ],
            EXPLORE_SELECT_FIXTURE: [
                CallbackQueryHandler(explore_select_fixture, pattern="^exp_fix:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, explore_select_fixture),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CallbackQueryHandler(cancel_callback, pattern="^cxl$"),
        ],
        name="explore_stats_conversation",
        persistent=False,
    )
    application.add_handler(explore_stats_conversation)

    untrack_conversation = ConversationHandler(
        entry_points=[CommandHandler("untrack", untrack_command)],
        states={
            SELECT_LEAGUE_FOR_UNTRACK: [
                CallbackQueryHandler(untrack_select_league, pattern="^un_league:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, untrack_select_league),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CallbackQueryHandler(cancel_callback, pattern="^cxl$"),
        ],
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
                CallbackQueryHandler(odds_select_league, pattern="^odds_league:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, odds_select_league),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CallbackQueryHandler(cancel_callback, pattern="^cxl$"),
        ],
        name="odds_conversation",
        persistent=False,
    )
    application.add_handler(odds_conversation)

    change_percent_conversation = ConversationHandler(
        entry_points=[CommandHandler("set_change_percent", set_change_percent_command)],
        states={
            SELECT_LEAGUE_FOR_CHANGE_PERCENT: [
                CallbackQueryHandler(set_change_percent_select_league, pattern="^chg_league:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_change_percent_select_league),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CallbackQueryHandler(cancel_callback, pattern="^cxl$"),
        ],
        name="change_percent_conversation",
        persistent=False,
    )
    application.add_handler(change_percent_conversation)

    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, photo_guidance_handler))
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
    unified_leagues = tracking_service.repository.list_subscribed_unified_competitions(
        update.effective_chat.id
    )

    if not unified_leagues:
        await update.message.reply_text(
            "No tenés ligas trackeadas para configurar.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    context.user_data[ODDS_TRACKS_CONTEXT_KEY] = unified_leagues
    context.user_data[ODDS_ENABLED_CONTEXT_KEY] = enabled

    prompt = (
        "¿Qué liga querés activar para cambios de odds?"
        if enabled
        else "¿Qué liga querés desactivar para cambios de odds?"
    )
    await update.message.reply_text(
        prompt,
        reply_markup=_build_choice_keyboard([lg["name"] for lg in unified_leagues], "odds_league"),
    )
    return SELECT_LEAGUE_FOR_ODDS




def _build_discovery_platform_selection_message(platforms: list[PlatformDescriptor]) -> str:
    """Build the platform prompt for `/track_league`."""

    return "¿Qué plataforma querés usar para buscar ligas?"






def _build_discovered_league_selection_message(options: list[LeagueDiscoveryOption]) -> str:
    """Build the league prompt for `/track_league`."""

    return "Elegí la liga a trackear:"






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














def _match_choice_keyboard(grouped_matches):
    """Inline keyboard for /matches: a 'Ver todos' button + one per match.

    Index 0 is "Ver todos"; index ``i`` (>=1) is ``grouped_matches[i-1]`` — the
    same mapping the legacy numeric keyboard used (number 1 = all).
    """

    labels = ["📋 Ver todos"] + [f"{g[0].home} vs {g[0].away}" for g in grouped_matches]
    return _build_choice_keyboard(labels, "mx_match")








_FIN_COMPETITION_ID = "spljp26"  # 2026 SPL Jalkapallo season; all FIN leagues share it.

# Full senior hierarchy (mirrors /fin_leagues). Fallback when the live ranking
# list is unavailable; also drives /fin_today classification + names.
_FIN_SENIOR_FALLBACK: dict[str, str] = {
    "VL": "Veikkausliiga (Tier 1)", "NL": "Kansallinen Liiga (Damas T1)",
    "M1L": "Ykkösliiga (Tier 2)", "N1": "Naisten Ykkönen (Damas T2)",
    "M1": "Ykkönen (Tier 3)", "N2": "Naisten Kakkonen (Damas T3)",
    "M2": "Kakkonen (Tier 4)", "N3": "Naisten Kolmonen (Damas T4)",
    "M3": "Kolmonen (Tier 5)", "N4": "Naisten Nelonen (Damas T5)",
    "M4": "Nelonen (Tier 6)", "N5": "Naisten Vitonen (Damas T6)",
    "M5": "Vitonen (Tier 7)", "M6": "Kutonen (Tier 8)", "M7": "Seiska (Tier 9)",
    "MSC": "Suomen Cup (Copa)", "LC": "Liigacup (Copa)",
    "NSC": "Naisten Suomen Cup (Copa Damas)", "M1LCUP": "Ykkösliigacup",
    "MRC": "Miesten Regions Cup", "MRRC": "Miesten Roots Cup",
}



def _resolve_fin_league(code: str) -> tuple[str, str] | None:
    """Resolve a league code to (competition_id, category_id).

    Accepts ANY federation category code shown in /fin_leagues (the season's
    competition_id is shared across leagues); an unknown code just yields no
    data downstream instead of a hard "invalid code" rejection.
    """
    code = (code or "").strip().upper()
    if not code:
        return None
    return (_FIN_COMPETITION_ID, code)


def _fin_senior_catalog(api) -> dict[str, dict]:
    """{category_id: {name, tier, gender}} for senior leagues + cups.

    Uses the live federation ranking list (same source as /fin_leagues) so the
    set stays in sync; falls back to a static hierarchy if unavailable.
    """
    catalog: dict[str, dict] = {}
    try:
        for l in api.get_league_ranking_list() or []:
            cid = str(l.get("category_id") or "")
            if cid:
                catalog[cid] = {"name": l.get("name") or cid, "tier": l.get("tier"), "gender": l.get("gender")}
    except Exception:
        pass
    if not catalog:
        catalog = {c: {"name": n, "tier": None, "gender": None} for c, n in _FIN_SENIOR_FALLBACK.items()}
    return catalog


def _fin_competitions_for_category(api, code: str, season: str = "2026") -> list[str]:
    """All competition_ids that host a category code this season.

    National leagues (VL, M1, M2, NL, N1, N2, cups) → one competition (spljp26).
    Regional leagues (Kolmonen M3, Nelonen M4, women N3+) run as SEVERAL regional
    competitions (Etelä/Länsi/Pohjois/Itä/Åland), so there is no single table.
    """

    code = (code or "").strip().upper()
    if not code:
        return []
    comps: list[str] = []
    try:
        for c in api.get_categories(season) or []:
            if str(c.get("category_id")) == code:
                cid = str(c.get("competition_id") or "")
                if cid and cid not in comps:
                    comps.append(cid)
    except Exception:
        pass
    return comps


# ============ Special-league commands: generic runners (Finland aesthetic) ============
# Both /fin_* and /swe_* go through ONE set of renderers so they look identical.































def _md_escape(text: str) -> str:
    """Escape Markdown-significant chars in free text (team names, etc.)."""
    s = str(text)
    for ch in ("\\", "_", "*", "`", "[", "]"):
        s = s.replace(ch, "\\" + ch)
    return s


def _format_fin_squad(team_label: str, players: list, icon: str) -> list[str]:
    """Render a team's full XI (with shirt, captain, scorers) + bench."""

    def _order(p):
        try:
            return (int(p.get("position_order") or 999), int(p.get("shirt_number") or 999))
        except (TypeError, ValueError):
            return (999, 999)

    starters = sorted([p for p in players if str(p.get("start")) == "1"], key=_order)
    bench = [p for p in players if str(p.get("start")) == "0"]
    out = [f"\n{icon} *{team_label}* — XI ({len(starters)}):"]
    for p in starters:
        num = str(p.get("shirt_number") or "?").rjust(2)
        cap = " Ⓒ" if str(p.get("captain")) in ("1", "true", "True") else ""
        pos = p.get("position_en") or p.get("position") or ""
        posn = f" _{pos}_" if pos else ""
        try:
            g = int(p.get("goals") or 0)
        except (TypeError, ValueError):
            g = 0
        goals = f" {g}⚽" if g > 0 else ""
        out.append(f"  `{num}` {p.get('player_name')}{cap}{posn}{goals}")
    if bench:
        names = ", ".join(f"{p.get('shirt_number')} {p.get('player_name')}" for p in bench[:12])
        out.append(f"  🔁 _Banco:_ {names}")
    return out




# ===================== Svenskfotboll (Swedish FA) commands =====================
# Mirrors the Finland (/fin_*) integration: standalone commands backed by the
# Swedish FA's HTTP feeds (svenskfotboll.se / FOGIS). 2026-season competition ids.




def _swe_resolve_comp_for_teams(client, home: str, away: str) -> str | None:
    """Find which tracked Swedish competition has BOTH teams (for analytics).

    The /swe_match endpoint only gives team names, not a league id, so we scan
    the known leagues' standings and match by normalised team name.
    """

    from services.special_peak import _norm_team

    h, a = _norm_team(home), _norm_team(away)
    if not h or not a:
        return None
    for _code, (cid, _name, _tier) in _SWE_LEAGUES.items():
        try:
            data = client.get_standings(cid)
            teams = {_norm_team(t.get("team")) for t in (data.get("teams") or [])}
        except Exception:
            continue
        if h in teams and a in teams:
            return cid
    return None
























async def _swe_matches_reply(update: Update, name: str, code: str, data: dict, *, header: str) -> None:
    matches = data.get("matches") or []
    if not matches:
        await update.message.reply_text("⚠️ No hay partidos para mostrar.")
        return
    lines = [f"{header}: <b>{name}</b> (2026)", "━━━━━━━━━━━━━━━━━━━━"]
    for mtch in matches[:25]:
        d_arg, t_arg = _convert_swe_to_arg_datetime(mtch.get("start_time_local"))
        score = ""
        if mtch.get("home_score") is not None and mtch.get("away_score") is not None:
            score = f" [{mtch.get('home_score')}-{mtch.get('away_score')}]"
        home_esc = escape_html(mtch.get('home','?'))
        away_esc = escape_html(mtch.get('away','?'))
        lines.append(f"<code>{d_arg} {t_arg}</code> {home_esc} vs {away_esc}{score}")
        lines.append(f"    🆔 <code>/swe_match {mtch.get('match_id','')}</code>")
    await _reply_text_chunks(update.message, "\n".join(lines), parse_mode=ParseMode.HTML)






















































# ===================== Peak digest (special-league daily scoring) =====================
# Detects today's Finland + Sweden federation matches, scores them 1-10
# (value-opportunity + B-Team/substitute detector) and flags peak + timing.






# ===================== Generic Stats & Peaks Consolidation =====================
from datetime import date











# Generic Stats Assistant Helpers & Commands









async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    args = context.args or []
    if args:
        code = args[0].lower().strip()
        adapter = _get_country_adapter(code)
        if adapter:
            await _run_special_today(update.message, args[1:], adapter)
            return
    await update.message.reply_text(
        "Seleccioná un país para ver los partidos de hoy:",
        reply_markup=get_country_selector_keyboard("today")
    )

async def standings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    args = context.args or []
    if len(args) >= 2:
        code = args[0].lower().strip()
        adapter = _get_country_adapter(code)
        if adapter:
            usage = f"❌ *Falta el código de liga.*\n\nUso: `/standings {code} [CÓDIGO]`"
            await _run_special_standings(update.message, args[1:], adapter, usage)
            return
    elif len(args) == 1:
        code = args[0].lower().strip()
        adapter = _get_country_adapter(code)
        if adapter:
            await _show_league_selector(update, code, "standings")
            return
    await update.message.reply_text(
        "Seleccioná un país para ver la tabla de posiciones:",
        reply_markup=get_country_selector_keyboard("standings")
    )

async def fixtures_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    args = context.args or []
    if len(args) >= 2:
        code = args[0].lower().strip()
        adapter = _get_country_adapter(code)
        if adapter:
            usage = f"❌ *Falta el código de liga.*\n\nUso: `/fixtures {code} [CÓDIGO]`"
            await _run_special_fixtures(update.message, args[1:], adapter, usage)
            return
    elif len(args) == 1:
        code = args[0].lower().strip()
        adapter = _get_country_adapter(code)
        if adapter:
            await _show_league_selector(update, code, "fixtures")
            return
    await update.message.reply_text(
        "Seleccioná un país para ver el fixture:",
        reply_markup=get_country_selector_keyboard("fixtures")
    )

async def match_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    args = context.args or []
    if len(args) >= 2:
        code = args[0].lower().strip()
        adapter = _get_country_adapter(code)
        if adapter:
            usage = f"❌ *Falta el ID del partido.*\n\nUso: `/match {code} [ID]`"
            await _run_special_match(update.message, args[1:], adapter, usage)
            return
    elif len(args) == 1:
        code = args[0].lower().strip()
        adapter = _get_country_adapter(code)
        if adapter:
            await _show_today_matches_selector(update, code)
            return
    await update.message.reply_text(
        "Seleccioná un país para ver los partidos y elegir uno:",
        reply_markup=get_country_selector_keyboard("match")
    )


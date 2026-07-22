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

from interfaces.telegram.handlers.tracking import (  # noqa: F401
    COMPETITION_URL_USAGE_MESSAGE,
    ENTER_COUNTRY_FOR_TRACK_LEAGUE,
    EVENT_URL_USAGE_MESSAGE,
    MANUAL_REFRESH_TASK_KEY,
    SELECT_LEAGUE_FOR_CHANGE_PERCENT,
    SELECT_LEAGUE_FOR_MATCHES,
    SELECT_LEAGUE_FOR_ODDS,
    SELECT_LEAGUE_FOR_TRACK_LEAGUE,
    SELECT_LEAGUE_FOR_UNTRACK,
    SELECT_MATCH_FOR_MATCHES,
    SELECT_PLATFORM_FOR_TRACK_LEAGUE,
    SET_CHANGE_PERCENT_USAGE_MESSAGE,
    TRACK_URL_USAGE_MESSAGE,
    UPDATE_TRACK_URL_USAGE_MESSAGE,
    _build_discovered_league_selection_message,
    _build_discovery_platform_selection_message,
    _build_grouped_match_selection_message,
    _match_choice_keyboard,
    _parse_on_off,
    _start_odds_toggle,
    _subscribed_unified,
    bulk_track_message_handler,
    check_little_changes_command,
    competition_url_command,
    confirm_all_little_changes_command,
    confirm_change_command,
    confirm_empty_track_command,
    confirm_track_command,
    event_url_command,
    league_command,
    leagues_command,
    link_league_command,
    list_tracks_command,
    matches_command,
    matches_select_league,
    matches_select_match,
    odds_off_command,
    odds_on_command,
    odds_select_league,
    refresh_tracks_command,
    relink_leagues_command,
    reminders_league_command,
    reminders_match_command,
    set_change_percent_command,
    set_change_percent_select_league,
    track_league_command,
    track_league_enter_country,
    track_league_select_league,
    track_league_select_platform,
    track_url_command,
    undo_league_merge_callback,
    unlink_league_command,
    untrack_command,
    untrack_select_league,
    update_track_url_command,
)

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


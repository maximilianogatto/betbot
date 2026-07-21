"""Handlers del dominio de estadísticas.

Comandos y conversaciones de /stats, el hub de exploración y el enlazado de
ligas con proveedores de stats. Se apoya en `common.py` para el vocabulario
compartido (claves de contexto, accesores a services, teclados); nunca importa
desde `commands.py` — es `commands.py` el que importa de acá.
"""
from __future__ import annotations

from core.models import ActiveEventRecord
from core.models import TrackedCompetitionSubscription
from core.stats_models import MatchIdentityCandidate
from core.stats_models import StatsLeagueOption
from core.stats_models import StatsProviderDescriptor
from interfaces.telegram.handlers.common import EXPLORE_TRACKS_CONTEXT_KEY
from interfaces.telegram.handlers.common import LINK_STATS_OPTIONS_CONTEXT_KEY
from interfaces.telegram.handlers.common import LINK_STATS_PROVIDERS_CONTEXT_KEY
from interfaces.telegram.handlers.common import LINK_STATS_SELECTED_PROVIDER_CONTEXT_KEY
from interfaces.telegram.handlers.common import LINK_STATS_SELECTED_TRACK_CONTEXT_KEY
from interfaces.telegram.handlers.common import LINK_STATS_TRACKS_CONTEXT_KEY
from interfaces.telegram.handlers.common import MATCHES_ACTIVE_CONTEXT_KEY
from interfaces.telegram.handlers.common import MATCHES_SELECTED_TRACK_CONTEXT_KEY
from interfaces.telegram.handlers.common import STATS_ACTIVE_CONTEXT_KEY
from interfaces.telegram.handlers.common import STATS_CANDIDATES_CONTEXT_KEY
from interfaces.telegram.handlers.common import STATS_CANDIDATE_MATCH_CONTEXT_KEY
from interfaces.telegram.handlers.common import STATS_CANDIDATE_PROVIDER_CONTEXT_KEY
from interfaces.telegram.handlers.common import STATS_SELECTED_TRACK_CONTEXT_KEY
from interfaces.telegram.handlers.common import STATS_TRACKS_CONTEXT_KEY
from interfaces.telegram.handlers.common import TRACK_STATS_OPTIONS_CONTEXT_KEY
from interfaces.telegram.handlers.common import TRACK_STATS_PROVIDERS_CONTEXT_KEY
from interfaces.telegram.handlers.common import TRACK_STATS_SELECTED_PROVIDER_CONTEXT_KEY
from interfaces.telegram.handlers.common import _build_choice_keyboard
from interfaces.telegram.handlers.common import _build_track_selection_message
from interfaces.telegram.handlers.common import _build_unified_league_selection_message
from interfaces.telegram.handlers.common import _clear_all_selection_context
from interfaces.telegram.handlers.common import _get_country_adapter
from interfaces.telegram.handlers.common import _parse_selection_number
from interfaces.telegram.handlers.common import _reply_text_chunks
from interfaces.telegram.handlers.common import _selected_index
from interfaces.telegram.handlers.common import _selection_target
from interfaces.telegram.handlers.common import _show_country_help
from interfaces.telegram.handlers.common import _show_league_selector
from interfaces.telegram.handlers.common import _show_today_matches_selector
from interfaces.telegram.handlers.common import get_country_selector_keyboard
from interfaces.telegram.handlers.common import get_stats_service
from interfaces.telegram.handlers.common import get_tracking_service
from interfaces.telegram.handlers.common import reply_with_result
from interfaces.telegram.handlers.special_leagues import _run_special_fixtures
from interfaces.telegram.handlers.special_leagues import _run_special_leagues
from interfaces.telegram.handlers.special_leagues import _run_special_match
from interfaces.telegram.handlers.special_leagues import _run_special_standings
from interfaces.telegram.handlers.special_leagues import _run_special_today
from interfaces.telegram.renderers import format_kickoff_labels
from telegram import ReplyKeyboardRemove
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.ext import ConversationHandler
import re

from services.stats import ExplorableStatsLeague
from services.stats import render_league_fixtures
from services.stats import render_league_table
from services.stats import render_team_row
from services.stats import render_top_scorers

from interfaces.telegram.handlers.common import (
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
    STATS_ACTIVE_CONTEXT_KEY,
    STATS_CANDIDATES_CONTEXT_KEY,
    STATS_CANDIDATE_MATCH_CONTEXT_KEY,
    STATS_CANDIDATE_PROVIDER_CONTEXT_KEY,
    STATS_SELECTED_TRACK_CONTEXT_KEY,
    STATS_TRACKS_CONTEXT_KEY,
    TRACK_STATS_OPTIONS_CONTEXT_KEY,
    TRACK_STATS_PROVIDERS_CONTEXT_KEY,
    TRACK_STATS_SELECTED_PROVIDER_CONTEXT_KEY,
    _build_choice_keyboard,
    _build_track_selection_message,
    _build_unified_league_selection_message,
    _clear_all_selection_context,
    _get_country_adapter,
    _parse_selection_number,
    _reply_text_chunks,
    _selected_index,
    _selection_target,
    _show_country_help,
    _show_league_selector,
    _show_today_matches_selector,
    get_country_selector_keyboard,
    get_stats_service,
    get_tracking_service,
    logger,
    reply_with_result,
)


SELECT_TRACK_FOR_LINK_STATS = 9


SELECT_PROVIDER_FOR_LINK_STATS = 10


ENTER_COUNTRY_FOR_LINK_STATS = 11


SELECT_LEAGUE_FOR_LINK_STATS = 12


SELECT_LEAGUE_FOR_STATS = 13


SELECT_MATCH_FOR_STATS = 14


SELECT_STATS_CANDIDATE = 15


EXPLORE_SELECT_LEAGUE = 16


SELECT_PROVIDER_FOR_TRACK_STATS = 19


ENTER_COUNTRY_FOR_TRACK_STATS = 20


SELECT_LEAGUE_FOR_TRACK_STATS = 21


HELP_STATS_MESSAGE = (
    "📊 <b>Estadísticas (Estándar)</b>\n\n"
    "  /link_stats — vincular una liga de odds con un proveedor de stats\n"
    "  /stats_links — vínculos activos odds ↔ stats\n"
    "  /track_stats — seguir una liga solo por stats (cache diario)\n"
    "  /stats_tracks — ligas seguidas solo por stats\n"
    "  /explore_stats — tabla, partidos previos, fixture y goleadores\n"
    "  /stats — reporte H2H por liga (elegís liga y partido)\n"
    "  <code>/stats &lt;n&gt; [provider]</code> — reporte del partido n de /matches\n"
    "  /platforms — casas de odds y proveedores de stats\n\n"
    "🌍 <b>Ligas especiales</b> <i>(federaciones oficiales)</i>\n"
    "  <i>Ascensos/copas que no figuran en sitios comunes.</i>\n"
    "  <code>/[país]_help</code> — guía del módulo del país\n"
    "  <code>/[país]_leagues</code> — escalafón de ligas y copas\n"
    "  <code>/[país]_today</code> — partidos de hoy con sus IDs\n"
    "  <code>/[país]_standings &lt;CÓDIGO&gt;</code> — tabla de posiciones\n"
    "  <code>/[país]_fixtures &lt;CÓDIGO&gt;</code> — calendario de una liga\n"
    "  <code>/[país]_results &lt;CÓDIGO&gt;</code> — últimos resultados <i>(solo Suecia)</i>\n"
    "  <code>/[país]_match &lt;ID&gt;</code> — reporte + detector B-Team <i>(alineaciones Fin/Swe)</i>\n\n"
    "  <i>Reemplazá [país] por:</i> "
    "🇫🇮 <code>fin</code> · 🇸🇪 <code>swe</code> · 🇷🇴 <code>ro</code> · "
    "🇸🇰 <code>sk</code> · 🇩🇿 <code>al</code> · 🇳🇴 <code>no</code>\n\n"
    "↩︎ /help"
)


STATS_URL_USAGE_MESSAGE = (
    "📊 <b>Reporte de stats de un partido</b>\n"
    "<code>/stats &lt;n&gt; [provider]</code>  <i>(n de</i> /matches<i>)</i>\n"
    "<i>Sin provider combina todos los linkeados; con provider usa solo ese.</i>\n"
    "Ejemplos: <code>/stats 3</code> · <code>/stats 3 sofascore</code>"
)


async def help_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/help_stats` command."""
    del context
    if update.message:
        await update.message.reply_text(HELP_STATS_MESSAGE, parse_mode=ParseMode.HTML)


async def _send_unified_stats_report(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    match_group: list[ActiveEventRecord],
    league_name: str,
    provider_filter: str | None = None,
) -> None:
    """Send the cross-book card (qué casas lo tienen + odds) and the stats report."""

    from interfaces.telegram.renderers import build_comparison_match_card_message

    stats_service = get_stats_service(context)
    await update.message.reply_text("Generando reporte de stats...", reply_markup=ReplyKeyboardRemove())

    card = build_comparison_match_card_message(match_group, full_odds=False)
    if card:
        await _reply_text_chunks(update.message, card, parse_mode=ParseMode.HTML)

    report = await stats_service.build_unified_match_stats_report(
        league_name=league_name,
        match_group=match_group,
        provider_filter=provider_filter,
    )
    await _reply_text_chunks(update.message, report.message, reply_markup=ReplyKeyboardRemove())


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle `/stats` interactive or `/stats <event_number>` from `/matches`."""

    if update.message is None:
        return ConversationHandler.END

    logger.info("Comando /stats recibido.")

    if len(context.args) == 0:
        if update.effective_chat is None:
            return ConversationHandler.END
        tracking_service = get_tracking_service(context)
        unified_leagues = tracking_service.repository.list_subscribed_unified_competitions(
            update.effective_chat.id
        )
        if not unified_leagues:
            await update.message.reply_text(
                "No tenés ligas trackeadas todavía.\n"
                "Usá /track_league o /track_url primero.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return ConversationHandler.END
        context.user_data[STATS_TRACKS_CONTEXT_KEY] = unified_leagues
        await update.message.reply_text(
            _build_unified_league_selection_message("De qué liga querés ver stats?", unified_leagues),
            reply_markup=_build_choice_keyboard([lg["name"] for lg in unified_leagues], "stx_league"),
        )
        return SELECT_LEAGUE_FOR_STATS

    if len(context.args) > 2 or not context.args[0].isdigit():
        await update.message.reply_text(STATS_URL_USAGE_MESSAGE, parse_mode=ParseMode.HTML)
        return ConversationHandler.END
    # /stats <n> [provider] — n indexa la última lista de /matches (unión cross-book,
    # sin repetidos). Sin provider combina todos los linkeados a la liga.
    provider_filter = context.args[1] if len(context.args) == 2 else None

    grouped_matches = context.user_data.get(MATCHES_ACTIVE_CONTEXT_KEY)
    selected_league = context.user_data.get(MATCHES_SELECTED_TRACK_CONTEXT_KEY)

    if not isinstance(grouped_matches, list) or not grouped_matches:
        await update.message.reply_text(
            "No tengo una lista reciente de partidos para este chat.\n\n"
            "Usá /matches, elegí una liga y después /stats <n>."
        )
        return ConversationHandler.END

    if not isinstance(selected_league, dict) or "id" not in selected_league:
        await update.message.reply_text(
            "No tengo una liga seleccionada recientemente.\n\n"
            "Usá /matches, elegí una liga y después /stats <n>."
        )
        return ConversationHandler.END

    # /matches numera con "1 - Ver todos", así que el partido N de la lista es
    # grouped_matches[N-2]. Aceptamos ese mismo número acá.
    if context.args[0] == "1":
        await update.message.reply_text(
            "El número 1 corresponde a \"Ver todos\".\n\n"
            "Elegí el número visible de un partido individual de la última lista de /matches."
        )
        return ConversationHandler.END

    group_index = int(context.args[0]) - 2
    if group_index < 0 or group_index >= len(grouped_matches):
        await update.message.reply_text(STATS_URL_USAGE_MESSAGE, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    await _send_unified_stats_report(
        update,
        context,
        match_group=grouped_matches[group_index],
        league_name=selected_league.get("name") or "la liga",
        provider_filter=provider_filter,
    )
    return ConversationHandler.END


async def stats_select_league(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle league selection during interactive `/stats`."""

    target = _selection_target(update)
    if target is None or update.effective_chat is None:
        return ConversationHandler.END

    unified_leagues = context.user_data.get(STATS_TRACKS_CONTEXT_KEY)
    if not isinstance(unified_leagues, list) or not unified_leagues:
        await target.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = await _selected_index(update, prefix="stx_league", count=len(unified_leagues))
    if selected_index is None:
        await target.reply_text(
            "Elegí una liga de la lista.",
            reply_markup=_build_choice_keyboard([lg["name"] for lg in unified_leagues], "stx_league"),
        )
        return SELECT_LEAGUE_FOR_STATS

    selected_league = unified_leagues[selected_index]
    tracking_service = get_tracking_service(context)

    # Unión de partidos de TODAS las plataformas de la liga (sin repetidos).
    active_events = tracking_service.repository.get_active_events_for_unified_competition(
        selected_league["id"],
        only_future=False,
    )
    if not active_events:
        tracked_links = tracking_service.repository.list_tracked_competitions_for_unified(
            selected_league["id"]
        )
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
    context.user_data[STATS_ACTIVE_CONTEXT_KEY] = grouped_matches
    context.user_data[STATS_SELECTED_TRACK_CONTEXT_KEY] = selected_league
    await target.reply_text(
        _build_unified_stats_match_selection_message(selected_league["name"], grouped_matches),
        reply_markup=_build_choice_keyboard(
            [f"{g[0].home} vs {g[0].away}" for g in grouped_matches], "stx_match"
        ),
    )
    return SELECT_MATCH_FOR_STATS


async def stats_select_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generate a stats report after interactive match selection."""

    target = _selection_target(update)
    if target is None:
        return ConversationHandler.END

    grouped_matches = context.user_data.get(STATS_ACTIVE_CONTEXT_KEY)
    selected_league = context.user_data.get(STATS_SELECTED_TRACK_CONTEXT_KEY)

    if not isinstance(grouped_matches, list) or not grouped_matches:
        await target.reply_text(
            "No encontré la selección de partidos. Probá de nuevo con /stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    if not isinstance(selected_league, dict) or "id" not in selected_league:
        await target.reply_text(
            "No encontré la liga seleccionada. Probá de nuevo con /stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = await _selected_index(update, prefix="stx_match", count=len(grouped_matches))
    if selected_index is None:
        await target.reply_text(
            "Elegí un partido de la lista.",
            reply_markup=_build_choice_keyboard(
                [f"{g[0].home} vs {g[0].away}" for g in grouped_matches], "stx_match"
            ),
        )
        return SELECT_MATCH_FOR_STATS

    match_group = grouped_matches[selected_index]
    league_name = selected_league.get("name") or "la liga"
    stats_service = get_stats_service(context)
    await target.reply_text("Generando reporte de stats...", reply_markup=ReplyKeyboardRemove())

    from interfaces.telegram.renderers import build_comparison_match_card_message

    card = build_comparison_match_card_message(match_group, full_odds=False)
    if card:
        await _reply_text_chunks(target, card, parse_mode=ParseMode.HTML)

    resolution, representative = await stats_service.resolve_unified_event(
        league_name=league_name,
        match_group=match_group,
    )

    if resolution.kind == "choose":
        context.user_data[STATS_CANDIDATES_CONTEXT_KEY] = list(resolution.candidates)
        context.user_data[STATS_CANDIDATE_MATCH_CONTEXT_KEY] = representative
        context.user_data[STATS_CANDIDATE_PROVIDER_CONTEXT_KEY] = resolution.provider_key
        await target.reply_text(
            "No estoy seguro de cuál es el partido de stats. Elegí el correcto:",
            reply_markup=_build_choice_keyboard(
                [c.label for c in resolution.candidates], "stx_cand"
            ),
        )
        return SELECT_STATS_CANDIDATE

    await _reply_text_chunks(
        target,
        (resolution.result.message if resolution.result else "No pude generar el reporte de stats."),
        reply_markup=ReplyKeyboardRemove(),
    )
    _clear_all_selection_context(context)
    return ConversationHandler.END


async def stats_select_candidate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Persist a manually chosen stats candidate and generate its report."""

    target = _selection_target(update)
    if target is None:
        return ConversationHandler.END

    candidates = context.user_data.get(STATS_CANDIDATES_CONTEXT_KEY)
    match = context.user_data.get(STATS_CANDIDATE_MATCH_CONTEXT_KEY)
    provider_key = context.user_data.get(STATS_CANDIDATE_PROVIDER_CONTEXT_KEY)

    if (
        not isinstance(candidates, list)
        or not candidates
        or not isinstance(match, ActiveEventRecord)
        or not isinstance(provider_key, str)
    ):
        await target.reply_text(
            "No encontré la selección de candidatos. Probá de nuevo con /stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = await _selected_index(update, prefix="stx_cand", count=len(candidates))
    if selected_index is None:
        await target.reply_text(
            "Elegí un partido de stats de la lista.",
            reply_markup=_build_choice_keyboard([c.label for c in candidates], "stx_cand"),
        )
        return SELECT_STATS_CANDIDATE

    stats_service = get_stats_service(context)
    await target.reply_text("Generando reporte de stats...", reply_markup=ReplyKeyboardRemove())
    result = await stats_service.build_report_for_chosen_candidate(
        match=match,
        provider_key=provider_key,
        link=candidates[selected_index].link,
    )
    await _reply_text_chunks(target, result.message, reply_markup=ReplyKeyboardRemove())
    _clear_all_selection_context(context)
    return ConversationHandler.END


_EXPLORE_MENU_LABELS = [
    "📊 Tabla de posiciones",
    "🗓️ Próximos partidos",
    "👟 Goleadores",
    "⚽ Buscar un equipo",
    "🔗 Link al proveedor",
    "📋 Elegir partido y reporte",
]


async def explore_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start `/explore_stats`: navigate stats of a stats-linked tracked league."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END

    logger.info("Comando /explore_stats recibido.")
    tracking_service = get_tracking_service(context)
    stats_service = get_stats_service(context)
    tracked_leagues = tracking_service.list_confirmed_tracks(update.effective_chat.id)

    linked = stats_service.list_explorable_leagues(
        chat_id=update.effective_chat.id,
        tracked_subscriptions=tracked_leagues,
    )

    if not linked:
        await update.message.reply_text(
            "No tenés ligas de stats configuradas todavía.\n"
            "Usá /link_stats para vincular odds o /track_stats para seguir una liga solo de stats.",
        )
        return ConversationHandler.END

    context.user_data[EXPLORE_TRACKS_CONTEXT_KEY] = linked
    await update.message.reply_text(
        "¿Qué liga querés explorar?",
        reply_markup=_build_choice_keyboard([lg.label for lg in linked], "exp_league"),
    )
    return EXPLORE_SELECT_LEAGUE


_STATSHUB_TOURNAMENT_RE = re.compile(r"statshub\.sportradar\.com/\S*?/tournament/(\d+)", re.IGNORECASE)


_HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _extract_statshub_tournament_id(text: str) -> str | None:
    """Extract a Statshub tournament id from a pasted URL, or None if not a URL."""

    match = _STATSHUB_TOURNAMENT_RE.search(text or "")
    return match.group(1) if match else None


def _extract_direct_stats_league_reference(text: str) -> str | None:
    """Return the provider-native league reference from a pasted direct URL."""

    statshub_tournament_id = _extract_statshub_tournament_id(text)
    if statshub_tournament_id is not None:
        return statshub_tournament_id
    stripped = (text or "").strip()
    return stripped if _HTTP_URL_RE.search(stripped) else None


async def track_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start `/track_stats`: follow a provider-native stats league independently."""

    if update.message is None:
        return ConversationHandler.END

    providers = get_stats_service(context).list_providers()
    if not providers:
        await update.message.reply_text(
            "No hay providers de stats con discovery habilitado.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END
    context.user_data[TRACK_STATS_PROVIDERS_CONTEXT_KEY] = providers
    await update.message.reply_text(
        _build_stats_provider_selection_message(providers),
        reply_markup=_build_choice_keyboard([p.display_name for p in providers], "ts_provider"),
    )
    return SELECT_PROVIDER_FOR_TRACK_STATS


async def track_stats_select_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Select the provider used by `/track_stats`."""

    target = _selection_target(update)
    if target is None:
        return ConversationHandler.END
    providers = context.user_data.get(TRACK_STATS_PROVIDERS_CONTEXT_KEY)
    if not isinstance(providers, list) or not providers:
        await target.reply_text("No encontré la selección de providers. Probá de nuevo con /track_stats.")
        return ConversationHandler.END
    selected_index = await _selected_index(update, prefix="ts_provider", count=len(providers))
    if selected_index is None:
        await target.reply_text(
            "Elegí un provider de la lista.",
            reply_markup=_build_choice_keyboard([p.display_name for p in providers], "ts_provider"),
        )
        return SELECT_PROVIDER_FOR_TRACK_STATS
    selected_provider = providers[selected_index]
    if not isinstance(selected_provider, StatsProviderDescriptor):
        await target.reply_text("El provider seleccionado no es válido.")
        return ConversationHandler.END
    context.user_data[TRACK_STATS_SELECTED_PROVIDER_CONTEXT_KEY] = selected_provider
    await target.reply_text(
        _build_stats_provider_input_message(selected_provider),
        reply_markup=ReplyKeyboardRemove(),
    )
    return ENTER_COUNTRY_FOR_TRACK_STATS


async def track_stats_enter_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Discover standalone stats leagues after receiving a country or Statshub URL."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END
    selected_provider = context.user_data.get(TRACK_STATS_SELECTED_PROVIDER_CONTEXT_KEY)
    if not isinstance(selected_provider, StatsProviderDescriptor):
        await update.message.reply_text("No encontré el provider seleccionado. Probá de nuevo con /track_stats.")
        return ConversationHandler.END
    country_name = (update.message.text or "").strip()
    if not country_name:
        await update.message.reply_text("Escribí un país válido.")
        return ENTER_COUNTRY_FOR_TRACK_STATS

    stats_service = get_stats_service(context)
    direct_reference = _extract_direct_stats_league_reference(country_name)
    if direct_reference is not None:
        await update.message.reply_text(f"Resolviendo liga de {selected_provider.display_name}...")
        try:
            option = await stats_service.describe_league(
                provider_key=selected_provider.key,
                league_id=direct_reference,
            )
        except Exception:
            logger.exception(
                "Standalone stats league describe-by-url failed provider=%s reference=%s",
                selected_provider.key,
                direct_reference,
            )
            option = None
        if option is None:
            await update.message.reply_text("No pude resolver esa URL de liga.", reply_markup=ReplyKeyboardRemove())
            _clear_all_selection_context(context)
            return ConversationHandler.END
        result = stats_service.track_stats_league(chat_id=update.effective_chat.id, option=option)
        await _reply_text_chunks(update.message, result.message, reply_markup=ReplyKeyboardRemove())
        _clear_all_selection_context(context)
        return ConversationHandler.END

    await update.message.reply_text(f"Buscando ligas de stats en {country_name}...")
    try:
        options = await stats_service.search_leagues(
            provider_key=selected_provider.key,
            country_name=country_name,
            limit=80,
        )
    except Exception:
        logger.exception(
            "Standalone stats league discovery failed provider=%s country=%s",
            selected_provider.key,
            country_name,
        )
        await update.message.reply_text(
            "No pude buscar ligas de stats ahora. Probá de nuevo en unos minutos.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END
    if not options:
        await update.message.reply_text(
            f"No encontré ligas de stats para {country_name} en {selected_provider.display_name}.\n"
            "Probá con otro país o /cancel para salir.",
        )
        return ENTER_COUNTRY_FOR_TRACK_STATS
    context.user_data[TRACK_STATS_OPTIONS_CONTEXT_KEY] = options
    shown = options[:25]
    await _reply_text_chunks(
        update.message,
        _build_stats_league_selection_message(options, prompt="Elegí la liga de stats a seguir:", limit=25),
        reply_markup=_build_choice_keyboard([opt.league_name for opt in shown], "ts_league"),
    )
    return SELECT_LEAGUE_FOR_TRACK_STATS


async def track_stats_select_league(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Persist one standalone provider-native stats league."""

    target = _selection_target(update)
    if target is None or update.effective_chat is None:
        return ConversationHandler.END
    options = context.user_data.get(TRACK_STATS_OPTIONS_CONTEXT_KEY)
    if not isinstance(options, list) or not options:
        await target.reply_text("No encontré la selección de ligas stats. Probá de nuevo con /track_stats.")
        return ConversationHandler.END
    shown = options[:25]
    selected_index = await _selected_index(update, prefix="ts_league", count=len(shown))
    if selected_index is None:
        await target.reply_text(
            "Elegí una liga de la lista.",
            reply_markup=_build_choice_keyboard([opt.league_name for opt in shown], "ts_league"),
        )
        return SELECT_LEAGUE_FOR_TRACK_STATS
    selected_option = options[selected_index]
    if not isinstance(selected_option, StatsLeagueOption):
        await target.reply_text("La liga stats seleccionada no es válida.")
        return ConversationHandler.END
    result = get_stats_service(context).track_stats_league(
        chat_id=update.effective_chat.id,
        option=selected_option,
    )
    await _reply_text_chunks(target, result.message, reply_markup=ReplyKeyboardRemove())
    _clear_all_selection_context(context)
    return ConversationHandler.END


async def link_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start `/link_stats` odds-track -> stats-league linking."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END

    tracking_service = get_tracking_service(context)
    tracked_leagues = tracking_service.list_confirmed_tracks(update.effective_chat.id)

    if not tracked_leagues:
        await update.message.reply_text(
            "No tenés ligas trackeadas todavía.\n"
            "Primero usá /track_league o /track_url.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    context.user_data[LINK_STATS_TRACKS_CONTEXT_KEY] = tracked_leagues

    await update.message.reply_text(
        _build_track_selection_message("¿Qué liga de odds querés vincular con stats?", tracked_leagues),
        reply_markup=_build_choice_keyboard(
            [t.tracked_league.competition_name for t in tracked_leagues], "ls_track"
        ),
    )
    return SELECT_TRACK_FOR_LINK_STATS


async def link_stats_select_track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle tracked odds league selection for `/link_stats`."""

    query = update.callback_query
    msg_obj = query.message if query else update.message
    if msg_obj is None:
        return ConversationHandler.END

    tracked_leagues = context.user_data.get(LINK_STATS_TRACKS_CONTEXT_KEY)
    if not isinstance(tracked_leagues, list) or not tracked_leagues:
        await msg_obj.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /link_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = None
    if query is not None:
        await query.answer()
        data = query.data
        if data.startswith("ls_track:"):
            selected_index = int(data.split(":")[1])
    else:
        selected_index = _parse_selection_number(update.message.text, len(tracked_leagues))

    if selected_index is None:
        await msg_obj.reply_text(
            "Elegí una liga de la lista.",
            reply_markup=_build_choice_keyboard(
                [t.tracked_league.competition_name for t in tracked_leagues], "ls_track"
            ),
        )
        return SELECT_TRACK_FOR_LINK_STATS

    selected_track = tracked_leagues[selected_index]
    if not isinstance(selected_track, TrackedCompetitionSubscription):
        await msg_obj.reply_text(
            "La liga seleccionada no es válida. Probá de nuevo con /link_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    stats_service = get_stats_service(context)
    providers = stats_service.list_providers()
    if not providers:
        await msg_obj.reply_text(
            "No hay providers de stats con discovery habilitado.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    context.user_data[LINK_STATS_SELECTED_TRACK_CONTEXT_KEY] = selected_track
    context.user_data[LINK_STATS_PROVIDERS_CONTEXT_KEY] = providers

    await msg_obj.reply_text(
        _build_stats_provider_selection_message(providers),
        reply_markup=_build_choice_keyboard([prov.display_name for prov in providers], "ls_provider"),
    )
    return SELECT_PROVIDER_FOR_LINK_STATS


async def link_stats_select_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle stats provider selection for `/link_stats`."""

    query = update.callback_query
    msg_obj = query.message if query else update.message
    if msg_obj is None:
        return ConversationHandler.END

    providers = context.user_data.get(LINK_STATS_PROVIDERS_CONTEXT_KEY)
    if not isinstance(providers, list) or not providers:
        await msg_obj.reply_text(
            "No encontré la selección de providers. Probá de nuevo con /link_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = None
    if query is not None:
        await query.answer()
        data = query.data
        if data.startswith("ls_provider:"):
            selected_index = int(data.split(":")[1])
    else:
        selected_index = _parse_selection_number(update.message.text, len(providers))

    if selected_index is None:
        await msg_obj.reply_text(
            "Elegí un provider de la lista.",
            reply_markup=_build_choice_keyboard([prov.display_name for prov in providers], "ls_provider"),
        )
        return SELECT_PROVIDER_FOR_LINK_STATS

    selected_provider = providers[selected_index]
    if not isinstance(selected_provider, StatsProviderDescriptor):
        await msg_obj.reply_text(
            "El provider seleccionado no es válido. Probá de nuevo con /link_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    context.user_data[LINK_STATS_SELECTED_PROVIDER_CONTEXT_KEY] = selected_provider
    await msg_obj.reply_text(
        _build_stats_provider_input_message(selected_provider),
        reply_markup=ReplyKeyboardRemove(),
    )
    return ENTER_COUNTRY_FOR_LINK_STATS


async def link_stats_enter_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Search stats provider leagues after the user enters a country."""

    if update.message is None:
        return ConversationHandler.END

    selected_provider = context.user_data.get(LINK_STATS_SELECTED_PROVIDER_CONTEXT_KEY)
    if not isinstance(selected_provider, StatsProviderDescriptor):
        await update.message.reply_text(
            "No encontré el provider seleccionado. Probá de nuevo con /link_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    country_name = (update.message.text or "").strip()
    if not country_name:
        await update.message.reply_text("Escribí un país válido o pegá una URL de liga del provider.")
        return ENTER_COUNTRY_FOR_LINK_STATS

    stats_service = get_stats_service(context)
    selected_track = context.user_data.get(LINK_STATS_SELECTED_TRACK_CONTEXT_KEY)

    # Direct provider URL, bypassing country discovery
    direct_reference = _extract_direct_stats_league_reference(country_name)
    if direct_reference is not None:
        if not isinstance(selected_track, TrackedCompetitionSubscription):
            await update.message.reply_text(
                "No encontré la liga de odds seleccionada. Probá de nuevo con /link_stats.",
                reply_markup=ReplyKeyboardRemove(),
            )
            _clear_all_selection_context(context)
            return ConversationHandler.END
        await update.message.reply_text(f"Resolviendo liga de {selected_provider.display_name}...")
        try:
            option = await stats_service.describe_league(
                provider_key=selected_provider.key,
                league_id=direct_reference,
            )
        except Exception:
            logger.exception(
                "Stats league describe-by-url failed provider=%s reference=%s",
                selected_provider.key,
                direct_reference,
            )
            option = None
        if option is None:
            await update.message.reply_text(
                f"No pude resolver esa URL en {selected_provider.display_name}.\n"
                "Verificá que sea una URL de liga/torneo del provider o probá con el país.",
                reply_markup=ReplyKeyboardRemove(),
            )
            _clear_all_selection_context(context)
            return ConversationHandler.END
        result = stats_service.link_league(
            tracked_competition_id=selected_track.tracked_league.id,
            option=option,
        )
        await update.message.reply_text(result.message, reply_markup=ReplyKeyboardRemove())
        _clear_all_selection_context(context)
        return ConversationHandler.END

    await update.message.reply_text(f"Buscando ligas de stats en {country_name}...")

    odds_league_name = None
    sample_events: list[MatchIdentityCandidate] = []
    if isinstance(selected_track, TrackedCompetitionSubscription):
        odds_league_name = selected_track.tracked_league.competition_name
        if update.effective_chat is not None:
            try:
                _, active_events = get_tracking_service(context).get_matches_for_track(
                    update.effective_chat.id,
                    selected_track.tracked_league.id,
                )
            except ValueError:
                active_events = []
            sample_events = [
                MatchIdentityCandidate(home=event.home, away=event.away, scheduled_at=event.scheduled_at)
                for event in (active_events or [])[:4]
            ]

    try:
        options = await stats_service.search_and_rank_leagues(
            provider_key=selected_provider.key,
            country_name=country_name,
            odds_league_name=odds_league_name,
            sample_events=sample_events,
            limit=80,
        )
    except RuntimeError as error:
        logger.exception(
            "Stats league discovery failed provider=%s country=%s",
            selected_provider.key,
            country_name,
        )
        message = str(error)
        if "Sportradar bootstrap failed" in message:
            await update.message.reply_text(
                "No pude renovar la sesión de Sportradar en modo headless.\n\n"
                "Para usarlo localmente, configurá SPORTRADAR_BOOTSTRAP_MODE=auto en .env "
                "y reiniciá el bot.",
                reply_markup=ReplyKeyboardRemove(),
            )
        else:
            await update.message.reply_text(
                "No pude buscar ligas de stats ahora. Probá de nuevo en unos minutos.",
                reply_markup=ReplyKeyboardRemove(),
            )
        _clear_all_selection_context(context)
        return ConversationHandler.END
    except Exception:
        logger.exception(
            "Stats league discovery failed provider=%s country=%s",
            selected_provider.key,
            country_name,
        )
        await update.message.reply_text(
            "No pude buscar ligas de stats ahora. Probá de nuevo en unos minutos.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    if not options:
        await update.message.reply_text(
            f"No encontré ligas de stats para {country_name} en {selected_provider.display_name}.\n\n"
            "Probá con otro nombre de país o pegá una URL directa de la liga del provider. (/cancel para salir)",
        )
        return ENTER_COUNTRY_FOR_LINK_STATS

    context.user_data[LINK_STATS_OPTIONS_CONTEXT_KEY] = options
    intro = ""
    if sample_events:
        intro = "🔢 Ordenadas por relevancia: la primera es la que más coincide con tus partidos.\n\n"

    await _reply_text_chunks(
        update.message,
        intro + _build_stats_league_selection_message(options, limit=25),
        reply_markup=_build_choice_keyboard([opt.league_name for opt in options[:20]], "ls_league"),
    )
    return SELECT_LEAGUE_FOR_LINK_STATS


async def link_stats_select_league(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Persist the selected stats league link."""

    query = update.callback_query
    msg_obj = query.message if query else update.message
    if msg_obj is None:
        return ConversationHandler.END

    selected_track = context.user_data.get(LINK_STATS_SELECTED_TRACK_CONTEXT_KEY)
    options = context.user_data.get(LINK_STATS_OPTIONS_CONTEXT_KEY)

    if not isinstance(selected_track, TrackedCompetitionSubscription):
        await msg_obj.reply_text(
            "No encontré la liga de odds seleccionada. Probá de nuevo con /link_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    if not isinstance(options, list) or not options:
        await msg_obj.reply_text(
            "No encontré la selección de ligas stats. Probá de nuevo con /link_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = None
    if query is not None:
        await query.answer()
        data = query.data
        if data.startswith("ls_league:"):
            selected_index = int(data.split(":")[1])
    else:
        selected_index = _parse_selection_number(update.message.text, len(options))

    if selected_index is None:
        await msg_obj.reply_text(
            "Elegí una liga de stats de la lista.",
            reply_markup=_build_choice_keyboard([opt.league_name for opt in options[:20]], "ls_league"),
        )
        return SELECT_LEAGUE_FOR_LINK_STATS

    selected_option = options[selected_index]
    if not isinstance(selected_option, StatsLeagueOption):
        await msg_obj.reply_text(
            "La liga stats seleccionada no es válida. Probá de nuevo con /link_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    stats_service = get_stats_service(context)
    result = stats_service.link_league(
        tracked_competition_id=selected_track.tracked_league.id,
        option=selected_option,
    )

    await _reply_text_chunks(msg_obj, result.message, reply_markup=ReplyKeyboardRemove())
    _clear_all_selection_context(context)
    return ConversationHandler.END


async def stats_links_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/stats_links` by showing stored odds-league -> stats-league mappings."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /stats_links recibido.")

    tracking_service = get_tracking_service(context)
    stats_service = get_stats_service(context)
    tracked_leagues = tracking_service.list_confirmed_tracks(update.effective_chat.id)
    result = stats_service.build_links_message(tracked_leagues)

    await reply_with_result(update, result)


async def stats_tracks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/stats_tracks` by listing standalone stats league subscriptions."""

    if update.message is None or update.effective_chat is None:
        return

    logger.info("Comando /stats_tracks recibido.")
    result = get_stats_service(context).build_stats_tracks_message(chat_id=update.effective_chat.id)
    await reply_with_result(update, result)


def _build_unified_stats_match_selection_message(
    unified_league_name: str,
    grouped_matches: list[list[ActiveEventRecord]],
) -> str:
    """Stats match picker: union of matches across books, with the books per row."""

    return f"¿De qué partido de {unified_league_name} querés ver stats?"


def _build_stats_provider_selection_message(providers: list[StatsProviderDescriptor]) -> str:
    """Build the stats provider prompt for `/link_stats`."""

    return "¿Qué provider de stats querés usar?"


def _build_stats_provider_input_message(provider: StatsProviderDescriptor) -> str:
    """Build the provider-specific country/direct-URL prompt."""

    lines = [
        f"Provider elegido: {provider.display_name}",
        "",
        "Tenés 2 formas de buscar o vincular:",
        "",
        "1) Escribí el país para buscar ligas de stats.",
        "Ejemplos: Spain, Australia, Argentina, England.",
        "",
        "2) Si la liga no aparece, pegá una URL directa de liga/torneo del provider.",
    ]
    if provider.key == "sportradar_statshub":
        lines.extend(
            [
                "Ejemplo Sportradar:",
                "https://statshub.sportradar.com/bet365/es/sport/1/tournament/28743",
            ]
        )
    elif provider.key == "sofascore_http":
        lines.extend(
            [
                "Ejemplo SofaScore:",
                "https://www.sofascore.com/es-la/football/tournament/australia/northern-territory-premier-league-women/33650#id:91941",
            ]
        )
    elif provider.key == "footystats_http":
        lines.extend(
            [
                "Ejemplo FootyStats:",
                "https://footystats.org/australia/northern-nsw-npl",
            ]
        )
    elif provider.key == "svenskfotboll_http":
        lines.extend(
            [
                "Ejemplo Svenskfotboll:",
                "País: Sweden | búsqueda: Allsvenskan",
                "ID/URL de liga: https://www.svenskfotboll.se/widget-go-to/?scr=table&ftid=133348",
            ]
        )
    return "\n".join(lines)


def _build_stats_league_selection_message(
    options: list[StatsLeagueOption],
    *,
    prompt: str = "Elegí la liga de stats a vincular:",
    limit: int = 25,
) -> str:
    """Build a stats-league prompt for linking or standalone tracking."""

    lines = [prompt]
    if len(options) > limit:
        lines.append(
            f"\n_(Mostrando {limit} de {len(options)} ligas encontradas. "
            "Si no ves tu liga, escribí una búsqueda más específica o pegá la URL directa.)_"
        )
    return "\n".join(lines)


def _build_stats_match_selection_message(
    tracked_league: TrackedCompetitionSubscription,
    matches: list[ActiveEventRecord],
) -> str:
    """Build the match prompt used by interactive `/stats`."""

    lines = [f"De qué partido querés generar stats en {tracked_league.tracked_league.league_name}?"]

    for index, match in enumerate(matches, start=1):
        label = format_kickoff_labels(
            match.scheduled_label_date,
            match.scheduled_label_time,
            with_year=True,
        )
        kickoff = f" | 🕒 {label}" if label and label != "Horario no disponible" else ""
        lines.append(f"{index} - {match.home} vs {match.away}{kickoff}")

    return "\n".join(lines)


async def stats_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats_help: portal to country-specific stats help."""
    if update.message is None:
        return
        
    args = context.args or []
    if args:
        code = args[0].lower().strip()
        await _show_country_help(update.message, code)
        return
        
    text = (
        "📈 <b>Portal de Estadísticas de Federaciones BetBot</b> 📈\n\n"
        "BetBot integra datos de federaciones oficiales de varios países para darte información de primera mano "
        "directamente de las asociaciones nacionales de fútbol.\n\n"
        "📖 <b>Comandos genéricos disponibles:</b>\n"
        "• <code>/stats_leagues [PAÍS]</code> - Lista las ligas del país seleccionado.\n"
        "• <code>/standings [PAÍS] [CÓDIGO]</code> - Muestra la tabla de posiciones de una liga.\n"
        "• <code>/fixtures [PAÍS] [CÓDIGO]</code> - Muestra los partidos de una liga.\n"
        "• <code>/today [PAÍS]</code> - Lista los partidos del día.\n"
        "• <code>/match [PAÍS] [ID]</code> - Detalle de alineación, rotación y eventos.\n\n"
        "Seleccioná un país a continuación para ver su guía y comandos específicos:"
    )
    await update.message.reply_text(
        text,
        reply_markup=get_country_selector_keyboard("help"),
        parse_mode="HTML"
    )


async def stats_leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    args = context.args or []
    if args:
        code = args[0].lower().strip()
        adapter = _get_country_adapter(code)
        if adapter:
            await _run_special_leagues(update.message, adapter)
            return
    await update.message.reply_text(
        "Seleccioná un país para ver sus ligas:",
        reply_markup=get_country_selector_keyboard("leagues")
    )


async def stats_callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries for consolidated generic stats commands."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    
    data = query.data
    parts = data.split(":")
    prefix = parts[0]
    
    if prefix == "stats_co":
        cmd = parts[1]
        code = parts[2]
        
        adapter = _get_country_adapter(code)
        if not adapter:
            await query.edit_message_text("❌ País no soportado.")
            return
            
        if cmd == "help":
            await _show_country_help(query.message, code)
        elif cmd == "leagues":
            await _run_special_leagues(query.message, adapter)
        elif cmd == "today":
            await _run_special_today(query.message, [], adapter)
        elif cmd in ("standings", "fixtures"):
            await _show_league_selector(query, code, cmd)
        elif cmd == "match":
            await _show_today_matches_selector(query, code)
            
    elif prefix == "stats_le":
        cmd = parts[1]
        code = parts[2]
        league_code = parts[3]
        
        adapter = _get_country_adapter(code)
        if not adapter:
            await query.edit_message_text("❌ País no soportado.")
            return
            
        if cmd == "standings":
            usage = f"❌ *Falta el código de liga.*\n\nUso: `/standings {code} [CÓDIGO]`"
            await _run_special_standings(query.message, [league_code], adapter, usage)
        elif cmd == "fixtures":
            usage = f"❌ *Falta el código de liga.*\n\nUso: `/fixtures {code} [CÓDIGO]`"
            await _run_special_fixtures(query.message, [league_code], adapter, usage)
            
    elif prefix == "stats_ma":
        code = parts[1]
        match_id = parts[2]
        
        adapter = _get_country_adapter(code)
        if not adapter:
            await query.edit_message_text("❌ País no soportado.")
            return
            
        usage_guide = f"❌ *ID de partido ausente o inválido.*\n\nUso: `/match {code} [ID]`"
        await _run_special_match(query.message, [match_id], adapter, usage_guide)


EXPLORE_MENU = 17


EXPLORE_TEAM_INPUT = 18


EXPLORE_SELECT_FIXTURE = 22


async def explore_select_league(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Load the selected league's cached overview and show the navigation menu."""

    target = _selection_target(update)
    if target is None:
        return ConversationHandler.END

    linked = context.user_data.get(EXPLORE_TRACKS_CONTEXT_KEY)
    if not isinstance(linked, list) or not linked:
        await target.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /explore_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = await _selected_index(update, prefix="exp_league", count=len(linked))
    if selected_index is None:
        await target.reply_text(
            "Elegí una liga de la lista.",
            reply_markup=_build_choice_keyboard([lg.label for lg in linked], "exp_league"),
        )
        return EXPLORE_SELECT_LEAGUE

    league = linked[selected_index]
    if not isinstance(league, ExplorableStatsLeague):
        await target.reply_text("La liga seleccionada no es válida.")
        return ConversationHandler.END
    stats_service = get_stats_service(context)
    await target.reply_text("Cargando datos de la liga...", reply_markup=ReplyKeyboardRemove())
    try:
        overview = await stats_service.get_league_overview(
            provider_key=league.provider_key,
            league_id=league.league_id,
        )
    except Exception:
        logger.exception("Explore stats overview failed league=%s", league.league_id)
        overview = None
    if not overview:
        await target.reply_text(
            "No pude cargar los datos de esa liga ahora. Probá más tarde.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    context.user_data[EXPLORE_OVERVIEW_CONTEXT_KEY] = overview
    context.user_data[EXPLORE_SELECTED_LEAGUE_CONTEXT_KEY] = league
    await target.reply_text(
        _explore_menu_text(overview),
        reply_markup=_explore_menu_keyboard(),
    )
    return EXPLORE_MENU


async def explore_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render the chosen view and keep the explorer menu open."""

    target = _selection_target(update)
    if target is None:
        return ConversationHandler.END

    overview = context.user_data.get(EXPLORE_OVERVIEW_CONTEXT_KEY)
    if not isinstance(overview, dict):
        await target.reply_text(
            "Se perdió el contexto. Probá de nuevo con /explore_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    choice = await _selected_index(update, prefix="exp_menu", count=6)
    if choice is None:
        await target.reply_text(
            _explore_menu_text(overview),
            reply_markup=_explore_menu_keyboard(),
        )
        return EXPLORE_MENU

    option = choice + 1
    if option == 4:
        await target.reply_text(
            "Escribí el nombre del equipo a buscar:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return EXPLORE_TEAM_INPUT

    if option == 6:
        league = context.user_data.get(EXPLORE_SELECTED_LEAGUE_CONTEXT_KEY)
        if not isinstance(league, ExplorableStatsLeague):
            await target.reply_text("Se perdió la liga seleccionada. Probá de nuevo con /explore_stats.")
            return ConversationHandler.END
        try:
            fixtures = await get_stats_service(context).list_fixtures(
                provider_key=league.provider_key,
                league_id=league.league_id,
                limit=30,
            )
        except Exception:
            logger.exception("Explore fixture list failed provider=%s league=%s", league.provider_key, league.league_id)
            fixtures = []
        if not fixtures:
            await target.reply_text("No hay partidos disponibles para generar reporte.")
            return EXPLORE_MENU
        context.user_data[EXPLORE_FIXTURES_CONTEXT_KEY] = fixtures
        await _reply_text_chunks(
            target,
            _build_provider_fixture_selection_message(fixtures),
            reply_markup=_build_choice_keyboard(
                [f"{fx.home} vs {fx.away}" for fx in fixtures], "exp_fix"
            ),
        )
        return EXPLORE_SELECT_FIXTURE

    if option == 1:
        message = render_league_table(overview)
    elif option == 2:
        message = render_league_fixtures(overview)
    elif option == 3:
        message = render_top_scorers(overview)
    else:
        message = f"🔗 {overview.get('source_url') or 'Sin link disponible.'}"

    await _reply_text_chunks(target, message)
    await target.reply_text(
        _explore_menu_text(overview),
        reply_markup=_explore_menu_keyboard(),
    )
    return EXPLORE_MENU


async def explore_team_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show one team's standings row, then return to the explorer menu."""

    if update.message is None:
        return ConversationHandler.END

    overview = context.user_data.get(EXPLORE_OVERVIEW_CONTEXT_KEY)
    if not isinstance(overview, dict):
        await update.message.reply_text(
            "Se perdió el contexto. Probá de nuevo con /explore_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    await _reply_text_chunks(update.message, render_team_row(overview, update.message.text or ""))
    await update.message.reply_text(
        _explore_menu_text(overview),
        reply_markup=_explore_menu_keyboard(),
    )
    return EXPLORE_MENU


async def explore_select_fixture(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generate a provider-native match report from `/explore_stats`."""

    target = _selection_target(update)
    if target is None:
        return ConversationHandler.END
    fixtures = context.user_data.get(EXPLORE_FIXTURES_CONTEXT_KEY)
    league = context.user_data.get(EXPLORE_SELECTED_LEAGUE_CONTEXT_KEY)
    if not isinstance(fixtures, list) or not fixtures or not isinstance(league, ExplorableStatsLeague):
        await target.reply_text("Se perdió la selección. Probá de nuevo con /explore_stats.")
        return ConversationHandler.END
    selected_index = await _selected_index(update, prefix="exp_fix", count=len(fixtures))
    if selected_index is None:
        await target.reply_text(
            "Elegí un partido de la lista.",
            reply_markup=_build_choice_keyboard(
                [f"{fx.home} vs {fx.away}" for fx in fixtures], "exp_fix"
            ),
        )
        return EXPLORE_SELECT_FIXTURE
    fixture = fixtures[selected_index]
    await target.reply_text("Generando reporte de stats...", reply_markup=ReplyKeyboardRemove())
    result = await get_stats_service(context).build_direct_match_report(
        provider_key=league.provider_key,
        stats_match_id=fixture.match_id,
    )
    await _reply_text_chunks(target, result.message)
    overview = context.user_data.get(EXPLORE_OVERVIEW_CONTEXT_KEY)
    if not isinstance(overview, dict):
        return ConversationHandler.END
    await target.reply_text(
        _explore_menu_text(overview),
        reply_markup=_explore_menu_keyboard(),
    )
    return EXPLORE_MENU


def _explore_menu_text(overview: dict) -> str:
    """Build the navigable explore menu shown after a league is selected."""

    name = overview.get("league_name") or "Liga"
    return (
        f"🔎 Explorando: {name}\n\n"
        "Elegí qué ver:\n"
        "1 - 📊 Tabla de posiciones\n"
        "2 - 🗓️ Próximos partidos\n"
        "3 - 👟 Goleadores\n"
        "4 - ⚽ Buscar un equipo\n"
        "5 - 🔗 Link al proveedor\n"
        "6 - 📋 Elegir partido y generar reporte\n\n"
        "/cancel para salir."
    )


def _explore_menu_keyboard():
    """Inline keyboard for the /explore_stats menu (index ``i`` = option ``i+1``)."""

    return _build_choice_keyboard(_EXPLORE_MENU_LABELS, "exp_menu")


def _build_provider_fixture_selection_message(fixtures: list) -> str:
    """Build the provider-native fixture prompt used by `/explore_stats`."""

    return "Elegí el partido para generar reporte:"



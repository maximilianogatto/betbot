"""Helpers y vocabulario compartidos entre los módulos de handlers.

Claves de contexto de las conversaciones, accesores a los services, teclados y
utilidades de respuesta. Viven acá para que los módulos por dominio
(special_leagues, stats, tracking...) se apoyen en un punto común en vez de
importarse entre sí o desde `commands.py` — eso generaría ciclos de importación.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Any

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.models import TrackedCompetitionSubscription
from interfaces.telegram.renderers import split_telegram_message
from services.models import CommandResult
from services.stats import StatsService
from services.tracking import TrackingService

logger = logging.getLogger(__name__)


def escape_html(text) -> str:
    """Escape text for Telegram HTML parse mode without escaping quotes."""
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


MATCHES_TRACKS_CONTEXT_KEY = "matches_tracks"


MATCHES_ACTIVE_CONTEXT_KEY = "matches_active"


MATCHES_SELECTED_TRACK_CONTEXT_KEY = "matches_selected_track"


STATS_TRACKS_CONTEXT_KEY = "stats_tracks"


STATS_ACTIVE_CONTEXT_KEY = "stats_active"


STATS_SELECTED_TRACK_CONTEXT_KEY = "stats_selected_track"


STATS_CANDIDATES_CONTEXT_KEY = "stats_candidates"


STATS_CANDIDATE_MATCH_CONTEXT_KEY = "stats_candidate_match"


STATS_CANDIDATE_PROVIDER_CONTEXT_KEY = "stats_candidate_provider"


EXPLORE_TRACKS_CONTEXT_KEY = "explore_tracks"


EXPLORE_OVERVIEW_CONTEXT_KEY = "explore_overview"


EXPLORE_SELECTED_LEAGUE_CONTEXT_KEY = "explore_selected_league"


EXPLORE_FIXTURES_CONTEXT_KEY = "explore_fixtures"


UNTRACK_TRACKS_CONTEXT_KEY = "untrack_tracks"


ODDS_TRACKS_CONTEXT_KEY = "odds_tracks"


ODDS_ENABLED_CONTEXT_KEY = "odds_enabled"


CHANGE_PERCENT_TRACKS_CONTEXT_KEY = "change_percent_tracks"


CHANGE_PERCENT_VALUE_CONTEXT_KEY = "change_percent_value"


TRACK_LEAGUE_PLATFORMS_CONTEXT_KEY = "track_league_platforms"


TRACK_LEAGUE_SELECTED_PLATFORM_CONTEXT_KEY = "track_league_selected_platform"


TRACK_LEAGUE_OPTIONS_CONTEXT_KEY = "track_league_options"


LINK_STATS_TRACKS_CONTEXT_KEY = "link_stats_tracks"


LINK_STATS_SELECTED_TRACK_CONTEXT_KEY = "link_stats_selected_track"


LINK_STATS_PROVIDERS_CONTEXT_KEY = "link_stats_providers"


LINK_STATS_SELECTED_PROVIDER_CONTEXT_KEY = "link_stats_selected_provider"


LINK_STATS_OPTIONS_CONTEXT_KEY = "link_stats_options"


TRACK_STATS_PROVIDERS_CONTEXT_KEY = "track_stats_providers"


TRACK_STATS_SELECTED_PROVIDER_CONTEXT_KEY = "track_stats_selected_provider"


TRACK_STATS_OPTIONS_CONTEXT_KEY = "track_stats_options"


def get_tracking_service(context: ContextTypes.DEFAULT_TYPE) -> TrackingService:
    """Retrieve the shared tracking service from the application."""

    tracking_service = context.application.bot_data.get("tracking_service")

    if not isinstance(tracking_service, TrackingService):
        raise RuntimeError("TrackingService no está configurado en la aplicación.")

    return tracking_service


def get_stats_service(context: ContextTypes.DEFAULT_TYPE) -> StatsService:
    """Retrieve the shared stats service from the application."""

    stats_service = context.application.bot_data.get("stats_service")

    if not isinstance(stats_service, StatsService):
        raise RuntimeError("StatsService no está configurado en la aplicación.")

    return stats_service


def get_live_watch_service(context: ContextTypes.DEFAULT_TYPE):
    """Retrieve the shared live-watch service from the application."""

    from services.live_watch import LiveWatchService

    service = context.application.bot_data.get("live_watch_service")
    if not isinstance(service, LiveWatchService):
        raise RuntimeError("LiveWatchService no está configurado en la aplicación.")
    return service


async def reply_with_result(update: Update, result: CommandResult) -> None:
    """Send a `CommandResult` message back to the current chat."""

    if update.message is None:
        return

    await _reply_text_chunks(update.message, result.message)


async def _reply_text_chunks(
    message,
    text: str,
    *,
    parse_mode: str | None = None,
    reply_markup=None,
) -> None:
    """Reply in multiple Telegram messages when the payload is too long."""

    chunks = split_telegram_message(text)
    for index, chunk in enumerate(chunks):
        await message.reply_text(
            chunk,
            parse_mode=parse_mode,
            reply_markup=reply_markup if index == 0 else None,
        )


async def _send_text_chunks(
    bot,
    chat_id: int,
    text: str,
    *,
    parse_mode: str | None = None,
) -> None:
    """Send one text in multiple Telegram bot messages when needed."""

    chunks = split_telegram_message(text)
    for chunk in chunks:
        await bot.send_message(
            chat_id=chat_id,
            text=chunk,
            parse_mode=parse_mode,
        )


def _build_unified_league_selection_message(prompt: str, leagues: list[dict[str, Any]]) -> str:
    # Options are shown as inline buttons; the message is just the prompt.
    return prompt


def _build_track_selection_message(prompt: str, tracks: list[TrackedCompetitionSubscription]) -> str:
    """Build a league-selection prompt (options rendered as inline buttons)."""

    return prompt


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


_CANCEL_CALLBACK_DATA = "cxl"


def sort_leagues_by_country_and_name(leagues: list[Any]) -> list[Any]:
    """Sort a list of leagues (dicts, objects or strings) by country then league name."""
    from core.league_naming import name_country_flag

    def _sort_key(item: Any) -> tuple[str, str]:
        name = ""
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("league_name") or "")
        elif hasattr(item, "league_name") and getattr(item, "league_name"):
            name = str(getattr(item, "league_name"))
        elif hasattr(item, "name") and getattr(item, "name"):
            name = str(getattr(item, "name"))
        else:
            name = str(item)
        country, _ = name_country_flag(name)
        return (country or "zzz", name.lower())

    return sorted(leagues, key=_sort_key)


def format_league_label(name: str) -> str:
    """Format a league name with its country flag emoji prefix if not already present."""
    from core.league_naming import name_country_flag

    if not name:
        return ""
    country, flag = name_country_flag(name)
    if flag and not name.strip().startswith(flag):
        return f"{flag} {name}"
    return name


def get_subscribed_unified_leagues(chat_id: int) -> list[dict[str, Any]]:
    """Return subscribed unified competitions sorted by country then league name."""
    from adapters.storage import get_storage

    unified = get_storage().list_subscribed_unified_competitions(chat_id)
    return sort_leagues_by_country_and_name(unified)


def _build_choice_keyboard(labels, prefix: str, *, cancel: bool = True):
    """Build a one-column inline keyboard; each button carries ``f'{prefix}:{index}'``.

    Replaces the legacy numeric ReplyKeyboard for in-conversation selections so
    the user taps a labelled button instead of typing a number. A ``❌ Cancelar``
    button is appended so the flow can be aborted without typing ``/cancel``.
    """

    keyboard = [
        [InlineKeyboardButton(str(label), callback_data=f"{prefix}:{index}")]
        for index, label in enumerate(labels)
    ]
    if cancel:
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data=_CANCEL_CALLBACK_DATA)])
    return InlineKeyboardMarkup(keyboard)


def _selection_target(update: Update) -> Message | None:
    """Return the message to reply to, whether from an inline button or text."""

    query = getattr(update, "callback_query", None)
    if query is not None:
        return query.message
    return update.message


async def _selected_index(update: Update, *, prefix: str, count: int) -> int | None:
    """Resolve a 0-based selection from an inline button or a typed number.

    Inline buttons (``f'{prefix}:{index}'``) are the primary path; a typed
    number is still accepted as a fallback. Returns None when nothing valid was
    chosen so the caller can re-prompt.
    """

    query = getattr(update, "callback_query", None)
    if query is not None:
        await query.answer()
        data = query.data or ""
        if not data.startswith(f"{prefix}:"):
            return None
        try:
            index = int(data.split(":", 1)[1])
        except ValueError:
            return None
        return index if 0 <= index < count else None
    text = update.message.text if update.message else None
    return _parse_selection_number(text, count)


def _clear_all_selection_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove temporary state used by interactive Telegram conversations."""

    context.user_data.pop(MATCHES_TRACKS_CONTEXT_KEY, None)
    context.user_data.pop(MATCHES_ACTIVE_CONTEXT_KEY, None)
    context.user_data.pop(MATCHES_SELECTED_TRACK_CONTEXT_KEY, None)
    context.user_data.pop(STATS_TRACKS_CONTEXT_KEY, None)
    context.user_data.pop(STATS_ACTIVE_CONTEXT_KEY, None)
    context.user_data.pop(STATS_SELECTED_TRACK_CONTEXT_KEY, None)
    context.user_data.pop(STATS_CANDIDATES_CONTEXT_KEY, None)
    context.user_data.pop(STATS_CANDIDATE_MATCH_CONTEXT_KEY, None)
    context.user_data.pop(STATS_CANDIDATE_PROVIDER_CONTEXT_KEY, None)
    context.user_data.pop(EXPLORE_TRACKS_CONTEXT_KEY, None)
    context.user_data.pop(EXPLORE_OVERVIEW_CONTEXT_KEY, None)
    context.user_data.pop(EXPLORE_SELECTED_LEAGUE_CONTEXT_KEY, None)
    context.user_data.pop(EXPLORE_FIXTURES_CONTEXT_KEY, None)
    context.user_data.pop(UNTRACK_TRACKS_CONTEXT_KEY, None)
    context.user_data.pop(ODDS_TRACKS_CONTEXT_KEY, None)
    context.user_data.pop(ODDS_ENABLED_CONTEXT_KEY, None)
    context.user_data.pop(CHANGE_PERCENT_TRACKS_CONTEXT_KEY, None)
    context.user_data.pop(CHANGE_PERCENT_VALUE_CONTEXT_KEY, None)
    context.user_data.pop(TRACK_LEAGUE_PLATFORMS_CONTEXT_KEY, None)
    context.user_data.pop(TRACK_LEAGUE_SELECTED_PLATFORM_CONTEXT_KEY, None)
    context.user_data.pop(TRACK_LEAGUE_OPTIONS_CONTEXT_KEY, None)
    context.user_data.pop(LINK_STATS_TRACKS_CONTEXT_KEY, None)
    context.user_data.pop(LINK_STATS_SELECTED_TRACK_CONTEXT_KEY, None)
    context.user_data.pop(LINK_STATS_PROVIDERS_CONTEXT_KEY, None)
    context.user_data.pop(LINK_STATS_SELECTED_PROVIDER_CONTEXT_KEY, None)
    context.user_data.pop(LINK_STATS_OPTIONS_CONTEXT_KEY, None)
    context.user_data.pop(TRACK_STATS_PROVIDERS_CONTEXT_KEY, None)
    context.user_data.pop(TRACK_STATS_SELECTED_PROVIDER_CONTEXT_KEY, None)
    context.user_data.pop(TRACK_STATS_OPTIONS_CONTEXT_KEY, None)


COUNTRIES_MAP = {
    "Finlandia 🇫🇮": "fin",
    "Suecia 🇸🇪": "swe",
    "Rumania 🇷🇴": "ro",
    "Eslovaquia 🇸🇰": "sk",
    "Argelia 🇩🇿": "al",
    "Noruega 🇳🇴": "no"
}


def get_country_selector_keyboard(cmd: str) -> InlineKeyboardMarkup:
    keyboard = []
    row = []
    for label, code in COUNTRIES_MAP.items():
        row.append(InlineKeyboardButton(label, callback_data=f"stats_co:{cmd}:{code}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)


def _get_country_adapter(country_code: str):
    # Import diferido: `special_leagues` importa de este módulo, así que traerlo
    # arriba cerraría un ciclo. Acá adentro se resuelve recién en la llamada.
    from interfaces.telegram.handlers.special_leagues import (
        _algeria_adapter,
        _finland_adapter,
        _norway_adapter,
        _romania_adapter,
        _slovakia_adapter,
        _sweden_adapter,
    )

    code = country_code.lower().strip()
    if code in ("fin", "finlandia", "finland"):
        return _finland_adapter()
    elif code in ("swe", "suecia", "sweden"):
        return _sweden_adapter()
    elif code in ("ro", "rumania", "romania"):
        return _romania_adapter()
    elif code in ("sk", "eslovaquia", "slovakia"):
        return _slovakia_adapter()
    elif code in ("al", "argelia", "algeria"):
        return _algeria_adapter()
    elif code in ("no", "noruega", "norway"):
        return _norway_adapter()
    return None


async def _show_country_help(message, code: str) -> None:
    code = code.lower().strip()
    if code in ("fin", "finlandia", "finland"):
        help_text = (
            "🇫🇮 <b>Guía de Estadísticas de la Federación de Finlandia</b> 🇫🇮\n\n"
            "Consultá estadísticas oficiales directo de la Asociación de Fútbol de Finlandia.\n\n"
            "📖 <b>Comandos disponibles:</b>\n"
            "• <code>/stats_leagues fin</code> - Jerarquía de ligas masculinas, femeninas y copas.\n"
            "• <code>/today fin</code> - Partidos programados para hoy.\n"
            "• <code>/standings fin [CÓDIGO]</code> - Tabla de posiciones (Ej: <code>VL</code>).\n"
            "• <code>/fixtures fin [CÓDIGO]</code> - Calendario de partidos y sus IDs.\n"
            "• <code>/match fin [ID_PARTIDO]</code> - Detalle del partido y análisis B-Team.\n"
        )
        await message.reply_text(help_text, parse_mode="HTML")
    elif code in ("swe", "suecia", "sweden"):
        help_text = (
            "🇸🇪 <b>Guía de Estadísticas de la Federación de Suecia</b> 🇸🇪\n\n"
            "Consultá datos oficiales directo de la Asociación Sueca de Fútbol (FOGIS).\n\n"
            "📖 <b>Comandos disponibles:</b>\n"
            "• <code>/stats_leagues swe</code> - Ligas suecas.\n"
            "• <code>/today swe</code> - Partidos suecos de hoy.\n"
            "• <code>/standings swe [CÓDIGO]</code> - Tabla de posiciones sueca.\n"
            "• <code>/fixtures swe [CÓDIGO]</code> - Fixtures suecos.\n"
            "• <code>/match swe [ID]</code> - Detalle de partido y análisis.\n"
        )
        await message.reply_text(help_text, parse_mode="HTML")
    elif code in ("ro", "rumania", "romania"):
        help_text = (
            "🇷🇴 <b>Guía de Estadísticas de la Federación de Rumania</b> 🇷🇴\n\n"
            "Consultá datos oficiales de la Federación Rumana de Fútbol (FRF).\n\n"
            "📖 <b>Comandos disponibles:</b>\n"
            "• <code>/stats_leagues ro</code> - Ligas rumanas.\n"
            "• <code>/today ro</code> - Partidos rumanos de hoy.\n"
            "• <code>/standings ro [CÓDIGO]</code> - Tabla de posiciones rumana.\n"
            "• <code>/fixtures ro [CÓDIGO]</code> - Fixtures rumanos.\n"
            "• <code>/match ro [ID]</code> - Detalle de partido.\n"
        )
        await message.reply_text(help_text, parse_mode="HTML")
    elif code in ("sk", "eslovaquia", "slovakia"):
        help_text = (
            "🇸🇰 <b>Guía de Estadísticas de la Federación de Eslovaquia</b> 🇸🇰\n\n"
            "Consultá datos oficiales de la Federación Eslovaca de Fútbol (Sportnet).\n\n"
            "📖 <b>Comandos disponibles:</b>\n"
            "• <code>/stats_leagues sk</code> - Ligas eslovacas.\n"
            "• <code>/today sk</code> - Partidos eslovacos de hoy.\n"
            "• <code>/standings sk [CÓDIGO]</code> - Tabla de posiciones eslovaca.\n"
            "• <code>/fixtures sk [CÓDIGO]</code> - Fixtures eslovacos.\n"
            "• <code>/match sk [ID]</code> - Detalle de partido.\n"
        )
        await message.reply_text(help_text, parse_mode="HTML")
    elif code in ("al", "argelia", "algeria"):
        help_text = (
            "🇩🇿 <b>Guía de Estadísticas de la Federación de Argelia</b> 🇩🇿\n\n"
            "Consultá datos oficiales de la Liga Nacional de Fútbol de Argelia (LNFF).\n\n"
            "📖 <b>Comandos disponibles:</b>\n"
            "• <code>/stats_leagues al</code> - Ligas argelinas.\n"
            "• <code>/today al</code> - Partidos argelinos de hoy.\n"
            "• <code>/standings al [CÓDIGO]</code> - Tabla de posiciones argelina.\n"
            "• <code>/fixtures al [CÓDIGO]</code> - Fixtures argelinos.\n"
            "• <code>/match al [ID]</code> - Detalle de partido.\n"
        )
        await message.reply_text(help_text, parse_mode="HTML")
    elif code in ("no", "noruega", "norway"):
        help_text = (
            "🇳🇴 <b>Guía de Estadísticas de la Federación de Noruega</b> 🇳🇴\n\n"
            "Consultá datos oficiales de la Federación Noruega de Fútbol (NFF).\n\n"
            "📖 <b>Comandos disponibles:</b>\n"
            "• <code>/stats_leagues no</code> - Ligas noruegas.\n"
            "• <code>/today no</code> - Partidos noruegos de hoy.\n"
            "• <code>/standings no [CÓDIGO]</code> - Tabla de posiciones noruega.\n"
            "• <code>/fixtures no [CÓDIGO]</code> - Fixtures noruegos.\n"
            "• <code>/match no [ID]</code> - Detalle de partido.\n"
        )
        await message.reply_text(help_text, parse_mode="HTML")
    else:
        await message.reply_text("❌ País no soportado. Países válidos: fin, swe, ro, sk, al, no")


async def _show_league_selector(update_or_query, country_code: str, cmd: str) -> None:
    adapter = _get_country_adapter(country_code)
    if not adapter:
        return
    import asyncio
    try:
        leagues = await asyncio.to_thread(adapter.leagues)
        if not leagues:
            text = "⚠️ No se encontraron ligas para este país."
            if hasattr(update_or_query, "message") and update_or_query.message:
                await update_or_query.message.reply_text(text)
            else:
                await update_or_query.edit_message_text(text)
            return
        
        keyboard = []
        for lg in leagues[:20]:
            keyboard.append([InlineKeyboardButton(f"{lg.name} ({lg.code})", callback_data=f"stats_le:{cmd}:{country_code}:{lg.code}")])
        
        text = f"🏆 Seleccioná una liga de {adapter.country}:"
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(update_or_query, "message") and update_or_query.message:
            await update_or_query.message.reply_text(text, reply_markup=reply_markup)
        else:
            await update_or_query.edit_message_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.exception("Failed to show league selector")
        msg = f"❌ Error al cargar ligas: {e}"
        if hasattr(update_or_query, "message") and update_or_query.message:
            await update_or_query.message.reply_text(msg)
        else:
            await update_or_query.edit_message_text(msg)
    finally:
        adapter.close()


async def _show_today_matches_selector(update_or_query, country_code: str) -> None:
    adapter = _get_country_adapter(country_code)
    if not adapter:
        return
    import asyncio
    try:
        rows, omitted = await asyncio.to_thread(adapter.today)
        if not rows:
            text = f"⚽ No hay partidos de hoy programados para {adapter.country}."
            if hasattr(update_or_query, "message") and update_or_query.message:
                await update_or_query.message.reply_text(text)
            else:
                await update_or_query.edit_message_text(text)
            return
        
        keyboard = []
        for row in rows[:20]:
            label = f"{row.home} vs {row.away}"
            if row.score:
                label += f" ({row.score})"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"stats_ma:{country_code}:{row.id}")])
            
        text = f"⚽ Partidos de hoy de {adapter.country}. Seleccioná uno para ver estadísticas:"
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(update_or_query, "message") and update_or_query.message:
            await update_or_query.message.reply_text(text, reply_markup=reply_markup)
        else:
            await update_or_query.edit_message_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.exception("Failed to show today matches selector")
        msg = f"❌ Error al cargar partidos de hoy: {e}"
        if hasattr(update_or_query, "message") and update_or_query.message:
            await update_or_query.message.reply_text(msg)
        else:
            await update_or_query.edit_message_text(msg)
    finally:
        adapter.close()



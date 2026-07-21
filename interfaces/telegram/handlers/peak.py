"""Handlers del scoring diario de partidos de ligas especiales (/peaks, /peak_today, /peak_on, /peak_off).

Se apoya en `common.py` para el vocabulario compartido; nunca importa desde
`commands.py` — es `commands.py` el que importa de acá y re-exporta.
"""
from __future__ import annotations

from adapters.storage import get_storage
from datetime import date
from services.special_peak import SpecialMatchScore
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram import Update
from telegram.ext import ContextTypes

from interfaces.telegram.handlers.common import (
    _reply_text_chunks,
    logger,
)


async def peak_today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /peak_today: ranked 1-10 scoring of today's special-league matches."""

    del context
    if update.message is None:
        return

    import asyncio as _asyncio

    from services.special_peak import build_peak_scores, render_peak_digest
    from stats_providers.palloliitto.api_client import PalloliittoAPI
    from stats_providers.svenskfotboll_http.client import SvenskfotbollHTTPClient

    await update.message.reply_text(
        "🎯 Analizando partidos de ligas especiales del día (Finlandia 🇫🇮 + Suecia 🇸🇪)..."
    )

    fin_api = PalloliittoAPI()
    swe_client = SvenskfotbollHTTPClient()
    try:
        scores = await _asyncio.to_thread(
            build_peak_scores, finland_api=fin_api, sweden_client=swe_client
        )
        digest = render_peak_digest(scores)
        await _reply_text_chunks(update.message, digest, parse_mode="Markdown")
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed in /peak_today")
        await update.message.reply_text(f"❌ Error al armar el peak del día: {e}")
    finally:
        fin_api.close()
        swe_client.close()


async def peak_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /peak_on: subscribe this chat to the daily peak digest push."""

    del context
    if update.message is None or update.effective_chat is None:
        return

    get_storage().set_peak_digest_subscription(update.effective_chat.id, True)
    await update.message.reply_text(
        "✅ Listo. Vas a recibir cada mañana el *Peak del día* de ligas especiales "
        "(Finlandia 🇫🇮 + Suecia 🇸🇪).\n"
        "Para verlo cuando quieras: `/peak_today`. Para desactivar: `/peak_off`.",
        parse_mode="Markdown",
    )


async def peak_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /peak_off: unsubscribe this chat from the daily peak digest push."""

    del context
    if update.message is None or update.effective_chat is None:
        return

    get_storage().set_peak_digest_subscription(update.effective_chat.id, False)
    await update.message.reply_text(
        "🔕 Desactivé el envío automático del Peak del día. Igual podés consultarlo con `/peak_today`.",
        parse_mode="Markdown",
    )


_PEAK_SCORES_CACHE = {}  # date_str -> list[SpecialMatchScore]


def _get_cached_peaks() -> list[SpecialMatchScore] | None:
    today_str = date.today().isoformat()
    return _PEAK_SCORES_CACHE.get(today_str)


def _set_cached_peaks(scores: list[SpecialMatchScore]) -> None:
    today_str = date.today().isoformat()
    _PEAK_SCORES_CACHE[today_str] = scores


def filter_peaks(scores: list[SpecialMatchScore], market: str) -> list[SpecialMatchScore]:
    market = market.lower().strip()
    if market == "wins":
        return [s for s in scores if s.favorite is not None or abs(s.edge) > 0.2]
    elif market == "goals":
        return [s for s in scores if s.score_int >= 5]
    elif market == "handicaps":
        return [s for s in scores if abs(s.edge) >= 0.4 or any(f.name == "Desnivel" for f in s.factors)]
    elif market == "btts":
        return [s for s in scores if s.score_int >= 5 and (s.favorite is None or abs(s.edge) < 0.6)]
    return scores


def render_filtered_peak_digest(scores: list[SpecialMatchScore], market: str) -> str:
    from services.special_peak import current_display_timezone, tz_offset_label
    
    tz = current_display_timezone()
    date_label = date.today().strftime("%d/%m/%Y")
    
    market_title = {
        "wins": "Wins (Favoritos) ✌️",
        "goals": "Goles (Over/Under) ⚽",
        "handicaps": "Hándicaps 📉",
        "btts": "BTTS (Ambos Anotan) 🥅",
        "all": "Todos"
    }.get(market, "Filtrados")
    
    header = [
        f"🎯 *Peak del día — Ligas Especiales* ({date_label})",
        f"🔍 *Filtro activo: {market_title}*",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    
    if not scores:
        header.append("\n📭 No hay partidos que cumplan con este criterio de filtro hoy.")
        return "\n".join(header)
        
    peaks = [s for s in scores if s.is_peak]
    rest = [s for s in scores if not s.is_peak]
    
    lines = list(header)
    lines.append(f"\n🔝 *{len(peaks)} oportunidad(es) destacada(s)* en este filtro.\n")
    
    if peaks:
        lines.append("⭐ *PEAKS (listos para apostar / vigilar):*")
        from services.special_peak import _render_entry
        for score in peaks:
            lines.extend(_render_entry(score, tz))
        lines.append("")
        
    if rest:
        lines.append("📋 *Resto del radar:*")
        from services.special_peak import _kickoff_label_for_display
        for score in rest:
            lines.append(
                f"  {score.badge} *{score.score_int}/10* · `{_kickoff_label_for_display(score, tz)}` "
                f"{score.home} vs {score.away} — {score.detail_command}"
            )
            
    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 Para el reporte completo de un partido usá su comando (ej `/fin_match <ID>`).")
    return "\n".join(lines)


async def peaks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /peaks: interactive peaks display with market filter buttons."""
    if update.message is None:
        return
        
    scores = _get_cached_peaks()
    if scores is None:
        await update.message.reply_text(
            "🎯 Analizando partidos de ligas especiales del día (Finlandia 🇫🇮 + Suecia 🇸🇪)..."
        )
        import asyncio
        from services.special_peak import build_peak_scores
        from stats_providers.palloliitto.api_client import PalloliittoAPI
        from stats_providers.svenskfotboll_http.client import SvenskfotbollHTTPClient
        
        fin_api = PalloliittoAPI()
        swe_client = SvenskfotbollHTTPClient()
        try:
            scores = await asyncio.to_thread(
                build_peak_scores, finland_api=fin_api, sweden_client=swe_client
            )
            _set_cached_peaks(scores)
        except Exception as e:
            logger.exception("Failed to build peak scores")
            await update.message.reply_text(f"❌ Error al armar el peak del día: {e}")
            return
        finally:
            fin_api.close()
            swe_client.close()
            
    from services.special_peak import render_peak_digest
    digest = render_peak_digest(scores)
    
    keyboard = [
        [
            InlineKeyboardButton("Wins ✌️", callback_data="peaks_filter:wins"),
            InlineKeyboardButton("Goles ⚽", callback_data="peaks_filter:goals"),
        ],
        [
            InlineKeyboardButton("Hándicaps 📉", callback_data="peaks_filter:handicaps"),
            InlineKeyboardButton("BTTS 🥅", callback_data="peaks_filter:btts"),
        ],
        [
            InlineKeyboardButton("Mostrar Todos 📋", callback_data="peaks_filter:all")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await _reply_text_chunks(update.message, digest, reply_markup=reply_markup, parse_mode="Markdown")


async def peaks_callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries for peak digest filtering."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    
    data = query.data
    market = data.split(":")[1]
    
    scores = _get_cached_peaks()
    if scores is None:
        await query.edit_message_text("⚠️ Los datos han expirado. Por favor corré `/peaks` de nuevo.")
        return
        
    filtered = filter_peaks(scores, market)
    digest = render_filtered_peak_digest(filtered, market)
    
    keyboard = [
        [
            InlineKeyboardButton("Wins ✌️" if market != "wins" else "Wins ✌️ (Activo)", callback_data="peaks_filter:wins"),
            InlineKeyboardButton("Goles ⚽" if market != "goals" else "Goles ⚽ (Activo)", callback_data="peaks_filter:goals"),
        ],
        [
            InlineKeyboardButton("Hándicaps 📉" if market != "handicaps" else "Hándicaps 📉 (Activo)", callback_data="peaks_filter:handicaps"),
            InlineKeyboardButton("BTTS 🥅" if market != "btts" else "BTTS 🥅 (Activo)", callback_data="peaks_filter:btts"),
        ],
        [
            InlineKeyboardButton("Mostrar Todos 📋" if market != "all" else "Mostrar Todos 📋 (Activo)", callback_data="peaks_filter:all")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(digest, reply_markup=reply_markup, parse_mode="Markdown")



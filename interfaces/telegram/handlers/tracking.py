"""Handlers del seguimiento de ligas y cuotas: alta/baja de tracks, /matches, refresh manual, umbrales de cambio y el merge/unlink de ligas unificadas.

Se apoya en `common.py` para el vocabulario compartido; nunca importa desde
`commands.py` — es `commands.py` el que importa de acá y re-exporta.
"""
from __future__ import annotations

from core.extractor_base import LeagueDiscoveryOption
from core.models import ActiveEventRecord
from core.models import PlatformDescriptor
from interfaces.telegram.renderers import build_little_changes_message
from services.tracking import TrackingService
from telegram import ReplyKeyboardRemove
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.ext import ConversationHandler
import asyncio

from interfaces.telegram.handlers.common import (
    CHANGE_PERCENT_TRACKS_CONTEXT_KEY,
    CHANGE_PERCENT_VALUE_CONTEXT_KEY,
    MATCHES_ACTIVE_CONTEXT_KEY,
    MATCHES_SELECTED_TRACK_CONTEXT_KEY,
    MATCHES_TRACKS_CONTEXT_KEY,
    ODDS_ENABLED_CONTEXT_KEY,
    ODDS_TRACKS_CONTEXT_KEY,
    TRACK_LEAGUE_OPTIONS_CONTEXT_KEY,
    TRACK_LEAGUE_PLATFORMS_CONTEXT_KEY,
    TRACK_LEAGUE_SELECTED_PLATFORM_CONTEXT_KEY,
    UNTRACK_TRACKS_CONTEXT_KEY,
    _build_choice_keyboard,
    _build_unified_league_selection_message,
    _clear_all_selection_context,
    _parse_selection_number,
    _reply_text_chunks,
    _selected_index,
    _selection_target,
    _send_text_chunks,
    escape_html,
    format_league_label,
    get_subscribed_unified_leagues,
    get_tracking_service,
    logger,
    reply_with_result,
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
    return get_subscribed_unified_leagues(chat_id)


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
    unified_leagues = _subscribed_unified(update.effective_chat.id)

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
        reply_markup=_build_choice_keyboard([format_league_label(lg["name"]) for lg in unified_leagues], "mx_league"),
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
    unified_leagues = _subscribed_unified(update.effective_chat.id)

    if not unified_leagues:
        await update.message.reply_text(
            "No tenés ligas trackeadas para eliminar.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    context.user_data[UNTRACK_TRACKS_CONTEXT_KEY] = unified_leagues
    await update.message.reply_text(
        "¿Qué liga querés dejar de trackear? (se quita de todas sus plataformas)",
        reply_markup=_build_choice_keyboard([format_league_label(lg["name"]) for lg in unified_leagues], "un_league"),
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
    unified_leagues = _subscribed_unified(update.effective_chat.id)

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
        reply_markup=_build_choice_keyboard([format_league_label(lg["name"]) for lg in unified_leagues], "chg_league"),
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
    unified_leagues = _subscribed_unified(update.effective_chat.id)

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
        reply_markup=_build_choice_keyboard([format_league_label(lg["name"]) for lg in unified_leagues], "odds_league"),
    )

    return SELECT_LEAGUE_FOR_ODDS


def _build_discovery_platform_selection_message(platforms: list[PlatformDescriptor]) -> str:
    """Build the platform prompt for `/track_league`."""

    return "¿Qué plataforma querés usar para buscar ligas?"


def _build_discovered_league_selection_message(options: list[LeagueDiscoveryOption]) -> str:
    """Build the league prompt for `/track_league`."""

    return "Elegí la liga a trackear:"


def _match_choice_keyboard(grouped_matches):
    """Inline keyboard for /matches: a 'Ver todos' button + one per match.

    Index 0 is "Ver todos"; index ``i`` (>=1) is ``grouped_matches[i-1]`` — the
    same mapping the legacy numeric keyboard used (number 1 = all).
    """

    labels = ["📋 Ver todos"] + [f"{g[0].home} vs {g[0].away}" for g in grouped_matches]
    return _build_choice_keyboard(labels, "mx_match")



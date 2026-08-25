"""Handlers transversales del bot: ayuda, arranque, cancelación, zona horaria, plataformas y diagnóstico.

Se apoya en `common.py` para el vocabulario compartido; nunca importa desde
`commands.py` — es `commands.py` el que importa de acá y re-exporta.
"""
from __future__ import annotations

from adapters.storage import get_storage
from core.timezones import COMMON_TIMEZONES
from core.timezones import get_zoneinfo
from services.timezones import resolve_chat_timezone
from core.timezones import set_display_timezone
from core.timezones import tz_offset_label
from interfaces.telegram.handlers.live_watch import HELP_LIVE_MESSAGE
from interfaces.telegram.handlers.stats import HELP_STATS_MESSAGE
from telegram import ReplyKeyboardRemove
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.ext import ConversationHandler
import asyncio

from monitoring import format_system_metrics_message
from monitoring import get_system_metrics
from interfaces.telegram.handlers.common import (
    _clear_all_selection_context,
    _selection_target,
    escape_html,
    get_stats_service,
    get_tracking_service,
)


HELP_MESSAGE = (
    "🤖 <b>BetBot · Ayuda</b>\n"
    "<i>Tocá un /comando para ejecutarlo · copiá los que llevan &lt;dato&gt;.</i>\n\n"
    "<b>⚙️ General</b>\n"
    "  /guide — guía paso a paso del flujo completo\n"
    "  /platforms — casas de odds y proveedores de stats\n"
    "  /sportradar_token — estado/importar token de stats\n"
    "  /status — estado del bot · /ping — responde pong\n"
    "  /resources — consumo de CPU/RAM del server\n"
    "  <code>/timezone &lt;zona&gt;</code> — zona horaria del chat (def. Argentina)\n"
    "  /cancel — cancela la selección en curso\n\n"
    "<b>📂 Secciones</b>\n"
    "  /help_matches — odds y seguimiento de partidos\n"
    "  /help_live — partidos en vivo\n"
    "  /help_stats — estadísticas H2H y ligas especiales\n"
    "  /help_leagues — ligas cross-plataforma y recordatorios\n\n"
    "💡 <i>Primer paso:</i> /track_league"
)


HELP_MATCHES_MESSAGE = (
    "📈 <b>Odds y seguimiento de partidos</b>\n\n"
    "<b>Seguir ligas</b>\n"
    "  /track_league — agregar liga (interactivo: casa → país → liga)\n"
    "  <code>/track_url &lt;url&gt;</code> — agregar liga por link directo\n"
    "  /confirm_track — confirmar la liga pendiente\n"
    "  /confirm_empty_track — confirmar aunque no tenga partidos hoy\n"
    "  /list_tracks — tus ligas en seguimiento\n"
    "  <code>/competition_url &lt;n&gt;</code> — link original de una liga\n"
    "  <code>/update_track_url &lt;n&gt; &lt;url&gt;</code> — actualizar el link\n"
    "  /refresh_tracks — refrescar partidos y detectar nuevos\n"
    "  /untrack — dejar de seguir una liga\n\n"
    "<b>Partidos y odds</b>\n"
    "  /matches — ver partidos de una liga\n"
    "  <code>/event_url &lt;n&gt;</code> — link directo del partido elegido\n"
    "  /odds_on · /odds_off — alertas de caída de cuotas\n"
    "  <code>/set_change_percent &lt;n&gt;</code> — % mínimo para alertar\n"
    "  /check_little_changes — cambios chicos pendientes\n"
    "  <code>/confirm_change &lt;n&gt;</code> — aprobar un cambio chico\n"
    "  /confirm_all_little_changes — aprobar todos\n\n"
    "<b>🎯 Peak del día</b> <i>(scoring 1–10)</i>\n"
    "  /peak_today — partidos especiales y cuándo entrar\n"
    "  /peak_on · /peak_off — envío automático cada mañana\n\n"
    "↩︎ /help"
)


HELP_LEAGUES_MESSAGE = (
    "🏆 <b>Ligas cross-plataforma</b> <i>(comparador + unificación)</i>\n\n"
    "  /leagues — tus ligas unificadas (qué casas y stats tiene cada una)\n"
    "  <code>/league &lt;N&gt;</code> — ficha: league_id + nombre por casa, y stats\n"
    "  <code>/link_league &lt;N&gt; &lt;M&gt;</code> — fusionar la liga M dentro de la N\n"
    "  <code>/unlink_league &lt;N&gt; &lt;casa&gt;</code> — separar una casa de una liga\n"
    "  /relink_leagues — re-unificar automáticamente por nombre\n\n"
    "⏰ <b>Recordatorios</b> <i>(5 min antes · def. OFF)</i>\n"
    "  <code>/reminders_league &lt;N&gt; on|off</code> — todos los partidos de la liga N\n"
    "  <code>/reminders_match &lt;n&gt; on|off</code> — un partido puntual (de /matches)\n\n"
    "  <i>El comparador de /matches agrupa solo las casas de la misma liga.</i>\n\n"
    "↩︎ /help"
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/start` command."""

    del context

    if update.message is None:
        return

    first_name = "amigo"
    if update.effective_user and update.effective_user.first_name:
        first_name = update.effective_user.first_name

    welcome_message = (
        f"⚽ <b>BetBot</b> — odds, stats y live de tus ligas.\n\n"
        f"Hola, {escape_html(first_name)}. Empezá acá:\n"
        "  /track_league — seguí una liga\n"
        "  /matches — mirá los partidos\n"
        "  /watch_live — vigilá un partido en vivo\n\n"
        "📚 Todo: /help   ·   🌐 Casas: /platforms"
    )

    await update.message.reply_text(welcome_message, parse_mode=ParseMode.HTML)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/help` command with optional category argument."""

    if update.message is None:
        return

    category = ""
    if context.args:
        category = context.args[0].strip().lower()

    if category in ("matches", "odds", "tracking"):
        await update.message.reply_text(HELP_MATCHES_MESSAGE, parse_mode=ParseMode.HTML)
    elif category == "live":
        await update.message.reply_text(HELP_LIVE_MESSAGE, parse_mode=ParseMode.HTML)
    elif category in ("stats", "statistics", "especial", "especiales", "federaciones"):
        await update.message.reply_text(HELP_STATS_MESSAGE, parse_mode=ParseMode.HTML)
    elif category in ("leagues", "ligas", "liga", "comparador", "reminders", "recordatorios"):
        await update.message.reply_text(HELP_LEAGUES_MESSAGE, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(HELP_MESSAGE, parse_mode=ParseMode.HTML)


async def help_matches_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/help_matches` command."""
    del context
    if update.message:
        await update.message.reply_text(HELP_MATCHES_MESSAGE, parse_mode=ParseMode.HTML)


async def help_live_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/help_live` command."""
    del context
    if update.message:
        await update.message.reply_text(HELP_LIVE_MESSAGE, parse_mode=ParseMode.HTML)


async def help_leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/help_leagues` command."""
    del context
    if update.message:
        await update.message.reply_text(HELP_LEAGUES_MESSAGE, parse_mode=ParseMode.HTML)


async def sportradar_token_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/sportradar_token` command.

    - No args: show current token status (expiry, validity).
    - With text arg: import a raw Sportradar token string.
    - With a .json file attachment (caption = /sportradar_token): import full
      session state JSON.
    """

    if update.message is None or update.effective_chat is None:
        return

    # --- File attachment (user sends .json with caption /sportradar_token) ---
    doc = update.message.document
    if doc is not None:
        file_name = (doc.file_name or "").lower()
        if not file_name.endswith(".json"):
            await update.message.reply_text(
                "⚠️ Solo se acepta un archivo <code>.json</code> de session state.",
                parse_mode=ParseMode.HTML,
            )
            return
        try:
            tg_file = await doc.get_file()
            raw_bytes = await tg_file.download_as_bytearray()
            json_text = raw_bytes.decode("utf-8")
        except Exception as exc:
            await update.message.reply_text(f"❌ Error al descargar el archivo: {exc}")
            return
        provider = _get_sportradar_provider(context)
        if provider is None:
            await update.message.reply_text("❌ Sportradar no está registrado como provider.")
            return
        result = await asyncio.to_thread(provider.import_session_json, json_text)
        if result.get("ok"):
            hours = round(result["seconds_left"] / 3600, 1) if result.get("seconds_left") else "?"
            await update.message.reply_text(
                f"✅ <b>Session state importado</b>\n"
                f"Expira: <code>{result.get('expires_at_utc', '?')}</code>\n"
                f"Quedan ~{hours}h",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(f"❌ {result.get('error', 'Error desconocido')}")
        return

    # --- Text arg: raw token string ---
    args_text = " ".join(context.args) if context.args else ""
    if args_text.strip():
        provider = _get_sportradar_provider(context)
        if provider is None:
            await update.message.reply_text("❌ Sportradar no está registrado como provider.")
            return
        result = await asyncio.to_thread(provider.import_token_string, args_text)
        if result.get("ok"):
            hours = round(result["seconds_left"] / 3600, 1) if result.get("seconds_left") else "?"
            await update.message.reply_text(
                f"✅ <b>Token importado</b>\n"
                f"Expira: <code>{result.get('expires_at_utc', '?')}</code>\n"
                f"Quedan ~{hours}h",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(f"❌ {result.get('error', 'Error desconocido')}")
        return

    # --- No args: show status ---
    provider = _get_sportradar_provider(context)
    if provider is None:
        await update.message.reply_text("❌ Sportradar no está registrado como provider.")
        return
    status = await asyncio.to_thread(provider.get_token_status)
    if not status.get("has_token"):
        await update.message.reply_text(
            "🔑 <b>Sin token de Sportradar</b>\n\n"
            "Generá el token en tu PC:\n"
            "<code>python -m stats_providers.sportradar_http.engine.session_manager --headed --seconds 8</code>\n\n"
            "Después pegá el token:\n"
            "<code>/sportradar_token &lt;token&gt;</code>\n\n"
            "O subí el <code>.json</code> como archivo.",
            parse_mode=ParseMode.HTML,
        )
        return
    emoji = "✅" if status.get("usable") else "⚠️"
    state_label = "vigente" if status.get("usable") else "vencido"
    hours = status.get("hours_left", "?")
    replay_label = " (replay-only)" if status.get("replay_only") else ""
    await update.message.reply_text(
        f"{emoji} <b>Token Sportradar{replay_label}</b>\n"
        f"Estado: <b>{state_label}</b>\n"
        f"Expira: <code>{status.get('expires_at_utc', '?')}</code>\n"
        f"Quedan: ~{hours}h\n\n"
        "Renovar: <code>/sportradar_token &lt;token&gt;</code>",
        parse_mode=ParseMode.HTML,
    )


def _get_sportradar_provider(context: ContextTypes.DEFAULT_TYPE):
    """Resolve the Sportradar BotReadyProvider from the stats service."""

    from stats_providers.sportradar_http.engine.bot_ready.provider import SportradarBotReadyProvider

    stats_service = context.application.bot_data.get("stats_service")
    if stats_service is None:
        return None
    for provider in getattr(stats_service, "_providers", {}).values():
        runtime = getattr(provider, "_runtime", None)
        if isinstance(runtime, SportradarBotReadyProvider):
            return runtime
    # Fallback: iterate the provider registry directly.
    from core.stats_provider_base import stats_provider_registry
    for provider in stats_provider_registry.list_registered():
        runtime = getattr(provider, "_runtime", None)
        if isinstance(runtime, SportradarBotReadyProvider):
            return runtime
    return None


async def apply_chat_timezone_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the active display timezone for the chat handling this update.

    Registered in an early handler group so every command response is rendered
    in the chat's configured timezone (default Argentina).
    """

    del context
    chat = update.effective_chat
    set_display_timezone(resolve_chat_timezone(chat.id) if chat is not None else None)


async def timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show or change this chat's display timezone (partidos, avisos y lives)."""

    if update.message is None or update.effective_chat is None:
        return

    from datetime import datetime

    chat_id = update.effective_chat.id
    args = context.args or []

    if not args:
        saved = get_storage().get_chat_timezone(chat_id)
        tz = resolve_chat_timezone(chat_id)
        now_local = datetime.now(tz)
        current_name = saved if saved else "por defecto (Argentina)"
        examples = "\n".join(f"  • <code>{name}</code>" for name in COMMON_TIMEZONES)
        await update.message.reply_text(
            "🕒 <b>Zona horaria de este chat</b>\n"
            f"Actual: <b>{current_name}</b> ({tz_offset_label(tz)})\n"
            f"Hora local ahora: <b>{now_local.strftime('%H:%M')}</b>\n\n"
            "Cambiala con <code>/timezone &lt;Zona&gt;</code> (nombre IANA). Ejemplos:\n"
            f"{examples}\n\n"
            "Volver al default: <code>/timezone reset</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    arg = " ".join(args).strip()
    if arg.lower() in {"reset", "default", "defecto", "arg", "argentina"}:
        get_storage().clear_chat_timezone(chat_id)
        set_display_timezone(None)
        tz = resolve_chat_timezone(chat_id)
        await update.message.reply_text(
            f"✅ Zona horaria restablecida al default ({tz_offset_label(tz)}).",
            parse_mode=ParseMode.HTML,
        )
        return

    tz = get_zoneinfo(arg)
    if tz is None:
        examples = ", ".join(COMMON_TIMEZONES[:4])
        await update.message.reply_text(
            f"❌ No reconozco la zona horaria <code>{arg}</code>.\n"
            f"Usá un nombre IANA válido, por ej: <code>{examples}</code>.\n"
            "Ver lista y zona actual: <code>/timezone</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    get_storage().set_chat_timezone(chat_id, arg)
    set_display_timezone(tz)
    now_local = datetime.now(tz)
    await update.message.reply_text(
        f"✅ Zona horaria de este chat: <b>{arg}</b> ({tz_offset_label(tz)}).\n"
        f"Hora local ahora: <b>{now_local.strftime('%H:%M')}</b>.\n"
        "Se aplica a horarios de partidos, avisos y lives.",
        parse_mode=ParseMode.HTML,
    )


async def platforms_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/platforms` showing both odds platforms and stats providers."""

    if update.message is None:
        return

    tracking_service = get_tracking_service(context)
    stats_service = get_stats_service(context)

    odds_platforms = tracking_service.list_supported_platforms()
    stats_providers = stats_service.list_providers()

    def _name(display: str) -> str:
        cleaned = (display or "").removesuffix(" HTTP").removesuffix(" Http")
        return escape_html(cleaned or display)

    lines = ["🌐 <b>Plataformas soportadas</b>", ""]
    lines.append("<b>🏦 Casas de odds</b>")
    for platform in odds_platforms:
        prefix = "✅" if platform.implemented else "⚪️"
        lines.append(f"{prefix} <b>{_name(platform.display_name)}</b>  <code>{escape_html(platform.key)}</code>")
        if platform.supports:
            lines.append(f"   <i>{escape_html(' · '.join(platform.supports))}</i>")

    lines.append("")
    lines.append("<b>📊 Proveedores de stats</b>")
    for provider in stats_providers:
        prefix = "✅" if provider.implemented else "⚪️"
        lines.append(f"{prefix} <b>{_name(provider.display_name)}</b>  <code>{escape_html(provider.key)}</code>")
        if provider.capabilities.supports_h2h:
            lines.append("   <i>H2H · reportes · tablas · fixtures</i>")

    lines.append("")
    lines.append("💡 <i>Seguí una liga con</i> /track_league")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


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


async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """End any active selection flow from the inline ``❌ Cancelar`` button."""

    query = getattr(update, "callback_query", None)
    if query is not None:
        await query.answer()
    _clear_all_selection_context(context)
    target = _selection_target(update)
    if target is not None:
        await target.reply_text("Operación cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


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


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unsupported Telegram commands."""

    del context

    if update.message is None:
        return

    await update.message.reply_text(
        "Todavía no conozco ese comando. Usá /help para ver la lista disponible."
    )



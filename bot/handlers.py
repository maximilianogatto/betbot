"""Telegram command handlers for the current sportsbook tracking bot flow."""

from __future__ import annotations

import asyncio
from datetime import date
import logging
import re
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

from bot.alerts import (
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
from monitors.stats import (
    ExplorableStatsLeague,
    StatsService,
    render_league_fixtures,
    render_league_table,
    render_team_row,
    render_top_scorers,
)
from monitors.tracking import CommandResult, TrackingService
from core.models import (
    ActiveEventRecord,
    TrackedCompetitionSubscription,
)
from adapters.storage import get_storage

logger = logging.getLogger(__name__)


def escape_html(text) -> str:
    """Escape text for Telegram HTML parse mode without escaping quotes."""
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


SELECT_LEAGUE_FOR_MATCHES = 1
SELECT_MATCH_FOR_MATCHES = 2
SELECT_LEAGUE_FOR_UNTRACK = 3
SELECT_LEAGUE_FOR_ODDS = 4
SELECT_LEAGUE_FOR_CHANGE_PERCENT = 5
SELECT_PLATFORM_FOR_TRACK_LEAGUE = 6
ENTER_COUNTRY_FOR_TRACK_LEAGUE = 7
SELECT_LEAGUE_FOR_TRACK_LEAGUE = 8
SELECT_TRACK_FOR_LINK_STATS = 9
SELECT_PROVIDER_FOR_LINK_STATS = 10
ENTER_COUNTRY_FOR_LINK_STATS = 11
SELECT_LEAGUE_FOR_LINK_STATS = 12
SELECT_LEAGUE_FOR_STATS = 13
SELECT_MATCH_FOR_STATS = 14
SELECT_STATS_CANDIDATE = 15
EXPLORE_SELECT_LEAGUE = 16
EXPLORE_MENU = 17
EXPLORE_TEAM_INPUT = 18
SELECT_PROVIDER_FOR_TRACK_STATS = 19
ENTER_COUNTRY_FOR_TRACK_STATS = 20
SELECT_LEAGUE_FOR_TRACK_STATS = 21
EXPLORE_SELECT_FIXTURE = 22

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
MANUAL_REFRESH_TASK_KEY = "manual_refresh_task"

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

HELP_LIVE_MESSAGE = (
    "🔴 <b>Partidos en vivo</b>\n\n"
    "  /watch_live — vigilar partidos (escribí los equipos o subí el fixture)\n"
    "  /import_sheet — importar la planilla de Google Drive\n"
    "  /watching — tus partidos en vigilancia (activos y salidos)\n"
    "  <code>/view_match &lt;id&gt;</code> — stats en vivo y cuotas de un partido\n"
    "  /live_status — cadencia, activos y último estado detectado\n"
    "  /live_settings — alertas live: goles, rojas y amarillas\n"
    "  <code>/unwatch &lt;id&gt;</code> — sacar de la vigilancia <i>(o /unwatch all)</i>\n\n"
    "↩︎ /help"
)

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

STATS_URL_USAGE_MESSAGE = (
    "📊 <b>Reporte de stats de un partido</b>\n"
    "<code>/stats &lt;n&gt; [provider]</code>  <i>(n de</i> /matches<i>)</i>\n"
    "<i>Sin provider combina todos los linkeados; con provider usa solo ese.</i>\n"
    "Ejemplos: <code>/stats 3</code> · <code>/stats 3 sofascore</code>"
)


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

    from monitors.live_watch import LiveWatchService

    service = context.application.bot_data.get("live_watch_service")
    if not isinstance(service, LiveWatchService):
        raise RuntimeError("LiveWatchService no está configurado en la aplicación.")
    return service


async def watch_live_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add fixtures to the live-watch list (one match per line, bulk paste or photo)."""

    if update.message is None or update.effective_chat is None:
        return

    # Check if this is a photo command
    if update.message.photo:
        await watch_live_photo_handler(update, context)
        return

    # Check if this is a reply to a photo message
    if update.message.reply_to_message and update.message.reply_to_message.photo:
        await watch_live_photo_handler(update, context, message_with_photo=update.message.reply_to_message)
        return

    raw = update.message.text or ""
    # Strip the leading "/watch_live" command token, keep the rest (multiline).
    body = raw.split(None, 1)[1] if len(raw.split(None, 1)) > 1 else ""
    lines = [line for line in body.splitlines() if line.strip()]
    if not lines:
        await update.message.reply_text(
            "📋 Pegá tu fixture, un partido por renglón. Ejemplos:\n"
            "/watch_live\n"
            "Murdoch - East Perth\n"
            "Australia Occidental | Subiaco - UWA\n"
            "Poli Iasi vs Otelul\n\n"
            "O subí una foto de tu fixture escribiendo /watch_live como epígrafe/comentario, o respondé /watch_live a una foto ya enviada.\n\n"
            "Cuando alguno salga en vivo en cualquier casa, te aviso.\n"
            "Ver lista: /watching · Borrar: /unwatch <id> (o /unwatch all)"
        )
        return

    service = get_live_watch_service(context)
    added = service.add_fixture_lines(update.effective_chat.id, lines)
    skipped = len(lines) - len(added)
    if not added:
        await update.message.reply_text(
            "No pude leer ningún partido. Usá 'Local - Visitante' (uno por renglón)."
        )
        return
    msg = [
        f"👁️ *Vigilando {len(added)} partido(s) en vivo:*",
        "━━━━━━━━━━━━━━━━━━━━\n"
    ]
    for entry in added:
        hint = f" ({entry.league_hint})" if entry.league_hint else ""
        disp_id = entry.chat_local_id if entry.chat_local_id is not None else entry.id
        msg.append(f"  *#{disp_id}* · `{entry.home}` vs `{entry.away}`{hint}")
    if skipped:
        msg.append(f"\n_(Se omitieron {skipped} renglones no legibles)_")
    msg.append("\nTe avisaré en este chat apenas salgan en vivo.")
    await _reply_text_chunks(update.message, "\n".join(msg), parse_mode="Markdown")


async def watch_live_photo_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    message_with_photo: Message | None = None
) -> None:
    """Handle photo messages sent with /watch_live as a caption or as a reply."""

    import httpx
    import os

    if update.message is None or update.effective_chat is None:
        return

    msg_to_read = message_with_photo or update.message

    if not msg_to_read.photo:
        await update.message.reply_text("❌ No se detectó ninguna imagen.")
        return

    loading_msg = await update.message.reply_text(
        "⏳ Leyendo fixture desde la imagen usando OCR de alta precisión..."
    )

    try:
        photo = msg_to_read.photo[-1]
        file = await photo.get_file()
        photo_bytes = await file.download_as_bytearray()

        api_key = os.getenv("OCR_SPACE_API_KEY", "helloworld")

        async with httpx.AsyncClient() as client:
            files = {"file": ("image.jpg", bytes(photo_bytes), "image/jpeg")}
            data = {
                "apikey": api_key,
                "language": "spa",
                "isTable": True,
            }
            response = await client.post(
                "https://api.ocr.space/parse/image",
                files=files,
                data=data,
                timeout=30.0
            )

        if response.status_code != 200:
            await loading_msg.edit_text(
                f"❌ Error de red con el servicio de OCR (HTTP {response.status_code})."
            )
            return

        res = response.json()
        if res.get("IsErroredOnProcessing") or "ParsedResults" not in res:
            error_msg = res.get("ErrorMessage") or "Error desconocido en el procesamiento de la imagen."
            await loading_msg.edit_text(f"❌ Error del servicio OCR: {error_msg}")
            return

        parsed_text = res["ParsedResults"][0].get("ParsedText", "")
        if not parsed_text.strip():
            await loading_msg.edit_text(
                "⚠️ No pude extraer ningún texto de la imagen. Asegurate de que la imagen sea nítida y legible."
            )
            return

        lines_to_add: list[str] = []
        fixture_separators = (" - ", " – ", " vs. ", " vs ", " v ", " x ")

        for row in parsed_text.splitlines():
            if not row.strip():
                continue
            columns = [col.strip() for col in row.split("\t") if col.strip()]
            if not columns:
                continue

            match_col_idx = -1
            for idx, col in enumerate(columns):
                if any(sep in col for sep in fixture_separators):
                    match_col_idx = idx
                    break

            if match_col_idx != -1:
                match_text = columns[match_col_idx]
                league_hint = None
                note = None
                time_str = None

                # Search for a time column anywhere in this row's columns
                for col in columns:
                    tm = re.search(r"\b(\d{1,2})[:.](\d{2})\b", col)
                    if tm:
                        time_str = f"{int(tm.group(1)):02d}:{tm.group(2)}"
                        break

                if match_col_idx > 0:
                    hint_candidate = columns[match_col_idx - 1]
                    if not any(header in hint_candidate.lower() for header in ("horario", "competicion", "partido", "detalle")):
                        if not re.search(r"\b(\d{1,2})[:.](\d{2})\b", hint_candidate):
                            league_hint = hint_candidate

                if match_col_idx + 1 < len(columns):
                    note_candidate = columns[match_col_idx + 1]
                    if not any(header in note_candidate.lower() for header in ("detalle", "note")):
                        if not re.search(r"\b(\d{1,2})[:.](\d{2})\b", note_candidate):
                            note = note_candidate

                line = ""
                if time_str:
                    line += f"{time_str} "
                if league_hint:
                    line += f"{league_hint} | "
                line += match_text
                if note:
                    line += f" ({note})"
                lines_to_add.append(line)

        if not lines_to_add:
            await loading_msg.edit_text(
                "⚠️ No encontré ningún partido formateado (tipo 'Local - Visitante') en la tabla. "
                "Asegurate de que las columnas de la tabla estén bien definidas y alineadas."
            )
            return

        service = get_live_watch_service(context)
        added = service.add_fixture_lines(update.effective_chat.id, lines_to_add)

        if not added:
            await loading_msg.edit_text(
                "❌ Se detectaron partidos pero no se pudieron registrar en tu vigilancia."
            )
            return

        msg = [
            "📸 *¡Fixture leído con éxito!* Vigilando partidos:",
            "━━━━━━━━━━━━━━━━━━━━\n"
        ]
        for entry in added:
            hint = f" ({entry.league_hint})" if entry.league_hint else ""
            disp_id = entry.chat_local_id if entry.chat_local_id is not None else entry.id
            msg.append(f"  *#{disp_id}* · `{entry.home}` vs `{entry.away}`{hint}")

        await loading_msg.delete()
        await _reply_text_chunks(update.message, "\n".join(msg), parse_mode="Markdown")

    except Exception as e:
        logger.exception("Error procesando foto de fixture")
        await loading_msg.edit_text(f"❌ Error procesando la imagen: {str(e)}")


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


async def import_sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Import and watch matches from the shared Google Sheet URL."""
    if update.message is None or update.effective_chat is None:
        return

    import os
    import httpx
    from monitors.live_watch import parse_sheet_fixture_lines, sheet_timezone

    url = os.getenv(
        "LIVE_WATCH_SHEET_URL",
        "https://docs.google.com/spreadsheets/d/17QRnS_BmmAz_7F4hvpUytPoD66U65W2f1pgF6q9y7fY/export?format=csv&gid=0"
    )

    loading_msg = await update.message.reply_text("⏳ Descargando y analizando planilla de partidos...")

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, timeout=20.0)

        if response.status_code != 200:
            await loading_msg.edit_text(f"❌ Error al descargar planilla (HTTP {response.status_code}).")
            return

        try:
            lines_to_add = parse_sheet_fixture_lines(response.text)
        except ValueError as err:
            await loading_msg.edit_text(f"❌ {err}")
            return

        if not lines_to_add:
            await loading_msg.edit_text("⚠️ No se encontraron partidos válidos en la planilla.")
            return

        service = get_live_watch_service(context)
        # Sheet times are Argentina wall-clock, not this chat's display timezone.
        added = service.add_fixture_lines(
            update.effective_chat.id, lines_to_add, times_tz=sheet_timezone()
        )

        total_read = len(lines_to_add)
        total_added = len(added)
        skipped = total_read - total_added

        if not added:
            await loading_msg.edit_text(
                f"📋 Se leyeron {total_read} partidos de la planilla, pero todos fueron omitidos por estar en el pasado o ya estar duplicados en tu lista."
            )
            return

        msg = [
            f"📊 *¡Importación completada con éxito!*",
            f"Se leyeron {total_read} partidos de la planilla.",
            f"➕ *Nuevos en vigilancia:* {total_added}",
            f"⏭️ *Omitidos (pasados/duplicados):* {skipped}",
            "\n━━━━━━━━━━━━━━━━━━━━\n"
        ]
        for entry in added:
            hint = f" ({entry.league_hint})" if entry.league_hint else ""
            disp_id = entry.chat_local_id if entry.chat_local_id is not None else entry.id
            msg.append(f"  *#{disp_id}* · `{entry.home}` vs `{entry.away}`{hint}")

        await _reply_text_chunks(update.message, "\n".join(msg), parse_mode="Markdown")
        await loading_msg.delete()

    except Exception as e:
        logger.exception("Error during sheet import")
        await loading_msg.edit_text(f"❌ Ocurrió un error inesperado al importar la planilla: {str(e)}")


async def watching_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    """List the chat's active live-watch fixtures."""

    if update.message is None or update.effective_chat is None:
        return
    service = get_live_watch_service(context)
    watching = service.list_watches(update.effective_chat.id, status="watching")
    fired = service.list_watches(update.effective_chat.id, status="fired")
    if not watching and not fired:
        await update.message.reply_text(
            "No tenés partidos en vigilancia. Cargá con /watch_live (uno por renglón)."
        )
        return
    lines: list[str] = []
    display_tz = current_display_timezone()
    if watching:
        lines.append(f"👁️ *En vigilancia:* _(hora {tz_offset_label(display_tz)})_")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        for e in watching:
            time_lbl = "Pendiente"
            if e.kickoff_at:
                try:
                    from datetime import datetime, timezone as _tz
                    dt = datetime.fromisoformat(e.kickoff_at)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=_tz.utc)
                    dt_local = dt.astimezone(display_tz)
                    time_lbl = dt_local.strftime('%H:%M')
                    if dt_local.date() != datetime.now(display_tz).date():
                        time_lbl = dt_local.strftime('%d/%m %H:%M')
                except Exception:
                    pass
            disp_id = e.chat_local_id if e.chat_local_id is not None else e.id
            hint = f" ({e.league_hint})" if e.league_hint else ""
            alerted_str = ""
            if e.fired_platforms:
                alerted_str = f" _(Alertados: {', '.join(p.replace('_http', '') for p in e.fired_platforms_list)})_"
            lines.append(
                f"  *#{disp_id}* · 🕒 `{time_lbl}`{hint}{alerted_str}\n"
                f"     ⚽ `{e.home}` vs `{e.away}`\n"
            )
    if fired:
        lines.append("\n🔴 *Ya salieron en vivo:*")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        for e in fired:
            platforms_str = ", ".join(p.replace("_http", "") for p in e.fired_platforms_list)
            disp_id = e.chat_local_id if e.chat_local_id is not None else e.id
            lines.append(
                f"  *#{disp_id}* · ⚽ `{e.home}` vs `{e.away}`\n"
                f"     🏦 → {platforms_str} {e.matched_minute or ''}\n".rstrip()
            )
    lines.append("\nBorrar: `/unwatch <id>` · `/unwatch all`")
    await _reply_text_chunks(update.message, "\n".join(lines), parse_mode="Markdown")


async def unwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove one (or all) live-watch fixtures for the chat."""

    if update.message is None or update.effective_chat is None:
        return
    service = get_live_watch_service(context)
    chat_id = update.effective_chat.id
    arg = (context.args[0].strip().lower() if context.args else "")
    if arg in ("all", "todo", "todos"):
        removed = service.clear_watches(chat_id)
        await update.message.reply_text(f"🗑️ Borré {removed} partido(s) de la vigilancia.")
        return
    if not arg.isdigit():
        await update.message.reply_text("Usá /unwatch <id> (mirá los ids con /watching) o /unwatch all.")
        return
    target_id = int(arg)
    ok = False
    if hasattr(service, "remove_watch_by_local_id"):
        ok = service.remove_watch_by_local_id(chat_id, target_id)
    if not ok:
        ok = service.remove_watch(chat_id, target_id)
    await update.message.reply_text("🗑️ Borrado." if ok else "No encontré ese id en tu vigilancia.")


async def live_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current live-watch cadence, active fixtures and stored live states."""

    if update.message is None or update.effective_chat is None:
        return

    service = get_live_watch_service(context)
    chat_id = update.effective_chat.id
    settings = service.get_alert_settings(chat_id)
    watches = service.list_watches(chat_id, status="watching")
    interval = service.get_recommended_poll_interval(default_normal=15.0, default_fast=10.0)

    lines = [
        "🔴 *Estado Live Watch*",
        f"⏱️ Próximo intervalo estimado: `{int(interval)}s`",
        f"⚽ Goles: {'on' if settings.alert_goals else 'off'} · 🟥 Rojas: {'on' if settings.alert_red_cards else 'off'} · 🟨 Amarillas: {'on' if settings.alert_yellow_cards else 'off'}",
        "",
    ]
    if not watches:
        lines.append("No tenés partidos activos en vigilancia.")
        await _reply_text_chunks(update.message, "\n".join(lines), parse_mode="Markdown")
        return

    lines.append(f"👁️ Activos: `{len(watches)}`")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    for entry in watches[:25]:
        disp_id = entry.chat_local_id if entry.chat_local_id is not None else entry.id
        hint = f" ({entry.league_hint})" if entry.league_hint else ""
        lines.append(f"*#{disp_id}* · `{entry.home}` vs `{entry.away}`{hint}")
        state = entry.live_state
        if state:
            for platform, payload in state.items():
                if str(platform).startswith("_"):
                    continue
                if not isinstance(payload, dict):
                    continue
                score = "-"
                if payload.get("home_score") is not None and payload.get("away_score") is not None:
                    score = f"{payload.get('home_score')}-{payload.get('away_score')}"
                minute = payload.get("minute") or "live"
                reds = ""
                if payload.get("home_red_cards") is not None or payload.get("away_red_cards") is not None:
                    reds = f" · 🟥 {payload.get('home_red_cards') or 0}/{payload.get('away_red_cards') or 0}"
                lines.append(f"   🏦 `{platform.replace('_http', '')}` · `{minute}` · `{score}`{reds}")
        else:
            lines.append("   Sin live detectado todavía.")
    if len(watches) > 25:
        lines.append(f"\nMostrando 25 de {len(watches)}.")

    lines.append("\nConfigurar: `/live_settings goals off`, `/live_settings reds off`, `/live_settings all on`")
    await _reply_text_chunks(update.message, "\n".join(lines), parse_mode="Markdown")


async def live_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View or update per-chat live alert switches."""

    if update.message is None or update.effective_chat is None:
        return

    service = get_live_watch_service(context)
    chat_id = update.effective_chat.id
    args = [arg.strip().lower() for arg in context.args if arg.strip()]

    if not args:
        settings = service.get_alert_settings(chat_id)
        await update.message.reply_text(_format_live_settings(settings))
        return

    if len(args) < 2:
        await update.message.reply_text(
            "Uso: /live_settings <goals|reds|yellows|all> <on|off>\n"
            "Ejemplos: /live_settings goals off · /live_settings reds on"
        )
        return

    target = args[0]
    value = _parse_live_setting_bool(args[1])
    if value is None:
        await update.message.reply_text("Valor inválido. Usá on/off, si/no, true/false o 1/0.")
        return

    kwargs: dict[str, bool] = {}
    if target in ("goals", "goles", "goal"):
        kwargs["alert_goals"] = value
    elif target in ("reds", "rojas", "red", "red_cards"):
        kwargs["alert_red_cards"] = value
    elif target in ("yellows", "amarillas", "yellow", "yellow_cards"):
        kwargs["alert_yellow_cards"] = value
    elif target in ("all", "todo", "todos"):
        kwargs["alert_goals"] = value
        kwargs["alert_red_cards"] = value
        kwargs["alert_yellow_cards"] = value
    else:
        await update.message.reply_text("Target inválido. Usá goals, reds, yellows o all.")
        return

    settings = service.update_alert_settings(chat_id, **kwargs)
    await update.message.reply_text(_format_live_settings(settings))


def _parse_live_setting_bool(raw: str) -> bool | None:
    normalized = raw.strip().lower()
    if normalized in ("on", "si", "sí", "yes", "true", "1", "activar", "activa"):
        return True
    if normalized in ("off", "no", "false", "0", "desactivar", "desactiva"):
        return False
    return None


def _format_live_settings(settings) -> str:
    return (
        "⚙️ Configuración live\n\n"
        f"⚽ Goles: {'on' if settings.alert_goals else 'off'}\n"
        f"🟥 Rojas: {'on' if settings.alert_red_cards else 'off'}\n"
        f"🟨 Amarillas: {'on' if settings.alert_yellow_cards else 'off'}\n\n"
        "Cambiar:\n"
        "/live_settings goals off\n"
        "/live_settings reds on\n"
        "/live_settings all on"
    )


def _format_live_state_report(
    home: str,
    away: str,
    league_hint: str | None,
    minute: str | None,
    home_score: int | None,
    away_score: int | None,
    home_red_cards: int | None,
    away_red_cards: int | None,
    home_yellow_cards: int | None,
    away_yellow_cards: int | None,
    live_stats: dict[str, Any],
    odds: dict[str, Any] | None,
    platform: str
) -> str:
    platform_lbl = platform.replace("_http", "").upper()
    lines = [
        f"🔴 *EN VIVO ({platform_lbl})*",
        f"⚽ *{home} vs {away}*",
    ]
    if league_hint:
        lines.append(f"🏆 Liga: {league_hint}")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    
    clock_str = minute or "en juego"
    if home_score is not None and away_score is not None:
        clock_str += f"  |  Marcador: *{home_score}-{away_score}*"
    lines.append(f"⏱️ Estado: {clock_str}")
    
    card_parts = []
    card_parts.append(f"🟥 Rojas: {home_red_cards or 0} / {away_red_cards or 0}")
    card_parts.append(f"🟨 Amarillas: {home_yellow_cards or 0} / {away_yellow_cards or 0}")
    lines.append(" ".join(card_parts))
    lines.append("")
    
    # Stats
    has_stats = False
    stats_lines = ["📊 *Estadísticas:*"]
    labels = [
        ("Posesión", "possession_home", "possession_away", "%"),
        ("Ataques", "attacks_home", "attacks_away", ""),
        ("Ataques peligrosos", "dangerous_attacks_home", "dangerous_attacks_away", ""),
        ("Tiros al arco", "shots_on_target_home", "shots_on_target_away", ""),
        ("Corners", "corners_home", "corners_away", ""),
    ]
    for label, home_key, away_key, suffix in labels:
        h_val = live_stats.get(home_key)
        a_val = live_stats.get(away_key)
        if h_val is not None or a_val is not None:
            has_stats = True
            h_str = f"{h_val}{suffix}" if h_val is not None else "-"
            a_str = f"{a_val}{suffix}" if a_val is not None else "-"
            stats_lines.append(f"• {label}: {h_str} vs {a_str}")
            
    if has_stats:
        lines.extend(stats_lines)
        lines.append("")
        
    # Odds
    if odds:
        o_h = odds.get("home")
        o_d = odds.get("draw")
        o_a = odds.get("away")
        h_str = f"{o_h:.2f}" if o_h is not None else "-"
        d_str = f"{o_d:.2f}" if o_d is not None else "-"
        a_str = f"{o_a:.2f}" if o_a is not None else "-"
        lines.append(f"💰 *Odds (1X2):* 1={h_str} | X={d_str} | 2={a_str}")
        
    return "\n".join(lines)


def format_watch_entry_report(entry, real_time_event=None) -> str:
    from core.models import LiveEventSnapshot
    if real_time_event and isinstance(real_time_event, LiveEventSnapshot):
        odds_dict = None
        if real_time_event.odds_1x2:
            odds_dict = {
                "home": real_time_event.odds_1x2.home,
                "draw": real_time_event.odds_1x2.draw,
                "away": real_time_event.odds_1x2.away,
            }
        return _format_live_state_report(
            home=real_time_event.home,
            away=real_time_event.away,
            league_hint=entry.league_hint,
            minute=real_time_event.minute,
            home_score=real_time_event.home_score,
            away_score=real_time_event.away_score,
            home_red_cards=real_time_event.home_red_cards,
            away_red_cards=real_time_event.away_red_cards,
            home_yellow_cards=real_time_event.home_yellow_cards,
            away_yellow_cards=real_time_event.away_yellow_cards,
            live_stats=real_time_event.live_stats or {},
            odds=odds_dict,
            platform=real_time_event.platform
        )
        
    state = entry.live_state
    if not state:
        return (
            f"⏳ *{entry.home} vs {entry.away}*\n"
            "El partido está en vigilancia pero todavía no fue detectado en vivo en ninguna plataforma."
        )
        
    reports = []
    for platform, payload in state.items():
        if platform.startswith("_"):
            continue
        if not isinstance(payload, dict):
            continue
        reports.append(
            _format_live_state_report(
                home=payload.get("home", entry.home),
                away=payload.get("away", entry.away),
                league_hint=entry.league_hint,
                minute=payload.get("minute"),
                home_score=payload.get("home_score"),
                away_score=payload.get("away_score"),
                home_red_cards=payload.get("home_red_cards"),
                away_red_cards=payload.get("away_red_cards"),
                home_yellow_cards=payload.get("home_yellow_cards"),
                away_yellow_cards=payload.get("away_yellow_cards"),
                live_stats=payload.get("live_stats") or {},
                odds=payload.get("odds"),
                platform=platform
            )
        )
        
    if not reports:
        return (
            f"⏳ *{entry.home} vs {entry.away}*\n"
            "El partido está en vigilancia pero todavía no tiene estadísticas registradas."
        )
        
    return "\n\n".join(reports)


async def view_match_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /view_match [id]: Show live stats, cards, minute, and live odds for a watched match."""
    if update.message is None or update.effective_chat is None:
        return

    usage_guide = (
        "❌ *ID de partido ausente o inválido.*\n\n"
        "Uso: `/view_match [ID]`\n"
        "Podés usar los IDs que figuran en `/watching` (por ejemplo, `#5` o el ID de base de datos).\n\n"
        "Ejemplos:\n"
        "• `/view_match 5`\n"
        "• `/view_match 123`"
    )

    if not context.args:
        await update.message.reply_text(usage_guide, parse_mode="Markdown")
        return

    arg = context.args[0].strip().replace("#", "")
    if not arg.isdigit():
        await update.message.reply_text(usage_guide, parse_mode="Markdown")
        return

    target_id = int(arg)
    chat_id = update.effective_chat.id
    service = get_live_watch_service(context)

    # Try to load watch entry
    entry = None
    if hasattr(service.repository, "get_live_watch_by_local_id"):
        entry = service.repository.get_live_watch_by_local_id(chat_id, target_id)
    if entry is None:
        if hasattr(service.repository, "get_live_watch"):
            entry = service.repository.get_live_watch(chat_id, target_id)

    if entry is None:
        await update.message.reply_text(
            f"❌ No encontré ningún partido en vigilancia con el ID `#{target_id}` en este chat.\n"
            "Corré `/watching` para ver tus partidos activos."
        )
        return

    loading_msg = await update.message.reply_text(
        f"🔍 Buscando estadísticas en vivo en tiempo real para *{entry.home} vs {entry.away}*..."
    )

    try:
        # Fetch current live events from extractors to see if it is playing right now
        live_events = await service.collect_live_events()
        
        # Search for best match in live events
        best_match = service._best_match(entry, live_events) if live_events else None
        
        if best_match is not None:
            score, event = best_match
            from monitors.live_watch import _event_live_state
            current_state = _event_live_state(event)
            service.repository.update_live_watch_platform_state(
                entry.id,
                platform=event.platform,
                state=current_state,
            )
            
            # Use the real-time event
            report = format_watch_entry_report(entry, real_time_event=event)
        else:
            # Not found in active live events, fall back to DB live_state
            report = format_watch_entry_report(entry, real_time_event=None)
            
        await loading_msg.delete()
        await _reply_text_chunks(update.message, report, parse_mode="Markdown")
        
    except Exception as e:
        logger.exception("Error in /view_match command")
        await loading_msg.edit_text(f"❌ Error al consultar estadísticas en vivo: {str(e)}")


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


async def help_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/help_stats` command."""
    del context
    if update.message:
        await update.message.reply_text(HELP_STATS_MESSAGE, parse_mode=ParseMode.HTML)


async def help_leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/help_leagues` command."""
    del context
    if update.message:
        await update.message.reply_text(HELP_LEAGUES_MESSAGE, parse_mode=ParseMode.HTML)


async def guide_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the `/guide` command."""

    del context

    if update.message is None:
        return

    await update.message.reply_text(GUIDE_MESSAGE, parse_mode=ParseMode.HTML)


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
    for provider in stats_provider_registry.providers:
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


async def _send_unified_stats_report(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    match_group: list[ActiveEventRecord],
    league_name: str,
    provider_filter: str | None = None,
) -> None:
    """Send the cross-book card (qué casas lo tienen + odds) and the stats report."""

    from bot.alerts import build_comparison_match_card_message

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

    from bot.alerts import group_events_by_physical_match

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

    from bot.alerts import build_comparison_match_card_message

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


_EXPLORE_MENU_LABELS = [
    "📊 Tabla de posiciones",
    "🗓️ Próximos partidos",
    "👟 Goleadores",
    "⚽ Buscar un equipo",
    "🔗 Link al proveedor",
    "📋 Elegir partido y reporte",
]


def _explore_menu_keyboard():
    """Inline keyboard for the /explore_stats menu (index ``i`` = option ``i+1``)."""

    return _build_choice_keyboard(_EXPLORE_MENU_LABELS, "exp_menu")


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
    result = tracking_service.build_competition_url_message(
        update.effective_chat.id,
        track_number,
    )

    await _reply_text_chunks(update.message, result.message, parse_mode=ParseMode.HTML)


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
            await tracking_service.dispatch_notifications(
                context.bot,
                summary,
                notify_failures=True,
                force_unavailable_warnings=True,
                unavailable_warning_chat_id=update.effective_chat.id,
            )
            summary_result = tracking_service.build_refresh_summary_message(summary)
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
    from bot.alerts import build_grouped_event_url_message

    message = build_grouped_event_url_message(group)
    if not message:
        await update.message.reply_text("No encontré URLs para ese partido.")
        return

    await _reply_text_chunks(update.message, message, parse_mode=ParseMode.HTML)


def _build_unified_league_selection_message(prompt: str, leagues: list[dict[str, Any]]) -> str:
    # Options are shown as inline buttons; the message is just the prompt.
    return prompt


def _build_grouped_match_selection_message(
    unified_league_name: str,
    grouped_matches: list[list[ActiveEventRecord]],
) -> str:
    """Build the second prompt used by `/matches` for unified leagues."""

    return f"¿Qué partido querés ver de {unified_league_name}?"


def _build_unified_stats_match_selection_message(
    unified_league_name: str,
    grouped_matches: list[list[ActiveEventRecord]],
) -> str:
    """Stats match picker: union of matches across books, with the books per row."""

    return f"¿De qué partido de {unified_league_name} querés ver stats?"


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
                from bot.alerts import group_events_by_physical_match
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

    from bot.alerts import group_events_by_physical_match
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
        from bot.alerts import build_comparison_match_card_message
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
        from bot.alerts import build_comparison_match_card_message
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


def _build_track_selection_message(prompt: str, tracks: list[TrackedCompetitionSubscription]) -> str:
    """Build a league-selection prompt (options rendered as inline buttons)."""

    return prompt


def _build_discovery_platform_selection_message(platforms: list[PlatformDescriptor]) -> str:
    """Build the platform prompt for `/track_league`."""

    return "¿Qué plataforma querés usar para buscar ligas?"


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


def _build_discovered_league_selection_message(options: list[LeagueDiscoveryOption]) -> str:
    """Build the league prompt for `/track_league`."""

    return "Elegí la liga a trackear:"


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


def _build_provider_fixture_selection_message(fixtures: list) -> str:
    """Build the provider-native fixture prompt used by `/explore_stats`."""

    return "Elegí el partido para generar reporte:"


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


def _selection_target(update: Update) -> Message | None:
    """Return the message to reply to, whether from an inline button or text."""

    query = getattr(update, "callback_query", None)
    if query is not None:
        return query.message
    return update.message


def _match_choice_keyboard(grouped_matches):
    """Inline keyboard for /matches: a 'Ver todos' button + one per match.

    Index 0 is "Ver todos"; index ``i`` (>=1) is ``grouped_matches[i-1]`` — the
    same mapping the legacy numeric keyboard used (number 1 = all).
    """

    labels = ["📋 Ver todos"] + [f"{g[0].home} vs {g[0].away}" for g in grouped_matches]
    return _build_choice_keyboard(labels, "mx_match")


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


def _convert_fin_to_arg_datetime(date_str: str | None, time_str: str | None) -> tuple[str, str]:
    """Convert Finnish match date & time (Europe/Helsinki) to Argentina (America/Argentina/Buenos_Aires) date & time."""
    if not time_str:
        return date_str or "N/A", "N/A"
    if not date_str or date_str == "N/A":
        from datetime import date
        date_str = date.today().isoformat()
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        time_str = str(time_str).strip()
        time_parts = time_str.split(":")
        if len(time_parts) < 2:
            return date_str, time_str
        hour = int(time_parts[0])
        minute = int(time_parts[1])
        second = int(time_parts[2]) if len(time_parts) > 2 else 0
        date_parts = str(date_str).strip().split("-")
        if len(date_parts) != 3:
            return date_str, time_str
        year = int(date_parts[0])
        month = int(date_parts[1])
        day = int(date_parts[2])
        helsinki_dt = datetime(year, month, day, hour, minute, second, tzinfo=ZoneInfo("Europe/Helsinki"))
        arg_dt = helsinki_dt.astimezone(ZoneInfo("America/Argentina/Buenos_Aires"))
        return arg_dt.strftime("%Y-%m-%d"), arg_dt.strftime("%H:%M")
    except Exception:
        return date_str, time_str


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

_FIN_LEAGUE_USAGE = (
    "💡 Mirá todos los códigos con `/fin_leagues`.\n"
    "Ejemplos: `VL` Veikkausliiga · `M1` Ykkönen · `M3` Kolmonen · `MSC` Suomen Cup."
)


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
def _finland_adapter():
    from bot.special_leagues import FinlandLeagues
    from stats_providers.palloliitto.api_client import PalloliittoAPI
    return FinlandLeagues(PalloliittoAPI())


def _sweden_adapter():
    from bot.special_leagues import SwedenLeagues
    from stats_providers.svenskfotboll_http.client import SvenskfotbollHTTPClient
    return SwedenLeagues(SvenskfotbollHTTPClient(), _SWE_LEAGUES)


def _romania_adapter():
    from bot.special_leagues import RomaniaLeagues
    from stats_providers.romania_http.client import RomaniaFRFHTTPClient
    return RomaniaLeagues(RomaniaFRFHTTPClient())


def _slovakia_adapter():
    from bot.special_leagues import SlovakiaLeagues
    from stats_providers.slovakia_http.client import SlovakSportnetHTTPClient
    return SlovakiaLeagues(SlovakSportnetHTTPClient())


def _algeria_adapter():
    from bot.special_leagues import AlgeriaLeagues
    from stats_providers.algeria_http.client import AlgeriaLNFFHTTPClient
    return AlgeriaLeagues(AlgeriaLNFFHTTPClient())


def _norway_adapter():
    from bot.special_leagues import NorwayLeagues
    from stats_providers.norway_http.client import NorwayNFFHTTPClient
    return NorwayLeagues(NorwayNFFHTTPClient())


async def _run_special_leagues(message, adapter) -> None:
    import asyncio
    from bot.special_leagues import render_leagues
    try:
        leagues = await asyncio.to_thread(adapter.leagues)
        await _reply_text_chunks(message, render_leagues(adapter, leagues), parse_mode="Markdown")
    except Exception as e:  # noqa: BLE001
        logger.exception("special leagues failed")
        await message.reply_text(f"❌ Error al recuperar las ligas: {e}")
    finally:
        adapter.close()


async def _run_special_today(message, args, adapter) -> None:
    import asyncio
    from datetime import date
    from bot.special_leagues import render_today
    today_str = date.today().isoformat()
    await message.reply_text(f"⚽ Consultando partidos de hoy ({today_str})...")
    try:
        rows, omitted = await asyncio.to_thread(adapter.today)
        selected = args[0] if args else None
        await _reply_text_chunks(message, render_today(adapter, rows, omitted, today_str, selected), parse_mode="Markdown")
    except Exception as e:  # noqa: BLE001
        logger.exception("special today failed")
        await message.reply_text(f"❌ Error al consultar partidos de hoy: {e}")
    finally:
        adapter.close()


async def _run_special_standings(message, args, adapter, usage: str) -> None:
    import asyncio
    from bot.special_leagues import render_standings
    if not args:
        await message.reply_text(usage, parse_mode="Markdown")
        adapter.close()
        return
    code = args[0].upper()
    await message.reply_text("📊 Cargando tabla de posiciones de la federación...")
    try:
        result = await asyncio.to_thread(adapter.standings, code)
        await _reply_text_chunks(message, render_standings(adapter, code, result), parse_mode="Markdown")
    except Exception as e:  # noqa: BLE001
        logger.exception("special standings failed")
        await message.reply_text(f"❌ Error al consultar posiciones: {e}")
    finally:
        adapter.close()


async def _run_special_fixtures(message, args, adapter, usage: str, *, results: bool = False) -> None:
    import asyncio
    from bot.special_leagues import render_fixtures
    if not args:
        await message.reply_text(usage, parse_mode="Markdown")
        adapter.close()
        return
    code = args[0].upper()
    await message.reply_text("🗓️ Consultando partidos...")
    try:
        fetch = adapter.results if (results and hasattr(adapter, "results")) else adapter.fixtures
        name, rows = await asyncio.to_thread(fetch, code)
        header = "Resultados" if results else "Fixture"
        await _reply_text_chunks(message, render_fixtures(adapter, code, name, rows, header=header), parse_mode="Markdown")
    except Exception as e:  # noqa: BLE001
        logger.exception("special fixtures failed")
        await message.reply_text(f"❌ Error al consultar partidos: {e}")
    finally:
        adapter.close()


async def _run_special_match(message, args, adapter, usage: str) -> None:
    import asyncio
    if not args:
        await message.reply_text(usage, parse_mode="Markdown")
        adapter.close()
        return
    match_id = args[0].strip()
    await message.reply_text("🔍 Recuperando datos detallados de alineación y estadísticas...")
    try:
        report = await asyncio.to_thread(adapter.match_report, match_id)
        await _reply_text_chunks(message, report, parse_mode="Markdown")
    except Exception as e:  # noqa: BLE001
        logger.exception("special match failed")
        await message.reply_text(f"❌ Error al generar reporte del partido: {e}")
    finally:
        adapter.close()



async def fin_leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /fin_leagues: List Finnish leagues hierarchy."""
    del context
    if update.message is None:
        return
    await _run_special_leagues(update.message, _finland_adapter())


async def fin_standings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /fin_standings [CÓDIGO]: standings for a Finnish league."""
    if update.message is None:
        return
    usage = (
        "❌ *Falta el código de liga.*\n\nUso: `/fin_standings [CÓDIGO_LIGA]`\n\n"
        + _FIN_LEAGUE_USAGE + "\n\nEjemplo: `/fin_standings VL`"
    )
    await _run_special_standings(update.message, (getattr(context, 'args', None) or []), _finland_adapter(), usage)


async def fin_fixtures_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /fin_fixtures [league_id]: Display recent/upcoming fixtures."""
    if update.message is None:
        return

    usage = (
        "❌ *Falta el código de liga.*\n\nUso: `/fin_fixtures [CÓDIGO_LIGA]`\n\n"
        + _FIN_LEAGUE_USAGE + "\n\nEjemplo: `/fin_fixtures VL`"
    )
    await _run_special_fixtures(update.message, (getattr(context, 'args', None) or []), _finland_adapter(), usage)


async def fin_today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /fin_today: today's senior matches (menu or per-league)."""
    if update.message is None:
        return
    await _run_special_today(update.message, (getattr(context, 'args', None) or []), _finland_adapter())


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


async def fin_match_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /fin_match [match_id]: Lineups, scores, cards, and starting regularity analysis (Value bet detector)."""
    if update.message is None:
        return

    usage_guide = (
        "❌ *ID de partido ausente o inválido.*\n\n"
        "Uso: `/fin_match [ID_PARTIDO]`\n\n"
        "💡 *¿Cómo conseguir el ID?*\n"
        "• Corré `/fin_today` para ver los partidos de hoy.\n"
        "• Corré `/fin_fixtures [LIGA]` para ver fixtures de una liga.\n\n"
        "Ejemplo: `/fin_match 4036852`"
    )
    await _run_special_match(update.message, (getattr(context, 'args', None) or []), _finland_adapter(), usage_guide)


def _calculate_rotation_for_team(api: PalloliittoAPI, home_name: str, team_id: str, primary_category: str, competition_id: str, starters: list, target_match_id: str) -> str:
    """Calculate regularity ratio of current lineup compared to the last 3 league games."""
    if not starters:
        return "⚠️ Sin datos de jugadores iniciales."
        
    try:
        league_matches = api.get_matches_by_league(competition_id, primary_category)
    except Exception:
        return "⚠️ No se pudieron cargar partidos de liga recientes para comparar."
        
    # Find recent played league matches for this team (exclude today's match itself)
    recent_matches = []
    for m in league_matches:
        m_id = str(m.get("match_id"))
        if m_id == str(target_match_id):
            continue
        if m.get("status") in ["Finished", "Played"] and m.get("walkover") != 1:
            if str(m.get("team_A_id")) == str(team_id) or str(m.get("team_B_id")) == str(team_id):
                recent_matches.append(m)
                
    recent_matches.sort(key=lambda x: x.get("date", ""), reverse=True)
    recent_matches = recent_matches[:3]
    
    if not recent_matches:
        return "✅ *100% regularidad estimada* (sin partidos de liga previos para comparar)."
        
    starter_counts = {}
    for rm in recent_matches:
        rm_id = rm.get("match_id")
        details = api.get_match_details(rm_id)
        if details:
            rm_lineup = details.get("lineups", [])
            for p in rm_lineup:
                if str(p.get("team_id")) == str(team_id) and p.get("start") == "1":
                    p_id = p.get("player_id")
                    starter_counts[p_id] = starter_counts.get(p_id, 0) + 1
                    
    min_starts = max(1, len(recent_matches) // 2 + (1 if len(recent_matches) % 2 != 0 else 0))
    regular_starter_ids = {p_id for p_id, count in starter_counts.items() if count >= min_starts}
    
    current_starter_ids = {p.get("player_id") for p in starters}
    matching_starters = current_starter_ids & regular_starter_ids
    
    regularity_ratio = len(matching_starters) / 11 if len(matching_starters) <= 11 else len(matching_starters) / len(starters)
    
    if regularity_ratio >= 0.70:
        return f"✅ *Regularidad: {regularity_ratio:.0%}* (Titulares habituales de liga. Juegan con el A-Team)."
    elif regularity_ratio >= 0.45:
        return f"⚠️ *Regularidad: {regularity_ratio:.0%}* (Rotación moderada/parcial. Algunos suplentes)."
    else:
        # Mass rotation!
        non_regulars = [p for p in starters if p.get("player_id") not in regular_starter_ids]
        non_regulars_str = ", ".join(f"{p.get('shirt_number')} {p.get('player_name')}" for p in non_regulars[:3])
        return (
            f"🚨 *Regularidad: {regularity_ratio:.0%}* (¡ROTACIÓN MASIVA / B-TEAM! Juegan suplentes).\n"
            f"   Nuevos titulares hoy: {non_regulars_str}..."
        )


async def fin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /fin_help: Document and guide the user on using the Finland Federation integration."""
    del context
    if update.message is None:
        return

    help_text = (
        "🇫🇮 <b>Guía de Estadísticas de la Federación de Finlandia</b> 🇫🇮\n\n"
        "Este módulo te permite consultar estadísticas oficiales directo de la Asociación de Fútbol de Finlandia "
        "(<code>tulospalvelu.palloliitto.fi</code>). Estas ligas de ascenso y copas no suelen figurar en sitios comunes "
        "de estadísticas, lo cual genera grandes oportunidades de valor.\n\n"
        "📖 <b>Comandos disponibles:</b>\n"
        "• <code>/fin_leagues</code> - Muestra la jerarquía oficial (escalafón) de ligas masculinas, femeninas y copas.\n"
        "• <code>/fin_today</code> - Lista los partidos programados para hoy en las categorías principales con sus IDs.\n"
        "• <code>/fin_standings [CÓDIGO]</code> - Muestra la tabla de posiciones actual de una liga (Ej: <code>/fin_standings VL</code>).\n"
        "• <code>/fin_fixtures [CÓDIGO]</code> - Muestra el calendario de partidos recientes y próximos de una liga y sus IDs.\n"
        "• <code>/fin_match [ID_PARTIDO]</code> - Muestra detalles de un partido (goles, tarjetas, alineaciones) y corre el "
        "<b>Análisis de Rotación de Alineación (Detector de Suplentes / B-Team)</b>.\n\n"
        "🔍 <b>¿Cómo funciona el Detector de Suplentes / B-Team?</b>\n"
        "En los partidos de copa (como la <i>Suomen Cup</i>) o en fechas de rotación, los equipos de divisiones superiores "
        "suelen alinear reservas, juveniles o un equipo 'B'.\n"
        "El comando <code>/fin_match [ID_PARTIDO]</code> analiza los titulares de hoy y los compara con los últimos 3 partidos "
        "de liga del equipo, calculando un <b>Ratio de Regularidad</b>:\n"
        "  🟢 <b>&gt;= 70%</b>: Juegan los titulares habituales (A-Team).\n"
        "  🟡 <b>45% - 69%</b>: Rotación parcial o moderada.\n"
        "  🚨 <b>&lt; 45%</b>: <b>¡ROTACIÓN MASIVA / B-TEAM!</b> Juegan suplentes.\n\n"
        "💡 <b>Flujo de Análisis Recomendado:</b>\n"
        "1️⃣ Corré <code>/fin_today</code> para ver qué partidos hay programados para hoy.\n"
        "2️⃣ Si ves un partido interesante (por ejemplo, un equipo de división alta contra uno de división baja en Suomen Cup), "
        "esperá a que falte 1 hora para el partido (cuando se cargan las alineaciones oficiales).\n"
        "3️⃣ Corré <code>/fin_match [ID_PARTIDO]</code>.\n"
        "4️⃣ Si detectás un ratio de regularidad muy bajo (🚨 &lt; 45%) para el equipo favorito, las cuotas del casino suelen "
        "estar desajustadas basándose en el poder del A-Team. ¡Esto te permite tomar apuestas de valor antes de que "
        "las cuotas se desplomen!"
    )

    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


# ===================== Svenskfotboll (Swedish FA) commands =====================
# Mirrors the Finland (/fin_*) integration: standalone commands backed by the
# Swedish FA's HTTP feeds (svenskfotboll.se / FOGIS). 2026-season competition ids.
_SWE_LEAGUES: dict[str, tuple[str, str, str]] = {
    "AL": ("133348", "Allsvenskan", "Tier 1 · Varones"),
    "SE": ("133340", "Superettan", "Tier 2 · Varones"),
    "EN": ("133338", "Ettan Norra", "Tier 3 · Varones"),
    "ES": ("133339", "Ettan Södra", "Tier 3 · Varones"),
    "DA": ("133440", "OBOS Damallsvenskan", "Tier 1 · Damas"),
    "EE": ("133439", "Elitettan", "Tier 2 · Damas"),
}


def _resolve_swe_league(code: str) -> tuple[str, str, str] | None:
    """Resolve a short league code to (competition_id, name, tier_label)."""

    return _SWE_LEAGUES.get((code or "").strip().upper())


def _swe_resolve_comp_for_teams(client, home: str, away: str) -> str | None:
    """Find which tracked Swedish competition has BOTH teams (for analytics).

    The /swe_match endpoint only gives team names, not a league id, so we scan
    the known leagues' standings and match by normalised team name.
    """

    from monitors.special_peak import _norm_team

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


def _convert_swe_to_arg_datetime(local_dt: str | None) -> tuple[str, str]:
    """Convert a Swedish local datetime ('YYYY-MM-DD[ T]HH:MM[:SS]') to Argentina."""

    if not local_dt:
        return "N/A", "N/A"
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        text = str(local_dt).strip().replace("T", " ")
        parts = text.split(" ")
        date_part = parts[0]
        time_part = parts[1] if len(parts) > 1 else "00:00"
        y, m, d = (int(x) for x in date_part.split("-"))
        tp = time_part.split(":")
        hh, mm = int(tp[0]), int(tp[1])
        ss = int(tp[2]) if len(tp) > 2 else 0
        swe = datetime(y, m, d, hh, mm, ss, tzinfo=ZoneInfo("Europe/Stockholm"))
        arg = swe.astimezone(ZoneInfo("America/Argentina/Buenos_Aires"))
        return arg.strftime("%Y-%m-%d"), arg.strftime("%H:%M")
    except Exception:
        return str(local_dt), "N/A"


def _swe_usage_guide(as_html: bool = False) -> str:
    if as_html:
        lines = ["💡 <b>Ligas disponibles (código):</b>"]
        for code, (_cid, name, tier) in _SWE_LEAGUES.items():
            lines.append(f"• <code>{code}</code> - {name} ({tier})")
        lines.append("\nEjemplo: <code>/swe_standings AL</code>")
        return "\n".join(lines)
    else:
        lines = ["💡 *Ligas disponibles (código):*"]
        for code, (_cid, name, tier) in _SWE_LEAGUES.items():
            lines.append(f"• `{code}` - {name} ({tier})")
        lines.append("\nEjemplo: `/swe_standings AL`")
        return "\n".join(lines)


_RO_LEAGUE_USAGE = "Escribí `/ro_standings [CÓDIGO]` o `/ro_fixtures [CÓDIGO]` con uno de estos códigos:\n- `RO1` (SuperLiga Feminină)\n- `RO1PO` (SuperLiga Play-off)\n- `RO1PL` (SuperLiga Play-out)\n- `RO2S1` (Liga 2 Seria 1)\n- `RO2S2` (Liga 2 Seria 2)"


async def ro_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ro_help: Display help for Romanian leagues."""
    del context
    if update.message is None:
        return
    help_text = (
        "🇷🇴 *Guía de Estadísticas de la Federación de Rumania* 🇷🇴\n\n"
        "Comandos disponibles:\n"
        "• `/ro_leagues` - Muestra la jerarquía de ligas y códigos\n"
        "• `/ro_standings [CÓDIGO]` - Tabla de posiciones actual\n"
        "• `/ro_fixtures [CÓDIGO]` - Calendario de partidos recientes/próximos\n"
        "• `/ro_today` - Partidos programados para hoy\n\n"
        + _RO_LEAGUE_USAGE
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def ro_leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ro_leagues: list Romanian leagues."""
    del context
    if update.message is None:
        return
    await _run_special_leagues(update.message, _romania_adapter())


async def ro_standings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ro_standings [CÓDIGO]: standings for a Romanian league."""
    if update.message is None:
        return
    usage = (
        "❌ *Falta el código de liga.*\n\nUso: `/ro_standings [CÓDIGO_LIGA]`\n\n"
        + _RO_LEAGUE_USAGE + "\n\nEjemplo: `/ro_standings RO2S1`"
    )
    await _run_special_standings(update.message, (getattr(context, 'args', None) or []), _romania_adapter(), usage)


async def ro_fixtures_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ro_fixtures [CÓDIGO]: Display recent/upcoming fixtures."""
    if update.message is None:
        return
    usage = (
        "❌ *Falta el código de liga.*\n\nUso: `/ro_fixtures [CÓDIGO_LIGA]`\n\n"
        + _RO_LEAGUE_USAGE + "\n\nEjemplo: `/ro_fixtures RO2S1`"
    )
    await _run_special_fixtures(update.message, (getattr(context, 'args', None) or []), _romania_adapter(), usage)


async def ro_today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ro_today: today's matches."""
    if update.message is None:
        return
    await _run_special_today(update.message, (getattr(context, 'args', None) or []), _romania_adapter())


async def ro_match_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ro_match [match_id]: details for a match (score, events, form, stats)."""
    if update.message is None:
        return
    usage_guide = (
        "❌ *ID de partido ausente o inválido.*\n\n"
        "Uso: `/ro_match [ID_PARTIDO]`\n\n"
        "💡 *¿Cómo conseguir el ID?*\n"
        "• Corré `/ro_today` para ver los partidos de hoy.\n"
        "• Corré `/ro_fixtures [LIGA]` para ver fixtures de una liga."
    )
    await _run_special_match(update.message, (getattr(context, 'args', None) or []), _romania_adapter(), usage_guide)


async def swe_leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /swe_leagues: list Swedish leagues."""
    del context
    if update.message is None:
        return
    await _run_special_leagues(update.message, _sweden_adapter())


async def swe_standings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /swe_standings [CODE]: standings for a Swedish league."""
    if update.message is None:
        return
    usage = "❌ *Falta el código de liga.*\n\nUso: `/swe_standings [CÓDIGO]`\n\n💡 Mirá los códigos con `/swe_leagues`."
    await _run_special_standings(update.message, (getattr(context, 'args', None) or []), _sweden_adapter(), usage)


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


async def swe_fixtures_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /swe_fixtures [CODE]: upcoming matches for a Swedish league."""
    if update.message is None:
        return
    usage = "❌ *Falta el código de liga.*\n\nUso: `/swe_fixtures [CÓDIGO]`\n\n💡 Mirá los códigos con `/swe_leagues`."
    await _run_special_fixtures(update.message, (getattr(context, 'args', None) or []), _sweden_adapter(), usage)


async def swe_results_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /swe_results [CODE]: latest results for a Swedish league."""
    if update.message is None:
        return
    usage = "❌ *Falta el código de liga.*\n\nUso: `/swe_results [CÓDIGO]`\n\n💡 Mirá los códigos con `/swe_leagues`."
    await _run_special_fixtures(update.message, (getattr(context, 'args', None) or []), _sweden_adapter(), usage, results=True)


async def swe_today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /swe_today: today's senior Swedish matches (menu or per-league)."""
    if update.message is None:
        return
    await _run_special_today(update.message, (getattr(context, 'args', None) or []), _sweden_adapter())


async def swe_match_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /swe_match [ID]: live/FOGIS detail for one match (score, events, form, stats)."""
    if update.message is None:
        return
    usage_guide = (
        "❌ *ID de partido ausente o inválido.*\n\n"
        "Uso: `/swe_match [ID_PARTIDO]`\n\n"
        "💡 *¿Cómo conseguir el ID?*\n"
        "• Corré `/swe_today` para ver los partidos de hoy.\n"
        "• Corré `/swe_fixtures [LIGA]` para ver fixtures de una liga."
    )
    await _run_special_match(update.message, (getattr(context, 'args', None) or []), _sweden_adapter(), usage_guide)


async def swe_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /swe_help: guide for the Sweden federation integration."""

    del context
    if update.message is None:
        return
    help_text = (
        "🇸🇪 <b>Guía de Estadísticas de la Federación de Suecia</b> 🇸🇪\n\n"
        "Consultá datos oficiales directo de la Asociación Sueca de Fútbol (<code>svenskfotboll.se</code> / FOGIS). "
        "Incluye divisiones de ascenso que no suelen estar en sitios comunes de stats.\n\n"
        "📖 <b>Comandos:</b>\n"
        "• <code>/swe_leagues</code> - Lista las ligas mapeadas y sus códigos.\n"
        "• <code>/swe_standings [CÓDIGO]</code> - Tabla de posiciones (Ej: <code>/swe_standings AL</code>).\n"
        "• <code>/swe_fixtures [CÓDIGO]</code> - Próximos partidos de la liga (con IDs).\n"
        "• <code>/swe_results [CÓDIGO]</code> - Últimos resultados de la liga.\n"
        "• <code>/swe_today</code> - Partidos suecos de hoy (horario Argentina) con IDs.\n"
        "• <code>/swe_match [ID]</code> - Detalle/vivo de un partido (marcador, eventos vía FOGIS).\n\n"
        "🥅 <b>Copa:</b> <code>SC</code> = Svenska Cupen (varones), <code>SCD</code> = Svenska Cupen (damas). "
        "Se resuelven solas cada temporada; al ser eliminatoria, usá <code>/swe_fixtures SC</code> (no tiene tabla única).\n\n"
        + _swe_usage_guide(as_html=True)
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


_SK_LEAGUE_USAGE = "Escribí `/sk_standings [CÓDIGO]` o `/sk_fixtures [CÓDIGO]` con uno de estos códigos:\n- `SK1A` (I. Liga Ženy - Play-off)\n- `SK1B` (I. Liga Ženy - Play-out)"


async def sk_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sk_help: Display help for Slovak leagues."""
    del context
    if update.message is None:
        return
    help_text = (
        "🇸🇰 *Guía de Estadísticas de la Federación de Eslovaquia* 🇸🇰\n\n"
        "Comandos disponibles:\n"
        "• `/sk_leagues` - Muestra la jerarquía de ligas y códigos\n"
        "• `/sk_standings [CÓDIGO]` - Tabla de posiciones actual\n"
        "• `/sk_fixtures [CÓDIGO]` - Calendario de partidos recientes/próximos\n"
        "• `/sk_today` - Partidos programados para hoy\n\n"
        + _SK_LEAGUE_USAGE
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def sk_leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sk_leagues: list Slovak leagues."""
    del context
    if update.message is None:
        return
    await _run_special_leagues(update.message, _slovakia_adapter())


async def sk_standings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sk_standings [CÓDIGO]: standings for a Slovak league."""
    if update.message is None:
        return
    usage = (
        "❌ *Falta el código de liga.*\n\nUso: `/sk_standings [CÓDIGO_LIGA]`\n\n"
        + _SK_LEAGUE_USAGE + "\n\nEjemplo: `/sk_standings SK1A`"
    )
    await _run_special_standings(update.message, (getattr(context, 'args', None) or []), _slovakia_adapter(), usage)


async def sk_fixtures_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sk_fixtures [CÓDIGO]: Display recent/upcoming fixtures."""
    if update.message is None:
        return
    usage = (
        "❌ *Falta el código de liga.*\n\nUso: `/sk_fixtures [CÓDIGO_LIGA]`\n\n"
        + _SK_LEAGUE_USAGE + "\n\nEjemplo: `/sk_fixtures SK1A`"
    )
    await _run_special_fixtures(update.message, (getattr(context, 'args', None) or []), _slovakia_adapter(), usage)


async def sk_today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sk_today: today's matches."""
    if update.message is None:
        return
    await _run_special_today(update.message, (getattr(context, 'args', None) or []), _slovakia_adapter())


async def sk_match_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sk_match [match_id]: details for a match (score, lineups, events, form, stats)."""
    if update.message is None:
        return
    usage_guide = (
        "❌ *ID de partido ausente o inválido.*\n\n"
        "Uso: `/sk_match [ID_PARTIDO]`\n\n"
        "💡 *¿Cómo conseguir el ID?*\n"
        "• Corré `/sk_today` para ver los partidos de hoy.\n"
        "• Corré `/sk_fixtures [LIGA]` para ver fixtures de una liga."
    )
    await _run_special_match(update.message, (getattr(context, 'args', None) or []), _slovakia_adapter(), usage_guide)


_AL_LEAGUE_USAGE = "Escribí `/al_standings [CÓDIGO]` o `/al_fixtures [CÓDIGO]` con el código:\n- `DZ1` (D1 Seniors Damas)"


async def al_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /al_help: Display help for Algerian leagues."""
    del context
    if update.message is None:
        return
    help_text = (
        "🇩🇿 *Guía de Estadísticas de la Federación de Argelia* 🇩🇿\n\n"
        "Comandos disponibles:\n"
        "• `/al_leagues` - Muestra la jerarquía de ligas y códigos\n"
        "• `/al_standings [CÓDIGO]` - Tabla de posiciones actual (calculada en tiempo real)\n"
        "• `/al_fixtures [CÓDIGO]` - Calendario de partidos recientes/próximos\n"
        "• `/al_today` - Partidos programados para hoy\n"
        "• `/al_match [ID]` - Detalle del partido y enlace oficial\n\n"
        + _AL_LEAGUE_USAGE
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def al_leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /al_leagues: list Algerian leagues."""
    del context
    if update.message is None:
        return
    await _run_special_leagues(update.message, _algeria_adapter())


async def al_standings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /al_standings [CÓDIGO]: standings for an Algerian league."""
    if update.message is None:
        return
    usage = (
        "❌ *Falta el código de liga.*\n\nUso: `/al_standings [CÓDIGO_LIGA]`\n\n"
        + _AL_LEAGUE_USAGE + "\n\nEjemplo: `/al_standings DZ1`"
    )
    await _run_special_standings(update.message, (getattr(context, 'args', None) or []), _algeria_adapter(), usage)


async def al_fixtures_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /al_fixtures [CÓDIGO]: Display recent/upcoming fixtures."""
    if update.message is None:
        return
    usage = (
        "❌ *Falta el código de liga.*\n\nUso: `/al_fixtures [CÓDIGO_LIGA]`\n\n"
        + _AL_LEAGUE_USAGE + "\n\nEjemplo: `/al_fixtures DZ1`"
    )
    await _run_special_fixtures(update.message, (getattr(context, 'args', None) or []), _algeria_adapter(), usage)


async def al_today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /al_today: today's matches."""
    if update.message is None:
        return
    await _run_special_today(update.message, (getattr(context, 'args', None) or []), _algeria_adapter())


async def al_match_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /al_match [match_id]: details for a match (score, form, stats)."""
    if update.message is None:
        return
    usage_guide = (
        "❌ *ID de partido ausente o inválido.*\n\n"
        "Uso: `/al_match [ID_PARTIDO]`\n\n"
        "💡 *¿Cómo conseguir el ID?*\n"
        "• Corré `/al_today` para ver los partidos de hoy.\n"
        "• Corré `/al_fixtures [LIGA]` para ver fixtures de una liga."
    )
    await _run_special_match(update.message, (getattr(context, 'args', None) or []), _algeria_adapter(), usage_guide)


_NO_LEAGUE_USAGE = "Escribí `/no_standings [CÓDIGO]` o `/no_fixtures [CÓDIGO]` con el código:\n- `NO1` (Toppserien)"


async def no_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /no_help: Display help for Norwegian leagues."""
    del context
    if update.message is None:
        return
    help_text = (
        "🇳🇴 *Guía de Estadísticas de la Federación de Noruega* 🇳🇴\n\n"
        "Comandos disponibles:\n"
        "• `/no_leagues` - Muestra la jerarquía de ligas y códigos\n"
        "• `/no_standings [CÓDIGO]` - Tabla de posiciones actual\n"
        "• `/no_fixtures [CÓDIGO]` - Calendario de partidos recientes/próximos\n"
        "• `/no_today` - Partidos programados para hoy\n"
        "• `/no_match [ID]` - Detalle del partido y enlace oficial\n\n"
        + _NO_LEAGUE_USAGE
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def no_leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /no_leagues: list Norwegian leagues."""
    del context
    if update.message is None:
        return
    await _run_special_leagues(update.message, _norway_adapter())


async def no_standings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /no_standings [CÓDIGO]: standings for a Norwegian league."""
    if update.message is None:
        return
    usage = (
        "❌ *Falta el código de liga.*\n\nUso: `/no_standings [CÓDIGO_LIGA]`\n\n"
        + _NO_LEAGUE_USAGE + "\n\nEjemplo: `/no_standings NO1`"
    )
    await _run_special_standings(update.message, (getattr(context, 'args', None) or []), _norway_adapter(), usage)


async def no_fixtures_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /no_fixtures [CÓDIGO]: Display recent/upcoming fixtures."""
    if update.message is None:
        return
    usage = (
        "❌ *Falta el código de liga.*\n\nUso: `/no_fixtures [CÓDIGO_LIGA]`\n\n"
        + _NO_LEAGUE_USAGE + "\n\nEjemplo: `/no_fixtures NO1`"
    )
    await _run_special_fixtures(update.message, (getattr(context, 'args', None) or []), _norway_adapter(), usage)


async def no_today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /no_today: today's matches."""
    if update.message is None:
        return
    await _run_special_today(update.message, (getattr(context, 'args', None) or []), _norway_adapter())


async def no_match_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /no_match [match_id]: details for a match (score, lineups, events, form, stats)."""
    if update.message is None:
        return
    usage_guide = (
        "❌ *ID de partido ausente o inválido.*\n\n"
        "Uso: `/no_match [ID_PARTIDO]`\n\n"
        "💡 *¿Cómo conseguir el ID?*\n"
        "• Corré `/no_today` para ver los partidos de hoy.\n"
        "• Corré `/no_fixtures [LIGA]` para ver fixtures de una liga."
    )
    await _run_special_match(update.message, (getattr(context, 'args', None) or []), _norway_adapter(), usage_guide)


# ===================== Peak digest (special-league daily scoring) =====================
# Detects today's Finland + Sweden federation matches, scores them 1-10
# (value-opportunity + B-Team/substitute detector) and flags peak + timing.
async def peak_today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /peak_today: ranked 1-10 scoring of today's special-league matches."""

    del context
    if update.message is None:
        return

    import asyncio as _asyncio

    from monitors.special_peak import build_peak_scores, render_peak_digest
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


# ===================== Generic Stats & Peaks Consolidation =====================
from datetime import date

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
    from monitors.special_peak import current_display_timezone, tz_offset_label
    
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
        from monitors.special_peak import _render_entry
        for score in peaks:
            lines.extend(_render_entry(score, tz))
        lines.append("")
        
    if rest:
        lines.append("📋 *Resto del radar:*")
        from monitors.special_peak import _kickoff_label_for_display
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
        from monitors.special_peak import build_peak_scores
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
            
    from monitors.special_peak import render_peak_digest
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


# Generic Stats Assistant Helpers & Commands
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

"""Telegram command handlers for the current sportsbook tracking bot flow."""

from __future__ import annotations

import asyncio
from datetime import date
from difflib import SequenceMatcher
import logging
import re
import unicodedata

from telegram import Message, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
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
    format_kickoff_labels,
    split_telegram_message,
)
from core.extractor_base import CompetitionUnavailableError, LeagueDiscoveryOption
from core.models import PlatformDescriptor
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
from storage.tracking_repository import ActiveEventRecord, TrackedCompetitionSubscription

logger = logging.getLogger(__name__)

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
    "Comandos generales\n"
    "/start - Mensaje de bienvenida\n"
    "/help - Lista de comandos\n"
    "/guide - Guía rápida del flujo\n"
    "/platforms - Plataformas soportadas\n"
    "/ping - Responde pong\n"
    "/status - Informa si el bot está online\n"
    "/resources - Muestra métricas simples de recursos\n"
    "/echo <texto> - Devuelve el texto enviado\n\n"
    "Tracking de ligas\n"
    "/track_league - Elegí plataforma, país y liga sin pegar URL\n"
    "/track_url <url> - Extrae una liga de una plataforma soportada y la deja pendiente\n"
    "/confirm_track - Confirma la última liga pendiente\n"
    "/confirm_empty_track - Confirma una liga válida pero vacía\n"
    "/link_stats - Vincula una liga trackeada con stats (por país o pegando una URL de Statshub)\n"
    "/stats_links - Lista las ligas vinculadas con stats\n"
    "/track_stats - Agrega una liga solo para stats y cache diario\n"
    "/stats_tracks - Lista las ligas seguidas solo para stats\n"
    "/explore_stats - Explora tabla, fixtures, equipos y reportes de stats\n"
    "/list_tracks - Lista las ligas trackeadas\n"
    "/competition_url <n> - Muestra la URL original de una liga trackeada\n"
    "/refresh_tracks - Actualiza partidos y detecta eventos nuevos\n"
    "/update_track_url <n> <url> - Actualiza la URL de una liga usando el número de /list_tracks\n"
    "/untrack - Permite dejar de trackear una liga\n\n"
    "Consulta de partidos\n"
    "/matches - Permite elegir una liga y ver sus partidos\n"
    "/event_url <n> - Muestra la URL directa de un partido de la última lista de /matches\n\n"
    "/stats <n> - Genera reporte de stats del partido de la última lista de /matches\n\n"
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
    "3b. /link_stats si la plataforma no trae stats directas\n"
    "3c. /stats_links para revisar vínculos activos\n"
    "3d. /track_stats para seguir una liga aunque no tenga colector de odds\n"
    "4. /list_tracks\n"
    "5. /competition_url <n>\n"
    "6. /matches\n"
    "7. /event_url <n>\n"
    "8. /stats <n>\n"
    "9. /update_track_url <n> <url> si el link cambió\n"
    "10. /odds_on\n"
    "11. /set_change_percent 20\n"
    "12. /check_little_changes\n"
    "13. /confirm_change <n> o /confirm_all_little_changes"
)

TRACK_URL_USAGE_MESSAGE = (
    "Usá /track_url <url_de_plataforma>.\n"
    "Primero podés usar /platforms para ver las plataformas disponibles\n"
    "y después pegar la URL de una competencia.\n\n"
    "Opcional: agregá un nombre con | al final (útil en Mystake):\n"
    "/track_url <url> | Australia NPL Northern NSW"
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

STATS_URL_USAGE_MESSAGE = (
    "Usá /stats <número_visible_en_/matches>.\n"
    "Primero corré /matches, elegí una liga y después pedí las stats del partido.\n"
    "Ejemplo:\n"
    "/stats 3"
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
    if watching:
        lines.append("👁️ *En vigilancia:*")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        for e in watching:
            time_lbl = "Pendiente"
            if e.kickoff_at:
                try:
                    from datetime import datetime
                    from zoneinfo import ZoneInfo
                    dt = datetime.fromisoformat(e.kickoff_at)
                    dt_arg = dt.astimezone(ZoneInfo("America/Argentina/Buenos_Aires"))
                    time_lbl = dt_arg.strftime('%H:%M')
                except Exception:
                    pass
            disp_id = e.chat_local_id if e.chat_local_id is not None else e.id
            hint = f" ({e.league_hint})" if e.league_hint else ""
            lines.append(
                f"  *#{disp_id}* · 🕒 `{time_lbl}`{hint}\n"
                f"     ⚽ `{e.home}` vs `{e.away}`\n"
            )
    if fired:
        lines.append("\n🔴 *Ya salieron en vivo:*")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        for e in fired:
            where = (e.matched_platform or "").replace("_http", "")
            disp_id = e.chat_local_id if e.chat_local_id is not None else e.id
            lines.append(
                f"  *#{disp_id}* · ⚽ `{e.home}` vs `{e.away}`\n"
                f"     🏦 → {where} {e.matched_minute or ''}\n".rstrip()
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


async def resources_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/resources` with runtime resource metrics."""

    if update.message is None:
        return

    metrics = get_system_metrics()
    await update.message.reply_text(format_system_metrics_message(metrics))


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle `/stats` interactive or `/stats <event_number>` from `/matches`."""

    if update.message is None:
        return ConversationHandler.END

    logger.info("Comando /stats recibido.")

    if len(context.args) == 0:
        if update.effective_chat is None:
            return ConversationHandler.END
        tracking_service = get_tracking_service(context)
        tracked_leagues = tracking_service.list_confirmed_tracks(update.effective_chat.id)
        if not tracked_leagues:
            await update.message.reply_text(
                "No tenés ligas trackeadas todavía.\n"
                "Usá /track_league o /track_url primero.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return ConversationHandler.END
        context.user_data[STATS_TRACKS_CONTEXT_KEY] = tracked_leagues
        await update.message.reply_text(
            _build_track_selection_message("De qué liga querés ver stats?", tracked_leagues),
            reply_markup=_build_numeric_keyboard(len(tracked_leagues), "Elegí la liga"),
        )
        return SELECT_LEAGUE_FOR_STATS

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text(STATS_URL_USAGE_MESSAGE)
        return ConversationHandler.END

    active_matches = context.user_data.get(MATCHES_ACTIVE_CONTEXT_KEY)
    tracked_subscription = context.user_data.get(MATCHES_SELECTED_TRACK_CONTEXT_KEY)

    if not isinstance(active_matches, list) or not active_matches:
        await update.message.reply_text(
            "No tengo una lista reciente de partidos para este chat.\n\n"
            "Usá /matches, elegí una liga y después /stats <n>."
        )
        return ConversationHandler.END

    if not isinstance(tracked_subscription, TrackedCompetitionSubscription):
        await update.message.reply_text(
            "No tengo una liga seleccionada recientemente.\n\n"
            "Usá /matches, elegí una liga y después /stats <n>."
        )
        return ConversationHandler.END

    selected_index = _parse_selection_number(context.args[0], len(active_matches) + 1)
    if selected_index is None:
        await update.message.reply_text(STATS_URL_USAGE_MESSAGE)
        return ConversationHandler.END

    if selected_index == 0:
        await update.message.reply_text(
            "El número 1 corresponde a \"Ver todos\".\n\n"
            "Elegí el número visible de un partido individual de la última lista de /matches."
        )
        return ConversationHandler.END

    stats_service = get_stats_service(context)
    await update.message.reply_text("Generando reporte de stats...")
    result = await stats_service.build_match_stats_report(
        tracked_subscription=tracked_subscription,
        matches=active_matches,
        event_number=selected_index,
    )
    await _reply_text_chunks(update.message, result.message)
    return ConversationHandler.END


async def stats_select_league(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle league selection during interactive `/stats`."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END

    tracked_leagues = context.user_data.get(STATS_TRACKS_CONTEXT_KEY)
    if not isinstance(tracked_leagues, list) or not tracked_leagues:
        await update.message.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = _parse_selection_number(update.message.text, len(tracked_leagues))
    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de liga.",
            reply_markup=_build_numeric_keyboard(len(tracked_leagues), "Elegí la liga"),
        )
        return SELECT_LEAGUE_FOR_STATS

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
        except (RuntimeError, ValueError):
            logger.exception(
                "Failed to refresh tracked league %s for stats chat_id=%s.",
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

    context.user_data[STATS_ACTIVE_CONTEXT_KEY] = active_matches
    context.user_data[STATS_SELECTED_TRACK_CONTEXT_KEY] = tracked_subscription
    await update.message.reply_text(
        _build_stats_match_selection_message(tracked_subscription, active_matches),
        reply_markup=_build_numeric_keyboard(len(active_matches), "Elegí el partido"),
    )
    return SELECT_MATCH_FOR_STATS


async def stats_select_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generate a stats report after interactive match selection."""

    if update.message is None:
        return ConversationHandler.END

    active_matches = context.user_data.get(STATS_ACTIVE_CONTEXT_KEY)
    tracked_subscription = context.user_data.get(STATS_SELECTED_TRACK_CONTEXT_KEY)

    if not isinstance(active_matches, list) or not active_matches:
        await update.message.reply_text(
            "No encontré la selección de partidos. Probá de nuevo con /stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    if not isinstance(tracked_subscription, TrackedCompetitionSubscription):
        await update.message.reply_text(
            "No encontré la liga seleccionada. Probá de nuevo con /stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = _parse_selection_number(update.message.text, len(active_matches))
    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de partido.",
            reply_markup=_build_numeric_keyboard(len(active_matches), "Elegí el partido"),
        )
        return SELECT_MATCH_FOR_STATS

    stats_service = get_stats_service(context)
    await update.message.reply_text("Generando reporte de stats...", reply_markup=ReplyKeyboardRemove())
    resolution = await stats_service.resolve_event(
        tracked_subscription=tracked_subscription,
        matches=active_matches,
        event_number=selected_index + 1,
    )

    if resolution.kind == "choose":
        context.user_data[STATS_CANDIDATES_CONTEXT_KEY] = list(resolution.candidates)
        context.user_data[STATS_CANDIDATE_MATCH_CONTEXT_KEY] = active_matches[resolution.event_index]
        context.user_data[STATS_CANDIDATE_PROVIDER_CONTEXT_KEY] = resolution.provider_key
        lines = [
            "No estoy seguro de cuál es el partido de stats. Elegí el correcto:",
            "",
        ]
        for index, candidate in enumerate(resolution.candidates, start=1):
            lines.append(f"{index} - {candidate.label}")
        lines.append("")
        lines.append("Si ninguno corresponde, usá /cancel.")
        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=_build_numeric_keyboard(len(resolution.candidates), "Elegí el partido de stats"),
        )
        return SELECT_STATS_CANDIDATE

    await _reply_text_chunks(
        update.message,
        (resolution.result.message if resolution.result else "No pude generar el reporte de stats."),
        reply_markup=ReplyKeyboardRemove(),
    )
    _clear_all_selection_context(context)
    return ConversationHandler.END


async def stats_select_candidate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Persist a manually chosen stats candidate and generate its report."""

    if update.message is None:
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
        await update.message.reply_text(
            "No encontré la selección de candidatos. Probá de nuevo con /stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = _parse_selection_number(update.message.text, len(candidates))
    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de partido de stats.",
            reply_markup=_build_numeric_keyboard(len(candidates), "Elegí el partido de stats"),
        )
        return SELECT_STATS_CANDIDATE

    stats_service = get_stats_service(context)
    await update.message.reply_text("Generando reporte de stats...", reply_markup=ReplyKeyboardRemove())
    result = await stats_service.build_report_for_chosen_candidate(
        match=match,
        provider_key=provider_key,
        link=candidates[selected_index].link,
    )
    await _reply_text_chunks(update.message, result.message, reply_markup=ReplyKeyboardRemove())
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
    lines = ["¿Qué liga querés explorar?"]
    for index, league in enumerate(linked, start=1):
        lines.append(f"{index} - {league.label}")
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=_build_numeric_keyboard(len(linked), "Elegí la liga"),
    )
    return EXPLORE_SELECT_LEAGUE


async def explore_select_league(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Load the selected league's cached overview and show the navigation menu."""

    if update.message is None:
        return ConversationHandler.END

    linked = context.user_data.get(EXPLORE_TRACKS_CONTEXT_KEY)
    if not isinstance(linked, list) or not linked:
        await update.message.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /explore_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = _parse_selection_number(update.message.text, len(linked))
    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de liga.",
            reply_markup=_build_numeric_keyboard(len(linked), "Elegí la liga"),
        )
        return EXPLORE_SELECT_LEAGUE

    league = linked[selected_index]
    if not isinstance(league, ExplorableStatsLeague):
        await update.message.reply_text("La liga seleccionada no es válida.")
        return ConversationHandler.END
    stats_service = get_stats_service(context)
    await update.message.reply_text("Cargando datos de la liga...", reply_markup=ReplyKeyboardRemove())
    try:
        overview = await stats_service.get_league_overview(
            provider_key=league.provider_key,
            league_id=league.league_id,
        )
    except Exception:
        logger.exception("Explore stats overview failed league=%s", league.league_id)
        overview = None
    if not overview:
        await update.message.reply_text(
            "No pude cargar los datos de esa liga ahora. Probá más tarde.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    context.user_data[EXPLORE_OVERVIEW_CONTEXT_KEY] = overview
    context.user_data[EXPLORE_SELECTED_LEAGUE_CONTEXT_KEY] = league
    await update.message.reply_text(
        _explore_menu_text(overview),
        reply_markup=_build_numeric_keyboard(6, "Elegí una opción"),
    )
    return EXPLORE_MENU


async def explore_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render the chosen view and keep the explorer menu open."""

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

    choice = _parse_selection_number(update.message.text, 6)
    if choice is None:
        await update.message.reply_text(
            _explore_menu_text(overview),
            reply_markup=_build_numeric_keyboard(6, "Elegí una opción"),
        )
        return EXPLORE_MENU

    option = choice + 1
    if option == 4:
        await update.message.reply_text(
            "Escribí el nombre del equipo a buscar:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return EXPLORE_TEAM_INPUT

    if option == 6:
        league = context.user_data.get(EXPLORE_SELECTED_LEAGUE_CONTEXT_KEY)
        if not isinstance(league, ExplorableStatsLeague):
            await update.message.reply_text("Se perdió la liga seleccionada. Probá de nuevo con /explore_stats.")
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
            await update.message.reply_text("No hay partidos disponibles para generar reporte.")
            return EXPLORE_MENU
        context.user_data[EXPLORE_FIXTURES_CONTEXT_KEY] = fixtures
        await _reply_text_chunks(
            update.message,
            _build_provider_fixture_selection_message(fixtures),
            reply_markup=_build_numeric_keyboard(len(fixtures), "Elegí el partido"),
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

    await _reply_text_chunks(update.message, message)
    await update.message.reply_text(
        _explore_menu_text(overview),
        reply_markup=_build_numeric_keyboard(6, "Elegí una opción"),
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
        reply_markup=_build_numeric_keyboard(6, "Elegí una opción"),
    )
    return EXPLORE_MENU


async def explore_select_fixture(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generate a provider-native match report from `/explore_stats`."""

    if update.message is None:
        return ConversationHandler.END
    fixtures = context.user_data.get(EXPLORE_FIXTURES_CONTEXT_KEY)
    league = context.user_data.get(EXPLORE_SELECTED_LEAGUE_CONTEXT_KEY)
    if not isinstance(fixtures, list) or not fixtures or not isinstance(league, ExplorableStatsLeague):
        await update.message.reply_text("Se perdió la selección. Probá de nuevo con /explore_stats.")
        return ConversationHandler.END
    selected_index = _parse_selection_number(update.message.text, len(fixtures))
    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de partido.",
            reply_markup=_build_numeric_keyboard(len(fixtures), "Elegí el partido"),
        )
        return EXPLORE_SELECT_FIXTURE
    fixture = fixtures[selected_index]
    await update.message.reply_text("Generando reporte de stats...", reply_markup=ReplyKeyboardRemove())
    result = await get_stats_service(context).build_direct_match_report(
        provider_key=league.provider_key,
        stats_match_id=fixture.match_id,
    )
    await _reply_text_chunks(update.message, result.message)
    overview = context.user_data.get(EXPLORE_OVERVIEW_CONTEXT_KEY)
    if not isinstance(overview, dict):
        return ConversationHandler.END
    await update.message.reply_text(
        _explore_menu_text(overview),
        reply_markup=_build_numeric_keyboard(6, "Elegí una opción"),
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
        await update.message.reply_text(TRACK_URL_USAGE_MESSAGE)
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
        reply_markup=_build_numeric_keyboard(len(platforms), "Elegí la plataforma"),
    )
    return SELECT_PLATFORM_FOR_TRACK_LEAGUE


async def track_league_select_platform(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Handle platform selection for `/track_league`."""

    if update.message is None:
        return ConversationHandler.END

    platforms = context.user_data.get(TRACK_LEAGUE_PLATFORMS_CONTEXT_KEY)
    if not isinstance(platforms, list) or not platforms:
        await update.message.reply_text(
            "No encontré la selección de plataformas. Probá de nuevo con /track_league.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = _parse_selection_number(update.message.text, len(platforms))
    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de plataforma.",
            reply_markup=_build_numeric_keyboard(len(platforms), "Elegí la plataforma"),
        )
        return SELECT_PLATFORM_FOR_TRACK_LEAGUE

    selected_platform = platforms[selected_index]
    if not isinstance(selected_platform, PlatformDescriptor):
        await update.message.reply_text(
            "La plataforma seleccionada no es válida. Probá de nuevo con /track_league.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    context.user_data[TRACK_LEAGUE_SELECTED_PLATFORM_CONTEXT_KEY] = selected_platform
    await update.message.reply_text(
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
        reply_markup=_build_numeric_keyboard(len(league_options), "Elegí la liga"),
    )
    return SELECT_LEAGUE_FOR_TRACK_LEAGUE


async def track_league_select_league(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Track the league selected during `/track_league`."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END

    league_options = context.user_data.get(TRACK_LEAGUE_OPTIONS_CONTEXT_KEY)
    if not isinstance(league_options, list) or not league_options:
        await update.message.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /track_league.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = _parse_selection_number(update.message.text, len(league_options))
    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de liga.",
            reply_markup=_build_numeric_keyboard(len(league_options), "Elegí la liga"),
        )
        return SELECT_LEAGUE_FOR_TRACK_LEAGUE

    selected_option = league_options[selected_index]
    if not isinstance(selected_option, LeagueDiscoveryOption):
        await update.message.reply_text(
            "La liga seleccionada no es válida. Probá de nuevo con /track_league.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    tracking_service = get_tracking_service(context)
    await update.message.reply_text(
        f"Guardando tracking de {selected_option.league_name}...",
        reply_markup=ReplyKeyboardRemove(),
    )
    result = await tracking_service.track_discovered_league(
        update.effective_chat.id,
        selected_option,
    )

    await _reply_text_chunks(update.message, result.message, reply_markup=ReplyKeyboardRemove())
    _clear_all_selection_context(context)
    return ConversationHandler.END


_STATSHUB_TOURNAMENT_RE = re.compile(r"statshub\.sportradar\.com/\S*?/tournament/(\d+)", re.IGNORECASE)


def _extract_statshub_tournament_id(text: str) -> str | None:
    """Extract a Statshub tournament id from a pasted URL, or None if not a URL."""

    match = _STATSHUB_TOURNAMENT_RE.search(text or "")
    return match.group(1) if match else None


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
        reply_markup=_build_numeric_keyboard(len(providers), "Elegí provider de stats"),
    )
    return SELECT_PROVIDER_FOR_TRACK_STATS


async def track_stats_select_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Select the provider used by `/track_stats`."""

    if update.message is None:
        return ConversationHandler.END
    providers = context.user_data.get(TRACK_STATS_PROVIDERS_CONTEXT_KEY)
    if not isinstance(providers, list) or not providers:
        await update.message.reply_text("No encontré la selección de providers. Probá de nuevo con /track_stats.")
        return ConversationHandler.END
    selected_index = _parse_selection_number(update.message.text, len(providers))
    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de provider.",
            reply_markup=_build_numeric_keyboard(len(providers), "Elegí provider"),
        )
        return SELECT_PROVIDER_FOR_TRACK_STATS
    selected_provider = providers[selected_index]
    if not isinstance(selected_provider, StatsProviderDescriptor):
        await update.message.reply_text("El provider seleccionado no es válido.")
        return ConversationHandler.END
    context.user_data[TRACK_STATS_SELECTED_PROVIDER_CONTEXT_KEY] = selected_provider
    await update.message.reply_text(
        (
            f"Provider elegido: {selected_provider.display_name}\n\n"
            "Escribí el país para buscar ligas de stats.\n"
            "Ejemplos: Spain, Australia, Argentina, England.\n\n"
            "Para Sportradar también podés pegar directamente una URL de torneo."
        ),
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
    tournament_id = _extract_statshub_tournament_id(country_name)
    if tournament_id is not None:
        await update.message.reply_text(f"Resolviendo torneo de Statshub id={tournament_id}...")
        try:
            option = await stats_service.describe_league(
                provider_key=selected_provider.key,
                league_id=tournament_id,
            )
        except Exception:
            logger.exception("Standalone stats league describe-by-url failed id=%s", tournament_id)
            option = None
        if option is None:
            await update.message.reply_text("No pude resolver esa URL de torneo.", reply_markup=ReplyKeyboardRemove())
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
    await _reply_text_chunks(
        update.message,
        _build_stats_league_selection_message(options, prompt="Elegí la liga de stats a seguir:"),
        reply_markup=_build_numeric_keyboard(len(options), "Elegí la liga stats"),
    )
    return SELECT_LEAGUE_FOR_TRACK_STATS


async def track_stats_select_league(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Persist one standalone provider-native stats league."""

    if update.message is None or update.effective_chat is None:
        return ConversationHandler.END
    options = context.user_data.get(TRACK_STATS_OPTIONS_CONTEXT_KEY)
    if not isinstance(options, list) or not options:
        await update.message.reply_text("No encontré la selección de ligas stats. Probá de nuevo con /track_stats.")
        return ConversationHandler.END
    selected_index = _parse_selection_number(update.message.text, len(options))
    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de liga stats.",
            reply_markup=_build_numeric_keyboard(len(options), "Elegí la liga stats"),
        )
        return SELECT_LEAGUE_FOR_TRACK_STATS
    selected_option = options[selected_index]
    if not isinstance(selected_option, StatsLeagueOption):
        await update.message.reply_text("La liga stats seleccionada no es válida.")
        return ConversationHandler.END
    result = get_stats_service(context).track_stats_league(
        chat_id=update.effective_chat.id,
        option=selected_option,
    )
    await _reply_text_chunks(update.message, result.message, reply_markup=ReplyKeyboardRemove())
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
        _build_track_selection_message("Qué liga de odds querés vincular con stats?", tracked_leagues),
        reply_markup=_build_numeric_keyboard(len(tracked_leagues), "Elegí la liga"),
    )
    return SELECT_TRACK_FOR_LINK_STATS


async def link_stats_select_track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle tracked odds league selection for `/link_stats`."""

    if update.message is None:
        return ConversationHandler.END

    tracked_leagues = context.user_data.get(LINK_STATS_TRACKS_CONTEXT_KEY)
    if not isinstance(tracked_leagues, list) or not tracked_leagues:
        await update.message.reply_text(
            "No encontré la selección de ligas. Probá de nuevo con /link_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = _parse_selection_number(update.message.text, len(tracked_leagues))
    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de liga.",
            reply_markup=_build_numeric_keyboard(len(tracked_leagues), "Elegí la liga"),
        )
        return SELECT_TRACK_FOR_LINK_STATS

    selected_track = tracked_leagues[selected_index]
    if not isinstance(selected_track, TrackedCompetitionSubscription):
        await update.message.reply_text(
            "La liga seleccionada no es válida. Probá de nuevo con /link_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    stats_service = get_stats_service(context)
    providers = stats_service.list_providers()
    if not providers:
        await update.message.reply_text(
            "No hay providers de stats con discovery habilitado.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    context.user_data[LINK_STATS_SELECTED_TRACK_CONTEXT_KEY] = selected_track
    context.user_data[LINK_STATS_PROVIDERS_CONTEXT_KEY] = providers
    await update.message.reply_text(
        _build_stats_provider_selection_message(providers),
        reply_markup=_build_numeric_keyboard(len(providers), "Elegí provider de stats"),
    )
    return SELECT_PROVIDER_FOR_LINK_STATS


async def link_stats_select_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle stats provider selection for `/link_stats`."""

    if update.message is None:
        return ConversationHandler.END

    providers = context.user_data.get(LINK_STATS_PROVIDERS_CONTEXT_KEY)
    if not isinstance(providers, list) or not providers:
        await update.message.reply_text(
            "No encontré la selección de providers. Probá de nuevo con /link_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = _parse_selection_number(update.message.text, len(providers))
    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de provider.",
            reply_markup=_build_numeric_keyboard(len(providers), "Elegí provider"),
        )
        return SELECT_PROVIDER_FOR_LINK_STATS

    selected_provider = providers[selected_index]
    if not isinstance(selected_provider, StatsProviderDescriptor):
        await update.message.reply_text(
            "El provider seleccionado no es válido. Probá de nuevo con /link_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    context.user_data[LINK_STATS_SELECTED_PROVIDER_CONTEXT_KEY] = selected_provider
    await update.message.reply_text(
        (
            f"Provider elegido: {selected_provider.display_name}\n\n"
            "Tenés 2 formas de vincular:\n\n"
            "1) Escribí el país para buscar (ej: Spain, Australia, England).\n\n"
            "2) Si la liga no aparece, buscala manualmente en la página de fútbol del proveedor:\n"
            "https://statshub.sportradar.com/bet365/es/sport/1\n"
            "abrí la liga y pegá acá su URL, por ejemplo:\n"
            "https://statshub.sportradar.com/bet365/es/sport/1/tournament/28743"
        ),
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
        await update.message.reply_text("Escribí un país válido o pegá una URL de Statshub.")
        return ENTER_COUNTRY_FOR_LINK_STATS

    stats_service = get_stats_service(context)
    selected_track = context.user_data.get(LINK_STATS_SELECTED_TRACK_CONTEXT_KEY)

    # Direct link by pasted Statshub tournament URL, bypassing country discovery
    # (which omits some valid tournaments, e.g. USL League Two).
    tournament_id = _extract_statshub_tournament_id(country_name)
    if tournament_id is not None:
        if not isinstance(selected_track, TrackedCompetitionSubscription):
            await update.message.reply_text(
                "No encontré la liga de odds seleccionada. Probá de nuevo con /link_stats.",
                reply_markup=ReplyKeyboardRemove(),
            )
            _clear_all_selection_context(context)
            return ConversationHandler.END
        await update.message.reply_text(f"Resolviendo torneo de Statshub id={tournament_id}...")
        try:
            option = await stats_service.describe_league(
                provider_key=selected_provider.key,
                league_id=tournament_id,
            )
        except Exception:
            logger.exception("Stats league describe-by-url failed id=%s", tournament_id)
            option = None
        if option is None:
            await update.message.reply_text(
                f"No pude resolver el torneo id={tournament_id} en {selected_provider.display_name}.\n"
                "Verificá la URL de Statshub o probá con el país.",
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
                "y reiniciá el bot. Auto prueba headless primero y solo abre navegador visible si Statshub lo bloquea.",
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
            "Probá con otro nombre de país, o buscala manualmente en:\n"
            "https://statshub.sportradar.com/bet365/es/sport/1\n"
            "abrí la liga y pegá acá su URL para vincularla. (/cancel para salir)",
        )
        return ENTER_COUNTRY_FOR_LINK_STATS

    context.user_data[LINK_STATS_OPTIONS_CONTEXT_KEY] = options
    intro = ""
    if sample_events:
        intro = "🔢 Ordenadas por relevancia: la #1 es la que más coincide con tus partidos.\n\n"
    await _reply_text_chunks(
        update.message,
        intro + _build_stats_league_selection_message(options),
        reply_markup=_build_numeric_keyboard(len(options), "Elegí la liga stats"),
    )
    return SELECT_LEAGUE_FOR_LINK_STATS


async def link_stats_select_league(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Persist the selected stats league link."""

    if update.message is None:
        return ConversationHandler.END

    selected_track = context.user_data.get(LINK_STATS_SELECTED_TRACK_CONTEXT_KEY)
    options = context.user_data.get(LINK_STATS_OPTIONS_CONTEXT_KEY)

    if not isinstance(selected_track, TrackedCompetitionSubscription):
        await update.message.reply_text(
            "No encontré la liga de odds seleccionada. Probá de nuevo con /link_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    if not isinstance(options, list) or not options:
        await update.message.reply_text(
            "No encontré la selección de ligas stats. Probá de nuevo con /link_stats.",
            reply_markup=ReplyKeyboardRemove(),
        )
        _clear_all_selection_context(context)
        return ConversationHandler.END

    selected_index = _parse_selection_number(update.message.text, len(options))
    if selected_index is None:
        await update.message.reply_text(
            "Elegí un número válido de liga stats.",
            reply_markup=_build_numeric_keyboard(len(options), "Elegí la liga stats"),
        )
        return SELECT_LEAGUE_FOR_LINK_STATS

    selected_option = options[selected_index]
    if not isinstance(selected_option, StatsLeagueOption):
        await update.message.reply_text(
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

    await _reply_text_chunks(update.message, result.message, reply_markup=ReplyKeyboardRemove())
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

    await _reply_text_chunks(update.message, result.message, parse_mode=ParseMode.HTML)


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

    await _reply_text_chunks(update.message, result.message, parse_mode=ParseMode.HTML)


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
        await _reply_text_chunks(
            update.message,
            build_all_matches_message(tracked_league.tracked_league, active_matches),
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.HTML,
        )
    else:
        selected_match = active_matches[selected_index - 1]
        await _reply_text_chunks(
            update.message,
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
    
    # Finnish Football Leagues and stats commands
    application.add_handler(CommandHandler("fin_help", fin_help_command))
    application.add_handler(CommandHandler("fin_leagues", fin_leagues_command))
    application.add_handler(CommandHandler("fin_standings", fin_standings_command))
    application.add_handler(CommandHandler("fin_fixtures", fin_fixtures_command))
    application.add_handler(CommandHandler("fin_today", fin_today_command))
    application.add_handler(CommandHandler("fin_match", fin_match_command))
    
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("resources", resources_command))
    application.add_handler(CommandHandler("echo", echo_command))
    application.add_handler(CommandHandler("track_url", track_url_command))
    application.add_handler(CommandHandler("confirm_track", confirm_track_command))
    application.add_handler(CommandHandler("confirm_empty_track", confirm_empty_track_command))
    application.add_handler(CommandHandler("list_tracks", list_tracks_command))
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
    application.add_handler(CommandHandler("watching", watching_command))
    application.add_handler(CommandHandler("unwatch", unwatch_command))

    track_league_conversation = ConversationHandler(
        entry_points=[CommandHandler(["track_league", "tracl_league"], track_league_command)],
        states={
            SELECT_PLATFORM_FOR_TRACK_LEAGUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, track_league_select_platform)
            ],
            ENTER_COUNTRY_FOR_TRACK_LEAGUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, track_league_enter_country)
            ],
            SELECT_LEAGUE_FOR_TRACK_LEAGUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, track_league_select_league)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        name="track_league_conversation",
        persistent=False,
    )
    application.add_handler(track_league_conversation)

    link_stats_conversation = ConversationHandler(
        entry_points=[CommandHandler("link_stats", link_stats_command)],
        states={
            SELECT_TRACK_FOR_LINK_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, link_stats_select_track)
            ],
            SELECT_PROVIDER_FOR_LINK_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, link_stats_select_provider)
            ],
            ENTER_COUNTRY_FOR_LINK_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, link_stats_enter_country)
            ],
            SELECT_LEAGUE_FOR_LINK_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, link_stats_select_league)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        name="link_stats_conversation",
        persistent=False,
    )
    application.add_handler(link_stats_conversation)

    track_stats_conversation = ConversationHandler(
        entry_points=[CommandHandler("track_stats", track_stats_command)],
        states={
            SELECT_PROVIDER_FOR_TRACK_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, track_stats_select_provider)
            ],
            ENTER_COUNTRY_FOR_TRACK_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, track_stats_enter_country)
            ],
            SELECT_LEAGUE_FOR_TRACK_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, track_stats_select_league)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        name="track_stats_conversation",
        persistent=False,
    )
    application.add_handler(track_stats_conversation)

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

    stats_conversation = ConversationHandler(
        entry_points=[CommandHandler("stats", stats_command)],
        states={
            SELECT_LEAGUE_FOR_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, stats_select_league)
            ],
            SELECT_MATCH_FOR_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, stats_select_match)
            ],
            SELECT_STATS_CANDIDATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, stats_select_candidate)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        name="stats_conversation",
        persistent=False,
    )
    application.add_handler(stats_conversation)

    explore_stats_conversation = ConversationHandler(
        entry_points=[CommandHandler("explore_stats", explore_stats_command)],
        states={
            EXPLORE_SELECT_LEAGUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, explore_select_league)
            ],
            EXPLORE_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, explore_menu)
            ],
            EXPLORE_TEAM_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, explore_team_input)
            ],
            EXPLORE_SELECT_FIXTURE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, explore_select_fixture)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        name="explore_stats_conversation",
        persistent=False,
    )
    application.add_handler(explore_stats_conversation)

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


def _build_discovery_platform_selection_message(platforms: list[PlatformDescriptor]) -> str:
    """Build the platform prompt for `/track_league`."""

    lines = ["Qué plataforma querés usar para buscar ligas?"]

    for index, platform in enumerate(platforms, start=1):
        lines.append(f"{index} - {platform.display_name} ({platform.key})")

    return "\n".join(lines)


def _build_stats_provider_selection_message(providers: list[StatsProviderDescriptor]) -> str:
    """Build the stats provider prompt for `/link_stats`."""

    lines = ["Qué provider de stats querés usar?"]

    for index, provider in enumerate(providers, start=1):
        live = "live" if provider.capabilities.supports_live else "prematch"
        lines.append(f"{index} - {provider.display_name} ({provider.key}) | {live}")

    return "\n".join(lines)


def _build_discovered_league_selection_message(options: list[LeagueDiscoveryOption]) -> str:
    """Build the league prompt for `/track_league`."""

    lines = ["Elegí la liga a trackear:"]

    for index, option in enumerate(options, start=1):
        games = f" | partidos={option.games_count}" if option.games_count is not None else ""
        lines.append(f"{index} - {option.league_name} | id={option.league_id}{games}")

    return "\n".join(lines)


def _build_stats_league_selection_message(
    options: list[StatsLeagueOption],
    *,
    prompt: str = "Elegí la liga de stats a vincular:",
) -> str:
    """Build a stats-league prompt for linking or standalone tracking."""

    lines = [prompt]

    for index, option in enumerate(options, start=1):
        season = f" | season={option.season_id}" if option.season_id else ""
        country = f" | {option.country_name}" if option.country_name else ""
        lines.append(f"{index} - {option.league_name}{country} | id={option.league_id}{season}")

    return "\n".join(lines)


def _build_provider_fixture_selection_message(fixtures: list) -> str:
    """Build the provider-native fixture prompt used by `/explore_stats`."""

    lines = ["Elegí el partido para generar reporte:"]
    for index, fixture in enumerate(fixtures, start=1):
        when = ""
        if isinstance(fixture.scheduled_at, str) and len(fixture.scheduled_at) >= 16:
            when = f" | {fixture.scheduled_at[8:10]}/{fixture.scheduled_at[5:7]} {fixture.scheduled_at[11:16]}"
        lines.append(f"{index} - {fixture.home} vs {fixture.away}{when}")
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


def _resolve_fin_league(code: str) -> tuple[str, str] | None:
    """Resolve a short league code to competition_id and category_id."""
    mapping = {
        "VL": ("spljp26", "VL"),
        "M1L": ("spljp26", "M1L"),
        "M1": ("spljp26", "M1"),
        "M2": ("spljp26", "M2"),
        "NL": ("spljp26", "NL"),
        "MSC": ("spljp26", "MSC"),
        "NSC": ("spljp26", "NSC"),
        "LC": ("spljp26", "LC"),
    }
    return mapping.get(code)


async def fin_leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /fin_leagues: List mapped leagues and hierarchy."""
    del context
    if update.message is None:
        return

    from stats_providers.palloliitto.api_client import PalloliittoAPI
    api = PalloliittoAPI()
    try:
        leagues = api.get_league_ranking_list()
        lines = [
            "🏆 *Jerarquía de Ligas Finlandesas (Escalafón)* 🏆\n",
            "Estas ligas no suelen figurar en sitios comunes de stats.",
            "Usá los comandos guiados abajo para explorar:\n",
        ]
        for l in leagues:
            icon = "⚽" if l["sport"] == "Football" else "🥅"
            gender_label = "Varones" if l["gender"] == "Men" else "Damas"
            lines.append(
                f"{icon} *{l['name']}* (Código: `{l['category_id']}`)\n"
                f"    Tierra: Tier {l['tier']} | {gender_label} | {l['sport']}\n"
            )
            
        lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        lines.append("👉 *¿Qué querés hacer ahora?*")
        lines.append("📊 Ver posiciones: `/fin_standings [CÓDIGO]`")
        lines.append("🗓️ Ver fixture: `/fin_fixtures [CÓDIGO]`")
        lines.append("📚 Ver guía de análisis: `/fin_help`")
        lines.append("Ejemplo: `/fin_standings VL`")
        
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.exception("Failed in /fin_leagues")
        await update.message.reply_text(f"❌ Error al recuperar las ligas: {e}")
    finally:
        api.close()


async def fin_standings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /fin_standings [league_id]: Display standings for a league."""
    if update.message is None:
        return

    usage_guide = (
        "❌ *Código de liga ausente o inválido.*\n\n"
        "Uso: `/fin_standings [CÓDIGO_LIGA]`\n\n"
        "💡 *Ligas disponibles:*\n"
        "• `VL` - Veikkausliiga (Tier 1)\n"
        "• `M1L` - Ykkösliiga (Tier 2)\n"
        "• `M1` - Ykkönen (Tier 3)\n"
        "• `M2` - Kakkonen (Tier 4)\n"
        "• `NL` - Kansallinen Liiga (Damas - Tier 1)\n"
        "• `MSC` - Suomen Cup (Copa)\n\n"
        "Ejemplo: `/fin_standings VL`"
    )

    if not context.args:
        await update.message.reply_text(usage_guide, parse_mode="Markdown")
        return

    league_code = context.args[0].upper()
    resolved = _resolve_fin_league(league_code)
    if not resolved:
        await update.message.reply_text(usage_guide, parse_mode="Markdown")
        return

    comp_id, cat_id = resolved[0], resolved[1]
    from stats_providers.palloliitto.api_client import PalloliittoAPI
    api = PalloliittoAPI()
    
    await update.message.reply_text("📊 Cargando tabla de posiciones de la federación...")
    try:
        # Group 1 is default
        standings = api.get_standings(competition_id=comp_id, category_id=cat_id, group_id="1")
        if not standings:
            await update.message.reply_text("⚠️ No hay posiciones disponibles para esta liga en el sistema.")
            return

        lines = [
            f"📊 *Posiciones: {league_code} (2026)*",
            "━━━━━━━━━━━━━━━━━━━━",
            " #  Equipo                PJ  Pts  Dif",
        ]
        for t in standings:
            pos = str(t.get("current_standing", 0)).rjust(2)
            name = (t.get("team_name", "Unknown"))[:20].ljust(20)
            played = str(t.get("matches_played", 0)).rjust(2)
            pts = str(t.get("points", 0)).rjust(3)
            diff = str(t.get("goals_diff", 0)).rjust(4)
            lines.append(f"` {pos} {name} {played} {pts} {diff}`")
            
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("👉 *Siguientes pasos:*")
        lines.append(f"🗓️ Ver fixture de esta liga: `/fin_fixtures {league_code}`")
        lines.append("⚽ Ver partidos de hoy: `/fin_today`")
        
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.exception("Failed in /fin_standings")
        await update.message.reply_text(f"❌ Error al consultar standings: {e}")
    finally:
        api.close()


async def fin_fixtures_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /fin_fixtures [league_id]: Display recent/upcoming fixtures."""
    if update.message is None:
        return

    usage_guide = (
        "❌ *Código de liga ausente o inválido.*\n\n"
        "Uso: `/fin_fixtures [CÓDIGO_LIGA]`\n\n"
        "💡 *Ligas disponibles:*\n"
        "• `VL` - Veikkausliiga (Tier 1)\n"
        "• `M1L` - Ykkösliiga (Tier 2)\n"
        "• `M1` - Ykkönen (Tier 3)\n"
        "• `M2` - Kakkonen (Tier 4)\n"
        "• `NL` - Kansallinen Liiga (Damas)\n"
        "• `MSC` - Suomen Cup (Copa)\n\n"
        "Ejemplo: `/fin_fixtures VL`"
    )

    if not context.args:
        await update.message.reply_text(usage_guide, parse_mode="Markdown")
        return

    league_code = context.args[0].upper()
    resolved = _resolve_fin_league(league_code)
    if not resolved:
        await update.message.reply_text(usage_guide, parse_mode="Markdown")
        return

    comp_id, cat_id = resolved[0], resolved[1]
    from stats_providers.palloliitto.api_client import PalloliittoAPI
    from datetime import date
    api = PalloliittoAPI()
    
    await update.message.reply_text("🗓️ Consultando fixtures en vivo...")
    try:
        matches = api.get_matches_by_league(competition_id=comp_id, category_id=cat_id)
        if not matches:
            await update.message.reply_text("⚠️ No se encontraron partidos cargados para esta liga.")
            return

        # Sort matches by date. Show upcoming or most recent finished (total 15)
        now_str = date.today().isoformat()
        upcoming = [m for m in matches if m.get("date", "") >= now_str]
        finished = [m for m in matches if m.get("date", "") < now_str]
        
        # We take up to 5 finished (for context) and up to 10 upcoming
        finished.sort(key=lambda x: x.get("date", ""), reverse=True)
        upcoming.sort(key=lambda x: x.get("date", ""))
        
        display_matches = list(reversed(finished[:5])) + upcoming[:10]
        
        lines = [
            f"🗓️ *Fixture de {league_code}*",
            "━━━━━━━━━━━━━━━━━━━━\n"
        ]
        for m in display_matches:
            date_val = m.get("date")
            time = m.get("time") or ""
            home = m.get("team_A_name") or m.get("club_A_name")
            away = m.get("team_B_name") or m.get("club_B_name")
            m_id = m.get("match_id")
            
            score = "vs"
            if m.get("status") in ["Finished", "Played"]:
                score = f"*{m.get('fs_A')}-{m.get('fs_B')}*"
            elif m.get("walkover") == 1:
                score = "Walkover"
                
            lines.append(f"• `{date_val} {time}`: {home} {score} {away}\n   ID del partido: `{m_id}`")
            
        lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 *¿Querés analizar las alineaciones y ver si juegan con suplentes?*")
        lines.append("Copia el ID del partido y corre:")
        lines.append("👉 `/fin_match [ID_PARTIDO]`")
        lines.append("Ejemplo: `/fin_match 4036852`")
        
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.exception("Failed in /fin_fixtures")
        await update.message.reply_text(f"❌ Error al consultar fixture: {e}")
    finally:
        api.close()


async def fin_today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /fin_today: Show matches scheduled for today with their IDs."""
    del context
    if update.message is None:
        return

    from stats_providers.palloliitto.api_client import PalloliittoAPI
    from datetime import date
    api = PalloliittoAPI()
    today_str = date.today().isoformat()
    
    await update.message.reply_text(f"⚽ Consultando partidos programados para hoy ({today_str})...")
    try:
        matches = api.get_matches_by_date(today_str)
        if not matches:
            await update.message.reply_text("📭 No hay partidos programados en la federación para el día de hoy.")
            return

        # Target adult categories to keep the output clean
        target_cats = {"VL", "M1L", "M1", "M2", "NL", "MSC", "NSC", "LC", "M1LCUP"}
        
        classified = []
        youth_or_others_count = 0
        for m in matches:
            cat_id = m.get("category_id")
            if cat_id in target_cats or "kakkonen" in str(m.get("category_name")).lower() or "ykkönen" in str(m.get("category_name")).lower():
                classified.append(m)
            else:
                youth_or_others_count += 1
                
        lines = [
            f"⚽ *Partidos de Hoy ({today_str})*",
            "━━━━━━━━━━━━━━━━━━━━\n"
        ]
        
        if not classified:
            lines.append("No hay partidos de ligas adultas principales para hoy.")
            if youth_or_others_count > 0:
                lines.append(f"_(Hay {youth_or_others_count} partidos en ligas juveniles o regionales menores hoy)_")
        else:
            for m in classified:
                cat_name = m.get("category_name") or "Liga"
                home = m.get("home_team_name") or m.get("club_A_name")
                away = m.get("away_team_name") or m.get("club_B_name")
                time = m.get("time") or "N/A"
                m_id = m.get("match_id")
                
                score = "vs"
                if m.get("status") in ["Finished", "Played"]:
                    score = f"*{m.get('fs_A')}-{m.get('fs_B')}*"
                elif m.get("live_period") != "-1":
                    score = f"🔴 *{m.get('fs_A')}-{m.get('fs_B')}*"
                    
                lines.append(
                    f"🏆 *{cat_name}* (🕒 `{time}`)\n"
                    f"   {home} {score} {away}\n"
                    f"   ID del partido: `{m_id}`\n"
                )
                
            if youth_or_others_count > 0:
                lines.append(f"ℹ️ _Omitidos {youth_or_others_count} partidos de categorías juveniles o ligas menores._\n")
                
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 *Detector de Suplentes / B-Team:*")
        lines.append("Para analizar alineaciones oficiales de hoy y ver si juegan titulares:")
        lines.append("👉 `/fin_match [ID_PARTIDO]`")
        
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.exception("Failed in /fin_today")
        await update.message.reply_text(f"❌ Error al consultar partidos de hoy: {e}")
    finally:
        api.close()


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

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(usage_guide, parse_mode="Markdown")
        return

    match_id = context.args[0]
    from stats_providers.palloliitto.api_client import PalloliittoAPI
    api = PalloliittoAPI()
    
    await update.message.reply_text("🔍 Recuperando datos detallados de alineación y estadísticas...")
    try:
        # 1. Fetch match details
        m = api.get_match_details(match_id)
        if not m:
            await update.message.reply_text("❌ No encontré un partido con ese ID. Por favor, verificá el número.")
            return

        home = m.get("club_A_name") or m.get("team_A_name") or "Local"
        away = m.get("club_B_name") or m.get("team_B_name") or "Visitante"
        date_val = m.get("date") or "N/A"
        time = m.get("time") or ""
        venue = m.get("venue_name") or "N/A"
        attendance = m.get("attendance") or "0"
        status = m.get("status") or "Scheduled"
        
        # General details
        lines = [
            f"⚽ *{home} vs {away}*",
            f"📍 Estadio: {venue} | Asistencia: {attendance}",
            f"📅 Fecha: {date_val} {time} | Estado: {status}",
            "━━━━━━━━━━━━━━━━━━━━"
        ]
        
        if m.get("walkover") == 1:
            lines.append("\n❌ *Partido Perdido / Walkover*")
            winner = home if m.get("winner") == "Home" else away
            score = f"{m.get('fs_A')}-{m.get('fs_B')}"
            lines.append(f"Ganador adjudicado: *{winner}* (Resultado: {score})")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            return
            
        if m.get("fs_A") is not None:
            lines.append(f"⚽ *Marcador final: {m.get('fs_A')} - {m.get('fs_B')}*")
            
        # Goals List
        goals = m.get("goals", [])
        if goals:
            lines.append("\n⚽ *Goles:*")
            for g in goals:
                scorer = g.get("player_name") or "Jugador"
                minute = g.get("minute") or "N/A"
                team = home if g.get("team_id") == m.get("team_A_id") else away
                lines.append(f" • {minute}': *{scorer}* ({team})")
                
        # Cards List
        bookings = m.get("bookings", [])
        if bookings:
            lines.append("\n🟨🟥 *Tarjetas:*")
            for b in bookings:
                player = b.get("player_name") or "Jugador"
                minute = b.get("minute") or "N/A"
                card = b.get("card_type") or "Yellow"
                card_icon = "🟨" if "yellow" in card.lower() else "🟥"
                team = home if b.get("team_id") == m.get("team_A_id") else away
                lines.append(f" • {minute}': {card_icon} *{player}* ({team})")
                
        # Lineup Rotation Analysis (Value bet detector!)
        lineups = m.get("lineups", [])
        if not lineups:
            lines.append("\n⚠️ *Alineaciones oficiales:*")
            lines.append("Las alineaciones oficiales aún no están disponibles para este partido en el sistema de la federación. (Se publican usualmente 1 hora antes del pitazo inicial).")
        else:
            home_id = m.get("team_A_id")
            away_id = m.get("team_B_id")
            home_starters = [p for p in lineups if p.get("team_id") == home_id and p.get("start") == "1"]
            away_starters = [p for p in lineups if p.get("team_id") == away_id and p.get("start") == "1"]
            
            lines.append("\n📋 *Titulares Confirmados:*")
            lines.append(f" • {home}: {len(home_starters)} en cancha.")
            lines.append(f" • {away}: {len(away_starters)} en cancha.")
            lines.append("\n🔍 *Análisis de Rotación (Detección de Suplentes/B-Team):*")
            
            # Run the rotation calculator for Home
            home_primary = m.get("team_A_primary_category_id") or m.get("category_id")
            home_rot_text = _calculate_rotation_for_team(api, home_name=home, team_id=home_id, primary_category=home_primary, competition_id=m.get("competition_id"), starters=home_starters, target_match_id=match_id)
            lines.append(f"\n🏘️ *Local ({home}):*\n{home_rot_text}")
            
            # Run the rotation calculator for Away
            away_primary = m.get("team_B_primary_category_id") or m.get("category_id")
            away_rot_text = _calculate_rotation_for_team(api, home_name=away, team_id=away_id, primary_category=away_primary, competition_id=m.get("competition_id"), starters=away_starters, target_match_id=match_id)
            lines.append(f"\n🚀 *Visitante ({away}):*\n{away_rot_text}")
            
            lines.append("\n💡 _¿Cómo interpretar? Si la regularidad es < 45% (🚨), el equipo está jugando con rotación masiva o suplentes en la copa. Esto suele provocar caídas rápidas en las cuotas de los casinos cuando los bots detectan la alineación oficial. ¡Aprovechá oportunidades de valor contra las cuotas pre-partido!_")
            
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.exception("Failed in /fin_match")
        await update.message.reply_text(f"❌ Error al consultar partido: {e}")
    finally:
        api.close()


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
        "🇫🇮 *Guía de Estadísticas de la Federación de Finlandia* 🇫🇮\n\n"
        "Este módulo te permite consultar estadísticas oficiales directo de la Asociación de Fútbol de Finlandia "
        "(`tulospalvelu.palloliitto.fi`). Estas ligas de ascenso y copas no suelen figurar en sitios comunes "
        "de estadísticas, lo cual genera grandes oportunidades de valor.\n\n"
        "📖 *Comandos disponibles:*\n"
        "• `/fin_leagues` - Muestra la jerarquía oficial (escalafón) de ligas masculinas, femeninas y copas.\n"
        "• `/fin_today` - Lista los partidos programados para hoy en las categorías principales con sus IDs.\n"
        "• `/fin_standings [CÓDIGO]` - Muestra la tabla de posiciones actual de una liga (Ej: `/fin_standings VL`).\n"
        "• `/fin_fixtures [CÓDIGO]` - Muestra el calendario de partidos recientes y próximos de una liga y sus IDs.\n"
        "• `/fin_match [ID_PARTIDO]` - Muestra detalles de un partido (goles, tarjetas, alineaciones) y corre el "
        "**Análisis de Rotación de Alineación (Detector de Suplentes / B-Team)**.\n\n"
        "🔍 *¿Cómo funciona el Detector de Suplentes / B-Team?*\n"
        "En los partidos de copa (como la *Suomen Cup*) o en fechas de rotación, los equipos de divisiones superiores "
        "suelen alinear reservas, juveniles o un equipo 'B'.\n"
        "El comando `/fin_match [ID_PARTIDO]` analiza los titulares de hoy y los compara con los últimos 3 partidos "
        "de liga del equipo, calculando un **Ratio de Regularidad**:\n"
        "  🟢 *>= 70%*: Juegan los titulares habituales (A-Team).\n"
        "  🟡 *45% - 69%*: Rotación parcial o moderada.\n"
        "  🚨 *< 45%*: *¡ROTACIÓN MASIVA / B-TEAM!* Juegan suplentes.\n\n"
        "💡 *Flujo de Análisis Recomendado:*\n"
        "1️⃣ Corré `/fin_today` para ver qué partidos hay programados para hoy.\n"
        "2️⃣ Si ves un partido interesante (por ejemplo, un equipo de división alta contra uno de división baja en Suomen Cup), "
        "esperá a que falte 1 hora para el partido (cuando se cargan las alineaciones oficiales).\n"
        "3️⃣ Corré `/fin_match [ID_PARTIDO]`.\n"
        "4️⃣ Si detectás un ratio de regularidad muy bajo (🚨 < 45%) para el equipo favorito, las cuotas del casino suelen "
        "estar desajustadas basándose en el poder del A-Team. ¡Esto te permite tomar apuestas de valor antes de que "
        "las cuotas se desplomen!"
    )

    await update.message.reply_text(help_text, parse_mode="Markdown")

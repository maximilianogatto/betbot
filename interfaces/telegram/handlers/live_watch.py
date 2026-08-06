"""Handlers del seguimiento en vivo: /watch_live, la watchlist y el import de la planilla.

Se apoya en `common.py` para el vocabulario compartido; nunca importa desde
`commands.py` — es `commands.py` el que importa de acá y re-exporta.
"""
from __future__ import annotations

from core.timezones import current_display_timezone
from core.timezones import tz_offset_label
from telegram import Message
from telegram import Update
from telegram.ext import ContextTypes
import re

from typing import Any

from interfaces.telegram.handlers.common import (
    _reply_text_chunks,
    get_live_watch_service,
    logger,
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


async def import_sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Import and watch matches from the shared Google Sheet URL."""
    if update.message is None or update.effective_chat is None:
        return

    import os
    import httpx
    from services.live_watch import parse_sheet_fixture_lines, sheet_timezone

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
            update.effective_chat.id,
            lines_to_add,
            times_tz=sheet_timezone(),
            # La planilla arrastra filas de partidos ya jugados: la papelera evita
            # re-cargarlos. Un pegado manual sigue sin este filtro.
            skip_recently_removed=True,
        )

        total_read = len(lines_to_add)
        total_added = len(added)
        skipped = total_read - total_added

        if not added:
            await loading_msg.edit_text(
                f"📋 Se leyeron {total_read} partidos de la planilla, pero todos fueron omitidos por estar en el pasado, ya estar duplicados en tu lista o haber salido de vigilancia hace menos de 2 días."
            )
            return

        msg = [
            f"📊 *¡Importación completada con éxito!*",
            f"Se leyeron {total_read} partidos de la planilla.",
            f"➕ *Nuevos en vigilancia:* {total_added}",
            f"⏭️ *Omitidos (pasados/duplicados/papelera):* {skipped}",
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
            from services.live_watch import _event_live_state
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



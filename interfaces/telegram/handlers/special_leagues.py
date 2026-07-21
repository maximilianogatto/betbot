"""Handlers de las ligas especiales (federaciones nacionales).

Comandos /fin_*, /swe_*, /no_*, /ro_*, /sk_* y /al_*: consultan las APIs de las
federaciones (Palloliitto, Svenskfotboll, NFF, FRF, Sportnet, LNFF) en vez de las
casas de apuestas. Extraído de `commands.py` en PR2-E5.
"""
from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from interfaces.telegram.handlers.common import logger, _reply_text_chunks


_SWE_LEAGUES: dict[str, tuple[str, str, str]] = {
    "AL": ("133348", "Allsvenskan", "Tier 1 · Varones"),
    "SE": ("133340", "Superettan", "Tier 2 · Varones"),
    "EN": ("133338", "Ettan Norra", "Tier 3 · Varones"),
    "ES": ("133339", "Ettan Södra", "Tier 3 · Varones"),
    "DA": ("133440", "OBOS Damallsvenskan", "Tier 1 · Damas"),
    "EE": ("133439", "Elitettan", "Tier 2 · Damas"),
}


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


_FIN_LEAGUE_USAGE = (
    "💡 Mirá todos los códigos con `/fin_leagues`.\n"
    "Ejemplos: `VL` Veikkausliiga · `M1` Ykkönen · `M3` Kolmonen · `MSC` Suomen Cup."
)


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


def _resolve_swe_league(code: str) -> tuple[str, str, str] | None:
    """Resolve a short league code to (competition_id, name, tier_label)."""

    return _SWE_LEAGUES.get((code or "").strip().upper())


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



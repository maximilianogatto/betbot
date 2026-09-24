"""Handlers del libro de apuestas (/bet, /tip, /bets, /settle…).

Toda la lógica vive en `services.ledger`; acá sólo se lee el comando, se llama
al service y se responde. El texto lo arma `interfaces/telegram/renderers/bets.py`.

Los nombres de comando van en inglés como el resto del bot; los textos, en
castellano. Los argumentos aceptan las dos formas (`won`/`ganada`,
`all`/`todas`, `max_match`/`max_partido`) para no romper la costumbre.

Dos cosas que el usuario nota y conviene no romper:

- Los errores de carga se contestan en una línea, con el ejemplo al lado: cargar
  una apuesta pasa mientras el partido corre, y no es momento de leer un manual.
- Una apuesta mal cargada se **anula**, no se borra: `/void_bet` la deja fuera de
  los reportes pero la fila queda.
"""

from __future__ import annotations

from datetime import datetime, timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from core.betting import ParseError, parse_bet_text
from core.betting.models import DEFAULT_LIMITS
from interfaces.telegram.handlers.common import (
    _reply_text_chunks, escape_html, get_live_watch_service, logger,
)
from interfaces.telegram.renderers.bets import (
    STATUS_FROM_ES,
    render_added,
    render_bet,
    render_exposure,
    render_report,
)
from services.ledger import LedgerService

#: Nombres cortos para los límites de riesgo (inglés, y los viejos en castellano).
LIMIT_ALIASES = {
    "max_stake": "max_stake_per_bet_usd",
    "max_match": "max_exposure_per_match_usd",
    "max_open": "max_open_exposure_usd",
    "daily_stop": "daily_stop_loss_usd",
    "max_bets_match": "max_bets_per_match",
    "max_apuesta": "max_stake_per_bet_usd",
    "max_partido": "max_exposure_per_match_usd",
    "max_abierto": "max_open_exposure_usd",
    "stop_diario": "daily_stop_loss_usd",
    "max_apuestas_partido": "max_bets_per_match",
}
LIMIT_KEYS_SHOWN = ("max_stake", "max_match", "max_open", "daily_stop", "max_bets_match")

#: Estados que acepta /settle, además de los de `STATUS_FROM_ES`.
SETTLE_STATUSES = ("won", "lost", "half_won", "half_lost", "push", "cashout")

HELP_BETS_MESSAGE = (
    "💰 <b>Libro de apuestas</b>\n"
    "<i>Registro propio: sirve para medir qué funciona, no para apostar por vos.</i>\n\n"
    "<b>Cargar</b>\n"
    "  <code>/bet Darwin -2.5 HT @1.66 10usd min 13 megapari</code>\n"
    "  <code>/tip Volta descanso-final G2/G2 @1.91 #grupo</code> — pick sin plata (1u)\n\n"
    "<b>Formato</b> <i>(en cualquier orden)</i>\n"
    "  cuota <code>@1.66</code> · monto <code>10usd</code> <code>5.000 ars</code> <code>$10</code>\n"
    "  mercado: <code>-2.5</code> <code>+1</code> <code>ah 0</code> · <code>over 2.5</code> "
    "<code>u3.5</code> · <code>tt over 3.5</code> · <code>gana</code> <code>empate</code> "
    "<code>1x</code> <code>dnb</code> · <code>ambos marcan no</code> · <code>G2/G2</code>\n"
    "  período: <code>HT</code>/<code>1T</code> o <code>2T</code> (si no, partido completo)\n"
    "  momento: <code>min 13</code> · <code>pre</code> · <code>con 1-0</code> · "
    "<code>a las 21:15</code>\n"
    "  combinada: separá con <code> + </code> · <code>#etiquetas</code> · "
    "<code>-- nota</code> al final\n\n"
    "<b>Ver y cerrar</b>\n"
    "  /bets — abiertas · <code>/bets all|settled|paper</code>\n"
    "  <code>/view_bet &lt;n&gt;</code> — cuota vista, CLV y resultado\n"
    "  <code>/settle &lt;n&gt; won|lost|half_won|half_lost|push|cashout [monto]</code>\n"
    "  <code>/void_bet &lt;n&gt;</code> — apuesta mal cargada (no la borra)\n\n"
    "<b>Riesgo y reportes</b>\n"
    "  /exposure — qué hay en juego y cómo va el día\n"
    "  <code>/report [hoy|ayer|semana|mes|semana_pasada|mes_pasado]</code> — P&amp;L, ROI,"
    " por casa, etiqueta y mercado. Llegan solos a las 9: el diario, el semanal los lunes"
    " y el mensual el 1°\n"
    "  <code>/set_limit max_match 30</code> — avisa, no bloquea\n"
    "  <i>límites:</i> " + " · ".join(LIMIT_KEYS_SHOWN) + "\n\n"
    "<i>Se liquidan solas cuando el partido termina (las del 1er tiempo, en el descanso)."
    " Si el partido no está trackeado, /bet lo pone en /watching para ver el resultado.</i>\n\n"
    "↩︎ /help"
)


def _ledger(context: ContextTypes.DEFAULT_TYPE) -> LedgerService:
    service = context.application.bot_data.get("ledger_service")
    if service is None:
        service = LedgerService()
        context.application.bot_data["ledger_service"] = service
    return service


def _args_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    return " ".join(context.args or []).strip()


def _bet_id(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    try:
        return int((context.args or [""])[0].lstrip("#"))
    except (ValueError, IndexError):
        return None


def _watch_unlinked(context: ContextTypes.DEFAULT_TYPE, bet) -> bool:
    """Partido que el bot no trackea: vigilarlo es la forma de tener su resultado."""
    if bet.chat_id is None or bet.status != "open":
        return False
    try:
        return bool(get_live_watch_service(context).watch_bet(bet.chat_id, bet))
    except Exception:
        logger.exception("No pude poner en vigilancia el partido de la apuesta #%s", bet.id)
        return False


async def _load(update: Update, context: ContextTypes.DEFAULT_TYPE, *, paper: bool) -> None:
    """Carga común de /bet y /tip."""
    text = _args_text(context)
    if not text:
        await update.message.reply_text(
            HELP_BETS_MESSAGE if not paper else
            "Registrá un pick sin plata, con la fuente como etiqueta:\n"
            "<code>/tip Volta descanso-final G2/G2 @1.91 #grupo_x</code>\n\n"
            "Cuenta 1 unidad. Registrá también los que NO tomás: sin esos no se puede "
            "medir la fuente.", parse_mode="HTML")
        return
    try:
        parsed = parse_bet_text(text, now=datetime.now(timezone.utc), source="telegram",
                                paper=paper)
        parsed.bet.chat_id = update.effective_chat.id if update.effective_chat else None
        result = _ledger(context).add_bet(parsed.bet)
    except (ParseError, ValueError) as error:
        await update.message.reply_text(f"✘ {escape_html(str(error))}", parse_mode="HTML")
        return
    except Exception:
        logger.exception("Fallo al registrar la apuesta")
        await update.message.reply_text("❌ No pude registrar la apuesta; quedó en el log.")
        return
    notes = list(parsed.notes)
    if _watch_unlinked(context, result.bet):
        notes.append("👁 Lo sumé a /watching: cuando termine el partido la enlazo y la liquido sola.")
    if paper and not parsed.bet.tags:
        notes.append("Sin #fuente: poné una etiqueta para poder medir de dónde vino el pick.")
    await _reply_text_chunks(update.message, render_added(result.bet, result.warnings, notes),
                             parse_mode="HTML")


async def bet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra una apuesta con plata real."""
    if update.message is None:
        return
    await _load(update, context, paper=False)


async def tip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra un pick ajeno sin plata, para medir la fuente."""
    if update.message is None:
        return
    await _load(update, context, paper=True)


async def bets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista las apuestas: abiertas por defecto, `all`, `settled` o `paper`."""
    if update.message is None:
        return
    arg = _args_text(context).lower()
    mode = "paper" if arg in {"paper", "tips", "papel"} else "real"
    if mode == "paper":
        arg = "all"
    status = (None if arg in {"all", "todas"}
              else "open" if arg in {"", "open", "abiertas"}
              else "settled" if arg in {"settled", "liquidadas", "cerradas"}
              else STATUS_FROM_ES.get(arg, arg))
    bets = _ledger(context).repository.list_bets(status=status, mode=mode, limit=15)
    if not bets:
        await update.message.reply_text("No hay apuestas con ese filtro. /bets all para ver todo.")
        return
    await _reply_text_chunks(update.message, "\n\n".join(render_bet(bet) for bet in bets),
                             parse_mode="HTML")


async def view_bet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detalle de una apuesta: cuota vista, CLV y resultado."""
    if update.message is None:
        return
    bet_id = _bet_id(context)
    bet = _ledger(context).repository.get_bet(bet_id) if bet_id is not None else None
    if bet is None:
        await update.message.reply_text("Uso: <code>/view_bet &lt;número&gt;</code>",
                                        parse_mode="HTML")
        return
    await _reply_text_chunks(update.message, render_bet(bet), parse_mode="HTML")


async def settle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Liquida a mano lo que el sistema no puede cerrar solo."""
    if update.message is None:
        return
    args = context.args or []
    bet_id = _bet_id(context)
    if bet_id is None or len(args) < 2:
        await update.message.reply_text(
            "Uso: <code>/settle &lt;n&gt; " + "|".join(SETTLE_STATUSES) +
            " [monto cobrado]</code>", parse_mode="HTML")
        return
    status = STATUS_FROM_ES.get(args[1].lower(), args[1].lower())
    try:
        amount = float(args[2].replace(",", ".")) if len(args) > 2 else None
        bet = _ledger(context).settle_manual(bet_id, status, return_amount=amount)
    except ValueError as error:
        await update.message.reply_text(f"✘ {escape_html(str(error))}", parse_mode="HTML")
        return
    await _reply_text_chunks(update.message, render_bet(bet), parse_mode="HTML")


async def void_bet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Anula una apuesta mal cargada. Queda registrada, fuera de los reportes."""
    if update.message is None:
        return
    bet_id = _bet_id(context)
    if bet_id is None:
        await update.message.reply_text("Uso: <code>/void_bet &lt;n&gt; [motivo]</code>",
                                        parse_mode="HTML")
        return
    reason = " ".join((context.args or [])[1:]) or "anulada por el usuario"
    try:
        bet = _ledger(context).void_bet(bet_id, reason)
    except ValueError as error:
        await update.message.reply_text(f"✘ {escape_html(str(error))}", parse_mode="HTML")
        return
    await _reply_text_chunks(
        update.message, "Anulada (queda registrada, fuera de los reportes):\n" + render_bet(bet),
        parse_mode="HTML")


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reporte del período: hoy, ayer, semana, mes (o la semana / el mes pasado)."""
    if update.message is None:
        return
    from services.ledger import report_window
    from services.timezones import resolve_chat_timezone

    period = (context.args or ["day"])[0].lower()
    chat_id = update.effective_chat.id if update.effective_chat else None
    try:
        since, until, label = report_window(period, now=datetime.now(timezone.utc),
                                            tz=resolve_chat_timezone(chat_id))
    except ValueError as error:
        await update.message.reply_text(f"✘ {escape_html(str(error))}", parse_mode="HTML")
        return
    report = _ledger(context).report(since, until, chat_id=chat_id, label=label)
    await _reply_text_chunks(update.message, render_report(report), parse_mode="HTML")


async def exposure_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Qué hay en juego ahora y cómo viene el día."""
    if update.message is None:
        return
    await _reply_text_chunks(update.message, render_exposure(_ledger(context).exposure()),
                             parse_mode="HTML")


async def set_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fija un límite de riesgo propio. El sistema avisa; nunca bloquea."""
    if update.message is None:
        return
    ledger = _ledger(context)
    args = context.args or []
    if len(args) != 2:
        current = {k: v for k, v in ledger.repository.get_limits().items() if v is not None}
        await update.message.reply_text(
            "Uso: <code>/set_limit &lt;clave&gt; &lt;valor|none&gt;</code>\n"
            "Claves: " + " · ".join(LIMIT_KEYS_SHOWN) + "\n"
            "Actuales: " + (", ".join(f"{k}={v:g}" for k, v in current.items()) or "ninguno") +
            "\n<i>Los límites avisan, no bloquean.</i>", parse_mode="HTML")
        return
    key = LIMIT_ALIASES.get(args[0].lower(), args[0].lower())
    if key not in DEFAULT_LIMITS:
        await update.message.reply_text(f"✘ No conozco el límite '{escape_html(args[0])}'.",
                                        parse_mode="HTML")
        return
    try:
        value = None if args[1].lower() in {"none", "ninguno", "-"} else float(args[1].replace(",", "."))
        ledger.set_limit(key, value)
    except ValueError as error:
        await update.message.reply_text(f"✘ {escape_html(str(error))}", parse_mode="HTML")
        return
    await update.message.reply_text(f"Listo: {escape_html(args[0])} = {escape_html(args[1])}")


async def help_bets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ayuda de la sección de apuestas."""
    del context
    if update.message is not None:
        await update.message.reply_text(HELP_BETS_MESSAGE, parse_mode="HTML")


#: Comando → handler. Una sola fuente para registrar y para testear los nombres.
BET_COMMANDS = (
    ("bet", bet_command),
    ("tip", tip_command),
    ("bets", bets_command),
    ("view_bet", view_bet_command),
    ("settle", settle_command),
    ("void_bet", void_bet_command),
    ("exposure", exposure_command),
    ("report", report_command),
    ("set_limit", set_limit_command),
    ("help_bets", help_bets_command),
)


def register_bet_handlers(application: Application) -> None:
    """Registra los comandos del libro. Se llama ANTES del catch-all de desconocidos."""
    for name, handler in BET_COMMANDS:
        application.add_handler(CommandHandler(name, handler))

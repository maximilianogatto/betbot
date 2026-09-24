"""Cómo se muestran las apuestas en Telegram.

Separado de los handlers para que el texto se pueda probar sin Telegram, y de
los services para que el dominio no sepa de HTML.
"""

from __future__ import annotations

from html import escape
from typing import Any

from core.betting.models import Bet, BetLeg


def escape_html(text: Any) -> str:
    """Igual que handlers.common.escape_html (sin escapar comillas). Local para que el
    renderer no cargue el paquete de handlers, que a su vez importa este módulo."""
    return escape(str(text or ""), quote=False)


STATUS_ES = {
    "open": "abierta", "won": "ganada", "lost": "perdida", "half_won": "medio ganada",
    "half_lost": "medio perdida", "push": "devuelta", "void": "anulada", "cashout": "cashout",
}
#: Lo que el usuario escribe -> estado interno. Acepta variantes con y sin tilde.
STATUS_FROM_ES = {
    "abierta": "open", "ganada": "won", "gano": "won", "ganó": "won", "perdida": "lost",
    "perdio": "lost", "perdió": "lost", "medio_ganada": "half_won", "medio_perdida": "half_lost",
    "devuelta": "push", "nula": "push", "anulada": "void", "cashout": "cashout",
}
MARKET_ES = {
    "asian_handicap": "Hcp", "goal_line": "Total", "1x2": "1X2", "btts": "Ambos marcan",
    "team_total_home": "Total local", "team_total_away": "Total visita",
    "double_chance": "Doble op.", "draw_no_bet": "DNB", "ht_ft": "Desc/Final",
    "both_halves_over": "Ambas mitades más de",
}
SIDE_ES = {"home": "local", "away": "visita", "draw": "empate", "over": "más",
           "under": "menos", "yes": "sí", "no": "no", "team": "equipo"}
_HT_FT_ES = {"1": "local", "x": "empate", "2": "visita"}


def _money(value: float | None, currency: str = "USD") -> str:
    return "—" if value is None else f"{value:+.2f} {currency}"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.1f}%"


def leg_line(leg: BetLeg) -> str:
    market = MARKET_ES.get(leg.market_type, leg.market_type)
    if leg.market_type == "ht_ft":
        side = "/".join(_HT_FT_ES.get(code, code) for code in str(leg.side).split("/"))
    elif leg.side == "home" and leg.home:
        side = leg.home
    elif leg.side == "away" and leg.away:
        side = leg.away
    else:
        side = SIDE_ES.get(leg.side, leg.side)
    line = "" if leg.line is None else (
        f" {leg.line:+g}" if leg.market_type == "asian_handicap" else f" {leg.line:g}")
    period = "" if leg.market_period == "FT" else f" {leg.market_period}"
    when = "pre" if leg.placed_phase == "prematch" else (
        f"{leg.placed_minute}'" if leg.placed_minute is not None else "en vivo")
    score = "" if leg.placed_home_score is None or leg.placed_phase == "prematch" else \
        f" ({leg.placed_home_score}-{leg.placed_away_score})"
    match = f"{leg.home} vs {leg.away}" if leg.home else leg.match_label
    if not leg.external_event_id:
        match += " (sin enlazar)"
    # Las patas de un Bet Builder no tienen cuota propia (la casa da sólo la combinada).
    odds = f" @{leg.odds:g}" if leg.odds else ""
    if leg.market_type == "both_halves_over":
        # Es una pregunta sí/no sobre la línea: "Ambas mitades más de 1.5: no".
        selection = f"{market}{line}{period}: {side}"
    else:
        selection = f"{market}{period} {side}{line}"
    return escape_html(f"{match} · {selection}{odds} · {when}{score}")


def render_bet(bet: Bet) -> str:
    paper = " · 📝 papel" if bet.mode == "paper" else ""
    head = (f"<b>#{bet.id}</b>{paper} · {STATUS_ES.get(bet.status, bet.status)} · "
            f"{bet.stake:g} {bet.currency} @{bet.odds_total:g}")
    if bet.bookmaker:
        head += f" · {escape_html(bet.bookmaker)}"
    lines = [head]
    for leg in bet.legs:
        extra = []
        if leg.observed_odds:
            extra.append(f"vista @{leg.observed_odds:g}")
        if leg.clv is not None:
            extra.append(f"CLV {_pct(leg.clv)}")
        elif leg.closing_line is not None and leg.closing_line != leg.line:
            extra.append(f"la línea cerró en {leg.closing_line:+g}")
        lines.append("  • " + leg_line(leg) + (f"  <i>[{', '.join(extra)}]</i>" if extra else ""))
    if bet.is_settled:
        result = _money(bet.profit, bet.currency)
        if bet.currency not in {"USD", "U"} and bet.profit_usd is not None:
            result += f" ({_money(bet.profit_usd)})"
        lines.append(f"  Resultado: <b>{result}</b>")
    if bet.notes:
        lines.append(f"  <i>{escape_html(bet.notes)}</i>")
    return "\n".join(lines)


def render_settled(bet: Bet) -> str:
    """Aviso del job cuando una apuesta se cierra sola al terminar el partido."""
    return "🏁 <b>Apuesta liquidada</b>\n" + render_bet(bet)


def render_added(bet: Bet, warnings: list[str], parse_notes: list[str]) -> str:
    title = "📝 Tip registrado en papel" if bet.mode == "paper" else "✅ Apuesta registrada"
    text = [title, render_bet(bet)]
    notes = [*parse_notes, *warnings]
    if notes:
        text.append("")
        text.extend(f"• {escape_html(note)}" for note in notes)
    text.append(f"\nSi algo quedó mal: <code>/void_bet {bet.id}</code>")
    return "\n".join(text)


def render_report(report: dict[str, Any], *, title: str = "Reporte") -> str:
    """Reporte de un período (día, semana, mes) para Telegram."""
    settled, placed = report["settled"], report["placed"]
    lines = [f"📊 <b>{escape_html(title)} · {escape_html(report['label'])}</b>"]
    extra = "".join(f" + {v:,.0f} {k}".replace(",", ".") for k, v in placed["without_usd"].items())
    lines.append(f"Cargadas: {placed['bets']} · {placed['stake_usd']:.2f} USD{extra}")
    if settled["bets"] or settled["void"] or settled["without_usd"]:
        counts = " · ".join(f"{icon} {settled[key]}" for key, icon in (
            ("won", "✅"), ("half_won", "½✅"), ("push", "↩️"), ("half_lost", "½❌"),
            ("lost", "❌"), ("cashout", "💸"), ("void", "🚫")) if settled[key])
        roi = f" · ROI {_pct(settled['roi'])}" if settled["roi"] is not None else ""
        lines.append(f"Liquidadas: {settled['bets']} ({counts}) · <b>{_money(settled['profit_usd'])}</b>{roi}")
        for currency, profit in settled["without_usd"].items():
            lines.append(f"  sin cotizar: {_money(profit, currency)}")
        for key, name in (("by_bookmaker", "Por casa"), ("by_tag", "Por etiqueta"),
                          ("by_market", "Por mercado")):
            groups = report[key][:6]
            if len(groups) > 1 or (groups and key != "by_market"):
                lines.append(f"{name}: " + " · ".join(
                    f"{escape_html(MARKET_ES.get(g['name'], g['name']))} {g['profit_usd']:+.2f} ({g['bets']})"
                    for g in groups))
        for key, name in (("best", "Mejor"), ("worst", "Peor")):
            bet = report[key]
            if bet:
                lines.append(f"{name}: #{bet['id']} {escape_html(bet['match'])} "
                             f"({escape_html(bet['bookmaker'] or '?')}) {bet['profit_usd']:+.2f}")
    else:
        lines.append("Sin apuestas liquidadas.")
    lines.append(f"Abiertas: {report['open']['bets']} · {report['open']['stake_usd']:.2f} USD en juego")
    if report["tips"]:
        lines.append("Tips (papel): " + " · ".join(
            f"#{escape_html(t['source'])} {t['tips']} → {t['units']:+.2f}u" for t in report["tips"][:6]))
    return "\n".join(lines)


def render_exposure(exposure: dict[str, Any]) -> str:
    lines = [f"💼 <b>Abiertas:</b> {exposure['open_bets']} · en juego "
             f"{exposure['open_stake_usd']:.2f} USD · hoy {_money(exposure['today_pnl_usd'])} "
             f"({exposure['today_settled']} liquidadas)"]
    for label, values in list(exposure["by_match"].items())[:10]:
        lines.append(f"  {escape_html(label)}: {values['stake_usd']:.2f} USD "
                     f"en {values['bets']} apuesta(s)")
    for scenario, stake in exposure["by_scenario"].items():
        lines.append(f"  <i>escenario</i> {escape_html(scenario)}: {stake:.2f} USD")
    limits = {k: v for k, v in exposure["limits"].items() if v is not None}
    lines.append("<b>Límites:</b> " + (", ".join(f"{k}={v:g}" for k, v in limits.items())
                                       if limits else "ninguno (/set_limit para fijarlos)"))
    return "\n".join(lines)

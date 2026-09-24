"""Liquidación de apuestas a partir del resultado. Dominio puro: sin storage.

Convenciones (las mismas que la tabla ``bet_legs``):

- ``line`` está expresada desde el lado elegido, como la muestra la casa:
  local -2.5 / visitante +2.5; en totales, la línea del total (4.5).
- Líneas de cuarto (-0.25, -0.75, 2.25...) se parten en dos medias apuestas
  de ±0.25, y el resultado es el promedio: así aparecen "medio ganada" y
  "medio perdida".
- ``handicap_from="placement"``: regla asiática in-play de algunas casas. Sólo
  cuentan los goles posteriores a la apuesta. Aplica al handicap asiático y al
  empate-no-válido; los totales siempre cuentan todos los goles del período.

``payout_factor`` es el retorno por unidad apostada: 0 perdida, 1 devuelta,
``odds`` ganada, y los intermedios para medias.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

Score = tuple[int, int]

HANDICAP_MARKETS = {"asian_handicap", "draw_no_bet"}


@dataclass(frozen=True)
class LegResult:
    status: str          # won | half_won | push | half_lost | lost
    payout_factor: float


def period_score(period: str, *, final: Optional[Score], halftime: Optional[Score]) -> Optional[Score]:
    """Marcador que decide un mercado de ese período, o None si todavía no se sabe."""
    if period == "HT":
        return halftime
    if period == "FT":
        return final
    if period == "2H":
        if final is None or halftime is None:
            return None
        return final[0] - halftime[0], final[1] - halftime[1]
    return None


def _remaining(period: str, score: Score, placement: Score, halftime: Optional[Score]) -> Score:
    """Goles del período posteriores a la apuesta (regla asiática in-play)."""
    if period == "2H":
        # Apostado antes del 2º tiempo: todo el 2º tiempo cuenta. Apostado
        # durante: sólo lo que vino después. En ambos casos, desde el máximo
        # entre el marcador al descanso y el marcador al apostar.
        base = (max(placement[0], halftime[0]), max(placement[1], halftime[1])) if halftime else placement
        full = (score[0] + (halftime[0] if halftime else 0), score[1] + (halftime[1] if halftime else 0))
        return full[0] - base[0], full[1] - base[1]
    return score[0] - placement[0], score[1] - placement[1]


def _unit(diff: float) -> str:
    if diff > 0:
        return "won"
    if diff < 0:
        return "lost"
    return "push"


def _split(line: float) -> tuple[float, ...]:
    """-0.75 -> (-0.5, -1.0); -1.0 -> (-1.0,)."""
    quarters = round(line * 4)
    if quarters % 2 == 0:
        return (line,)
    return (line - 0.25, line + 0.25)


def _combine(outcomes: list[str], odds: float) -> LegResult:
    factors = {"won": odds, "push": 1.0, "lost": 0.0}
    factor = sum(factors[o] for o in outcomes) / len(outcomes)
    if len(outcomes) == 1 or outcomes[0] == outcomes[1]:
        status = outcomes[0]
    elif set(outcomes) == {"won", "push"}:
        status = "half_won"
    elif set(outcomes) == {"lost", "push"}:
        status = "half_lost"
    else:  # won + lost no ocurre con cuartos, pero por las dudas
        status = "half_won" if factor >= 1 else "half_lost"
    return LegResult(status=status, payout_factor=round(factor, 6))


def settle_leg(
    *,
    market_type: str,
    market_period: str,
    side: str,
    line: Optional[float],
    odds: float,
    final: Optional[Score],
    halftime: Optional[Score],
    placement: Optional[Score] = None,
    handicap_from: str = "full",
) -> Optional[LegResult]:
    """Resultado de una pata, o None si falta información o el mercado no se conoce.

    None nunca es "perdida": significa "liquidar a mano".
    """
    score = period_score(market_period, final=final, halftime=halftime)
    if score is None:
        return None
    home, away = score

    if market_type in HANDICAP_MARKETS:
        if handicap_from == "placement":
            if placement is None:
                return None
            home, away = _remaining(market_period, score, placement, halftime)
        handicap = 0.0 if market_type == "draw_no_bet" else line
        if handicap is None or side not in {"home", "away"}:
            return None
        margin = home - away if side == "home" else away - home
        return _combine([_unit(margin + part) for part in _split(handicap)], odds)

    if market_type in {"goal_line", "team_total_home", "team_total_away"}:
        if line is None or side not in {"over", "under"}:
            return None
        goals = {"goal_line": home + away, "team_total_home": home, "team_total_away": away}[market_type]
        sign = 1 if side == "over" else -1
        return _combine([_unit(sign * (goals - part)) for part in _split(line)], odds)

    if market_type == "1x2":
        winner = "home" if home > away else "away" if away > home else "draw"
        return _combine(["won" if side == winner else "lost"], odds)

    if market_type == "ht_ft":
        # Descanso/Final: "2/2" = visita gana el 1er tiempo y el partido.
        if final is None or halftime is None or side.count("/") != 1:
            return None
        code = lambda h, a: "1" if h > a else "2" if a > h else "x"
        actual = f"{code(*halftime)}/{code(*final)}"
        return _combine(["won" if side.lower() == actual else "lost"], odds)

    if market_type == "double_chance":
        covered = {"1x": home >= away, "x2": away >= home, "12": home != away}.get(side)
        return None if covered is None else _combine(["won" if covered else "lost"], odds)

    if market_type == "btts":
        both = home > 0 and away > 0
        if side not in {"yes", "no"}:
            return None
        return _combine(["won" if both == (side == "yes") else "lost"], odds)

    return None


def combine_ticket(leg_results: list[LegResult]) -> tuple[str, float]:
    """Estado y factor de retorno de un ticket (simple o combinada).

    En una combinada el factor es el producto de las patas: una pata devuelta
    multiplica por 1, una medio perdida por 0.5.
    """
    factor = 1.0
    for result in leg_results:
        factor *= result.payout_factor
    factor = round(factor, 6)
    if len(leg_results) == 1:
        return leg_results[0].status, factor
    # Por estado y no sólo por el producto: las patas de un Bet Builder no tienen
    # cuota propia (factor 0 aunque ganen) y el ticket paga la cuota combinada.
    if any(r.status == "lost" for r in leg_results):
        return "lost", 0.0
    if all(r.status == "won" for r in leg_results):
        return "won", factor
    if factor == 0:
        return "lost", factor
    if factor == 1:
        return "push", factor
    if all(r.status == "won" for r in leg_results):
        return "won", factor
    return ("half_won" if factor > 1 else "half_lost"), factor

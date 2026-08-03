"""Línea justa a partir de intensidades de gol — matemática pura, sin red ni numpy.

Dado ``lam_home``/``lam_away`` (las intensidades del modelo de goles, entrenado
en ``research/`` y servido por ``services.prediction``), deriva las magnitudes con
las que se apuesta: 1X2, over/under, BTTS, total esperado y hándicap justo.

Vive en ``core`` porque es dominio puro (una función de dos números a una línea).
Python estándar solamente (el runtime del bot no tiene numpy/scipy).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MAX_GOALS = 10  # truncamiento de la matriz de marcadores; nórdicas ~1.2-1.9/lado


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _side_pmf(lam: float, max_goals: int = MAX_GOALS) -> list[float]:
    """PMF por lado sobre {0..max_goals} con bin de cola en max_goals (suma 1)."""
    p = [_poisson_pmf(k, lam) for k in range(max_goals)]
    p.append(max(0.0, 1.0 - sum(p)))  # cola P(Y>=max_goals)
    return p


@dataclass(frozen=True)
class FairLine:
    """Línea que el modelo considera justa para un partido."""

    lam_home: float
    lam_away: float
    p_home: float
    p_draw: float
    p_away: float
    p_over25: float
    p_under25: float
    p_btts: float
    expected_total_goals: float      # λ_home + λ_away
    expected_supremacy: float        # λ_home − λ_away (diferencia esperada)
    fair_handicap: float             # hándicap asiático que equilibra el partido
    fair_goal_line: float            # línea de goles que parte 50/50 el over/under

    def as_dict(self) -> dict:
        return {
            "lam_home": round(self.lam_home, 4),
            "lam_away": round(self.lam_away, 4),
            "p_home": round(self.p_home, 4),
            "p_draw": round(self.p_draw, 4),
            "p_away": round(self.p_away, 4),
            "p_over25": round(self.p_over25, 4),
            "p_under25": round(self.p_under25, 4),
            "p_btts": round(self.p_btts, 4),
            "expected_total_goals": round(self.expected_total_goals, 3),
            "expected_supremacy": round(self.expected_supremacy, 3),
            "fair_handicap": round(self.fair_handicap, 2),
            "fair_goal_line": round(self.fair_goal_line, 2),
        }


def _fair_handicap(diff: dict[int, float]) -> float:
    """Hándicap asiático justo para el LOCAL (línea de cuarto que equilibra el AH).

    Home -h cubre si (goles_home − goles_away) > h; visita cubre si < h. El
    hándicap justo es el h que minimiza |P(local cubre) − P(visita cubre)|.
    Simétrico → 0; local favorito → negativo (da goles). Desempate: menor |h|.
    """
    best_h, best_gap = 0.0, float("inf")
    for i in range(-24, 25):  # −6.0 … +6.0 en pasos de 0.25
        h = i * 0.25
        p_home = sum(p for d, p in diff.items() if d > h)
        p_away = sum(p for d, p in diff.items() if d < h)
        gap = abs(p_home - p_away)
        if gap < best_gap - 1e-12 or (abs(gap - best_gap) <= 1e-12 and abs(h) < abs(best_h)):
            best_gap, best_h = gap, h
    return -best_h  # como se cotiza: hándicap del local


def _fair_total_line(total: dict[int, float]) -> float:
    """Línea de goles justa: la media-línea (x.5) con over/under más cerca de 50/50."""
    best_g, best_gap = 0.5, float("inf")
    max_total = max(total)
    g = 0.5
    while g <= max_total + 0.5:
        p_over = sum(p for k, p in total.items() if k > g)
        gap = abs(p_over - 0.5)
        if gap < best_gap:
            best_gap, best_g = gap, g
        g += 1.0
    return best_g


def fair_line(lam_home: float, lam_away: float, *, max_goals: int = MAX_GOALS,
              current_home: int = 0, current_away: int = 0) -> FairLine:
    """Línea justa desde intensidades. Con ``current_*`` es la línea EN VIVO del
    resultado final: goles finales = marcador actual + goles restantes (Poisson
    con ``lam_*`` = intensidad RESTANTE). Sin marcador (default 0-0) es pre-match.
    """
    ph = _side_pmf(lam_home, max_goals)   # goles restantes por lado
    pa = _side_pmf(lam_away, max_goals)
    ch, ca = current_home, current_away

    p_home = p_draw = p_away = 0.0
    p_over25 = p_btts = 0.0
    diff: dict[int, float] = {}
    total: dict[int, float] = {}
    for i, pi in enumerate(ph):
        for j, pj in enumerate(pa):
            m = pi * pj
            fh, fa = ch + i, ca + j                 # marcador final
            if fh > fa:
                p_home += m
            elif fh == fa:
                p_draw += m
            else:
                p_away += m
            if fh + fa >= 3:
                p_over25 += m
            if fh >= 1 and fa >= 1:
                p_btts += m
            diff[fh - fa] = diff.get(fh - fa, 0.0) + m
            total[fh + fa] = total.get(fh + fa, 0.0) + m

    return FairLine(
        lam_home=lam_home, lam_away=lam_away,
        p_home=p_home, p_draw=p_draw, p_away=p_away,
        p_over25=p_over25, p_under25=1.0 - p_over25, p_btts=p_btts,
        expected_total_goals=(ch + ca) + lam_home + lam_away,
        expected_supremacy=(ch - ca) + lam_home - lam_away,
        fair_handicap=_fair_handicap(diff),
        fair_goal_line=_fair_total_line(total),
    )

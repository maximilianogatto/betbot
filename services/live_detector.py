"""Producto B — detector de error grosero en vivo (plan §9).

Compara la línea que el modelo considera justa **para la situación en vivo**
(expectativa RESTANTE + marcador actual) contra la línea que publica la casa, y
avisa sólo cuando la diferencia es grosera y el estado que ve el modelo está
fresco. Python puro (capa services); usa ``core.fair_line`` y consume la salida
de ``services.prediction``. No toca el esquema.

La clave (plan §9): NO se compara la línea pre-match cruda contra la de la casa.
Si va 0-3 al minuto 60, el −4.5 pre-match no significa nada; el detector
recalcula la intensidad restante y suma el marcador, así que no dispara ahí.

Salvaguardas:
- **Estado fresco**: una discrepancia grande muchas veces NO es error de la casa,
  es que la casa sabe algo que el modelo no (lesión, expulsión no capturada, feed
  atrasado). Si el estado no es reciente, no se alerta.
- **Umbral alto**: busca errores groseros, no ventajas de 2%.
- **Todo evaluación se devuelve** (disparó o no) para poder medir la tasa de
  falsos positivos, no estimarla de memoria.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.fair_line import FairLine, fair_line

TOTAL_MINUTES = 90


@dataclass(frozen=True)
class LiveState:
    minute: int
    current_home: int
    current_away: int
    red_home: int = 0
    red_away: int = 0
    state_age_seconds: float = 0.0   # antigüedad del snapshot que ve el modelo


@dataclass(frozen=True)
class DetectorParams:
    edge_threshold: float = 0.30       # diferencia p_modelo − q_casa para "grosero"
    model_prob_floor: float = 0.55     # el modelo debe estar razonablemente seguro
    max_staleness_seconds: float = 120.0
    red_self_mult: float = 0.75        # cada roja baja el ataque restante propio
    red_opp_mult: float = 1.15         # y sube el del rival
    min_remaining_minutes: int = 5     # con muy poco tiempo no tiene sentido


@dataclass(frozen=True)
class DetectionResult:
    fired: bool
    reason: str
    outcome: str | None            # 'H' | 'D' | 'A' donde el modelo ve el error
    edge: float                    # p_modelo − q_casa en ese outcome
    model_probs: tuple[float, float, float]
    book_probs: tuple[float, float, float] | None
    live_line: FairLine


def remaining_intensities(pre_lam_home: float, pre_lam_away: float, state: LiveState,
                          params: DetectorParams) -> tuple[float, float]:
    """Intensidad de gol para lo que queda de partido (tasa constante + rojas)."""
    rem = max(0.0, (TOTAL_MINUTES - min(state.minute, TOTAL_MINUTES)) / TOTAL_MINUTES)
    lam_h = pre_lam_home * rem
    lam_a = pre_lam_away * rem
    # rojas: bajan el ataque del sancionado, suben el del rival
    lam_h *= params.red_self_mult ** state.red_home * params.red_opp_mult ** state.red_away
    lam_a *= params.red_self_mult ** state.red_away * params.red_opp_mult ** state.red_home
    return lam_h, lam_a


def live_fair_line(pre_lam_home: float, pre_lam_away: float, state: LiveState,
                   params: DetectorParams) -> FairLine:
    lam_h, lam_a = remaining_intensities(pre_lam_home, pre_lam_away, state, params)
    return fair_line(lam_h, lam_a,
                     current_home=state.current_home, current_away=state.current_away)


def evaluate_from_prediction(prediction, state: LiveState,
                             book_odds: tuple[float, float, float] | None,
                             params: DetectorParams | None = None) -> DetectionResult:
    """Seam PredictionService→detector: usa las λ pre-match del ``Prediction``.

    ``prediction`` es el DTO de ``services.prediction.PredictionService.predict``;
    de ahí salen las intensidades pre-match sobre las que el detector recalcula la
    situación en vivo. Así el orquestador no desarma el DTO a mano.
    """
    return evaluate(prediction.line.lam_home, prediction.line.lam_away,
                    state, book_odds, params)


def implied_probs(odds_home: float, odds_draw: float, odds_away: float
                  ) -> tuple[float, float, float]:
    """Probabilidades implícitas de la casa sin margen: q_r = (1/o_r)/Σ(1/o_s)."""
    inv = [1.0 / o for o in (odds_home, odds_draw, odds_away)]
    s = sum(inv)
    return inv[0] / s, inv[1] / s, inv[2] / s


def evaluate(pre_lam_home: float, pre_lam_away: float, state: LiveState,
             book_odds: tuple[float, float, float] | None,
             params: DetectorParams | None = None) -> DetectionResult:
    """Evalúa la situación en vivo. Siempre devuelve un resultado (disparó o no)."""
    params = params or DetectorParams()
    line = live_fair_line(pre_lam_home, pre_lam_away, state, params)
    model = (line.p_home, line.p_draw, line.p_away)

    def result(fired, reason, outcome=None, edge=0.0, book=None):
        return DetectionResult(fired, reason, outcome, edge, model, book, line)

    remaining = TOTAL_MINUTES - min(state.minute, TOTAL_MINUTES)
    if remaining < params.min_remaining_minutes:
        return result(False, f"quedan {remaining}min (<{params.min_remaining_minutes})")
    if state.state_age_seconds > params.max_staleness_seconds:
        return result(False, f"estado rancio ({state.state_age_seconds:.0f}s): la casa "
                             "puede saber algo que el modelo no")
    if book_odds is None or any(o <= 1.0 for o in book_odds):
        return result(False, "sin cuotas 1X2 en vivo válidas")

    book = implied_probs(*book_odds)
    edges = [model[k] - book[k] for k in range(3)]
    k = max(range(3), key=lambda i: edges[i])
    outcome = "HDA"[k]
    if edges[k] >= params.edge_threshold and model[k] >= params.model_prob_floor:
        return result(True, f"la casa precia {outcome} en {book[k]:.0%} y el modelo "
                            f"en {model[k]:.0%} (edge {edges[k]:+.0%})",
                      outcome=outcome, edge=edges[k], book=book)
    return result(False, f"máxima discrepancia {outcome} edge {edges[k]:+.0%} "
                        f"(<{params.edge_threshold:.0%} o modelo poco seguro)",
                  outcome=outcome, edge=edges[k], book=book)

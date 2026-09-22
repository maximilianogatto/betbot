"""Aplana el ``markets_payload`` de un evento a filas por (mercado, línea, lado).

Los extractores normalizan las cuotas a una misma forma: ``1x2`` plano,
``asian_handicap`` / ``goal_line`` con ``selections``, y ``alternative_markets``
como lista de mercados con nombre (ahí aparecen los de primer tiempo). El
archivo histórico guarda ese payload tal cual; para leerlo —seguir una línea en
el tiempo, buscar la cuota de cierre de un mercado puntual, calcular CLV— hace
falta explotarlo a filas.

Puro y sin dependencias: es dominio, no almacenamiento.
"""

from __future__ import annotations

from collections import defaultdict
import re
import unicodedata
from typing import Any, Optional

_HALF_RE = re.compile(
    r"1st half|first half|half[ -]?time|1(?:ª|a|er|°)? ?(?:parte|tiempo)|primer tiempo|\b1h\b",
    re.IGNORECASE,
)


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _slug(value: Any) -> str:
    return _normalize(value).replace(" ", "_") or "unknown"


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace("+", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def market_period(name: Any) -> str:
    """``HT`` para mercados de primer tiempo, ``FT`` para el resto."""
    return "HT" if _HALF_RE.search(str(name or "")) else "FT"


def market_type(name: Any) -> str:
    normalized = _normalize(name)
    if "handicap" in normalized:
        return "asian_handicap"
    if "goal line" in normalized or "total" in normalized or "over under" in normalized:
        return "goal_line"
    if "both teams" in normalized:
        return "btts"
    return _slug(name)


def selection_side(selection: Any, *, home: str, away: str) -> str:
    """Texto de la selección -> lado canónico (home/away/draw/over/under/yes/no)."""
    normalized = _normalize(selection)
    if normalized in {"1", "home", "local"} or (normalized and normalized == _normalize(home)):
        return "home"
    if normalized in {"2", "away", "visitante"} or (normalized and normalized == _normalize(away)):
        return "away"
    if normalized in {"x", "draw", "empate"}:
        return "draw"
    if normalized.startswith(("over", "mas", "más")):
        return "over"
    if normalized.startswith(("under", "menos")):
        return "under"
    if normalized in {"yes", "si", "sí"}:
        return "yes"
    if normalized == "no":
        return "no"
    return _slug(selection)


def _selection_rows(market: dict[str, Any], *, kind: str, period: str,
                    home: str, away: str) -> list[dict[str, Any]]:
    rows = []
    for selection in market.get("selections") or []:
        if not isinstance(selection, dict):
            continue
        odds = _to_float(selection.get("odds"))
        if odds is None:
            continue
        rows.append({
            "market_type": kind,
            "market_period": period,
            "line": _to_float(selection.get("line")),
            "side": selection_side(selection.get("selection"), home=home, away=away),
            "odds": odds,
        })
    return rows


def flatten_markets(markets: dict[str, Any] | None, *, home: str, away: str) -> list[dict[str, Any]]:
    """Filas ``{market_type, market_period, line, side, odds, overround?}``."""
    if not isinstance(markets, dict):
        return []
    rows: list[dict[str, Any]] = []

    one_x_two = markets.get("1x2")
    if isinstance(one_x_two, dict):
        for side in ("home", "draw", "away"):
            odds = _to_float(one_x_two.get(side))
            if odds is not None:
                rows.append({"market_type": "1x2", "market_period": "FT",
                             "line": None, "side": side, "odds": odds})

    for key, market in markets.items():
        if key in {"1x2", "alternative_markets"} or not isinstance(market, dict):
            continue
        name = market.get("market_name") or key
        rows.extend(_selection_rows(market, kind=market_type(key), period=market_period(name),
                                    home=home, away=away))

    for market in markets.get("alternative_markets") or []:
        if isinstance(market, dict):
            name = market.get("market_name")
            rows.extend(_selection_rows(market, kind=market_type(name), period=market_period(name),
                                        home=home, away=away))

    attach_overround(rows)
    return rows


def attach_overround(rows: list[dict[str, Any]]) -> None:
    """Suma de 1/cuota por mercado completo.

    En handicap la línea del visitante se invierte para emparejarla con la del
    local (-0.5 local con +0.5 visita); si no, cada lado parecería un mercado.
    """
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        line = row["line"]
        if row["market_type"] == "asian_handicap" and line is not None and row["side"] == "away":
            line = -line
        groups[(row["market_type"], row["market_period"], line)].append(row)
    for (kind, _, _), members in groups.items():
        expected = 3 if kind == "1x2" else 2
        if len(members) == expected and len({m["side"] for m in members}) == expected:
            overround = sum(1.0 / m["odds"] for m in members)
            for member in members:
                member["overround"] = round(overround, 5)


def find_market(rows: list[dict[str, Any]], *, market_type: str, market_period: str = "FT",
                side: str, line: float | None = None) -> Optional[dict[str, Any]]:
    """La fila de un mercado puntual, para comparar una apuesta contra el archivo."""
    for row in rows:
        if (row["market_type"] == market_type and row["market_period"] == market_period
                and row["side"] == side and row["line"] == line):
            return row
    return None

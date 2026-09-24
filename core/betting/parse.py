"""Interpreta una apuesta escrita a mano (Telegram) y la convierte en ``BetInput``.

Formato libre, en el orden que sea. Una selección por partido, varias
separadas con `` + `` para una combinada:

    Darwin -2.5 HT @1.66 10usd min 13 megapari
    Darwin vs Palmerston over 2.5 1T @1.60 5.000 ars min 13 con 1-0
    Salisbury -2 @1.68 + Adelaide over 3.5 @1.9 20usdt 20bet #goleada -- nota

Qué reconoce:

- cuota: ``@1.66`` (obligatoria en cada selección)
- monto: ``10usd``, ``10 usdt``, ``5.000 ars``, ``$10`` (``$`` = moneda por defecto)
- mercado: handicap con signo (``-2.5``, ``+1``, ``ah 0``), ``over/under 2.5``
  (también ``o2.5``, ``más de``/``menos de``), ``tt over 3.5`` (total del equipo),
  ``gana``/``ml``, ``empate``, ``1x``/``x2``/``12``, ``dnb``, ``ambos marcan si/no``,
  descanso/final ``G2/G2`` (también ``ht/ft 1/1``, ``x/2``)
- período: ``HT``/``1T``/``PT`` primer tiempo, ``2T``/``ST`` segundo, si no, partido
- momento: ``min 13`` o ``13'`` (en vivo), ``pre`` (antes del partido),
  ``con 1-0`` (marcador al apostar), ``a las 21:15`` (hora, Argentina)
- casa: megapari, melbet, 20bet, bet365... · ``desde``: handicap asiático
  que cuenta sólo goles posteriores a la apuesta
- ``#etiquetas`` y ``-- nota`` al final
- ``papel``: tip registrado sin plata (1u si no se pone monto), para medir una fuente
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import os
import re
from typing import Optional
from zoneinfo import ZoneInfo

from core.betting.models import BOOKMAKER_FAMILIES, BetInput, LegInput
from core.league_naming import team_name_similarity

KNOWN_BOOKMAKERS = sorted(set(BOOKMAKER_FAMILIES), key=len, reverse=True)
_ARG_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

_NUM = r"\d+(?:[.,]\d+)?"
# `u21`, `o19`: categoría (U13-U23), no under/over. Ninguna línea de gol llega a 13.
_NOT_AGE = r"(?!(?:1[3-9]|2[0-3])(?![\d.,]))"
_CURRENCIES = {"usd": "USD", "usdt": "USDT", "u$s": "USD", "us$": "USD", "dolares": "USD",
               "dólares": "USD", "ars": "ARS", "pesos": "ARS"}

_ODDS_RE = re.compile(rf"@\s*({_NUM})")
_STAKE_RE = re.compile(
    rf"(?:(?<![\w.])\$\s*(\d{{1,3}}(?:\.\d{{3}})+|{_NUM})"
    rf"|(\d{{1,3}}(?:\.\d{{3}})+|{_NUM})\s*(usdt|usd|u\$s|us\$|ars|pesos|d[oó]lares)\b"
    rf"|\bstake\s+({_NUM}))",
    re.IGNORECASE,
)
_MINUTE_RE = re.compile(r"(?:\bmin(?:uto)?\.?\s*(\d{1,3})\b['’]?|(?<![\d.@])(\d{1,3})['’])", re.IGNORECASE)
_SCORE_RE = re.compile(r"(?:\bcon\s+|\()(\d{1,2})\s*[-:]\s*(\d{1,2})\)?", re.IGNORECASE)
_CLOCK_RE = re.compile(r"\ba\s+las\s+(\d{1,2})[:.](\d{2})\b", re.IGNORECASE)
_TAG_RE = re.compile(r"#([\wáéíóúñ]+)", re.IGNORECASE)
# "descanso-final G2/G2", "ht/ft 1/1", "d/f x/2", "G2/G2" (G = gana, X/E = empate)
_HTFT_RE = re.compile(
    r"(?:\b(?:ht\s*/\s*ft|htft|descanso\s*[-/]?\s*final|medio\s+tiempo\s*[-/]\s*final|d\s*/\s*f)\b\s*:?\s*)?"
    r"(?<![\w.])g?([12xe])\s*/\s*g?([12xe])(?![\w.])",
    re.IGNORECASE,
)

_PERIOD_PATTERNS = [
    (re.compile(r"\b(?:ht|1t|pt|1er\s+tiempo|primer\s+tiempo|1ª?\s*parte)\b", re.IGNORECASE), "HT"),
    (re.compile(r"\b(?:2t|st|2do\s+tiempo|segundo\s+tiempo|2ª?\s*parte|2h)\b", re.IGNORECASE), "2H"),
    (re.compile(r"\b(?:ft|final)\b", re.IGNORECASE), "FT"),
]


class ParseError(ValueError):
    pass


@dataclass
class ParsedBet:
    bet: BetInput
    notes: list[str] = field(default_factory=list)


def _number(raw: str, *, thousands: bool = False) -> float:
    """``thousands=True`` sólo para montos: "5.000 ars" es 5000. En cuotas y
    líneas NUNCA: "@1.605" es 1.605, no mil seiscientos cinco."""
    raw = raw.strip()
    if thousands and re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
        raw = raw.replace(".", "")
    return float(raw.replace(",", "."))


def _take(pattern: re.Pattern, text: str) -> tuple[Optional[re.Match], str]:
    match = pattern.search(text)
    if not match:
        return None, text
    return match, (text[:match.start()] + " " + text[match.end():])


def _parse_leg(segment: str) -> tuple[LegInput, list[str]]:
    notes: list[str] = []
    text = f" {segment} "

    odds_match, text = _take(_ODDS_RE, text)
    if not odds_match:
        raise ParseError(f"falta la cuota (@1.85) en: '{segment.strip()}'")
    odds = _number(odds_match.group(1))
    if odds <= 1.0:
        raise ParseError(f"cuota inválida: {odds}")

    # Descanso/Final va antes que el período: "HT/FT" y "Descanso-Final"
    # contienen las mismas palabras que marcan un período.
    htft, text = _take(_HTFT_RE, text)
    if htft:
        side = "/".join("x" if g.lower() in {"x", "e"} else g for g in (htft.group(1), htft.group(2)))
        label = re.sub(r"\s+", " ", text).strip(" ,;|")
        if not label:
            raise ParseError(f"falta el partido en: '{segment.strip()}'")
        return LegInput(match_label=label, market_type="ht_ft", side=side, odds=odds,
                        market_period="FT"), notes

    period = "FT"
    for pattern, value in _PERIOD_PATTERNS:
        match, text = _take(pattern, text)
        if match:
            period = value
            break

    market_type: Optional[str] = None
    side: Optional[str] = None
    line: Optional[float] = None

    rules: list[tuple[re.Pattern, callable]] = [
        (re.compile(r"\b(?:ambos\s+(?:equipos\s+)?marcan|btts)\b\s*(s[ií]|no|yes)?", re.IGNORECASE),
         lambda m: ("btts", "no" if (m.group(1) or "si").lower() == "no" else "yes", None)),
        (re.compile(rf"\b(?:tt|total\s+(?:del\s+)?equipo)\s+(over|under|o|u|m[aá]s(?:\s+de)?|menos(?:\s+de)?)\s*({_NUM})",
                    re.IGNORECASE),
         lambda m: ("team_total", "under" if m.group(1).lower().startswith(("u", "menos")) else "over",
                    _number(m.group(2)))),
        (re.compile(rf"\b(over|m[aá]s\s+de|m[aá]s)\s*({_NUM})|\bo{_NOT_AGE}({_NUM})\b", re.IGNORECASE),
         lambda m: ("goal_line", "over", _number(m.group(2) or m.group(3)))),
        (re.compile(rf"\b(under|menos\s+de|menos)\s*({_NUM})|\bu{_NOT_AGE}({_NUM})\b", re.IGNORECASE),
         lambda m: ("goal_line", "under", _number(m.group(2) or m.group(3)))),
        (re.compile(r"\b(dnb|empate\s+no\s+v[aá]lido|draw\s+no\s+bet)\b", re.IGNORECASE),
         lambda m: ("draw_no_bet", "team", None)),
        (re.compile(r"(?<![\w.])(1x|x2|12)(?![\w.])", re.IGNORECASE),
         lambda m: ("double_chance", m.group(1).lower(), None)),
        (re.compile(r"\b(empate|draw)\b", re.IGNORECASE), lambda m: ("1x2", "draw", None)),
        (re.compile(r"\b(gana|ganador|ml|victoria)\b", re.IGNORECASE), lambda m: ("1x2", "team", None)),
        (re.compile(rf"\b(?:ah|hcp|h[aá]ndicap)\s*([+-]?{_NUM})", re.IGNORECASE),
         lambda m: ("asian_handicap", "team", _number(m.group(1).lstrip("+")))),
        (re.compile(rf"(?<![\w.@])([+-]{_NUM})(?![\w.])"),
         lambda m: ("asian_handicap", "team", _number(m.group(1).lstrip("+")))),
    ]
    for pattern, build in rules:
        match = pattern.search(text)
        if match:
            market_type, side, line = build(match)
            text = text[:match.start()] + " " + text[match.end():]
            break
    if market_type is None:
        raise ParseError(f"no reconozco el mercado en: '{segment.strip()}' "
                         "(ej: -2.5, over 2.5, gana, empate, ambos marcan)")

    label = re.sub(r"\s+", " ", text.replace("'", " ").replace("’", " ")).strip(" ,;|")
    if not label:
        raise ParseError(f"falta el equipo o partido en: '{segment.strip()}'")
    has_both_teams = bool(_VS_RE.search(f" {label} "))
    needs_team = side == "team" or market_type == "team_total"
    team = label if needs_team else None
    if needs_team and has_both_teams:
        split = _split_match_and_team(label)
        if split is None:
            raise ParseError(f"en '{segment.strip()}' nombrá sólo el equipo al que apostás, no el partido")
        label, team = split
    return LegInput(match_label=label, market_type=market_type, side=side, odds=odds, line=line,
                    market_period=period, team=team), notes


_VS_RE = re.compile(r"\s(?:vs\.?|v|x|-|–)\s", re.IGNORECASE)
# Marcas de categoría/genéricas: no alcanzan para decir a qué equipo se apostó.
_GENERIC_TEAM_TOKENS = re.compile(
    r"\b(?:w|f|women|fem(?:enino)?|u\d{2}|sub-?\d{2}|ii|iii|b|res(?:erves)?|fc|cf|sc|ac|club)\b",
    re.IGNORECASE)
_TEAM_REPEAT_SIMILARITY = 0.85


def _split_match_and_team(label: str) -> Optional[tuple[str, str]]:
    """``A vs B <equipo>`` -> (``A vs B``, ``<equipo>``) cuando el final repite un lado.

    Es como se anota en el grupo ("San Marino u21 vs Kosovo u21 Kosovou21 -3.5",
    "Bnot Netanya vs ASA Tel Aviv - Asa tel aviv -2.5"). Un separador después del
    partido marca el equipo; si no hay, se elige el corte en el que el final repite
    un lado. El equipo tiene que parecerse claramente a uno de los dos; si no, None
    y se pide sólo el equipo como antes.
    """
    separator = _VS_RE.search(f" {label} ")
    if separator is None:
        return None
    padded = f" {label} "
    home = padded[:separator.start()].strip()
    rest = padded[separator.end():].strip()
    if not home or not rest:
        return None

    explicit = list(_TEAM_SEPARATOR_RE.finditer(rest))
    if explicit:
        away, team = rest[:explicit[-1].start()].strip(), rest[explicit[-1].end():].strip()
        if away and _repeat_key(team, home, away) is not None:
            return f"{home} vs {away}", team

    words = rest.split()
    best: Optional[tuple[tuple, str, str]] = None
    for cut in range(1, len(words)):
        away, team = " ".join(words[:cut]), " ".join(words[cut:])
        key = _repeat_key(team, home, away)
        if key is not None and (best is None or key > best[0]):
            best = (key, away, team)
    if best is None:
        return None
    _, away, team = best
    # "Kosovo u21 San Marino" puede cortar en "Kosovo | u21 San Marino": la marca de
    # categoría pegada al principio del equipo es del visitante.
    team_tokens = team.split()
    while len(team_tokens) > 1 and _GENERIC_TEAM_TOKENS.fullmatch(team_tokens[0]):
        away = f"{away} {team_tokens.pop(0)}"
    return f"{home} vs {away}", " ".join(team_tokens)


_TEAM_SEPARATOR_RE = re.compile(r"\s+(?:-|–|\||/|:)\s+")


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _repeat_key(team: str, home: str, away: str) -> Optional[tuple]:
    """Qué tan claro repite ``team`` a un lado. None si no alcanza.

    Orden: igual al lado sin contar espacios ("Kosovou21" = "Kosovo u21"), después la
    similitud y después cuántas palabras coinciden (así "ASA | Tel Aviv Asa tel aviv"
    pierde contra "ASA Tel Aviv | Asa tel aviv").
    """
    core = _GENERIC_TEAM_TOKENS.sub(" ", team)
    if sum(ch.isalpha() for ch in core) < 3:
        return None
    best = None
    for side in (home, away):
        score = team_name_similarity(team, side)
        if score < _TEAM_REPEAT_SIMILARITY:
            continue
        side_core = _GENERIC_TEAM_TOKENS.sub(" ", side)
        exact = _compact(team) == _compact(side) or _compact(core) == _compact(side_core)
        team_words, side_words = len(core.split()) or 1, len(side_core.split()) or 1
        coverage = min(team_words, side_words) / max(team_words, side_words)
        key = (exact, round(score, 1), coverage, len(team))
        best = key if best is None or key > best else best
    return best


def parse_bet_text(raw: str, *, now: Optional[datetime] = None, source: str = "telegram",
                   paper: bool = False) -> ParsedBet:
    """Texto -> ``BetInput``. Lanza ``ParseError`` con un mensaje para el usuario."""
    text = (raw or "").strip()
    if not text:
        raise ParseError("escribí la apuesta, por ejemplo: Darwin -2.5 HT @1.66 10usd min 13 megapari")
    notes_text = None
    if " -- " in f" {text} ":
        text, notes_text = [part.strip() for part in f" {text} ".split(" -- ", 1)]
    tags = [t.lower() for t in _TAG_RE.findall(text)]
    text = _TAG_RE.sub(" ", text)
    notes: list[str] = []

    # Tip en papel: se registra sin plata, en unidades, para medir la fuente.
    paper_match, text = _take(re.compile(r"\b(?:papel|paper)\b", re.IGNORECASE), f" {text} ")
    paper = paper or bool(paper_match)

    # Datos globales del ticket: pueden estar en cualquier parte del texto.
    stake_match, text = _take(_STAKE_RE, f" {text} ")
    if not stake_match and not paper:
        raise ParseError("falta el monto (ej: 10usd, 5.000 ars, $10)")
    if not stake_match:
        stake, currency = 1.0, "U"
    elif stake_match.group(1):
        stake, currency = _number(stake_match.group(1), thousands=True), os.getenv("LEDGER_DEFAULT_CURRENCY", "USD").upper()
        notes.append(f"'$' se tomó como {currency} (moneda por defecto).")
    elif stake_match.group(2):
        stake, currency = _number(stake_match.group(2), thousands=True), _CURRENCIES[stake_match.group(3).lower()]
    else:
        stake, currency = _number(stake_match.group(4), thousands=True), os.getenv("LEDGER_DEFAULT_CURRENCY", "USD").upper()

    bookmaker = None
    for name in KNOWN_BOOKMAKERS:
        pattern = re.compile(rf"(?:\ben\s+)?\b{re.escape(name)}\b", re.IGNORECASE)
        match, text = _take(pattern, text)
        if match:
            bookmaker = name
            break

    minute_match, text = _take(_MINUTE_RE, text)
    minute = int(minute_match.group(1) or minute_match.group(2)) if minute_match else None
    score_match, text = _take(_SCORE_RE, text)
    score = (int(score_match.group(1)), int(score_match.group(2))) if score_match else None
    clock_match, text = _take(_CLOCK_RE, text)
    prematch_match, text = _take(re.compile(r"\b(?:pre|prematch|previa|pre-?partido)\b", re.IGNORECASE), text)
    from_match, text = _take(re.compile(r"\bdesde\b", re.IGNORECASE), text)
    full_match, text = _take(re.compile(r"\bcompleto\b", re.IGNORECASE), text)

    placed_at = None
    if clock_match:
        local_now = (now or datetime.now(timezone.utc)).astimezone(_ARG_TZ)
        placed_local = local_now.replace(hour=int(clock_match.group(1)), minute=int(clock_match.group(2)),
                                         second=0, microsecond=0)
        if placed_local > local_now:  # "a las 23:50" cargado a las 00:30 es de ayer
            placed_local -= timedelta(days=1)
        placed_at = placed_local.astimezone(timezone.utc).isoformat()

    if prematch_match and minute is not None:
        raise ParseError("dice 'pre' y también un minuto: ¿fue antes o durante el partido?")

    segments = [s for s in re.split(r"\s\+\s", text) if s.strip()]
    legs: list[LegInput] = []
    for segment in segments:
        leg, leg_notes = _parse_leg(segment)
        notes.extend(leg_notes)
        leg.placed_minute = minute
        leg.placed_phase = "prematch" if prematch_match else ("live" if minute is not None else None)
        leg.placed_score = score
        if from_match:
            leg.handicap_from = "placement"
        elif full_match:
            leg.handicap_from = "full"
        legs.append(leg)
    if len(legs) > 1 and minute is not None:
        notes.append("El minuto se aplicó a todas las selecciones de la combinada.")

    bet = BetInput(legs=legs, stake=stake, currency=currency, bookmaker=bookmaker,
                   placed_at=placed_at, source=source, tags=tags, notes=notes_text,
                   mode="paper" if paper else "real")
    return ParsedBet(bet=bet, notes=notes)

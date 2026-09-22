"""Libro de apuestas: tipos, liquidación y lectura de una apuesta escrita a mano.

Todo lo de acá es dominio puro (no toca storage ni Telegram), así que la
liquidación —que es donde más fácil se cuelan errores: líneas de cuarto,
primer tiempo, regla asiática in-play— se puede probar sin levantar nada.
"""

from core.betting.models import (
    BET_STATUSES,
    BOOKMAKER_FAMILIES,
    BOOKMAKER_FEEDS,
    DEFAULT_LIMITS,
    INPLAY_AH_FROM_PLACEMENT,
    USD_LIKE,
    AddBetResult,
    Bet,
    BetInput,
    BetLeg,
    LegInput,
    market_label,
)
from core.betting.parse import ParseError, ParsedBet, parse_bet_text
from core.betting.settlement import LegResult, combine_ticket, period_score, settle_leg

__all__ = [
    "BET_STATUSES", "BOOKMAKER_FAMILIES", "BOOKMAKER_FEEDS", "DEFAULT_LIMITS",
    "INPLAY_AH_FROM_PLACEMENT", "USD_LIKE", "AddBetResult", "Bet", "BetInput", "BetLeg",
    "LegInput", "market_label", "ParseError", "ParsedBet", "parse_bet_text",
    "LegResult", "combine_ticket", "period_score", "settle_leg",
]

"""Tipos del libro de apuestas. Dominio puro: sin storage ni Telegram.

Una apuesta tiene una o más **patas** (una sola = simple; varias = combinada).
La pata es la unidad de análisis: es la que se enlaza a un partido, la que se
liquida y la que después se agrupa por liga, mercado o minuto de entrada.

Dos decisiones que se repiten en todo el módulo:

- **La línea se guarda desde el lado elegido**, como la muestra la casa: local
  -2.5 y visitante +2.5 son dos filas distintas, no una con el signo invertido.
- **El modo `paper`** registra un pick sin plata (1 unidad) para medir una
  fuente de picks sin arriesgar nada. No suma a la exposición ni dispara
  límites, y los reportes lo separan del dinero real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

#: Casa donde se apostó -> extractor del bot que publica los mismos precios.
#: Sin esta correspondencia no hay cuota observada ni CLV para esa apuesta.
BOOKMAKER_FEEDS = {
    "megapari": "1xbet_http", "melbet": "1xbet_http", "betwinner": "1xbet_http",
    "1xbet": "1xbet_http", "spinbetter": "1xbet_http", "paripesa": "1xbet_http",
    "22bet": "1xbet_http", "linebet": "1xbet_http",
    "bet365": "bet365", "mystake": "mystake_http", "solcasino": "solcasino_http",
    "betwarrior": "betwarrior_http", "mrpunter": "mrpunter_http", "betovo": "betovo_http",
    "playzilla": "betovo_http",  # misma plataforma que Betovo
    # 20bet no tiene extractor todavía: la apuesta se registra y se liquida
    # igual, pero queda sin cuota observada ni CLV.
}

#: Familia comercial, para agrupar en los reportes: las "rusas" comparten precio.
BOOKMAKER_FAMILIES = {
    **{name: "rusas" for name, feed in BOOKMAKER_FEEDS.items() if feed == "1xbet_http"},
    "bet365": "bet365",
    "mystake": "independiente", "solcasino": "independiente", "playzilla": "independiente",
    "20bet": "independiente", "betwarrior": "independiente", "mrpunter": "independiente",
    "betovo": "independiente",
}

#: Casas cuyo handicap asiático EN VIVO cuenta sólo los goles posteriores a la
#: apuesta. Es una regla de cada casa, no una convención general: si no está
#: acá se asume marcador completo, y se puede forzar por apuesta.
INPLAY_AH_FROM_PLACEMENT = {"bet365"}

USD_LIKE = {"USD", "USDT", "U$S", "US$"}

#: Límites de riesgo. Los fija el usuario y el sistema sólo avisa: nunca bloquea
#: una apuesta, porque la decisión y la ejecución son de la persona.
DEFAULT_LIMITS: dict[str, Optional[float]] = {
    "max_stake_per_bet_usd": None,
    "max_exposure_per_match_usd": None,
    "max_open_exposure_usd": None,
    "daily_stop_loss_usd": None,
    "max_bets_per_match": None,
}

BET_STATUSES = {"open", "won", "lost", "half_won", "half_lost", "push", "void", "cashout"}


@dataclass
class LegInput:
    """Una selección tal como la describe quien la carga, antes de resolverla."""

    match_label: str                # lo que escribió el usuario ("Darwin", "Darwin vs Palmerston")
    market_type: str
    side: Optional[str]             # home | away | draw | over | under | yes | no | 1x | 2/2 ...
    odds: float
    line: Optional[float] = None
    market_period: str = "FT"       # FT | HT | 2H
    team: Optional[str] = None      # equipo nombrado, cuando el lado depende de él
    platform: Optional[str] = None  # si ya se conoce el evento del bot
    external_event_id: Optional[str] = None
    placed_minute: Optional[int] = None
    placed_phase: Optional[str] = None      # prematch | live
    placed_score: Optional[tuple[int, int]] = None
    handicap_from: Optional[str] = None     # full | placement


@dataclass
class BetInput:
    """Un ticket completo, como se carga."""

    legs: list[LegInput]
    stake: float
    currency: str = "USD"
    fx_to_usd: Optional[float] = None
    odds_total: Optional[float] = None
    bookmaker: Optional[str] = None
    ticket_id: Optional[str] = None
    placed_at: Optional[str] = None
    source: str = "telegram"        # telegram | cli | import | llm
    scenario: Optional[str] = None  # hipótesis de fondo: agrupa exposición correlacionada
    thesis: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    notes: Optional[str] = None
    model_probability: Optional[float] = None
    mode: str = "real"              # real | paper
    chat_id: Optional[int] = None


@dataclass
class BetLeg:
    """Una pata ya resuelta y guardada."""

    id: Optional[int] = None
    bet_id: Optional[int] = None
    platform: Optional[str] = None
    external_event_id: Optional[str] = None
    match_label: str = ""
    home: Optional[str] = None
    away: Optional[str] = None
    competition_name: Optional[str] = None
    kickoff_at: Optional[str] = None
    placed_phase: str = "prematch"
    placed_minute: Optional[int] = None
    placed_home_score: Optional[int] = None
    placed_away_score: Optional[int] = None
    market_type: str = ""
    market_period: str = "FT"
    side: str = ""
    line: Optional[float] = None
    odds: float = 0.0
    handicap_from: str = "full"
    status: str = "open"
    payout_factor: Optional[float] = None
    observed_odds: Optional[float] = None   # la cuota que el bot veía en ese instante
    closing_odds: Optional[float] = None    # último precio visto de esa misma línea
    closing_line: Optional[float] = None    # línea vigente al cierre, si la nuestra se movió
    clv: Optional[float] = None
    created_at: Optional[str] = None


@dataclass
class Bet:
    """Un ticket guardado, con sus patas."""

    id: Optional[int] = None
    created_at: Optional[str] = None
    placed_at: Optional[str] = None
    source: str = "telegram"
    chat_id: Optional[int] = None
    bookmaker: Optional[str] = None
    bookmaker_family: Optional[str] = None
    ticket_id: Optional[str] = None
    stake: float = 0.0
    currency: str = "USD"
    fx_to_usd: Optional[float] = None
    stake_usd: Optional[float] = None
    odds_total: float = 0.0
    status: str = "open"
    return_amount: Optional[float] = None
    profit: Optional[float] = None
    profit_usd: Optional[float] = None
    settled_at: Optional[str] = None
    settlement_source: Optional[str] = None   # auto | manual
    scenario: Optional[str] = None
    thesis: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    model_probability: Optional[float] = None
    mode: str = "real"
    legs: list[BetLeg] = field(default_factory=list)

    @property
    def is_settled(self) -> bool:
        return self.status not in {"open", "void"}


@dataclass
class AddBetResult:
    """Lo que devuelve cargar una apuesta: el ticket y lo que hay que avisar."""

    bet: Bet
    warnings: list[str] = field(default_factory=list)


def market_label(leg: Any) -> str:
    """Etiqueta corta y estable de un mercado, para agrupar en reportes."""
    return f"{leg.market_type} {leg.market_period}"

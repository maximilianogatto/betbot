from __future__ import annotations

from typing import Optional, Protocol

from core.betting.models import Bet, BetLeg


class BetsPort(Protocol):
    """Registro de apuestas: lo apostado, cómo salió y con qué contexto.

    Nada se borra. Una apuesta mal cargada se anula (``status='void'``) y queda
    fuera de los reportes, pero la fila permanece: el registro de lo que se
    decidió en su momento es justamente lo que después permite evaluar el
    criterio, y borrarlo sería reescribir la historia.
    """

    def add_bet(self, bet: Bet) -> Bet:
        """Guarda el ticket con sus patas y devuelve el ticket con ids."""
        ...

    def get_bet(self, bet_id: int) -> Optional[Bet]:
        ...

    def list_bets(self, *, status: str | None = None, mode: str = "real",
                  limit: int = 20) -> list[Bet]:
        """Últimas apuestas. ``status='settled'`` trae las ya liquidadas."""
        ...

    def list_open_bets(self, *, mode: str | None = None) -> list[Bet]:
        ...

    def bets_for_event(self, *, platform: str, external_event_id: str,
                       only_open: bool = True) -> list[Bet]:
        """Apuestas enlazadas a un partido: lo que hay que liquidar cuando termina."""
        ...

    def link_leg(self, leg_id: int, *, platform: str, external_event_id: str,
                 home: Optional[str], away: Optional[str], competition_name: Optional[str],
                 kickoff_at: Optional[str], side: str) -> bool:
        """Enlaza tarde una pata sin partido. False si ya estaba enlazada."""
        ...

    def settle_bet(self, bet_id: int, *, status: str, return_amount: float,
                   profit: float, profit_usd: float | None, settlement_source: str,
                   legs: list[BetLeg], notes: str | None = None) -> Bet:
        """Cierra el ticket y sus patas en una sola transacción."""
        ...

    def settled_pnl_since(self, *, since: str, mode: str = "real") -> tuple[float, int]:
        """(resultado en USD, cantidad) de lo liquidado desde una fecha. Para el stop-loss."""
        ...

    def get_limits(self) -> dict[str, Optional[float]]:
        ...

    def bets_between(self, *, since: str, until: str, by: str = "settled",
                     chat_id: Optional[int] = None, mode: Optional[str] = None) -> list[Bet]:
        """Apuestas liquidadas (by="settled") o cargadas (by="placed") en [since, until)."""
        ...

    def report_chats(self) -> list[int]:
        """Chats que tienen apuestas: los que reciben reportes."""
        ...

    def get_ledger_setting(self, key: str) -> Optional[str]:
        ...

    def set_ledger_setting(self, key: str, value: str) -> None:
        ...

    def set_limit(self, key: str, value: Optional[float]) -> None:
        ...

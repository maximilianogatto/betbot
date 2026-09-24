from __future__ import annotations

from datetime import datetime, timezone

from adapters.storage.connection import open_connection
from core.betting.models import DEFAULT_LIMITS, Bet, BetLeg
from core.ports.bets import BetsPort

_BET_FIELDS = (
    "created_at", "placed_at", "source", "chat_id", "bookmaker", "bookmaker_family",
    "ticket_id", "stake", "currency", "fx_to_usd", "stake_usd", "odds_total", "mode",
    "status", "return_amount", "profit", "profit_usd", "settled_at", "settlement_source",
    "scenario", "thesis", "tags", "notes", "model_probability",
)
_LEG_FIELDS = (
    "bet_id", "platform", "external_event_id", "match_label", "home", "away",
    "competition_name", "kickoff_at", "placed_phase", "placed_minute",
    "placed_home_score", "placed_away_score", "market_type", "market_period", "side",
    "line", "odds", "handicap_from", "status", "payout_factor", "observed_odds",
    "closing_odds", "closing_line", "clv", "created_at",
)


def _row_to_leg(row) -> BetLeg:
    return BetLeg(id=row["id"], **{name: row[name] for name in _LEG_FIELDS})


def _row_to_bet(row, legs: list[BetLeg]) -> Bet:
    return Bet(id=row["id"], legs=legs, **{name: row[name] for name in _BET_FIELDS})


class SQLiteBetsAdapter(BetsPort):
    """Implementa BetsPort sobre `bets` + `bet_legs`."""

    def add_bet(self, bet: Bet) -> Bet:
        now = datetime.now(timezone.utc).isoformat()
        values = {name: getattr(bet, name) for name in _BET_FIELDS}
        values["created_at"] = bet.created_at or now
        columns = ", ".join(_BET_FIELDS)
        placeholders = ", ".join(f":{name}" for name in _BET_FIELDS)
        with open_connection() as conn:
            cursor = conn.execute(
                f"INSERT INTO bets ({columns}) VALUES ({placeholders})", values)
            bet_id = int(cursor.lastrowid)
            for leg in bet.legs:
                leg.bet_id = bet_id
                leg.created_at = leg.created_at or now
                leg_values = {name: getattr(leg, name) for name in _LEG_FIELDS}
                leg_cursor = conn.execute(
                    f"INSERT INTO bet_legs ({', '.join(_LEG_FIELDS)}) "
                    f"VALUES ({', '.join(f':{name}' for name in _LEG_FIELDS)})", leg_values)
                leg.id = int(leg_cursor.lastrowid)
        bet.id, bet.created_at = bet_id, values["created_at"]
        return bet

    def get_bet(self, bet_id: int) -> Bet | None:
        with open_connection() as conn:
            row = conn.execute("SELECT * FROM bets WHERE id = ?", (bet_id,)).fetchone()
            if row is None:
                return None
            legs = conn.execute(
                "SELECT * FROM bet_legs WHERE bet_id = ? ORDER BY id", (bet_id,)).fetchall()
        return _row_to_bet(row, [_row_to_leg(leg) for leg in legs])

    def list_bets(self, *, status: str | None = None, mode: str = "real",
                  limit: int = 20) -> list[Bet]:
        sql = "SELECT id FROM bets WHERE 1 = 1"
        params: list = []
        if status == "settled":
            sql += " AND status NOT IN ('open', 'void')"
        elif status:
            sql += " AND status = ?"
            params.append(status)
        if mode:
            sql += " AND mode = ?"
            params.append(mode)
        sql += " ORDER BY COALESCE(placed_at, created_at) DESC, id DESC LIMIT ?"
        params.append(limit)
        with open_connection() as conn:
            ids = [row["id"] for row in conn.execute(sql, params)]
        return [bet for bet in (self.get_bet(bet_id) for bet_id in ids) if bet]

    def list_open_bets(self, *, mode: str | None = None) -> list[Bet]:
        sql = "SELECT id FROM bets WHERE status = 'open'"
        params: list = []
        if mode:
            sql += " AND mode = ?"
            params.append(mode)
        with open_connection() as conn:
            ids = [row["id"] for row in conn.execute(sql, params)]
        return [bet for bet in (self.get_bet(bet_id) for bet_id in ids) if bet]

    def bets_for_event(self, *, platform: str, external_event_id: str,
                       only_open: bool = True) -> list[Bet]:
        sql = ("SELECT DISTINCT l.bet_id AS id FROM bet_legs l JOIN bets b ON b.id = l.bet_id"
               " WHERE l.platform = ? AND l.external_event_id = ?")
        if only_open:
            sql += " AND b.status = 'open'"
        with open_connection() as conn:
            ids = [row["id"] for row in conn.execute(sql, (platform, str(external_event_id)))]
        return [bet for bet in (self.get_bet(bet_id) for bet_id in ids) if bet]

    def link_leg(self, leg_id: int, *, platform: str, external_event_id: str,
                 home: str | None, away: str | None, competition_name: str | None,
                 kickoff_at: str | None, side: str) -> bool:
        # Sólo patas sin partido: un enlace existente no se pisa.
        with open_connection() as conn:
            cursor = conn.execute(
                "UPDATE bet_legs SET platform = ?, external_event_id = ?, home = ?, away = ?,"
                " competition_name = COALESCE(?, competition_name),"
                " kickoff_at = COALESCE(?, kickoff_at), side = ?"
                " WHERE id = ? AND external_event_id IS NULL",
                (platform, str(external_event_id), home, away, competition_name, kickoff_at,
                 side, leg_id))
        return cursor.rowcount > 0

    def settle_bet(self, bet_id: int, *, status: str, return_amount: float, profit: float,
                   profit_usd: float | None, settlement_source: str, legs: list[BetLeg],
                   notes: str | None = None) -> Bet:
        now = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            for leg in legs:
                conn.execute(
                    "UPDATE bet_legs SET status = ?, payout_factor = ?, closing_odds = ?,"
                    " closing_line = ?, clv = ? WHERE id = ?",
                    (leg.status, leg.payout_factor, leg.closing_odds, leg.closing_line,
                     leg.clv, leg.id))
            # La condición sobre status evita liquidar dos veces si dos flujos
            # (el cierre del partido y una carga tardía) coinciden.
            conn.execute(
                "UPDATE bets SET status = ?, return_amount = ?, profit = ?, profit_usd = ?,"
                " settled_at = ?, settlement_source = ?, notes = COALESCE(?, notes)"
                " WHERE id = ? AND status = 'open'",
                (status, round(return_amount, 4), round(profit, 4),
                 round(profit_usd, 4) if profit_usd is not None else None,
                 now, settlement_source, notes, bet_id))
        return self.get_bet(bet_id)

    def settled_pnl_since(self, *, since: str, mode: str = "real") -> tuple[float, int]:
        with open_connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(profit_usd), 0) AS pnl, COUNT(*) AS n FROM bets"
                " WHERE status NOT IN ('open', 'void') AND mode = ? AND settled_at >= ?",
                (mode, since)).fetchone()
        return float(row["pnl"] or 0.0), int(row["n"] or 0)

    def get_limits(self) -> dict[str, float | None]:
        limits = dict(DEFAULT_LIMITS)
        with open_connection() as conn:
            for row in conn.execute("SELECT key, value FROM ledger_settings"):
                if row["key"] in limits:
                    raw = row["value"]
                    limits[row["key"]] = None if raw in ("", "none") else float(raw)
        return limits

    def set_limit(self, key: str, value: float | None) -> None:
        if key not in DEFAULT_LIMITS:
            raise ValueError(f"límite desconocido: {key}. Opciones: {', '.join(DEFAULT_LIMITS)}")
        with open_connection() as conn:
            conn.execute(
                "INSERT INTO ledger_settings (key, value, updated_at) VALUES (?,?,?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
                " updated_at = excluded.updated_at",
                (key, "none" if value is None else str(value),
                 datetime.now(timezone.utc).isoformat()))

from __future__ import annotations

from adapters.storage.connection import open_connection
from core.models import OddsSnapshot
from core.ports.odds_history import OddsHistoryPort

_FIELDS = (
    "platform", "external_event_id", "unified_competition_id",
    "home", "away", "competition_name", "scheduled_at",
    "captured_at", "provider_observed_at", "status",
    "odds_home", "odds_draw", "odds_away", "markets_json",
    "is_suspended", "payload_hash",
)


def _row_to_snapshot(row) -> OddsSnapshot:
    values = {name: row[name] for name in _FIELDS}
    values["is_suspended"] = bool(values["is_suspended"])
    return OddsSnapshot(id=row["id"], **values)


class SQLiteOddsHistoryAdapter(OddsHistoryPort):
    """Implementa OddsHistoryPort sobre la tabla `odds_history`."""

    def archive_snapshots(self, snapshots: list[OddsSnapshot]) -> int:
        if not snapshots:
            return 0
        columns = ", ".join(_FIELDS)
        placeholders = ", ".join(f":{name}" for name in _FIELDS)
        rows = []
        for snapshot in snapshots:
            values = {name: getattr(snapshot, name) for name in _FIELDS}
            values["is_suspended"] = int(bool(snapshot.is_suspended))
            rows.append(values)
        with open_connection() as conn:
            # OR IGNORE por el índice de idempotencia: un poll repetido con el
            # mismo payload en el mismo instante no duplica la fila.
            cursor = conn.executemany(
                f"INSERT OR IGNORE INTO odds_history ({columns}) VALUES ({placeholders})", rows)
            return cursor.rowcount

    def last_snapshot(self, *, platform: str, external_event_id: str) -> OddsSnapshot | None:
        with open_connection() as conn:
            row = conn.execute(
                "SELECT * FROM odds_history WHERE platform = ? AND external_event_id = ?"
                " ORDER BY captured_at DESC, id DESC LIMIT 1",
                (platform, str(external_event_id)),
            ).fetchone()
        return _row_to_snapshot(row) if row is not None else None

    def list_snapshots(self, *, platform: str, external_event_id: str,
                       limit: int = 500) -> list[OddsSnapshot]:
        with open_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM odds_history WHERE platform = ? AND external_event_id = ?"
                " ORDER BY captured_at, id LIMIT ?",
                (platform, str(external_event_id), limit),
            ).fetchall()
        return [_row_to_snapshot(row) for row in rows]

    def last_prematch_snapshot(self, *, platform: str, external_event_id: str,
                               kickoff_at: str) -> OddsSnapshot | None:
        """Cierre *observado*: el último que alcanzamos a ver antes del kickoff.

        No es la closing line oficial de la casa, y el nombre lo dice a propósito.
        """
        with open_connection() as conn:
            row = conn.execute(
                "SELECT * FROM odds_history WHERE platform = ? AND external_event_id = ?"
                " AND captured_at < ? AND is_suspended = 0"
                " ORDER BY captured_at DESC, id DESC LIMIT 1",
                (platform, str(external_event_id), kickoff_at),
            ).fetchone()
        return _row_to_snapshot(row) if row is not None else None

from __future__ import annotations

from datetime import datetime, timezone

from core.models import MatchResult
from core.ports.match_results import MatchResultsPort
from adapters.storage.connection import open_connection

# Columnas que se copian tal cual entre la fila y el dataclass.
_FIELDS = (
    "platform", "external_event_id", "unified_competition_id",
    "home", "away", "competition_name", "country_name",
    "kickoff_at", "actual_start_at", "status",
    "final_home_score", "final_away_score", "ht_home_score", "ht_away_score",
    "xg_home", "xg_away", "shots_on_target_home", "shots_on_target_away",
    "red_cards_home", "red_cards_away",
    "goal_minutes_json", "red_card_minutes_json",
    "stats_provider", "stats_match_id", "raw_payload_json",
    "source", "recorded_at", "updated_at",
)


def _row_to_result(row) -> MatchResult:
    return MatchResult(id=row["id"], **{name: row[name] for name in _FIELDS})


class SQLiteMatchResultsAdapter(MatchResultsPort):
    """Implementa MatchResultsPort sobre la tabla `match_results`."""

    def record_match_result(self, result: MatchResult) -> MatchResult:
        """Guarda el resultado; si ya existe ese partido, lo actualiza.

        La idempotencia es por `(platform, external_event_id)`. Un partido
        cargado a mano no tiene esa clave, así que siempre inserta: la
        deduplicación de esos casos es responsabilidad de quien llama.
        """

        now_iso = datetime.now(timezone.utc).isoformat()
        values = {name: getattr(result, name) for name in _FIELDS}
        values["recorded_at"] = result.recorded_at or now_iso
        values["updated_at"] = now_iso

        columns = ", ".join(_FIELDS)
        placeholders = ", ".join(f":{name}" for name in _FIELDS)
        # En el conflicto no se pisa recorded_at: la primera vez que se vio el
        # partido es un dato histórico y no debe moverse.
        updates = ", ".join(
            f"{name} = excluded.{name}" for name in _FIELDS if name != "recorded_at"
        )

        with open_connection() as conn:
            row = conn.execute(
                f"""
                INSERT INTO match_results ({columns})
                VALUES ({placeholders})
                ON CONFLICT(platform, external_event_id)
                    WHERE platform IS NOT NULL AND external_event_id IS NOT NULL
                    DO UPDATE SET {updates}
                RETURNING *
                """,
                values,
            ).fetchone()
        return _row_to_result(row)

    def get_match_result(self, *, platform: str, external_event_id: str) -> MatchResult | None:
        with open_connection() as conn:
            row = conn.execute(
                "SELECT * FROM match_results WHERE platform = ? AND external_event_id = ?",
                (platform, str(external_event_id)),
            ).fetchone()
        return _row_to_result(row) if row is not None else None

    def list_match_results_pending_enrichment(self, *, limit: int = 20) -> list[MatchResult]:
        """Resultados a los que todavía les falta pasar por un proveedor de stats.

        Son los archivados desde el live: tienen marcador pero no xG, o quedaron
        con el estado sin confirmar porque se los dejó de ver antes del final.
        Se devuelven los más recientes primero — son los que más importan y los
        que el proveedor todavía tiene disponibles.
        """

        with open_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM match_results
                WHERE stats_provider IS NULL
                  AND (status = 'UNKNOWN' OR xg_home IS NULL)
                ORDER BY kickoff_at DESC, id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [_row_to_result(row) for row in rows]

    def list_match_results(
        self,
        *,
        unified_competition_id: int | None = None,
        since: str | None = None,
        until: str | None = None,
        only_settled: bool = False,
        limit: int | None = None,
    ) -> list[MatchResult]:
        query = "SELECT * FROM match_results WHERE 1=1"
        params: list = []
        if unified_competition_id is not None:
            query += " AND unified_competition_id = ?"
            params.append(int(unified_competition_id))
        if since is not None:
            query += " AND kickoff_at >= ?"
            params.append(since)
        if until is not None:
            query += " AND kickoff_at <= ?"
            params.append(until)
        if only_settled:
            # Un partido suspendido no es un 0-0: se excluye de los análisis.
            query += (
                " AND status = 'FINISHED'"
                " AND final_home_score IS NOT NULL AND final_away_score IS NOT NULL"
            )
        query += " ORDER BY kickoff_at DESC, id DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))

        with open_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_result(row) for row in rows]

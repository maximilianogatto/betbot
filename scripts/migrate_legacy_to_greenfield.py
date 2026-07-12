"""Migración one-shot: config del esquema LEGACY (main/prod) → greenfield.

Copia SOLO la configuración del usuario (ligas trackeadas, suscripciones, links y
suscripciones de stats, timezone, peak digest). NO copia estado efímero
(active_events, baselines, small_changes, sent_alerts, stats_payload_cache): eso
se repuebla solo en el primer ciclo de refresh.

Preserva los IDs originales para mantener consistentes las foreign keys entre
competencias / unified / suscripciones / stats-links. Es introspectivo: mapea por
nombre de columna y solo copia las que existan en el source (tolera drift del
esquema legacy por `_ensure_column`).

Uso:
    python scripts/migrate_legacy_to_greenfield.py --source PROD.sqlite3 --dest NUEVA.sqlite3 [--force]

Recomendado: correr sobre una COPIA del .sqlite3 de prod, nunca sobre el vivo.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Permitir importar el paquete del proyecto al correr como script suelto.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.storage.schema import initialize_schema  # noqa: E402
from core.league_naming import extract_league_traits, league_slug  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.OperationalError:
        return set()


# (tabla_source, tabla_dest, {col_source: col_dest}). Orden = respeta FKs.
TABLE_MAP: list[tuple[str, str, dict[str, str]]] = [
    (
        "unified_competitions", "unified_competitions",
        {
            "id": "id", "name": "name", "created_at": "created_at", "updated_at": "updated_at",
            "public_id": "public_id", "display_name": "display_name",
            "country": "country", "gender": "gender", "age_group": "age_group",
        },
    ),
    (
        "tracked_competitions", "competitions",
        {
            "id": "id", "platform": "platform",
            "competition_external_id": "external_id", "competition_name": "name",
            "source_url": "source_url", "metadata_json": "metadata_json",
            "unified_competition_id": "unified_competition_id",
            "enabled": "enabled", "reminders_enabled": "reminders_enabled",
            "last_refreshed_at": "last_refreshed_at",
            "consecutive_unavailable_refreshes": "consecutive_unavailable_refreshes",
            "last_unavailable_refresh_at": "last_unavailable_at",
            "last_unavailable_reason": "last_unavailable_reason",
            "last_unavailable_notification_at": "last_unavailable_notified_at",
            "created_at": "created_at", "updated_at": "updated_at",
        },
    ),
    (
        "competition_subscriptions", "subscriptions",
        {
            "telegram_chat_id": "chat_id", "tracked_competition_id": "competition_id",
            "notify_new_events": "notify_new_events", "notify_odds_changes": "notify_odds_changes",
            "change_threshold_percent": "change_threshold_percent",
            "reminders_enabled": "reminders_enabled", "enabled": "enabled",
            "created_at": "created_at", "updated_at": "updated_at",
        },
    ),
    (
        "stats_league_links", "stats_league_links",
        {
            "id": "id", "tracked_competition_id": "competition_id",
            "stats_provider": "provider", "stats_league_id": "league_id",
            "stats_league_name": "league_name", "stats_country_name": "country_name",
            "confidence": "confidence", "payload_json": "payload_json",
            "created_at": "created_at", "updated_at": "updated_at",
        },
    ),
    (
        "stats_league_subscriptions", "stats_league_subscriptions",
        {
            "telegram_chat_id": "chat_id", "stats_provider": "provider",
            "stats_league_id": "league_id", "stats_league_name": "league_name",
            "stats_country_name": "country_name", "source_url": "source_url",
            "payload_json": "payload_json", "enabled": "enabled",
            "created_at": "created_at", "updated_at": "updated_at",
        },
    ),
    ("chat_settings", "chat_settings",
     {"chat_id": "chat_id", "timezone": "timezone", "updated_at": "updated_at"}),
    ("peak_digest_subscriptions", "peak_digest_subscriptions",
     {"chat_id": "chat_id", "enabled": "enabled", "updated_at": "updated_at"}),
]

# Defaults para columnas dest NOT NULL que el source podría no tener.
DEST_DEFAULTS: dict[str, dict[str, object]] = {
    "competitions": {"reminders_enabled": 0, "enabled": 1, "consecutive_unavailable_refreshes": 0},
    "subscriptions": {"reminders_enabled": 0, "enabled": 1,
                      "notify_new_events": 1, "notify_odds_changes": 1,
                      "change_threshold_percent": 20.0},
    "stats_league_links": {"confidence": 1.0},
    "stats_league_subscriptions": {"enabled": 1},
    "peak_digest_subscriptions": {"enabled": 1},
}


def _unique_public_id(base: str, used: set[str]) -> str:
    base = base or "league"
    slug = base
    n = 2
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def _migrate_table(
    src: sqlite3.Connection,
    dst: sqlite3.Connection,
    src_table: str,
    dst_table: str,
    colmap: dict[str, str],
    used_public_ids: set[str],
) -> int:
    src_cols = _columns(src, src_table)
    if not src_cols:
        print(f"  · {src_table}: no existe en el source, salteado.")
        return 0
    dst_cols = _columns(dst, dst_table)
    # Solo columnas presentes en ambos lados.
    active = {s: d for s, d in colmap.items() if s in src_cols and d in dst_cols}
    now = _now_iso()
    rows = src.execute(f"SELECT * FROM {src_table}").fetchall()
    src_index = {name: i for i, name in enumerate(
        [r[1] for r in src.execute(f"PRAGMA table_info({src_table})").fetchall()]
    )}
    inserted = 0
    for row in rows:
        values: dict[str, object] = {}
        for s_col, d_col in active.items():
            values[d_col] = row[src_index[s_col]]
        # Rellenar NOT NULL faltantes con defaults sensatos.
        for d_col, default in DEST_DEFAULTS.get(dst_table, {}).items():
            if values.get(d_col) is None:
                values[d_col] = default
        for ts in ("created_at", "updated_at"):
            if ts in dst_cols and not values.get(ts):
                values[ts] = now
        # unified_competitions: public_id NOT NULL UNIQUE — generar si falta.
        if dst_table == "unified_competitions":
            pid = values.get("public_id")
            if not pid:
                traits = extract_league_traits(str(values.get("name") or ""))
                base = league_slug(str(values.get("name") or "")) or "league"
                pid = base
            values["public_id"] = _unique_public_id(str(pid), used_public_ids)
            for tcol in ("country", "gender", "age_group"):
                if tcol in dst_cols and values.get(tcol) is None:
                    traits = extract_league_traits(str(values.get("name") or ""))
                    values[tcol] = traits.get(tcol)
        cols = list(values.keys())
        placeholders = ", ".join("?" for _ in cols)
        dst.execute(
            f"INSERT INTO {dst_table} ({', '.join(cols)}) VALUES ({placeholders})",
            [values[c] for c in cols],
        )
        inserted += 1
    print(f"  · {src_table} → {dst_table}: {inserted} filas ({len(active)} columnas mapeadas)")
    return inserted


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, help="DB legacy (esquema prod/main)")
    ap.add_argument("--dest", required=True, help="DB greenfield destino (se crea)")
    ap.add_argument("--force", action="store_true", help="sobreescribir dest si existe")
    args = ap.parse_args()

    src_path = Path(args.source)
    dst_path = Path(args.dest)
    if not src_path.exists():
        print(f"ERROR: source no existe: {src_path}")
        return 1
    if dst_path.exists():
        if not args.force:
            print(f"ERROR: dest ya existe: {dst_path} (usá --force para sobreescribir)")
            return 1
        dst_path.unlink()

    src = sqlite3.connect(src_path)
    if not _columns(src, "tracked_competitions"):
        print("ERROR: el source no parece un DB legacy (falta tracked_competitions).")
        return 1

    dst = sqlite3.connect(dst_path)
    dst.execute("PRAGMA foreign_keys = ON")
    initialize_schema(dst)

    print(f"Migrando config {src_path.name} → {dst_path.name} ...")
    used_public_ids: set[str] = set()
    total = 0
    try:
        for src_table, dst_table, colmap in TABLE_MAP:
            total += _migrate_table(src, dst, src_table, dst_table, colmap, used_public_ids)
        dst.commit()
    except Exception as exc:  # noqa: BLE001
        dst.rollback()
        print(f"ERROR durante la migración (rollback): {exc}")
        return 1
    finally:
        src.close()

    # Verificación de integridad de FKs.
    fk_problems = dst.execute("PRAGMA foreign_key_check").fetchall()
    dst.close()
    if fk_problems:
        print(f"⚠️  FK check encontró {len(fk_problems)} problemas: {fk_problems[:5]}")
        return 1

    print(f"\n✅ Migración OK: {total} filas de config. FK check limpio.")
    print("   Los eventos/odds se repueblan solos en el primer refresh del bot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

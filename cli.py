#!/usr/bin/env python3
"""CLI administrative tool for BetBot's database and monitoring management."""

import argparse
import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Cargar .env antes de resolver BETBOT_DB_PATH.
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection, resolve_database_path
from bot.config import load_settings
from typing import Any

def print_table(headers: list[str], rows: list[list[Any]]) -> None:
    """Helper to format and print a text-based table in terminal."""
    if not rows:
        print("No hay registros que mostrar.")
        return

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(str(cell)))

    # Draw header separator
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    print(sep)

    # Draw header row
    header_str = "|" + "|".join(f" {headers[idx]:<{widths[idx]}} " for idx in range(len(headers))) + "|"
    print(header_str)
    print(sep)

    # Draw data rows
    for row in rows:
        row_str = "|" + "|".join(f" {str(row[idx]):<{widths[idx]}} " for idx in range(len(row))) + "|"
        print(row_str)
    print(sep)

def cmd_stats(args, repo: SqliteStorage) -> None:
    """Print overall database size and row counts."""

    print("\n=== BETBOT DATABASE STATISTICS ===")
    db_file_path = resolve_database_path()
    with open_connection() as con:
        if os.path.exists(db_file_path):
            size_mb = os.path.getsize(db_file_path) / (1024 * 1024)
            print(f"Ruta DB: {db_file_path}")
            print(f"Tamaño archivo DB: {size_mb:.2f} MB")
        else:
            print("Archivo de base de datos no se pudo inicializar.")
            return

        tables = [
            "competitions",
            "unified_competitions",
            "subscriptions",
            "events",
            "baselines",
            "live_watch_entries",
            "small_changes",
        ]
        rows = []
        for table in tables:
            try:
                count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                rows.append([table, count])
            except Exception:
                rows.append([table, "N/A"])
        
        print("\nConteos de Filas por Tabla:")
        print_table(["Tabla", "Cantidad de Filas"], rows)

def cmd_list_competitions(args, repo: SqliteStorage) -> None:
    """List all registered and tracked competitions."""
    with open_connection() as con:
        rows = con.execute(
            """
            SELECT id, platform, external_id, name, enabled, last_refreshed_at
            FROM competitions
            ORDER BY platform, name
            """
        ).fetchall()
        
        table_rows = []
        for r in rows:
            table_rows.append([
                r["id"],
                r["platform"],
                r["external_id"],
                r["name"][:40],
                "SÍ" if r["enabled"] else "NO",
                r["last_refreshed_at"] or "Nunca"
            ])
            
        print("\nLigas y Competiciones Monitoreadas:")
        print_table(["ID", "Plataforma", "ID Externo", "Nombre Liga", "Activa", "Último Scrape"], table_rows)

def cmd_list_events(args, repo: SqliteStorage) -> None:
    """List currently stored events/matches."""
    with open_connection() as con:
        rows = con.execute(
            """
            SELECT e.id, e.home, e.away, e.scheduled_at, e.status, COALESCE(uc.name, c.name) as league_name
            FROM events e
            JOIN competitions c ON c.id = e.competition_id
            LEFT JOIN unified_competitions uc ON uc.id = c.unified_competition_id
            ORDER BY e.scheduled_at DESC, e.id DESC
            LIMIT 40
            """
        ).fetchall()
        
        table_rows = []
        for r in rows:
            status_desc = str(r["status"] or "PREMATCH")
            table_rows.append([
                r["id"],
                r["home"][:20],
                r["away"][:20],
                r["scheduled_at"] or "N/A",
                status_desc,
                r["league_name"][:25]
            ])
            
        print("\nÚltimos Partidos Detectados (Límite 40):")
        print_table(["ID", "Local", "Visitante", " Kickoff (UTC)", "Estado", "Liga Unificada"], table_rows)

def cmd_prune(args, repo: SqliteStorage) -> None:
    """Manually run database pruning."""
    print(f"Ejecutando purga manual de base de datos con umbral de {args.days} días, "
          f"sent_alerts de {args.sent_alerts_days} días y small_changes de {args.small_changes_days} días...")
    stats = repo.prune_old_data(
        days_threshold=args.days,
        sent_alerts_days=args.sent_alerts_days,
        small_changes_days=args.small_changes_days
    )
    print("Purga completada con éxito.")
    rows = [[k, v] for k, v in stats.items()]
    print_table(["Métrica de Limpieza", "Registros Eliminados"], rows)

def main() -> None:
    # Setup argument parser
    parser = argparse.ArgumentParser(description="BetBot Command Line Admin Tool")
    subparsers = parser.add_subparsers(dest="command", help="Comandos administrativos disponibles")
    
    # stats command
    subparsers.add_parser("stats", help="Muestra estadísticas generales del almacenamiento y filas de base de datos.")
    
    # list-competitions command
    subparsers.add_parser("list-competitions", help="Muestra la lista de ligas bajo monitoreo.")
    
    # list-events command
    subparsers.add_parser("list-events", help="Muestra la lista de partidos y eventos detectados.")
    
    # prune command
    prune_parser = subparsers.add_parser("prune", help="Purga registros antiguos/expirados de la base de datos.")
    prune_parser.add_argument("--days", type=int, default=14, help="Días mínimos de antigüedad para purgar (default: 14).")
    prune_parser.add_argument("--sent-alerts-days", type=int, default=30, help="Días mínimos de antigüedad para purgar alertas enviadas (default: 30).")
    prune_parser.add_argument("--small-changes-days", type=int, default=7, help="Días mínimos de antigüedad para purgar cambios menores pendientes (default: 7).")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
        
    try:
        load_settings()
        repo = SqliteStorage()
    except Exception as e:
        print(f"Error al inicializar configuración o repositorio: {e}")
        sys.exit(1)

    # Execute commands
    if args.command == "stats":
        cmd_stats(args, repo)
    elif args.command == "list-competitions":
        cmd_list_competitions(args, repo)
    elif args.command == "list-events":
        cmd_list_events(args, repo)
    elif args.command == "prune":
        cmd_prune(args, repo)

if __name__ == "__main__":
    main()

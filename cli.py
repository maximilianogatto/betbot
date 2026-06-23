#!/usr/bin/env python3
"""CLI administrative tool for BetBot's database and monitoring management."""

import argparse
import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from storage.tracking_repository import SqliteTrackingRepository, _connect
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

def cmd_stats(args, repo: SqliteTrackingRepository) -> None:
    """Print overall database size and row counts."""
    from storage.tracking_repository import DB_FILE_PATH
    
    print("\n=== BETBOT DATABASE STATISTICS ===")
    with _connect() as con:
        if os.path.exists(DB_FILE_PATH):
            size_mb = os.path.getsize(DB_FILE_PATH) / (1024 * 1024)
            print(f"Ruta DB: {DB_FILE_PATH}")
            print(f"Tamaño archivo DB: {size_mb:.2f} MB")
        else:
            print("Archivo de base de datos no se pudo inicializar.")
            return

        tables = ["tracked_competitions", "unified_competitions", "chat_subscriptions", 
                  "events", "event_odds_snapshots", "live_watch_entries", "small_changes"]
        rows = []
        for table in tables:
            try:
                count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                rows.append([table, count])
            except Exception:
                rows.append([table, "N/A"])
        
        print("\nConteos de Filas por Tabla:")
        print_table(["Tabla", "Cantidad de Filas"], rows)

def cmd_list_competitions(args, repo: SqliteTrackingRepository) -> None:
    """List all registered and tracked competitions."""
    with _connect() as con:
        rows = con.execute(
            """
            SELECT id, platform, competition_external_id, competition_name, enabled, last_refreshed_at
            FROM tracked_competitions
            ORDER BY platform, competition_name
            """
        ).fetchall()
        
        table_rows = []
        for r in rows:
            table_rows.append([
                r["id"],
                r["platform"],
                r["competition_external_id"],
                r["competition_name"][:40],
                "SÍ" if r["enabled"] else "NO",
                r["last_refreshed_at"] or "Nunca"
            ])
            
        print("\nLigas y Competiciones Monitoreadas:")
        print_table(["ID", "Plataforma", "ID Externo", "Nombre Liga", "Activa", "Último Scrape"], table_rows)

def cmd_list_events(args, repo: SqliteTrackingRepository) -> None:
    """List currently stored events/matches."""
    with _connect() as con:
        rows = con.execute(
            """
            SELECT e.id, e.home, e.away, e.scheduled_at, e.status_flags, uc.name as league_name
            FROM events e
            JOIN unified_competitions uc ON e.unified_competition_id = uc.id
            ORDER BY e.scheduled_at DESC, e.id DESC
            LIMIT 40
            """
        ).fetchall()
        
        table_rows = []
        for r in rows:
            # Map status flags
            flags = r["status_flags"]
            status_desc = "PREMATCH"
            if flags & 2:
                status_desc = "LIVE"
            if flags & 4:
                status_desc = "FINISHED"
                
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

def cmd_prune(args, repo: SqliteTrackingRepository) -> None:
    """Manually run database pruning."""
    print(f"Ejecutando purga manual de base de datos con umbral de {args.days} días...")
    stats = repo.prune_old_data(days_threshold=args.days)
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
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
        
    try:
        settings = load_settings()
        repo = SqliteTrackingRepository(
            default_change_threshold_percent=settings.tracking_default_change_threshold_percent,
            default_notify_odds_changes=settings.tracking_default_notify_odds_changes,
        )
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

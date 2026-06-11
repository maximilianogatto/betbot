#!/usr/bin/env python
"""Export / import the portable league seed (generic, user-agnostic data).

The SQLite DB is gitignored and does not travel to a cloud deploy. This tool moves
the curated league knowledge (unified competitions + tracked competitions + stats
links) in and out of a committed JSON file (``seeds/leagues.json``).

Usage:
    python scripts/seed_leagues.py export                 # DB  -> seeds/leagues.json
    python scripts/seed_leagues.py import                 # seed -> DB (preserve existing)
    python scripts/seed_leagues.py import --overwrite      # seed -> DB (refresh fields too)
    python scripts/seed_leagues.py export --path other.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.league_seed import (  # noqa: E402
    SEED_FILE_PATH,
    import_league_seed,
    load_seed_file,
    write_seed_file,
)


def _cmd_export(args: argparse.Namespace) -> int:
    target = write_seed_file(args.path)
    data = load_seed_file(target) or {}
    leagues = data.get("leagues") or []
    platforms = sum(len(league.get("platforms") or []) for league in leagues)
    stats = sum(len(league.get("stats_links") or []) for league in leagues)
    unlinked = len(data.get("unlinked_platforms") or [])
    print(
        f"✅ Exportado a {target} (v{data.get('version')})\n"
        f"   {len(leagues)} ligas en el registro\n"
        f"   {platforms} links de plataforma" + (f" (+{unlinked} sin liga)" if unlinked else "") + "\n"
        f"   {stats} links de stats"
    )
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    data = load_seed_file(args.path)
    if not data:
        print(f"❌ No existe el seed {args.path or SEED_FILE_PATH}. Corré 'export' primero.")
        return 1
    counts = import_league_seed(data, overwrite=args.overwrite)
    print(
        "✅ Importado"
        + (" (overwrite)" if args.overwrite else "")
        + f"\n   unified: +{counts['unified_created']}"
        + f"\n   tracked: +{counts['tracked_inserted']} nuevas, "
        + f"{counts['tracked_updated']} actualizadas, {counts['tracked_skipped']} sin tocar"
        + f"\n   stats:   +{counts['stats_inserted']} nuevos, "
        + f"{counts['stats_updated']} actualizados, {counts['stats_skipped']} omitidos"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export/import the portable league seed.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="DB -> seed JSON")
    p_export.add_argument("--path", type=Path, default=None, help="Destino (default seeds/leagues.json)")
    p_export.set_defaults(func=_cmd_export)

    p_import = sub.add_parser("import", help="seed JSON -> DB")
    p_import.add_argument("--path", type=Path, default=None, help="Origen (default seeds/leagues.json)")
    p_import.add_argument("--overwrite", action="store_true", help="Refrescar campos de filas existentes")
    p_import.set_defaults(func=_cmd_import)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

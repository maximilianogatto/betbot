"""Vinculador semanal de ligas con proveedores de stats: corre en la Mac, no en el VPS.

El matching por equipos es pesado para el e2-micro (más de una hora al 85% de CPU,
y un pico así ya trabó el pool de 1xBet), en la Mac tarda un minuto. Entonces:

1. copia la base del VPS (backup de sqlite, sin frenar al bot),
2. corre `scripts.link_stats_by_teams --apply` contra la copia, proveedor por proveedor
   (federaciones primero, después Statshub y Flashscore; sin --audit: sólo agrega),
3. sube al VPS únicamente los links nuevos o cambiados (upsert por liga+proveedor).

Uso: python -m scripts.link_stats_weekly [--dry-run] [--providers a,b] [--workdir DIR]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import shlex
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

VPS = "maximilianogatto@34.145.103.191"
SSH_KEY = Path.home() / ".ssh" / "betbot_vps"
CHAT_ID = 1804247844
PROVIDERS = ("palloliitto", "svenskfotboll_http", "norway_nff_http", "romania_frf_http",
             "slovakia_sportnet_http", "algeria_lnff_http", "sportradar_statshub", "flashscore_http")
COLUMNS = ("competition_id", "provider", "league_id", "league_name", "country_name",
           "confidence", "payload_json", "created_at", "updated_at")

# Corre del lado del VPS: lee los links por stdin y los inserta/actualiza.
_REMOTE_UPSERT = """
import json, sqlite3, sys
rows = json.load(sys.stdin)
conn = sqlite3.connect("data/tracking.sqlite3", timeout=30)
cols = %r
with conn:
    for row in rows:
        conn.execute(
            f"INSERT INTO stats_league_links ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
            "ON CONFLICT(competition_id, provider) DO UPDATE SET league_id=excluded.league_id, "
            "league_name=excluded.league_name, country_name=excluded.country_name, "
            "confidence=excluded.confidence, payload_json=excluded.payload_json, "
            "updated_at=excluded.updated_at",
            [row[c] for c in cols])
print(len(rows))
""" % (COLUMNS,)


def _ssh(command: str, *, stdin: str | None = None) -> str:
    result = subprocess.run(
        ["ssh", "-i", str(SSH_KEY), "-o", "BatchMode=yes", VPS, command],
        input=stdin, capture_output=True, text=True, timeout=600, check=True)
    return result.stdout


def fetch_copy(workdir: Path) -> Path:
    """Backup consistente en el VPS (la API de sqlite, no copiar el archivo vivo) y scp."""
    _ssh("cd ~/betbot && betbot/bin/python -c \"import sqlite3; s=sqlite3.connect('data/tracking.sqlite3'); "
         "d=sqlite3.connect('/tmp/linkcopy.sqlite3'); s.backup(d); d.close()\"")
    target = workdir / "linkcopy.sqlite3"
    subprocess.run(["scp", "-q", "-i", str(SSH_KEY), "-o", "BatchMode=yes",
                    f"{VPS}:/tmp/linkcopy.sqlite3", str(target)], check=True, timeout=600)
    _ssh("rm -f /tmp/linkcopy.sqlite3")
    return target


TOKEN = "stats_providers/sportradar_http/engine/reports/session_state_headed.json"


def fetch_token(repo: Path) -> None:
    """El token de Statshub vigente es el del VPS (la Mac lo renueva y lo sube ahí)."""
    subprocess.run(["scp", "-q", "-i", str(SSH_KEY), "-o", "BatchMode=yes",
                    f"{VPS}:~/betbot/{TOKEN}", str(repo / TOKEN)], check=True, timeout=120)


def read_links(db: Path) -> dict[tuple[int, str], dict]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return {(row["competition_id"], row["provider"]): {c: row[c] for c in COLUMNS}
                for row in conn.execute(f"SELECT {', '.join(COLUMNS)} FROM stats_league_links")}
    finally:
        conn.close()


def changed_links(before: dict, after: dict) -> list[dict]:
    """Los links que el vinculador agregó o cambió (liga o nombre distintos)."""
    keys = ("league_id", "league_name", "country_name")
    return [row for key, row in after.items()
            if key not in before or any(before[key][k] != row[k] for k in keys)]


def run_linker(db: Path, provider: str, repo: Path, workdir: Path) -> str:
    cache = workdir / f"{provider}_fixtures.json"
    cache.unlink(missing_ok=True)  # equipos de esta semana, no los de la anterior
    env = {**os.environ, "BETBOT_DB_PATH": str(db), "SPORTRADAR_REPLAY_ONLY": "true",
           "PYTHONPATH": str(repo)}
    result = subprocess.run(
        [sys.executable, "-m", "scripts.link_stats_by_teams", "--chat-id", str(CHAT_ID),
         "--provider", provider, "--cache", str(cache), "--apply"],
        cwd=repo, env=env, capture_output=True, text=True, timeout=1800)
    tail = (result.stdout + result.stderr).strip().splitlines()[-3:]
    return f"{provider}: exit={result.returncode} " + " / ".join(tail)[:300]


def push(rows: list[dict]) -> int:
    if not rows:
        return 0
    out = _ssh(f"cd ~/betbot && betbot/bin/python -c {shlex.quote(_REMOTE_UPSERT)}", stdin=json.dumps(rows))
    return int(out.strip() or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="no sube nada al VPS")
    parser.add_argument("--providers", default=",".join(PROVIDERS))
    parser.add_argument("--workdir", default=str(Path.home() / ".local/share/betbot-token/linker"))
    args = parser.parse_args()

    repo = Path(__file__).resolve().parent.parent
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    db = fetch_copy(workdir)
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    if "sportradar_statshub" in providers:
        fetch_token(repo)
    before = read_links(db)
    for provider in providers:
        print(run_linker(db, provider, repo, workdir), flush=True)
    rows = changed_links(before, read_links(db))
    pushed = 0 if args.dry_run else push(rows)
    summary = {"at": started.isoformat(timespec="seconds"), "links_before": len(before),
               "new_or_changed": len(rows), "pushed": pushed, "dry_run": args.dry_run,
               "links": [f"{r['provider']}: {r['league_name']} (comp {r['competition_id']})" for r in rows]}
    (workdir / "last_run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

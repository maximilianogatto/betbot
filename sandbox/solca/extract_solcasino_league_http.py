from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from betby_http import (  # noqa: E402
    build_league_odds_document,
    config_from_site_url,
    extract_tournament_id,
    fetch_prematch_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract Solcasino/Rainbet league odds through Betby/sptpub HTTP only."
    )
    parser.add_argument("url", help="Solcasino/Rainbet sports URL with bt-path tournament id.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory for JSON outputs.")
    parser.add_argument("--lang", default="en", help="Betby feed language. Defaults to en.")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout per request.")
    parser.add_argument("--save-raw", action="store_true", help="Also save merged_snapshot.json.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON outputs.")
    return parser.parse_args()


def write_json(path: Path, payload: object, *, pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    indent = 2 if pretty else None
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent), encoding="utf-8")


def main() -> int:
    args = parse_args()
    config = config_from_site_url(args.url, language=args.lang)
    tournament_id = extract_tournament_id(args.url)

    manifest, merged_snapshot, chunks = fetch_prematch_snapshot(
        config,
        timeout_seconds=args.timeout,
    )
    league_odds = build_league_odds_document(
        merged_snapshot,
        config=config,
        source_url=args.url,
        tournament_id=tournament_id,
        manifest=manifest,
        chunks=chunks,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "manifest.json", manifest, pretty=args.pretty)
    write_json(args.out_dir / "chunks_summary.json", chunks, pretty=args.pretty)
    write_json(args.out_dir / "league_odds.json", league_odds, pretty=args.pretty)
    if args.save_raw:
        write_json(args.out_dir / "merged_snapshot.json", merged_snapshot, pretty=args.pretty)

    summary = league_odds["summary"]
    print(f"Solcasino/Rainbet HTTP extraction completed: {args.out_dir}")
    print(f"- tournament_id={tournament_id}")
    print(f"- chunks={len(chunks)}")
    print(
        "- matches={matches_count} 1x2={matches_with_1x2} handicap={matches_with_handicap} totals={matches_with_totals}".format(
            **summary
        )
    )
    print(f"- {args.out_dir / 'league_odds.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

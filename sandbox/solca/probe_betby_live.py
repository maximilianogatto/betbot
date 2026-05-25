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
    fetch_live_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe Betby live feed for one tournament through HTTP only."
    )
    parser.add_argument("url", help="Betby sportsbook URL with tournament id in bt-path or path.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory for live probe outputs.")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--save-raw", action="store_true", help="Also save merged_live_snapshot.json.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON outputs.")
    return parser.parse_args()


def write_json(path: Path, payload: object, *, pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    indent = 2 if pretty else None
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent), encoding="utf-8")


def write_report(path: Path, document: dict[str, object]) -> None:
    source = document["source"]  # type: ignore[index]
    league = document["league"]  # type: ignore[index]
    summary = document["summary"]  # type: ignore[index]
    matches = document["matches"]  # type: ignore[index]

    lines = [
        "# Betby Live Probe",
        "",
        f"- Platform: `{source['platform']}`",
        f"- Feed: `{source['feed']}`",
        f"- Tournament id: `{league['league_id']}`",
        f"- League: `{league['league']}`",
        f"- Country: `{league['country']}`",
        f"- Snapshot endpoint: `{source['snapshot_endpoint']}`",
        f"- Chunks: `{len(source['chunk_versions'])}`",
        f"- Matches in live feed: `{summary['matches_in_live_feed']}`",
        f"- Currently live: `{summary['matches_currently_live']}`",
        "",
        "## Matches",
        "",
    ]

    if not matches:
        lines.append("- No target tournament events were present in the live snapshot.")
    for match in matches:
        live_state = match["live_state"]
        clock = live_state.get("clock") or {}
        market_status = match["market_status"]
        lines.append(
            "- {home} vs {away} | live={is_live} status={status} match_status={match_status} clock={clock} 1x2={has_1x2} totals={has_totals} handicap={has_handicap}".format(
                home=match["home"],
                away=match["away"],
                is_live=live_state.get("is_live"),
                status=live_state.get("status_code"),
                match_status=live_state.get("match_status_code"),
                clock=clock.get("match_time") or "-",
                has_1x2=market_status["has_1x2"],
                has_totals=market_status["has_totals"],
                has_handicap=market_status["has_handicap"],
            )
        )

    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "- `version=0` on `/api/v4/live/brand/...` returns the same manifest/chunk pattern as prematch.",
            "- `state.status == 1` and/or `state.clock` are usable first-pass live signals.",
            "- The sandbox keeps `raw_state` because match status code meanings still need mapping per sport/provider.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    config = config_from_site_url(args.url, language=args.lang)
    tournament_id = extract_tournament_id(args.url)

    manifest, merged_snapshot, chunks = fetch_live_snapshot(config, timeout_seconds=args.timeout)
    document = build_league_odds_document(
        merged_snapshot,
        config=config,
        source_url=args.url,
        tournament_id=tournament_id,
        manifest=manifest,
        chunks=chunks,
        feed="live",
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "live_manifest.json", manifest, pretty=args.pretty)
    write_json(args.out_dir / "live_chunks_summary.json", chunks, pretty=args.pretty)
    write_json(args.out_dir / "live_league.json", document, pretty=args.pretty)
    write_report(args.out_dir / "live_probe_report.md", document)
    if args.save_raw:
        write_json(args.out_dir / "merged_live_snapshot.json", merged_snapshot, pretty=args.pretty)

    summary = document["summary"]
    print(f"Betby live probe completed: {args.out_dir}")
    print(f"- tournament_id={tournament_id}")
    print(f"- chunks={len(chunks)}")
    print(
        "- live_feed={matches_in_live_feed} currently_live={matches_currently_live} 1x2={matches_with_1x2} totals={matches_with_totals}".format(
            **summary
        )
    )
    print(f"- {args.out_dir / 'live_league.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from betby_http import (  # noqa: E402
    build_prematch_url,
    config_from_site_url,
    default_headers,
    extract_league_matches,
    extract_tournament_id,
    fetch_json,
    snapshot_versions_from_manifest,
)

import httpx  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe Betby/sptpub snapshot manifest and chunk URLs without browser."
    )
    parser.add_argument("url", help="Solcasino/Rainbet URL with bt-path.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory for probe outputs.")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_report(path: Path, report: dict[str, object]) -> None:
    lines = [
        "# Betby/Sptpub HTTP Probe",
        "",
        f"- Platform: `{report['platform']}`",
        f"- Tournament id: `{report['tournament_id']}`",
        f"- Manifest URL: `{report['manifest_url']}`",
        f"- Manifest status: `{report['manifest_status']}`",
        f"- Manifest version: `{report['manifest_version']}`",
        f"- Chunks discovered: `{len(report['chunks'])}`",
        f"- Target matches found: `{report['target_matches_count']}`",
        "",
        "## Chunks",
        "",
    ]
    for chunk in report["chunks"]:  # type: ignore[index]
        lines.append(
            "- version={version} status={status} bytes={bytes} events={events_count} tournaments={tournaments_count} target={target_hit}".format(
                **chunk
            )
        )
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "- `version=0` returns a small manifest with `top_events_versions` and `rest_events_versions`.",
            "- Each advertised version is a plain HTTP JSON chunk.",
            "- Merging chunks by top-level dictionaries reconstructs the current prematch snapshot.",
            "- This is enough for lightweight browserless league tracking when the target tournament is present.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    config = config_from_site_url(args.url, language=args.lang)
    tournament_id = extract_tournament_id(args.url)
    headers = default_headers(config)
    manifest_url = build_prematch_url(config, 0)
    chunks: list[dict[str, object]] = []

    with httpx.Client(timeout=args.timeout, follow_redirects=True) as client:
        response = client.get(manifest_url, headers=headers)
        response.raise_for_status()
        manifest = response.json()
        if not isinstance(manifest, dict):
            raise ValueError("Manifest response is not a JSON object.")

        versions = snapshot_versions_from_manifest(manifest)
        for version in versions:
            url = build_prematch_url(config, version)
            chunk_response = client.get(url, headers=headers)
            chunk_response.raise_for_status()
            chunk = chunk_response.json()
            if not isinstance(chunk, dict):
                chunk = {}
            target_matches = extract_league_matches(
                chunk,
                tournament_id=tournament_id,
                platform=config.platform,
            )
            chunks.append(
                {
                    "version": version,
                    "url": url,
                    "status": chunk_response.status_code,
                    "bytes": len(chunk_response.content),
                    "events_count": len(chunk.get("events") or {}),
                    "tournaments_count": len(chunk.get("tournaments") or {}),
                    "target_hit": bool(target_matches),
                    "target_matches_count": len(target_matches),
                }
            )

    report = {
        "platform": config.platform,
        "tournament_id": tournament_id,
        "manifest_url": manifest_url,
        "manifest_status": response.status_code,
        "manifest_version": manifest.get("version"),
        "manifest_keys": list(manifest.keys()),
        "versions": versions,
        "chunks": chunks,
        "target_matches_count": sum(int(chunk["target_matches_count"]) for chunk in chunks),
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "manifest.json", manifest)
    write_json(args.out_dir / "snapshot_probe.json", report)
    write_report(args.out_dir / "snapshot_probe_report.md", report)

    print(f"Probe completed: {args.out_dir}")
    print(f"- chunks={len(chunks)}")
    print(f"- target_matches={report['target_matches_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run an HTTP-only SofaScore discovery and match snapshot probe.

The script proves the future provider path without a browser:

    sport categories -> country tournaments -> scheduled/live events -> match

Usage:
    ../BetBot/betbot/bin/python sandbox/sofascore_http/probe_provider.py \
        --date 2026-06-01 \
        --category-id 34 \
        --event-id 16200011 \
        --out-dir sandbox/sofascore_http/examples/http_only_probe
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sandbox.sofascore_http.build_match_snapshot import build_snapshot
from sandbox.sofascore_http.client import SofaScoreHTTPClient
from sandbox.sofascore_http.normalizers import normalize_fixture, normalize_league_option


def run_probe(
    client: SofaScoreHTTPClient,
    *,
    date: str,
    category_id: int,
    event_id: int | None,
) -> dict[str, Any]:
    """Fetch compact discovery samples and an optional match snapshot."""

    categories = client.get_categories()
    tournaments = client.get_category_tournaments(category_id)
    scheduled_events = client.get_scheduled_events(date)
    live_events = client.get_live_events()
    snapshot = build_snapshot(client, event_id) if event_id is not None else None
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "transport": "curl_cffi_http_only",
        "browser_required": False,
        "inputs": {
            "date": date,
            "category_id": category_id,
            "event_id": event_id,
        },
        "counts": {
            "football_categories": len(categories),
            "category_tournaments": len(tournaments),
            "scheduled_events": len(scheduled_events),
            "live_events": len(live_events),
        },
        "category_tournaments": [normalize_league_option(item) for item in tournaments],
        "scheduled_event_samples": [normalize_fixture(item) for item in scheduled_events[:10]],
        "live_event_samples": [normalize_fixture(item) for item in live_events[:10]],
        "match_snapshot": snapshot,
    }


def render_report(payload: dict[str, Any]) -> str:
    """Render one concise feasibility report from an HTTP-only probe."""

    counts = payload["counts"]
    inputs = payload["inputs"]
    snapshot = payload.get("match_snapshot")
    lines = [
        "# SofaScore HTTP-only Provider Probe",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Transport: `{payload['transport']}`",
        f"- Browser required after discovery: `{payload['browser_required']}`",
        f"- Date: `{inputs['date']}`",
        f"- Category ID: `{inputs['category_id']}`",
        "",
        "## Discovery",
        "",
        f"- Football categories: `{counts['football_categories']}`",
        f"- Tournaments in selected category: `{counts['category_tournaments']}`",
        f"- Scheduled events on date: `{counts['scheduled_events']}`",
        f"- Live football events: `{counts['live_events']}`",
        "",
        "## Useful HTTP endpoints",
        "",
        "- `sport/football/categories/all`: country/category discovery.",
        "- `category/<id>/unique-tournaments`: league discovery.",
        "- `unique-tournament/<id>/seasons`: season discovery.",
        "- `sport/football/scheduled-events/<date>`: prematch fixture discovery.",
        "- `sport/football/events/live`: live fixture discovery.",
        "- `event/<id>`: event metadata, status, score and clock.",
        "- `event/<id>/statistics`: match statistics when covered.",
        "- `event/<id>/incidents`: goals, cards, substitutions and period markers.",
        "- `event/<id>/lineups`: lineups when covered.",
        "- `event/<id>/h2h`: compact H2H counters.",
        "- `event/<id>/win-probability`: SofaScore probability model when covered.",
        "- `event/<id>/odds/1/all`: provider-specific odds, including live 1X2.",
        "",
    ]
    if isinstance(snapshot, dict):
        match = snapshot["match"]
        coverage = snapshot["coverage"]
        lines.extend(
            [
                "## Match sample",
                "",
                f"- Match: `{match['home']} vs {match['away']}`",
                f"- SofaScore event ID: `{match['match_id']}`",
                f"- Status: `{match['status']}` / `{match['status_description']}`",
                f"- Score: `{match['score_home']}-{match['score_away']}`",
                f"- Coverage: `{json.dumps(coverage, ensure_ascii=False, sort_keys=True)}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Conclusion",
            "",
            "SofaScore is viable as an HTTP-only stats-provider candidate when requests use "
            "`curl_cffi`. Plain `httpx` replay returned `403` for every tested URL, while "
            "`curl_cffi` returned JSON without browser cookies or a bootstrap token. Keep "
            "Playwright only as an offline endpoint-discovery tool.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    """Run and persist the HTTP-only provider probe."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--category-id", type=int, required=True)
    parser.add_argument("--event-id", type=int)
    parser.add_argument("--out-dir", type=Path, default=Path("sandbox/sofascore_http/examples/http_only_probe"))
    args = parser.parse_args()

    payload = run_probe(
        SofaScoreHTTPClient(),
        date=args.date,
        category_id=args.category_id,
        event_id=args.event_id,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "provider_probe.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.out_dir / "provider_probe.md").write_text(render_report(payload), encoding="utf-8")
    print(f"Wrote SofaScore HTTP-only provider probe to {args.out_dir}")


if __name__ == "__main__":
    main()


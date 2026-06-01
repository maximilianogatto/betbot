"""Validate the bot-ready SofaScore adapter over HTTP-only requests.

Usage:
    ../BetBot/betbot/bin/python sandbox/sofascore_http/validate_bot_ready.py \
        --country Australia \
        --query "Northern NSW" \
        --league-id 1638 \
        --event-id 16200011 \
        --out-dir sandbox/sofascore_http/examples/bot_ready_validation
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from stats_providers.sofascore_http import SofaScoreBotReadyStatsProvider


async def run_validation(
    provider: SofaScoreBotReadyStatsProvider,
    *,
    country: str,
    query: str | None,
    league_id: str,
    event_id: str | None,
) -> dict[str, Any]:
    """Run one compact future-BetBot provider flow."""

    leagues = await provider.search_leagues(country_name=country, query=query)
    fixtures = await provider.list_fixtures(league_id)
    overview = await provider.get_league_overview(league_id)
    report = await provider.build_match_report(event_id) if event_id else None
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": asdict(provider.describe_provider()),
        "inputs": {
            "country": country,
            "query": query,
            "league_id": league_id,
            "event_id": event_id,
        },
        "counts": {
            "matching_leagues": len(leagues),
            "league_fixtures": len(fixtures),
            "standings_tables": len((overview or {}).get("standings", {}).get("tables") or []),
        },
        "league_samples": [_compact_model(item) for item in leagues[:10]],
        "fixture_samples": [_compact_model(item) for item in fixtures[:10]],
        "league_overview": overview,
        "match_report": asdict(report) if report else None,
    }


def _compact_model(value: Any) -> dict[str, Any]:
    """Serialize one dataclass sample without repeating provider-native payloads."""

    payload = asdict(value)
    payload.pop("raw_payload", None)
    return payload


def render_validation_report(payload: dict[str, Any]) -> str:
    """Render a concise Markdown summary suitable for code review."""

    inputs = payload["inputs"]
    counts = payload["counts"]
    lines = [
        "# SofaScore Bot-ready Validation",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Country: `{inputs['country']}`",
        f"- Query: `{inputs['query']}`",
        f"- League ID: `{inputs['league_id']}`",
        f"- Event ID: `{inputs['event_id']}`",
        "",
        "## Contract Flow",
        "",
        f"- Matching leagues: `{counts['matching_leagues']}`",
        f"- Current-season fixtures: `{counts['league_fixtures']}`",
        f"- Standings tables: `{counts['standings_tables']}`",
        "",
    ]
    report = payload.get("match_report")
    if isinstance(report, dict):
        lines.extend(["## Match Report", "", str(report.get("markdown") or "Sin reporte."), ""])
    lines.extend(
        [
            "## Conclusion",
            "",
            "The adapter implements BetBot's `StatsProvider` contract without browser "
            "bootstrap. It remains isolated under `sandbox/` until production registration "
            "is explicitly approved.",
            "",
        ]
    )
    return "\n".join(lines)


async def async_main(args: argparse.Namespace) -> None:
    """Run validation and write inspectable outputs."""

    provider = SofaScoreBotReadyStatsProvider()
    try:
        payload = await run_validation(
            provider,
            country=args.country,
            query=args.query,
            league_id=args.league_id,
            event_id=args.event_id,
        )
    finally:
        await provider.stop()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "bot_ready_validation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.out_dir / "bot_ready_validation.md").write_text(
        render_validation_report(payload),
        encoding="utf-8",
    )
    print(f"Wrote SofaScore bot-ready validation to {args.out_dir}")


def main() -> None:
    """Parse command-line arguments and run validation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", required=True)
    parser.add_argument("--query")
    parser.add_argument("--league-id", required=True)
    parser.add_argument("--event-id")
    parser.add_argument("--out-dir", type=Path, default=Path("sandbox/sofascore_http/examples/bot_ready_validation"))
    asyncio.run(async_main(parser.parse_args()))


if __name__ == "__main__":
    main()

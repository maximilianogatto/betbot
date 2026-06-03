"""Run a compact Svenskfotboll HTTP-only probe.

Example:
    ./betbot/bin/python sandbox/svenskfotboll_http/probe_svenskfotboll.py \\
      --query allsvenskan --ftid 133348 --out-dir sandbox/svenskfotboll_http/examples/latest

Outputs:
    leagues.json
    league_snapshot.json
    live_snapshot.json
    endpoint_report.md
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from sandbox.svenskfotboll_http.client import SvenskfotbollHTTPClient


def build_probe(
    *,
    query: str | None,
    ftid: str | None,
    out_dir: Path,
    limit: int,
    live_date: date | None = None,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}

    with SvenskfotbollHTTPClient() as client:
        leagues = client.search_leagues(query=query, limit=limit)
        outputs["leagues"] = _write_json(out_dir / "leagues.json", leagues)

        if ftid:
            standings = client.get_standings(ftid)
            upcoming = client.get_upcoming_matches(ftid, limit=limit)
            latest = client.get_latest_results(ftid, limit=limit)
            league_snapshot = {
                "provider": "svenskfotboll_http",
                "competition_id": str(ftid),
                "standings": standings,
                "upcoming_matches": upcoming,
                "latest_results": latest,
            }
            outputs["league_snapshot"] = _write_json(out_dir / "league_snapshot.json", league_snapshot)

        ticker = client.get_livescore_ticker()
        overview = client.get_live_overview(day=live_date)
        first_live_id = next((game["match_id"] for game in ticker if game.get("is_live") and game.get("match_id")), None)
        game_info = client.get_live_game_info(first_live_id) if first_live_id else None
        live_snapshot = {
            "provider": "svenskfotboll_http",
            "ticker": ticker,
            "overview": overview,
            "sample_game_info": game_info,
        }
        outputs["live_snapshot"] = _write_json(out_dir / "live_snapshot.json", live_snapshot)

        outputs["endpoint_report"] = _write_text(
            out_dir / "endpoint_report.md",
            render_endpoint_report(
                query=query,
                ftid=ftid,
                leagues=leagues,
                league_snapshot=league_snapshot if ftid else None,
                live_snapshot=live_snapshot,
            ),
        )

    return outputs


def render_endpoint_report(
    *,
    query: str | None,
    ftid: str | None,
    leagues: list[dict[str, Any]],
    league_snapshot: dict[str, Any] | None,
    live_snapshot: dict[str, Any],
) -> str:
    lines = [
        "# Svenskfotboll HTTP Probe",
        "",
        "## Summary",
        "",
        "- Discovery works via `/api/comp-find/filter` and `/api/comp-find/getfiltercriteria`.",
        "- League standings, upcoming fixtures and latest results work via `/widget.aspx` with `ftid`.",
        "- Live state works via `/api/livescore-ticker/` plus FOGIS XML under `c01.fogis.se`.",
        "- Detail pages and `go-to` pages are Cloudflare-protected and should not be part of the lightweight provider.",
        "",
        "## Query",
        "",
        f"- query: `{query or ''}`",
        f"- ftid: `{ftid or ''}`",
        f"- league matches found: `{len(leagues)}`",
        "",
        "## Useful Endpoints",
        "",
        "| Purpose | Endpoint | Payload | Notes |",
        "| --- | --- | --- | --- |",
        "| League discovery | `/api/comp-find/filter` | JSON | Large full tree, client-side filtering. |",
        "| Filter metadata | `/api/comp-find/getfiltercriteria` | JSON | Association/district/gender/age filters. |",
        "| Matches today | `/api/matches-today/games/?associationId=1&dateOffset=0` | JSON | Good for national/today fixture scan. |",
        "| League standings | `/widget.aspx?p=1&scr=tablesmall&ftid=<id>` | JSON + HTML table | Parseable without browser. |",
        "| Upcoming fixtures | `/widget.aspx?p=1&scr=cominginleague&ftid=<id>&nbr=<n>` | JSON + HTML table | Provides `fmid` in row links. |",
        "| Latest results | `/widget.aspx?p=1&scr=latestinleague&ftid=<id>&nbr=<n>` | JSON + HTML table | Provides scores and `fmid`. |",
        "| Live ticker | `/api/livescore-ticker/` | JSON | Quick live/finished/today status. |",
        "| Live overview | `https://c01.fogis.se/.../overview-1-YYYYMMDD.xml` | XML | Full daily live state by association. |",
        "| Live game info | `https://c01.fogis.se/.../game-info-<fmid>.xml` | XML | Events, score, status, aggregate stats. |",
        "| Live changes | `https://c01.fogis.se/.../changes-1.xml` | XML | Polling index for changed game XML files. |",
        "",
    ]
    if leagues:
        lines.extend(["## League Examples", ""])
        for item in leagues[:10]:
            lines.append(
                f"- `{item.get('competition_id')}` {item.get('name')} "
                f"categories={', '.join(item.get('categories') or [])}"
            )
        lines.append("")
    if league_snapshot:
        standings = league_snapshot.get("standings", {})
        upcoming = league_snapshot.get("upcoming_matches", {})
        latest = league_snapshot.get("latest_results", {})
        lines.extend(
            [
                "## League Snapshot",
                "",
                f"- standings teams: `{len(standings.get('teams') or [])}`",
                f"- upcoming matches: `{len(upcoming.get('matches') or [])}`",
                f"- latest results: `{len(latest.get('matches') or [])}`",
                "",
            ]
        )
    ticker = live_snapshot.get("ticker") or []
    sample = live_snapshot.get("sample_game_info") or {}
    lines.extend(
        [
            "## Live Snapshot",
            "",
            f"- ticker games: `{len(ticker)}`",
            f"- live ticker games: `{sum(1 for game in ticker if game.get('is_live'))}`",
            f"- sample live match id: `{sample.get('match_id') or ''}`",
            f"- sample event summary: `{json.dumps(sample.get('event_summary') or {}, ensure_ascii=False)}`",
            "",
            "## Feasibility",
            "",
            "This can become a BetBot stats provider for Swedish competitions.",
            "The strongest version is HTTP-only for discovery, fixtures, standings, results and live game XML.",
            "Limitations: league/match detail pages are Cloudflare-protected, and widget tables are HTML inside JSON rather than clean JSON.",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_json(path: Path, value: Any) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_text(path: Path, value: str) -> Path:
    path.write_text(value, encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe Svenskfotboll HTTP endpoints.")
    parser.add_argument("--query", default="allsvenskan", help="League search query.")
    parser.add_argument("--ftid", default=None, help="Competition id to fetch through widgets.")
    parser.add_argument("--limit", type=int, default=20, help="Max leagues/matches to keep.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("sandbox/svenskfotboll_http/examples/latest"),
        help="Output directory.",
    )
    parser.add_argument("--live-date", default=None, help="YYYY-MM-DD for livescore overview; defaults to today.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    live_date = date.fromisoformat(args.live_date) if args.live_date else None
    outputs = build_probe(query=args.query, ftid=args.ftid, out_dir=args.out_dir, limit=args.limit, live_date=live_date)
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()

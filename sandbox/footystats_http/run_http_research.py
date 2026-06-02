"""Run a compact browserless FootyStats feasibility check.

The output intentionally stores summaries rather than raw HTML or giant API
responses. This makes the evidence safe to inspect and cheap to regenerate.

Usage:
    ./betbot/bin/python sandbox/footystats_http/run_http_research.py \
        --out-dir sandbox/footystats_http/examples/latest
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sandbox.footystats_http.client import FootyStatsHTTPClient
from sandbox.footystats_http.normalizers import (
    discover_league_links,
    extract_embedded_match_data,
    extract_match_page_ids,
    extract_script_ajax_endpoints,
    parse_match_live_panel,
)


DEFAULT_LEAGUE_PATH = "/australia/northern-nsw-npl"
DEFAULT_MATCH_PATH = "/morocco/olympique-dcheira-vs-club-omnisports-de-meknes-h2h-stats"
GLOBAL_SCRIPT_URL = "https://cdn.footystats.org/js/global-min159.js"


def utc_now_iso() -> str:
    """Return one UTC generation timestamp."""

    return datetime.now(UTC).isoformat()


def build_summary(
    client: FootyStatsHTTPClient,
    *,
    league_path: str,
    match_path: str,
    include_official_demo: bool,
) -> dict[str, Any]:
    """Fetch representative sources and return bounded feasibility evidence."""

    homepage = client.fetch_public_page("/")
    league_html = client.fetch_public_page(league_path)
    match_html = client.fetch_public_page(match_path)
    live_scores = client.fetch_live_scores()
    script_text = client.request("GET", GLOBAL_SCRIPT_URL).text
    leagues = discover_league_links(homepage)
    australia_leagues = [item.to_dict() for item in leagues if item.country_slug == "australia"]
    official_demo: dict[str, Any] | None = None
    if include_official_demo:
        payload = client.official_api_request(
            "league-matches",
            api_key="example",
            params={"league_id": 2012},
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        first_match = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
        official_demo = {
            "success": payload.get("success") if isinstance(payload, dict) else None,
            "pager": payload.get("pager") if isinstance(payload, dict) else None,
            "match_count": len(data) if isinstance(data, list) else None,
            "sample_match_id": str(first_match.get("id")) if first_match.get("id") is not None else None,
            "sample_keys": sorted(first_match),
            "sample_odds_keys": sorted(key for key in first_match if key.startswith("odds_")),
        }
    match_ids = extract_match_page_ids(match_html)
    return {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "sources": {
            "homepage": "https://footystats.org/",
            "league_page": f"https://footystats.org{league_path}",
            "match_page": f"https://footystats.org{match_path}",
            "live_scores": "https://footystats.org/ajax_livescore.php",
            "official_api_demo": (
                "https://api.football-data-api.com/league-matches?key=example&league_id=2012"
                if include_official_demo
                else None
            ),
        },
        "public_html": {
            "homepage_bytes": len(homepage.encode()),
            "discovered_league_count": len(leagues),
            "australia_league_count": len(australia_leagues),
            "australia_leagues_sample": australia_leagues[:10],
            "league_page_bytes": len(league_html.encode()),
            "league_embedded_match_count": len(extract_embedded_match_data(league_html)),
            "match_page_bytes": len(match_html.encode()),
            "match_page_ids": match_ids,
            "match_live_panel": parse_match_live_panel(match_html),
        },
        "public_ajax": {
            "live_score_count": len(live_scores),
            "live_scores": [item.to_dict() for item in live_scores],
            "script_endpoint_count": len(extract_script_ajax_endpoints(script_text)),
            "script_endpoints": extract_script_ajax_endpoints(script_text),
        },
        "official_api_demo": official_demo,
        "metrics": [metric.to_dict() for metric in client.metrics],
    }


def render_report(summary: dict[str, Any]) -> str:
    """Render a concise Markdown feasibility report."""

    public_html = summary["public_html"]
    public_ajax = summary["public_ajax"]
    official_demo = summary["official_api_demo"]
    lines = [
        "# FootyStats HTTP Feasibility",
        "",
        f"Generated at `{summary['generated_at']}`.",
        "",
        "## Result",
        "",
        "FootyStats can be queried without a browser. It exposes three distinct contracts:",
        "",
        "1. Public server-rendered HTML pages with league discovery and rich stats.",
        "2. Public AJAX helpers, including a browserless live-score JSON feed.",
        "3. An official key-authenticated JSON API intended for stable integrations.",
        "",
        "## Public HTML",
        "",
        f"- Discovered league links from homepage: `{public_html['discovered_league_count']}`.",
        f"- Australian league links: `{public_html['australia_league_count']}`.",
        f"- Embedded league match records: `{public_html['league_embedded_match_count']}`.",
        f"- Match page IDs: `{public_html['match_page_ids']}`.",
        f"- Live match panel present in sampled page: `{public_html['match_live_panel']['is_live_panel_present']}`.",
        "",
        "## Public AJAX",
        "",
        f"- Current live-score records: `{public_ajax['live_score_count']}`.",
        f"- AJAX endpoints referenced by frontend script: `{public_ajax['script_endpoint_count']}`.",
        "",
    ]
    if official_demo:
        lines.extend(
            [
                "## Official JSON API",
                "",
                f"- Demo request success: `{official_demo['success']}`.",
                f"- Demo league matches returned: `{official_demo['match_count']}`.",
                f"- Sample odds fields: `{len(official_demo['sample_odds_keys'])}`.",
                "",
            ]
        )
    lines.extend(
        [
            "## Recommendation",
            "",
            "Use the official JSON API as the production candidate if a licensed key is available. "
            "Use public HTML and AJAX only as an isolated research/fallback path because their markup "
            "and undocumented endpoint contracts can change without notice.",
            "",
        ]
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Execute the HTTP-only research pass and write compact outputs."""

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with FootyStatsHTTPClient(timeout=args.timeout, retries=args.retries) as client:
        summary = build_summary(
            client,
            league_path=args.league_path,
            match_path=args.match_path,
            include_official_demo=not args.skip_official_demo,
        )
    (out_dir / "http_research_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "http_feasibility_report.md").write_text(render_report(summary), encoding="utf-8")
    return summary


def main() -> None:
    """Run the compact HTTP-only FootyStats feasibility CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="sandbox/footystats_http/examples/latest")
    parser.add_argument("--league-path", default=DEFAULT_LEAGUE_PATH)
    parser.add_argument("--match-path", default=DEFAULT_MATCH_PATH)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--skip-official-demo", action="store_true")
    args = parser.parse_args()
    summary = run(args)
    print(
        "FootyStats HTTP research complete: "
        f"leagues={summary['public_html']['discovered_league_count']} "
        f"live_scores={summary['public_ajax']['live_score_count']} "
        f"output={args.out_dir}"
    )


if __name__ == "__main__":
    main()

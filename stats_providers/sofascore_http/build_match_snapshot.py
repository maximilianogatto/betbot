"""Build a compact SofaScore match snapshot over HTTP-only endpoints.

Usage:
    ../BetBot/betbot/bin/python sandbox/sofascore_http/build_match_snapshot.py \
        16200011 \
        --out sandbox/sofascore_http/captures/live_16200011/match_snapshot.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from stats_providers.sofascore_http.client import SofaScoreHTTPClient
from stats_providers.sofascore_http.normalizers import build_match_snapshot


def build_snapshot(client: SofaScoreHTTPClient, event_id: int) -> dict:
    """Fetch optional event documents defensively and normalize one snapshot."""

    return build_match_snapshot(
        event=client.get_event(event_id),
        statistics=client.get_event_statistics(event_id),
        incidents=client.get_event_incidents(event_id),
        lineups=client.get_event_lineups(event_id),
        h2h=client.get_event_h2h(event_id),
        win_probability=client.get_event_win_probability(event_id),
        odds=client.get_event_odds(event_id),
    )


def main() -> None:
    """Run the HTTP-only snapshot builder."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event_id", type=int)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    snapshot = build_snapshot(SofaScoreHTTPClient(), args.event_id)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    match = snapshot["match"]
    print(
        f"Built SofaScore snapshot {args.out}: "
        f"{match.get('home')} vs {match.get('away')} status={match.get('status')}"
    )


if __name__ == "__main__":
    main()

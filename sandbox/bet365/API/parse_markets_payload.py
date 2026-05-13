from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from parser import (
    build_league_1x2_projection,
    build_event_url,
    detect_payload_kind,
    extract_sportradar_url,
    flatten_markets,
    looks_like_coupon_payload,
    looks_like_markets_payload,
    parse_bet365_payload_file,
    parse_bet365_payload_text,
    parse_coupon_payload_file,
    parse_coupon_payload_text,
    parse_markets_payload_file,
    parse_markets_payload_text,
    summarize_parsed_payload,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parsea payloads pipe-separated de Bet365 capturados desde red.",
    )
    parser.add_argument("input_path", help="Archivo .txt/.body con el payload crudo.")
    parser.add_argument("--out", help="Archivo destino para el JSON parseado.")
    parser.add_argument(
        "--host",
        default="www.bet365.es",
        help="Host usado para construir event_url a partir de event_pd.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    parsed = parse_bet365_payload_file(args.input_path, host=args.host)
    payload_type = parsed.get("payload_type")

    if payload_type == "unknown":
        print("No pude reconocer el tipo de payload Bet365.", file=sys.stderr)
        return 1

    print(summarize_parsed_payload(parsed), file=sys.stderr)

    if args.out:
        output_path = Path(args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if payload_type == "markets":
            league_events_path = output_path.parent / "parsed_league_events.json"
            league_markets_path = output_path.parent / "parsed_league_markets.json"
            league_events_path.write_text(
                json.dumps(parsed.get("events") or [], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            league_markets_path.write_text(
                json.dumps(flatten_markets(parsed.get("events") or []), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    sys.stdout.write(json.dumps(parsed, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

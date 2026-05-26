from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.http_research.core import build_endpoint_catalog
from sandbox.sportradar_stats.http_research.reporting import (
    render_endpoint_catalog,
    render_token_analysis,
    summarize_tokens,
    utc_now_iso,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild Statshub HTTP research reports from responses.ndjson.")
    parser.add_argument("capture_dir", type=Path)
    return parser.parse_args()


def iter_records(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def main() -> int:
    args = parse_args()
    responses_path = args.capture_dir / "responses.ndjson"
    fetch_only_path = args.capture_dir / "fetch_only.ndjson"
    if not responses_path.exists():
        raise FileNotFoundError(responses_path)
    records = list(iter_records(responses_path))
    catalog = build_endpoint_catalog(records)
    rendered_catalog = render_endpoint_catalog(catalog)
    (args.capture_dir / "endpoints_index.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.capture_dir / "endpoint_report.md").write_text(rendered_catalog, encoding="utf-8")
    (args.capture_dir / "endpoint_catalog.md").write_text(rendered_catalog, encoding="utf-8")
    token_payload = {
        "generated_at": utc_now_iso(),
        "source": str(fetch_only_path),
        "signed_url_count": sum(1 for record in records if record.get("has_signed_token")),
        "token_payloads": summarize_tokens(records),
        "mutation_results": [],
    }
    (args.capture_dir / "token_analysis.md").write_text(
        render_token_analysis(token_payload),
        encoding="utf-8",
    )
    print(f"Wrote {args.capture_dir / 'endpoints_index.json'}")
    print(f"Wrote {args.capture_dir / 'endpoint_catalog.md'}")
    print(f"Wrote {args.capture_dir / 'token_analysis.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Generate Markdown documentation from typed endpoint specs."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stats_providers.sportradar_http.engine.endpoints.catalog import render_endpoint_catalog_v2


def main() -> int:
    """Write `reports/endpoint_catalog_v2.md`."""

    out = Path("stats_providers/sportradar_http/engine/reports/endpoint_catalog_v2.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_endpoint_catalog_v2(), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

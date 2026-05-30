"""Generate Markdown documentation for derived feature definitions."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stats_providers.sportradar_http.engine.features_engine import FEATURE_DEFINITIONS, MATCH_FEATURE_DEFINITIONS


DEFAULT_OUT = Path("stats_providers/sportradar_http/engine/reports/feature_catalog.md")


def parse_args() -> argparse.Namespace:
    """Parse output path for the generated feature catalog."""

    parser = argparse.ArgumentParser(description="Generate Sportradar feature catalog documentation.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def render_feature_catalog() -> str:
    """Render feature definitions and interpretation notes as Markdown."""

    lines = [
        "# Sportradar Feature Catalog",
        "",
        f"- Generated at: `{datetime.now(UTC).isoformat()}`",
        "- Scope: research-only feature definitions for `stats_providers/sportradar_http/engine`.",
        "",
        "## Conventions",
        "",
        "- Positive gap features favor the home team unless the definition says otherwise.",
        "- Rates are normalized to `0..1` when the source metric is naturally a share.",
        "- Raw goal features keep football units, usually goals per match, and are not probabilities.",
        "- Missing evidence must remain `None`; the feature engine must not invent values.",
        "- `attack_strength` is a context index, not a probability or model prediction.",
        "",
        "## League Features",
        "",
    ]
    for key, definition in sorted(FEATURE_DEFINITIONS.items()):
        lines.append(f"- `{key}`: {definition}")
    lines.extend(["", "## Match Features", ""])
    for key, definition in sorted(MATCH_FEATURE_DEFINITIONS.items()):
        lines.append(f"- `{key}`: {definition}")
    lines.extend(
        [
            "",
            "## Interpretation Notes",
            "",
            "- `attack_strength_home = mean(home home-split goals_for_avg, away away-split goals_against_avg)`.",
            "- `attack_strength_away = mean(away away-split goals_for_avg, home home-split goals_against_avg)`.",
            "- `over_tendency_index = mean(attack_strength_home, attack_strength_away)`, so values are in raw goals-context units.",
            "- `btts_tendency_index` is a `0..1` share when both teams have BTTS split rates.",
            "- `h2h_home_edge` ranges from `-1..1`; positive means H2H evidence favors the home team.",
            "- Live pressure shares use dangerous attack counts from `stats_match_situation` and sum to `1.0` when both sides have evidence.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    """Write the generated feature catalog to disk."""

    args = parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_feature_catalog(), encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

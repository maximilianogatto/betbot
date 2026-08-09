"""Pure compact report rendering for SofaScore match snapshots."""

from __future__ import annotations

from typing import Any

from services.unified_match_report import render_unified_match_report


def render_match_report(snapshot: dict[str, Any]) -> str:
    """Render a comprehensive, standardized match report."""

    return render_unified_match_report(snapshot)


__all__ = ["render_match_report"]

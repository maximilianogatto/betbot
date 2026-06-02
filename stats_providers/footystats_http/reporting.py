"""Compact provider-level report rendering for FootyStats."""

from __future__ import annotations

from typing import Any


def render_match_report(snapshot: dict[str, Any]) -> str:
    """Render a readable report without coupling the provider to Telegram."""

    match = snapshot.get("match") if isinstance(snapshot.get("match"), dict) else {}
    live = snapshot.get("live_state") if isinstance(snapshot.get("live_state"), dict) else {}
    lines = [
        str(match.get("title") or "Partido FootyStats"),
        "",
        f"- Fuente: {snapshot.get('source_mode') or 'public_html'}",
        f"- Estado: {match.get('status') or 'sin confirmar'}",
    ]
    if live.get("score_home") is not None and live.get("score_away") is not None:
        minute = f" · {live.get('minute')}'" if live.get("minute") else ""
        lines.append(f"- Live: {live['score_home']}-{live['score_away']}{minute}")
    source_url = snapshot.get("source_url")
    if source_url:
        lines.extend(["", f"🔗 {source_url}"])
    lines.extend(
        [
            "",
            "Cobertura pública inicial: fixtures, tabla y marcador live liviano.",
            "Para ampliar H2H, odds y métricas avanzadas configurá FOOTYSTATS_API_KEY.",
        ]
    )
    return "\n".join(lines)


__all__ = ["render_match_report"]

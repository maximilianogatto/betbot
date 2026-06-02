"""Render a compact Markdown match report from Flashscore feeds."""

from __future__ import annotations

from typing import Any

# Flashscore incident type codes (df_sui IE field) -> short Spanish label.
_INCIDENT_TYPES = {
    "8": "⚽ Gol",
    "1": "⚽ Gol",
    "7": "🟨 Amarilla",
    "4": "🟥 Roja",
    "9": "🔄 Cambio",
    "2": "🟨🟨 Doble amarilla",
}


def render_match_report(snapshot: dict[str, Any]) -> str:
    """Build the Telegram-ready report from a normalized Flashscore snapshot."""

    match = snapshot.get("match") or {}
    home = match.get("home") or "Local"
    away = match.get("away") or "Visitante"
    lines = [f"{home} vs {away}", ""]

    status = match.get("status")
    score = match.get("score")
    if score:
        lines.append(f"- Marcador: {score}")
    if status:
        lines.append(f"- Estado: {status}")
    if match.get("kickoff_utc"):
        lines.append(f"- Inicio UTC: {match['kickoff_utc']}")

    stats = snapshot.get("statistics") or []
    if stats:
        lines.append("\nEstadísticas:")
        for row in stats[:10]:
            name = row.get("name")
            h = row.get("home")
            a = row.get("away")
            if name and (h or a):
                lines.append(f"- {name}: {h} | {a}")

    incidents = snapshot.get("incidents") or []
    if incidents:
        lines.append("\nEventos:")
        for inc in incidents[:12]:
            label = _INCIDENT_TYPES.get(str(inc.get("type")), inc.get("type") or "")
            minute = inc.get("minute") or ""
            player = inc.get("player") or ""
            running = ""
            if inc.get("home_score") or inc.get("away_score"):
                running = f" ({inc.get('home_score') or 0}-{inc.get('away_score') or 0})"
            lines.append(f"- {minute} {label}{running} {player}".rstrip())

    return "\n".join(lines)

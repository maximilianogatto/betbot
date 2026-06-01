"""Pure compact report rendering for SofaScore match snapshots."""

from __future__ import annotations

from typing import Any


_STAT_LABELS = (
    "Ball possession",
    "Corner kicks",
    "Yellow cards",
    "Red cards",
    "Shots on target",
    "Shots off target",
)


def render_match_report(snapshot: dict[str, Any]) -> str:
    """Render one readable provider-level report without Telegram coupling."""

    match = snapshot.get("match") if isinstance(snapshot.get("match"), dict) else {}
    live = snapshot.get("live_state") if isinstance(snapshot.get("live_state"), dict) else {}
    lines = [
        f"{match.get('home') or 'Local'} vs {match.get('away') or 'Visitante'}",
        "",
        f"- Estado: {_status_label(match)}",
    ]
    score_home = match.get("score_home")
    score_away = match.get("score_away")
    if score_home is not None and score_away is not None:
        lines.append(f"- Marcador: {score_home}-{score_away}")
    scheduled = str(match.get("start_time_utc") or "")
    if len(scheduled) >= 16:
        lines.append(f"- Inicio UTC: {scheduled[:16].replace('T', ' ')}")

    odds = snapshot.get("odds") if isinstance(snapshot.get("odds"), dict) else {}
    odds_1x2 = odds.get("1x2") if isinstance(odds.get("1x2"), dict) else {}
    if any(value is not None for value in odds_1x2.values()):
        lines.extend(["", "Odds 1X2:", f"- 1={_fmt(odds_1x2.get('home'))} | X={_fmt(odds_1x2.get('draw'))} | 2={_fmt(odds_1x2.get('away'))}"])

    win_probability = snapshot.get("win_probability")
    if isinstance(win_probability, dict) and win_probability:
        lines.extend(
            [
                "",
                "Probabilidad SofaScore:",
                f"- Local {_pct(win_probability.get('homeWin'))} | Empate {_pct(win_probability.get('draw'))} | Visitante {_pct(win_probability.get('awayWin'))}",
            ]
        )

    statistics = live.get("statistics") if isinstance(live.get("statistics"), dict) else {}
    visible_stats = [(label, statistics[label]) for label in _STAT_LABELS if isinstance(statistics.get(label), dict)]
    if visible_stats:
        lines.extend(["", "Estadísticas:"])
        for label, values in visible_stats:
            lines.append(f"- {label}: {_fmt(values.get('home'))} | {_fmt(values.get('away'))}")

    h2h = snapshot.get("h2h") if isinstance(snapshot.get("h2h"), dict) else {}
    duel = h2h.get("teamDuel") if isinstance(h2h.get("teamDuel"), dict) else {}
    if duel:
        lines.extend(
            [
                "",
                "H2H:",
                f"- Local {duel.get('homeWins', 0)} | Empates {duel.get('draws', 0)} | Visitante {duel.get('awayWins', 0)}",
            ]
        )

    incidents = [item for item in live.get("incidents") or [] if _is_reportable_incident(item)]
    if incidents:
        lines.extend(["", "Eventos recientes:"])
        for incident in incidents[:8]:
            lines.append(f"- {_incident_label(incident)}")

    coverage = snapshot.get("coverage") if isinstance(snapshot.get("coverage"), dict) else {}
    available = sorted(key.removeprefix("has_") for key, value in coverage.items() if value)
    if available:
        lines.extend(["", f"Cobertura: {', '.join(available)}"])
    return "\n".join(lines)


def _status_label(match: dict[str, Any]) -> str:
    status = str(match.get("status_description") or match.get("status") or "unknown")
    return status


def _is_reportable_incident(incident: Any) -> bool:
    return isinstance(incident, dict) and incident.get("incidentType") in {"goal", "card"}


def _incident_label(incident: dict[str, Any]) -> str:
    minute = incident.get("time")
    prefix = f"{minute}' " if minute is not None else ""
    side = "local" if incident.get("isHome") else "visitante"
    incident_type = incident.get("incidentType")
    player = incident.get("player") if isinstance(incident.get("player"), dict) else {}
    name = player.get("name") or "Jugador"
    if incident_type == "goal":
        score = ""
        if incident.get("homeScore") is not None and incident.get("awayScore") is not None:
            score = f" ({incident['homeScore']}-{incident['awayScore']})"
        return f"{prefix}Gol {side}: {name}{score}"
    card = incident.get("incidentClass") or "card"
    return f"{prefix}{card} {side}: {name}"


def _fmt(value: Any) -> str:
    return "-" if value is None else str(value)


def _pct(value: Any) -> str:
    return "-" if value is None else f"{value}%"


__all__ = ["render_match_report"]

"""Mensaje del panel de stats en vivo (/live_stats, /view_match y el botón de las alertas)."""

from __future__ import annotations

from datetime import datetime
from html import escape as _escape

from core.live_stats import LiveStatsView

_SOURCE_NAMES = {"1xbet": "1xBet", "statshub": "Statshub"}


def escape(text: str) -> str:
    return _escape(text, quote=False)  # en HTML de Telegram las comillas van tal cual


def _value(number: int | None, suffix: str) -> str:
    return "-" if number is None else f"{number}{suffix}"


def build_live_stats_message(view: LiveStatsView, *, updated_at: datetime) -> str:
    score = (f"{view.home_score}-{view.away_score}"
             if view.home_score is not None and view.away_score is not None else "vs")
    lines = [f"📊 <b>{escape(view.home)} {score} {escape(view.away)}</b>"]
    if view.competition:
        lines.append(f"🏆 {escape(view.competition)}")
    clock = [part for part in (view.period, view.minute) if part]
    if view.ht_score:
        clock.append(f"1T {view.ht_score[0]}-{view.ht_score[1]}")
    if clock:
        lines.append("⏱️ " + " · ".join(escape(part) for part in clock))
    if view.rows:
        table = [f"{_value(row.home, row.suffix):>4}  {row.label:<18}{_value(row.away, row.suffix):>4}"
                 for row in view.rows]
        lines.append("<pre>" + escape("\n".join(table)) + "</pre>")
    else:
        lines.append("Todavía no hay estadísticas de este partido.")
    main, *others = view.sources
    source = _SOURCE_NAMES.get(main, main)
    for other in others:
        extra = [row.label.lower() for row in view.rows if row.source == other]
        detail = ", ".join(extra[:4]) + ("…" if len(extra) > 4 else "")
        source += f" + {_SOURCE_NAMES.get(other, other)}" + (f" ({detail})" if detail else "")
    lines.append(f"<i>Fuente: {escape(source)} · {updated_at:%H:%M:%S}</i>")
    return "\n".join(lines)

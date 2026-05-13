"""Formatting helpers for sportsbook notifications and match messages."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from html import escape
import json
from typing import TYPE_CHECKING

from storage.tracking_repository import (
    ActiveEventRecord,
    SmallChangeRecord,
    TrackedCompetition,
)

if TYPE_CHECKING:
    from monitors.models import MarketChangeDetail, SubscriptionOddsAlert

MAX_GROUPED_ALERT_ITEMS = 10


def build_new_event_alert_message(
    tracked_league: TrackedCompetition,
    match: ActiveEventRecord,
) -> str:
    """Build a compact HTML-formatted Telegram message for a new event."""

    lines = [
        f"🌐 <b>Plataforma:</b> {escape(tracked_league.platform_display_name)}",
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}",
        "",
        "🆕 <b>Nuevo partido</b>",
        "",
    ]
    lines.extend(_build_match_block_lines(match))
    return "\n".join(lines)


def build_grouped_new_event_alert_message(
    tracked_league: TrackedCompetition,
    matches: Sequence[ActiveEventRecord],
    *,
    max_items: int = MAX_GROUPED_ALERT_ITEMS,
) -> str:
    """Build one grouped Telegram message for multiple new events."""

    total_matches = len(matches)
    lines = [
        f"🌐 <b>Plataforma:</b> {escape(tracked_league.platform_display_name)}",
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}",
        "",
        f"📋 <b>Nuevos partidos:</b> {total_matches}",
    ]

    for match in matches[:max_items]:
        lines.append("")
        lines.extend(_build_match_block_lines(match))

    remaining = total_matches - min(total_matches, max_items)
    if remaining > 0:
        lines.append("")
        lines.append(f"... y {remaining} más")

    return "\n".join(lines)


def build_odds_change_alert_message(
    tracked_league: TrackedCompetition,
    alert: SubscriptionOddsAlert,
) -> str:
    """Build a readable HTML-formatted Telegram message for an odds change."""

    current = alert.match
    baseline = alert.baseline
    lines = [
        f"📈 <b>Cambio de odds - {escape(tracked_league.platform_display_name)}</b>",
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}",
        f"⚽ <b>Partido:</b> {escape(current.home)} vs {escape(current.away)}",
        f"🕒 <b>Horario:</b> {escape(format_kickoff_text(current))}",
        "",
    ]

    if "1x2" in alert.changed_market_types:
        lines.extend(
            [
                "<b>1X2 antes</b>",
                f"1: {format_odd_text(baseline.baseline_home)}",
                f"X: {format_odd_text(baseline.baseline_draw)}",
                f"2: {format_odd_text(baseline.baseline_away)}",
                "",
                "<b>1X2 ahora</b>",
                f"1: {format_odd_text(current.odds_home)}",
                f"X: {format_odd_text(current.odds_draw)}",
                f"2: {format_odd_text(current.odds_away)}",
            ]
        )
    else:
        lines.extend(
            [
                "<b>1X2 actual</b>",
                f"1: {format_odd_text(current.odds_home)}",
                f"X: {format_odd_text(current.odds_draw)}",
                f"2: {format_odd_text(current.odds_away)}",
            ]
        )

    if alert.change_details:
        extra_market_details = _details_without_1x2(alert.change_details)
        lines.append("")
        lines.append(
            f"📌 <b>Mercados afectados:</b> {escape(_format_changed_market_types(alert.changed_market_types))}"
        )
        if extra_market_details:
            lines.extend(_build_market_change_detail_lines(extra_market_details, max_items=6))

    lines.append("")
    lines.append(f"📊 <b>Variación máxima:</b> {alert.max_percent_change:.1f}%")
    return "\n".join(lines)


def build_grouped_odds_change_alert_message(
    tracked_league: TrackedCompetition,
    alerts: Sequence[SubscriptionOddsAlert],
    *,
    max_items: int = MAX_GROUPED_ALERT_ITEMS,
) -> str:
    """Build one grouped Telegram message for multiple odds changes."""

    total_changes = len(alerts)
    lines = [
        f"🌐 <b>Plataforma:</b> {escape(tracked_league.platform_display_name)}",
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}",
        "",
        f"📈 <b>Cambios de odds:</b> {total_changes}",
    ]

    for alert in alerts[:max_items]:
        baseline = alert.baseline
        current = alert.match
        lines.append("")
        lines.append(f"🕒 <b>{escape(format_kickoff_text(current))}</b>")
        lines.append(f"⚽ {escape(current.home)} vs {escape(current.away)}")
        lines.append(f"📌 Mercados: {escape(_format_changed_market_types(alert.changed_market_types))}")
        if "1x2" in alert.changed_market_types:
            lines.append(
                "Antes: "
                f"1={format_odd_text(baseline.baseline_home)} | "
                f"X={format_odd_text(baseline.baseline_draw)} | "
                f"2={format_odd_text(baseline.baseline_away)}"
            )
            lines.append(
                "Ahora: "
                f"1={format_odd_text(current.odds_home)} | "
                f"X={format_odd_text(current.odds_draw)} | "
                f"2={format_odd_text(current.odds_away)}"
            )
        else:
            lines.append(
                "1X2 actual: "
                f"1={format_odd_text(current.odds_home)} | "
                f"X={format_odd_text(current.odds_draw)} | "
                f"2={format_odd_text(current.odds_away)}"
            )
        extra_market_details = _details_without_1x2(alert.change_details)
        if extra_market_details:
            lines.extend(_build_market_change_detail_lines(extra_market_details, max_items=3))
        lines.append(f"📊 Variación máxima: {alert.max_percent_change:.1f}%")

    remaining = total_changes - min(total_changes, max_items)
    if remaining > 0:
        lines.append("")
        lines.append(f"... y {remaining} más")

    return "\n".join(lines)


def build_match_reminder_alert_message(
    tracked_league: TrackedCompetition,
    match: ActiveEventRecord,
) -> str:
    """Build an HTML-formatted Telegram reminder sent 5 minutes before kickoff."""
    lines = [
        f"⏰ <b>Recordatorio de partido (5 min) - {escape(tracked_league.platform_display_name)}</b>",
        "",
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}",
        f"⚽ <b>Partido:</b> {escape(match.home)} vs {escape(match.away)}",
        f"🕒 <b>Hora:</b> {escape(format_kickoff_text(match))}",
        "",
        "💰 <b>Odds actuales:</b>",
        (
            f"1={format_odd_text(match.odds_home)} | "
            f"X={format_odd_text(match.odds_draw)} | "
            f"2={format_odd_text(match.odds_away)}"
        ),
    ]
    lines.extend(_build_extra_market_lines(match))
    return "\n".join(lines)


def build_match_card_message(
    tracked_league: TrackedCompetition,
    match: ActiveEventRecord,
) -> str:
    """Build an HTML-formatted Telegram message for one stored match."""

    lines = [
        f"🌐 <b>Plataforma:</b> {escape(tracked_league.platform_display_name)}",
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}",
        "",
    ]
    lines.extend(_build_match_block_lines(match))
    return "\n".join(lines)


def build_competition_unavailable_warning_message(
    tracked_league: TrackedCompetition,
    *,
    track_number: int,
    title: str = "⚠️ <b>No se pudo refrescar la liga</b>",
) -> str:
    """Build a friendly warning for a competition that could not be refreshed."""

    return (
        f"{title}\n\n"
        f"🌐 <b>Plataforma:</b> {escape(tracked_league.platform_display_name)}\n"
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}\n\n"
        "Puede estar temporalmente vacía, la plataforma puede haber removido los eventos "
        "o el link puede haber cambiado.\n\n"
        "🔗 <b>URL actual:</b>\n"
        f"{escape(tracked_league.url)}\n\n"
        "Verificá la liga en el navegador.\n"
        "Si el link cambió, actualizalo con:\n\n"
        f"<code>/update_track_url {track_number} &lt;nuevo_link&gt;</code>\n\n"
        "📌 <b>Ejemplo:</b>\n"
        f"<code>/update_track_url {track_number} https://example.com/...</code>"
    )


def build_competition_url_message(tracked_league: TrackedCompetition, url: str) -> str:
    """Build the Telegram message that exposes one tracked competition URL."""

    return (
        f"🌐 <b>Plataforma:</b> {escape(tracked_league.platform_display_name)}\n"
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}\n\n"
        "🔗 <b>URL:</b>\n"
        f"{escape(url)}"
    )


def build_event_url_message(match: ActiveEventRecord, url: str) -> str:
    """Build the Telegram message that exposes one direct event URL."""

    return (
        f"⚽ <b>{escape(match.home)} vs {escape(match.away)}</b>\n\n"
        f"🔗 {escape(url)}"
    )


def build_event_stats_message(match: ActiveEventRecord, stats_url: str) -> str:
    """Build the Telegram message that exposes one direct stats URL."""

    return (
        f"📊 <b>Stats para {escape(match.home)} vs {escape(match.away)}</b>\n\n"
        f"{escape(stats_url)}"
    )


def build_all_matches_message(
    tracked_league: TrackedCompetition,
    matches: list[ActiveEventRecord],
) -> str:
    """Build an HTML-formatted Telegram message containing all active matches."""

    lines = [
        f"🌐 <b>Plataforma:</b> {escape(tracked_league.platform_display_name)}",
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}",
        "",
        f"📋 <b>Partidos activos:</b> {len(matches)}",
    ]

    for match in matches:
        lines.append("")
        lines.extend(_build_match_block_lines(match))

    return "\n".join(lines)


def build_little_changes_message(changes: list[SmallChangeRecord]) -> str:
    """Build an HTML-formatted list of pending little changes."""

    lines = ["🧩 <b>Little changes pendientes</b>"]

    for index, change in enumerate(changes, start=1):
        lines.append("")
        lines.append(f"<b>{index}.</b> {escape(change.league_name)}")
        lines.append(f"⚽ {escape(change.home)} vs {escape(change.away)}")
        lines.append(f"🕒 {escape(format_kickoff_labels(change.kickoff_label_date, change.kickoff_label_time))}")
        lines.append(
            "Antes: "
            f"1={format_odd_text(change.baseline_home)} | "
            f"X={format_odd_text(change.baseline_draw)} | "
            f"2={format_odd_text(change.baseline_away)}"
        )
        lines.append(
            "Ahora: "
            f"1={format_odd_text(change.current_home)} | "
            f"X={format_odd_text(change.current_draw)} | "
            f"2={format_odd_text(change.current_away)}"
        )
        lines.append(f"📊 Variación máxima: {change.max_percent_change:.1f}%")

    return "\n".join(lines)


def format_kickoff_text(match: ActiveEventRecord) -> str:
    """Format kickoff text for Telegram output."""

    date_label = (match.kickoff_label_date or "").strip()
    time_label = (match.kickoff_label_time or "").strip()

    formatted_labels = format_kickoff_labels(date_label, time_label)
    if formatted_labels != "Horario no disponible":
        return formatted_labels

    if match.kickoff_at is not None:
        return match.kickoff_at

    return "Horario no disponible"


def format_kickoff_labels(date_label: str | None, time_label: str | None) -> str:
    """Format kickoff labels when only raw date/time strings are available."""

    normalized_date = (date_label or "").strip()
    normalized_time = (time_label or "").strip()
    rendered_date = _with_weekday_prefix(normalized_date)

    if rendered_date and normalized_time:
        return f"{rendered_date} {normalized_time}"

    if rendered_date:
        return rendered_date

    if normalized_time:
        return normalized_time

    return "Horario no disponible"


def _with_weekday_prefix(date_label: str) -> str:
    """Prefix plain ISO-style dates with their weekday in Spanish."""

    if not date_label:
        return ""

    prefix = date_label[:10]
    try:
        parsed = datetime.strptime(prefix, "%Y-%m-%d")
    except ValueError:
        return date_label

    weekday_name = (
        "Lunes",
        "Martes",
        "Miércoles",
        "Jueves",
        "Viernes",
        "Sábado",
        "Domingo",
    )[parsed.weekday()]
    suffix = date_label[10:].strip()

    if suffix:
        return f"{weekday_name} {prefix} {suffix}"

    return f"{weekday_name} {prefix}"


def _build_match_block_lines(match: ActiveEventRecord) -> list[str]:
    """Build the standard three-line event block used across Telegram messages."""

    lines = [
        f"🕒 <b>{escape(format_kickoff_text(match))}</b>",
        f"⚽ {escape(match.home)} vs {escape(match.away)}",
        (
            "💰 "
            f"1={format_odd_text(match.odds_home)} | "
            f"X={format_odd_text(match.odds_draw)} | "
            f"2={format_odd_text(match.odds_away)}"
        ),
    ]
    lines.extend(_build_extra_market_lines(match))
    return lines


def format_odd_text(value: float | None) -> str:
    """Format one decimal odd for Telegram output."""

    if value is None:
        return "-"

    return f"{value:.2f}"


def _build_market_change_detail_lines(
    change_details: Sequence[MarketChangeDetail],
    *,
    max_items: int,
) -> list[str]:
    lines: list[str] = []

    for detail in change_details[:max_items]:
        descriptor = _format_market_detail_descriptor(detail)
        lines.append(
            "• "
            f"{escape(descriptor)}: "
            f"{format_odd_text(detail.before)} -> {format_odd_text(detail.after)} "
            f"({detail.percent_change:.1f}%)"
        )

    remaining = len(change_details) - min(len(change_details), max_items)
    if remaining > 0:
        lines.append(f"• ... y {remaining} cambios más")

    return lines


def _format_market_detail_descriptor(detail: MarketChangeDetail) -> str:
    market_name = detail.market_name or _market_type_display_name(detail.market_type)
    selection_bits = [detail.selection]
    if detail.line:
        selection_bits.append(detail.line)

    return f"{market_name} | {' '.join(bit for bit in selection_bits if bit)}"


def _format_changed_market_types(market_types: Sequence[str]) -> str:
    if not market_types:
        return "Sin detalle"
    return ", ".join(_market_type_display_name(market_type) for market_type in market_types)


def _market_type_display_name(market_type: str) -> str:
    return {
        "1x2": "1X2",
        "asian_handicap": "Asian Handicap",
        "goal_line": "Goal Line",
        "alternative_markets": "Mercados alternativos",
    }.get(market_type, market_type.replace("_", " ").title())


def _details_without_1x2(
    change_details: Sequence[MarketChangeDetail],
) -> list[MarketChangeDetail]:
    return [detail for detail in change_details if detail.market_type != "1x2"]


def _build_extra_market_lines(match: ActiveEventRecord) -> list[str]:
    markets_payload = _loads_optional_markets_json(match.markets_json)
    if not markets_payload:
        return []

    lines: list[str] = []
    asian_line = _format_asian_handicap_line(match, markets_payload.get("asian_handicap"))
    goal_line = _format_two_way_market_line("📏 GL", markets_payload.get("goal_line"))

    if asian_line:
        lines.append(asian_line)
    if goal_line:
        lines.append(goal_line)

    return lines


def _format_asian_handicap_line(
    match: ActiveEventRecord,
    market_payload: object,
) -> str:
    if not isinstance(market_payload, dict):
        return "📐 AH Sin línea valor"

    selections = market_payload.get("selections")
    if not isinstance(selections, list) or not selections:
        return "📐 AH Sin línea valor"

    normalized_home = _normalize_name(match.home)
    normalized_away = _normalize_name(match.away)
    home_selection: dict[str, object] | None = None
    away_selection: dict[str, object] | None = None

    for selection_payload in selections:
        if not isinstance(selection_payload, dict):
            continue

        normalized_selection = _normalize_name(selection_payload.get("selection"))
        if normalized_selection == normalized_home and home_selection is None:
            home_selection = selection_payload
        elif normalized_selection == normalized_away and away_selection is None:
            away_selection = selection_payload

    if home_selection is None or away_selection is None:
        return "📐 AH Sin línea valor"

    rendered_home = _format_asian_selection("L", home_selection)
    rendered_away = _format_asian_selection("V", away_selection)

    if rendered_home is None or rendered_away is None:
        return "📐 AH Sin línea valor"

    return f"📐 AH {escape(rendered_home)} | {escape(rendered_away)}"


def _format_two_way_market_line(prefix: str, market_payload: object) -> str | None:
    if not isinstance(market_payload, dict):
        return None

    selections = market_payload.get("selections")
    if not isinstance(selections, list) or not selections:
        return None

    rendered_selections: list[str] = []
    for selection_payload in selections[:4]:
        if not isinstance(selection_payload, dict):
            continue
        selection_name = str(selection_payload.get("selection") or "").strip()
        line = str(selection_payload.get("line") or "").strip()
        odds = _coerce_optional_float(selection_payload.get("odds"))
        if odds is None:
            continue

        label_parts = [selection_name]
        if line:
            label_parts.append(line)
        label = " ".join(part for part in label_parts if part).strip() or "?"
        rendered_selections.append(f"{label}={format_odd_text(odds)}")

    if not rendered_selections:
        return None

    return f"{prefix} {' | '.join(escape(item) for item in rendered_selections)}"


def _format_asian_selection(
    side_label: str,
    selection_payload: dict[str, object],
) -> str | None:
    line = str(selection_payload.get("line") or "").strip()
    odds = _coerce_optional_float(selection_payload.get("odds"))
    if not line or odds is None:
        return None
    return f"{side_label}({line}):{format_odd_text(odds)}"


def _loads_optional_markets_json(raw_value: str | None) -> dict[str, object] | None:
    normalized_value = (raw_value or "").strip()
    if not normalized_value:
        return None

    try:
        payload = json.loads(normalized_value)
    except json.JSONDecodeError:
        return None

    return payload if isinstance(payload, dict) else None


def _coerce_optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized_value = value.strip()
        if not normalized_value:
            return None
        try:
            return float(normalized_value)
        except ValueError:
            return None
    return None


def _normalize_name(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())

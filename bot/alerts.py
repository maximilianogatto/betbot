"""Formatting helpers for sportsbook notifications and match messages."""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from storage.tracking_repository import (
    ActiveEventRecord,
    EventBaseline,
    SmallChangeRecord,
    TrackedCompetition,
)

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
    baseline: EventBaseline,
    current: ActiveEventRecord,
    max_percent_change: float,
) -> str:
    """Build a readable HTML-formatted Telegram message for an odds change."""

    return (
        f"📈 <b>Cambio de odds - {escape(tracked_league.platform_display_name)}</b>\n"
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}\n"
        f"⚽ <b>Partido:</b> {escape(current.home)} vs {escape(current.away)}\n"
        f"🕒 <b>Horario:</b> {escape(format_kickoff_text(current))}\n\n"
        "<b>Antes</b>\n"
        f"1: {format_odd_text(baseline.baseline_home)}\n"
        f"X: {format_odd_text(baseline.baseline_draw)}\n"
        f"2: {format_odd_text(baseline.baseline_away)}\n\n"
        "<b>Ahora</b>\n"
        f"1: {format_odd_text(current.odds_home)}\n"
        f"X: {format_odd_text(current.odds_draw)}\n"
        f"2: {format_odd_text(current.odds_away)}\n\n"
        f"📊 <b>Variación máxima:</b> {max_percent_change:.1f}%"
    )


def build_grouped_odds_change_alert_message(
    tracked_league: TrackedCompetition,
    changes: Sequence[tuple[EventBaseline, ActiveEventRecord, float]],
    *,
    max_items: int = MAX_GROUPED_ALERT_ITEMS,
) -> str:
    """Build one grouped Telegram message for multiple odds changes."""

    total_changes = len(changes)
    lines = [
        f"🌐 <b>Plataforma:</b> {escape(tracked_league.platform_display_name)}",
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}",
        "",
        f"📈 <b>Cambios de odds:</b> {total_changes}",
    ]

    for baseline, current, max_percent_change in changes[:max_items]:
        lines.append("")
        lines.append(f"🕒 <b>{escape(format_kickoff_text(current))}</b>")
        lines.append(f"⚽ {escape(current.home)} vs {escape(current.away)}")
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
        lines.append(f"📊 Variación máxima: {max_percent_change:.1f}%")

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

    return (
        f"⏰ <b>Recordatorio de partido (5 min) - {escape(tracked_league.platform_display_name)}</b>\n\n"
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}\n"
        f"⚽ <b>Partido:</b> {escape(match.home)} vs {escape(match.away)}\n"
        f"🕒 <b>Hora:</b> {escape(format_kickoff_text(match))}\n\n"
        "💰 <b>Odds actuales:</b>\n"
        f"1={format_odd_text(match.odds_home)} | "
        f"X={format_odd_text(match.odds_draw)} | "
        f"2={format_odd_text(match.odds_away)}"
    )


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

    if normalized_date and normalized_time:
        return f"{normalized_date} {normalized_time}"

    if normalized_date:
        return normalized_date

    if normalized_time:
        return normalized_time

    return "Horario no disponible"


def _build_match_block_lines(match: ActiveEventRecord) -> list[str]:
    """Build the standard three-line event block used across Telegram messages."""

    return [
        f"🕒 <b>{escape(format_kickoff_text(match))}</b>",
        f"⚽ {escape(match.home)} vs {escape(match.away)}",
        (
            "💰 "
            f"1={format_odd_text(match.odds_home)} | "
            f"X={format_odd_text(match.odds_draw)} | "
            f"2={format_odd_text(match.odds_away)}"
        ),
    ]


def format_odd_text(value: float | None) -> str:
    """Format one decimal odd for Telegram output."""

    if value is None:
        return "-"

    return f"{value:.2f}"

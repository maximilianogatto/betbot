"""Formatting helpers for Bet365 notifications and match messages."""

from __future__ import annotations

from html import escape

from storage.bet365_tracking import ActiveMatchRecord, TrackedLeague


def build_new_event_alert_message(tracked_league: TrackedLeague, match: ActiveMatchRecord) -> str:
    """Build a compact HTML-formatted Telegram message for a new event."""

    return (
        "🆕 <b>Nuevo evento - Bet365</b>\n"
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}\n"
        f"⚽ <b>Partido:</b> {escape(match.home)} vs {escape(match.away)}\n"
        f"🕒 <b>Horario:</b> {escape(format_kickoff_text(match))}\n"
        f"💰 <b>Odds:</b> 1={format_odd_text(match.odds_home)} | "
        f"X={format_odd_text(match.odds_draw)} | "
        f"2={format_odd_text(match.odds_away)}"
    )


def build_odds_change_alert_message(
    tracked_league: TrackedLeague,
    before: ActiveMatchRecord,
    after: ActiveMatchRecord,
) -> str:
    """Build a readable HTML-formatted Telegram message for an odds change."""

    return (
        "📈 <b>Cambio de odds - Bet365</b>\n"
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}\n"
        f"⚽ <b>Partido:</b> {escape(after.home)} vs {escape(after.away)}\n"
        f"🕒 <b>Horario:</b> {escape(format_kickoff_text(after))}\n\n"
        "<b>Antes</b>\n"
        f"1: {format_odd_text(before.odds_home)}\n"
        f"X: {format_odd_text(before.odds_draw)}\n"
        f"2: {format_odd_text(before.odds_away)}\n\n"
        "<b>Ahora</b>\n"
        f"1: {format_odd_text(after.odds_home)}\n"
        f"X: {format_odd_text(after.odds_draw)}\n"
        f"2: {format_odd_text(after.odds_away)}"
    )


def build_match_card_message(tracked_league: TrackedLeague, match: ActiveMatchRecord) -> str:
    """Build an HTML-formatted Telegram message for one stored match."""

    return (
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}\n\n"
        f"🕒 <b>{escape(format_kickoff_text(match))}</b>\n"
        f"⚽ {escape(match.home)} vs {escape(match.away)}\n"
        f"💰 1={format_odd_text(match.odds_home)} | "
        f"X={format_odd_text(match.odds_draw)} | "
        f"2={format_odd_text(match.odds_away)}"
    )


def build_all_matches_message(
    tracked_league: TrackedLeague,
    matches: list[ActiveMatchRecord],
) -> str:
    """Build an HTML-formatted Telegram message containing all active matches."""

    lines = [
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}",
        "",
        f"📋 <b>Partidos activos:</b> {len(matches)}",
    ]

    for match in matches:
        lines.append("")
        lines.append(f"🕒 <b>{escape(format_kickoff_text(match))}</b>")
        lines.append(f"⚽ {escape(match.home)} vs {escape(match.away)}")
        lines.append(
            "💰 "
            f"1={format_odd_text(match.odds_home)} | "
            f"X={format_odd_text(match.odds_draw)} | "
            f"2={format_odd_text(match.odds_away)}"
        )

    return "\n".join(lines)


def format_kickoff_text(match: ActiveMatchRecord) -> str:
    """Format kickoff text for Telegram output."""

    date_label = (match.kickoff_label_date or "").strip()
    time_label = (match.kickoff_label_time or "").strip()

    if date_label and time_label:
        return f"{date_label} {time_label}"

    if date_label:
        return date_label

    if time_label:
        return time_label

    if match.kickoff_at is not None:
        return match.kickoff_at

    return "Horario no disponible"


def format_odd_text(value: float | None) -> str:
    """Format one decimal odd for Telegram output."""

    if value is None:
        return "-"

    return f"{value:.2f}"

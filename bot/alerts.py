"""Formatting helpers for sportsbook notifications and match messages."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from html import escape
import json
from typing import TYPE_CHECKING

from core.timezones import current_display_timezone
from core.models import (
    ActiveEventRecord,
    SmallChangeRecord,
    TrackedCompetition,
)
from core.match_identity import (  # dominio: identidad/agrupado de partidos
    group_events_by_physical_match,
    physical_match_similarity,
)

if TYPE_CHECKING:
    from monitors.models import MarketChangeDetail, SubscriptionOddsAlert

MAX_GROUPED_ALERT_ITEMS = 10
TELEGRAM_SAFE_MESSAGE_LIMIT = 3900
SPANISH_WEEKDAY_ABBREVIATIONS = (
    "Lun",
    "Mar",
    "Mié",
    "Jue",
    "Vie",
    "Sáb",
    "Dom",
)


def build_new_event_alert_message(
    tracked_league: TrackedCompetition,
    match: ActiveEventRecord,
) -> str:
    """Build a compact HTML-formatted Telegram message for a new event, including cross-platform comparisons."""

    lines = [
        f"🌐 <b>Plataforma:</b> {escape(tracked_league.platform_display_name)}",
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}",
        "",
        "🆕 <b>Nuevo partido</b>",
        "",
    ]
    lines.extend(_build_match_block_lines(match))

    # Cross-platform odds comparison if available
    from adapters.storage import get_storage
    tracking_repository = get_storage()
    other_matches = []
    if tracked_league.unified_competition_id is not None:
        all_active = tracking_repository.get_active_events_for_unified_competition(
            tracked_league.unified_competition_id,
            only_future=True,
        )
        for active in all_active:
            if active.id != match.id and active.platform != match.platform:
                if _physical_match_similarity(match, active) >= 0.80:
                    other_matches.append(active)

    if other_matches:
        lines.append("")
        lines.append("💰 <b>Comparación de Odds (Otras Plataformas):</b>")
        for other in other_matches:
            tracked_other = tracking_repository.get_tracked_competition(other.tracked_competition_id)
            plat_disp = escape(tracked_other.platform_display_name) if tracked_other else escape(other.platform.capitalize())
            lines.append(
                f"• <b>{plat_disp}:</b> "
                f"1={format_odd_text(other.odds_home)} | "
                f"X={format_odd_text(other.odds_draw)} | "
                f"2={format_odd_text(other.odds_away)}"
            )

    return "\n".join(lines)


def build_grouped_new_event_alert_message(
    tracked_league: TrackedCompetition,
    matches: Sequence[ActiveEventRecord],
    *,
    max_items: int | None = None,
) -> str:
    """Build one grouped Telegram message for multiple new events, including cross-platform comparisons."""

    total_matches = len(matches)
    lines = [
        f"🌐 <b>Plataforma:</b> {escape(tracked_league.platform_display_name)}",
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}",
        "",
        f"📋 <b>Nuevos partidos:</b> {total_matches}",
    ]

    from adapters.storage import get_storage
    tracking_repository = get_storage()

    visible_matches = matches if max_items is None else matches[:max_items]
    for match in visible_matches:
        lines.append("")
        lines.extend(_build_match_block_lines(match))

        # Check if it exists on other platforms
        other_matches = []
        if tracked_league.unified_competition_id is not None:
            all_active = tracking_repository.get_active_events_for_unified_competition(
                tracked_league.unified_competition_id,
                only_future=True,
            )
            for active in all_active:
                if active.id != match.id and active.platform != match.platform:
                    if _physical_match_similarity(match, active) >= 0.80:
                        other_matches.append(active)

        if other_matches:
            lines.append("💰 <b>Comparación (Otras Plats):</b>")
            for other in other_matches:
                tracked_other = tracking_repository.get_tracked_competition(other.tracked_competition_id)
                plat_disp = escape(tracked_other.platform_display_name) if tracked_other else escape(other.platform.capitalize())
                lines.append(
                    f"  • {plat_disp}: 1={format_odd_text(other.odds_home)} | X={format_odd_text(other.odds_draw)} | 2={format_odd_text(other.odds_away)}"
                )

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
    max_items: int | None = None,
) -> str:
    """Build one grouped Telegram message for multiple odds changes."""

    total_changes = len(alerts)
    lines = [
        f"🌐 <b>Plataforma:</b> {escape(tracked_league.platform_display_name)}",
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}",
        "",
        f"📈 <b>Cambios de odds:</b> {total_changes}",
    ]

    visible_alerts = alerts if max_items is None else alerts[:max_items]
    for alert in visible_alerts:
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

    return "\n".join(lines)


def build_match_reminder_alert_message(
    tracked_league: TrackedCompetition,
    match: ActiveEventRecord,
) -> str:
    """Build an HTML-formatted Telegram reminder sent 5 minutes before kickoff, comparing other bookmakers."""
    from adapters.storage import get_storage
    tracking_repository = get_storage()
    other_matches = []
    if tracked_league.unified_competition_id is not None:
        all_active = tracking_repository.get_active_events_for_unified_competition(
            tracked_league.unified_competition_id,
            only_future=False,
        )
        for active in all_active:
            if active.id != match.id and active.platform != match.platform:
                if _physical_match_similarity(match, active) >= 0.80:
                    other_matches.append(active)

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

    if other_matches:
        lines.append("")
        lines.append("💰 <b>Odds en otras plataformas:</b>")
        for other in other_matches:
            tracked_other = tracking_repository.get_tracked_competition(other.tracked_competition_id)
            plat_disp = escape(tracked_other.platform_display_name) if tracked_other else escape(other.platform.capitalize())
            lines.append(
                f"• <b>{plat_disp}:</b> "
                f"1={format_odd_text(other.odds_home)} | "
                f"X={format_odd_text(other.odds_draw)} | "
                f"2={format_odd_text(other.odds_away)}"
            )

    lines.extend(_build_extra_market_lines(match))
    return "\n".join(lines)


def build_match_card_message(
    tracked_league: TrackedCompetition,
    match: ActiveEventRecord,
    *,
    full_odds: bool = False,
) -> str:
    """Build an HTML-formatted Telegram message for one stored match."""

    lines = [
        f"🌐 <b>Plataforma:</b> {escape(tracked_league.platform_display_name)}",
        f"🏷️ <b>Liga:</b> {escape(tracked_league.league_name)}",
        "",
        f"🕒 <b>{escape(format_kickoff_text(match))}</b>",
        f"⚽ <b>{escape(match.home)} vs {escape(match.away)}</b>",
        "",
        (
            "💰 <b>1X2:</b>\n"
            f"1: {format_odd_text(match.odds_home)} | "
            f"X: {format_odd_text(match.odds_draw)} | "
            f"2: {format_odd_text(match.odds_away)}"
        ),
    ]

    if full_odds:
        markets_payload = _loads_optional_markets_json(match.markets_json)
        if markets_payload:
            btts_selections = _find_btts_selections(markets_payload)
            btts_formatted = _format_btts(btts_selections)
            if btts_formatted:
                lines.append("")
                lines.append(btts_formatted)

            ah_selections = _collect_all_handicap_selections(markets_payload)
            ah_lines = _format_all_handicap_lines(ah_selections, match)
            if ah_lines:
                lines.append("")
                lines.append("📐 <b>Handicap Asiático:</b>")
                lines.extend(ah_lines)

            gl_selections = _collect_all_goal_line_selections(markets_payload)
            gl_lines = _format_all_goal_lines(gl_selections)
            if gl_lines:
                lines.append("")
                lines.append("📏 <b>Línea de Goles:</b>")
                lines.extend(gl_lines)
    else:
        lines.append("")
        lines.extend(_build_extra_market_lines(match))

    return "\n".join(lines)


# La identidad física de partidos es DOMINIO, no presentación: vive en
# `core/match_identity.py` (PR2-E3). Se re-exporta acá por compatibilidad con los
# handlers que ya la importaban desde este módulo.
_physical_match_similarity = physical_match_similarity


def build_comparison_match_card_message(
    matches: list[ActiveEventRecord],
    *,
    full_odds: bool = False,
) -> str:
    """Build a comparison card showing odds from all platforms/bookmakers for the same physical match."""
    if not matches:
        return ""
        
    from adapters.storage import get_storage
    tracking_repository = get_storage()

    representative = matches[0]
    lines = [
        f"⚽ <b>{escape(representative.home)} vs {escape(representative.away)}</b>",
        f"🕒 {escape(format_kickoff_text(representative))}",
    ]

    for match in matches:
        tracked = tracking_repository.get_tracked_competition(match.tracked_competition_id)
        plat_disp = escape(tracked.platform_display_name) if tracked else escape(match.platform.capitalize())
        lines.append("")
        lines.append(f"🏦 <b>{plat_disp}</b>")
        lines.append(
            f"   <b>1X2</b>  1={format_odd_text(match.odds_home)}  "
            f"X={format_odd_text(match.odds_draw)}  2={format_odd_text(match.odds_away)}"
        )

        markets_payload = _loads_optional_markets_json(match.markets_json)
        if markets_payload:
            if full_odds:
                ah_lines = _format_all_handicap_lines(_collect_all_handicap_selections(markets_payload), match)
                if ah_lines:
                    lines.append("   📐 <b>Hándicap Asiático</b>")
                    lines.extend(f"   {line}" for line in ah_lines)
                gl_lines = _format_all_goal_lines(_collect_all_goal_line_selections(markets_payload))
                if gl_lines:
                    lines.append("   📏 <b>Línea de Goles</b>")
                    lines.extend(f"   {line}" for line in gl_lines)
            else:
                for line in _build_extra_market_lines(match):
                    lines.append(f"   {line}")

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


def build_grouped_event_url_message(matches: Sequence[ActiveEventRecord]) -> str:
    """Build a Telegram message exposing one direct event URL per bookmaker.

    `matches` is the cross-book group for a single physical match (as produced by
    `group_events_by_physical_match`). Each record carries its own `event_url` and
    `platform`, so we list one entry per house.
    """

    if not matches:
        return ""

    from adapters.storage import get_storage
    tracking_repository = get_storage()

    representative = matches[0]
    lines = [f"⚽ <b>{escape(representative.home)} vs {escape(representative.away)}</b>"]

    for match in matches:
        tracked = tracking_repository.get_tracked_competition(match.tracked_competition_id)
        plat_disp = escape(tracked.platform_display_name) if tracked else escape(match.platform.capitalize())
        lines.append("")
        lines.append(f"🏦 <b>{plat_disp}</b>")
        if match.event_url:
            lines.append(f"🔗 {escape(match.event_url)}")
        else:
            lines.append("⚠️ Sin link directo disponible.")

    return "\n".join(lines)


def build_event_stats_message(match: ActiveEventRecord, stats_url: str) -> str:
    """Build the Telegram message that exposes one direct stats URL."""

    return (
        f"📊 <b>Stats para {escape(match.home)} vs {escape(match.away)}</b>\n\n"
        f"{escape(stats_url)}"
    )


def split_telegram_message(text: str, max_len: int = TELEGRAM_SAFE_MESSAGE_LIMIT) -> list[str]:
    """Split a long Telegram message on line boundaries when possible."""

    if max_len <= 0:
        raise ValueError("max_len debe ser mayor que cero.")

    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_length = 0

    for line in text.split("\n"):
        line_length = len(line)
        separator_length = 1 if current_lines else 0

        if line_length > max_len:
            if current_lines:
                chunks.append("\n".join(current_lines))
                current_lines = []
                current_length = 0

            chunks.extend(_split_long_line(line, max_len))
            continue

        if current_length + separator_length + line_length > max_len and current_lines:
            chunks.append("\n".join(current_lines))
            current_lines = [line]
            current_length = line_length
            continue

        current_lines.append(line)
        current_length += separator_length + line_length

    if current_lines:
        chunks.append("\n".join(current_lines))

    return chunks or [text]


def _split_long_line(line: str, max_len: int) -> list[str]:
    return [
        line[index:index + max_len]
        for index in range(0, len(line), max_len)
    ]


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
    """Format kickoff text for Telegram output, in the local display timezone.

    Prefer the offset-aware `kickoff_at` (true UTC) so it converts correctly to
    the chat's display timezone. The raw date/time labels are naive UTC wall-clock
    strings; rendering them directly showed the UTC hour (e.g. 23:15) instead of
    the local hour. Labels are only a fallback when no timestamp exists.
    """

    if match.kickoff_at:
        formatted_kickoff = format_display_datetime(match.kickoff_at)
        if formatted_kickoff is not None:
            return formatted_kickoff

    date_label = (match.kickoff_label_date or "").strip()
    time_label = (match.kickoff_label_time or "").strip()
    formatted_labels = format_kickoff_labels(date_label, time_label)
    if formatted_labels != "Horario no disponible":
        return formatted_labels

    return "Horario no disponible"


def format_kickoff_labels(
    date_label: str | None,
    time_label: str | None,
    *,
    with_year: bool = False,
) -> str:
    """Format kickoff labels when only raw date/time strings are available."""

    normalized_date = (date_label or "").strip()
    normalized_time = (time_label or "").strip()

    if normalized_date and normalized_time:
        combined = format_display_datetime(f"{normalized_date}T{normalized_time}", with_year=with_year)
        if combined is not None:
            return combined

    if normalized_date:
        rendered_date = _format_display_date_label(normalized_date, with_year=with_year)
        if rendered_date is not None:
            return rendered_date

    if normalized_time:
        return normalized_time

    return "Horario no disponible"


def format_display_datetime(value: datetime | str | None, *, with_year: bool = False) -> str | None:
    """Format one date/time value for Telegram as `Mié 13/05 23:00` (or with year)."""

    if value is None:
        return None

    parsed = _parse_display_datetime(value)
    if parsed is None:
        return None

    localized = parsed.astimezone(current_display_timezone())
    weekday = SPANISH_WEEKDAY_ABBREVIATIONS[localized.weekday()]
    pattern = "%d/%m/%Y %H:%M" if with_year else "%d/%m %H:%M"
    return f"{weekday} {localized.strftime(pattern)}"


def _format_display_date_label(date_label: str, *, with_year: bool = False) -> str | None:
    """Format one plain ISO-style date label, optionally including the year."""

    if not date_label:
        return None

    prefix = date_label[:10]
    try:
        parsed = datetime.strptime(prefix, "%Y-%m-%d")
    except ValueError:
        return None

    weekday = SPANISH_WEEKDAY_ABBREVIATIONS[parsed.weekday()]
    pattern = "%d/%m/%Y" if with_year else "%d/%m"
    return f"{weekday} {parsed.strftime(pattern)}"


def _parse_display_datetime(value: datetime | str) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None

        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            try:
                parsed = datetime.strptime(normalized, "%Y-%m-%dT%H:%M")
            except ValueError:
                return None
    else:
        return None

    if parsed.tzinfo is None:
        # Naive labels are the source's wall-clock (unknown zone): render them as
        # given by anchoring to the active display tz (no shift).
        parsed = parsed.replace(tzinfo=current_display_timezone())

    return parsed


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
) -> str | None:
    if not isinstance(market_payload, dict):
        return None

    selections = market_payload.get("selections")
    if not isinstance(selections, list) or not selections:
        return None

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
        return None

    rendered_home = _format_asian_selection("L", home_selection)
    rendered_away = _format_asian_selection("V", away_selection)

    if rendered_home is None or rendered_away is None:
        return None

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


def _parse_line_float(line_str: str | None) -> float | None:
    if line_str is None:
        return None
    try:
        cleaned = str(line_str).replace("+", "").replace(",", ".").strip()
        for sep in (",", "/", "-"):
            if sep in cleaned:
                parts = [float(p.strip()) for p in cleaned.split(sep) if p.strip()]
                if parts:
                    return abs(sum(parts) / len(parts))
        return abs(float(cleaned))
    except ValueError:
        return None


def _find_btts_selections(markets_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if "both_teams_to_score" in markets_payload:
        market = markets_payload["both_teams_to_score"]
        if isinstance(market, dict):
            return market.get("selections") or []

    alt_markets = markets_payload.get("alternative_markets") or []
    for market in alt_markets:
        if not isinstance(market, dict):
            continue
        name = str(market.get("market_name") or "").lower()
        if "ambos" in name or "both teams to score" in name or "btts" in name:
            return market.get("selections") or []

    return []


def _collect_all_handicap_selections(markets_payload: dict[str, Any]) -> list[dict[str, Any]]:
    selections = []
    ah = markets_payload.get("asian_handicap")
    if isinstance(ah, dict):
        selections.extend(ah.get("selections") or [])

    alt_markets = markets_payload.get("alternative_markets") or []
    for market in alt_markets:
        if not isinstance(market, dict):
            continue
        name = str(market.get("market_name") or "").lower()
        m_id = str(market.get("market_id") or "")
        if "handicap" in name or "hándicap" in name or m_id in ("938", "50138", "50137", "50265"):
            selections.extend(market.get("selections") or [])

    return selections


def _collect_all_goal_line_selections(markets_payload: dict[str, Any]) -> list[dict[str, Any]]:
    selections = []
    gl = markets_payload.get("goal_line")
    if isinstance(gl, dict):
        selections.extend(gl.get("selections") or [])

    alt_markets = markets_payload.get("alternative_markets") or []
    for market in alt_markets:
        if not isinstance(market, dict):
            continue
        name = str(market.get("market_name") or "").lower()
        m_id = str(market.get("market_id") or "")
        if "goal line" in name or "total de goles" in name or "línea de gol" in name or m_id in ("10143", "50139", "50136", "50266", "10164", "10165", "10166", "10233", "10239"):
            selections.extend(market.get("selections") or [])

    return selections


def _format_btts(selections: list[dict[str, Any]]) -> str | None:
    if not selections:
        return None

    yes_sel = None
    no_sel = None
    for sel in selections:
        sel_name = str(sel.get("selection") or "").lower()
        if "yes" in sel_name or "sí" in sel_name or "si" in sel_name:
            yes_sel = sel
        elif "no" in sel_name:
            no_sel = sel

    if yes_sel and no_sel:
        y_odds = format_odd_text(yes_sel.get("odds"))
        n_odds = format_odd_text(no_sel.get("odds"))
        return f"⚽ <b>Ambos anotan:</b> Sí={y_odds} | No={n_odds}"
    else:
        parts = []
        for sel in selections:
            sel_name = sel.get("selection") or ""
            odds = format_odd_text(sel.get("odds"))
            parts.append(f"{sel_name}={odds}")
        return f"⚽ <b>Ambos anotan:</b> {', '.join(parts)}"


def _format_all_handicap_lines(selections: list[dict[str, Any]], match: ActiveEventRecord) -> list[str]:
    if not selections:
        return []

    groups = {}
    for sel in selections:
        line_str = sel.get("line")
        if line_str is None:
            continue
        val = _parse_line_float(line_str)
        if val is None:
            continue
        groups.setdefault(val, []).append(sel)

    lines_output = []
    for val in sorted(groups.keys()):
        group_sels = groups[val]
        normalized_home = _normalize_name(match.home)
        normalized_away = _normalize_name(match.away)

        home_sel = None
        away_sel = None
        for sel in group_sels:
            sel_name = _normalize_name(sel.get("selection"))
            if sel_name == normalized_home:
                home_sel = sel
            elif sel_name == normalized_away:
                away_sel = sel

        if home_sel and away_sel:
            h_line = home_sel.get("line") or ""
            a_line = away_sel.get("line") or ""
            h_odds = format_odd_text(home_sel.get("odds"))
            a_odds = format_odd_text(away_sel.get("odds"))
            lines_output.append(f"• AH {h_line}: {h_odds} | AH {a_line}: {a_odds}")
        else:
            parts = []
            for sel in group_sels:
                sel_name = sel.get("selection") or ""
                line = sel.get("line") or ""
                odds = format_odd_text(sel.get("odds"))
                parts.append(f"{sel_name} {line}: {odds}")
            lines_output.append(f"• {', '.join(parts)}")

    return lines_output


def _format_all_goal_lines(selections: list[dict[str, Any]]) -> list[str]:
    if not selections:
        return []

    groups = {}
    for sel in selections:
        line_str = sel.get("line")
        if line_str is None:
            continue
        val = _parse_line_float(line_str)
        if val is None:
            continue
        groups.setdefault(val, []).append(sel)

    lines_output = []
    for val in sorted(groups.keys()):
        group_sels = groups[val]
        over_sel = None
        under_sel = None
        for sel in group_sels:
            sel_name = str(sel.get("selection") or "").lower()
            if "over" in sel_name or "más" in sel_name or "mas" in sel_name:
                over_sel = sel
            elif "under" in sel_name or "menos" in sel_name:
                under_sel = sel

        if over_sel and under_sel:
            line_val = over_sel.get("line") or ""
            o_odds = format_odd_text(over_sel.get("odds"))
            u_odds = format_odd_text(under_sel.get("odds"))
            lines_output.append(f"• GL Over {line_val}: {o_odds} | Under {line_val}: {u_odds}")
        else:
            parts = []
            for sel in group_sels:
                sel_name = sel.get("selection") or ""
                line = sel.get("line") or ""
                odds = format_odd_text(sel.get("odds"))
                parts.append(f"{sel_name} {line}: {odds}")
            lines_output.append(f"• {', '.join(parts)}")

    return lines_output

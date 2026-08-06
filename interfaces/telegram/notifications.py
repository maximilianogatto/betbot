"""Telegram-specific notification orchestrator.

Handles sending new-event and odds-change alerts, merge notifications,
and warning messages to Telegram chats, isolating presentation and telegram
types from the core services.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from core.timezones import set_display_timezone
from services.timezones import resolve_chat_timezone
from services.models import (
    RefreshSummary,
    CompetitionRefreshResult,
    UnavailableCompetitionRefresh,
    SubscriptionOddsAlert,
)
from services.change_detection import evaluate_subscription_odds_change
from interfaces.telegram.renderers import (
    build_new_event_alert_message,
    build_grouped_new_event_alert_message,
    build_odds_change_alert_message,
    build_grouped_odds_change_alert_message,
    build_match_reminder_alert_message,
    build_competition_unavailable_warning_message,
    split_telegram_message,
)

logger = logging.getLogger(__name__)

# Constants ported from tracking service configurations
UNAVAILABLE_WARNING_FAILURE_THRESHOLD = 5
UNAVAILABLE_WARNING_COOLDOWN_SECONDS = 3600 * 24  # 24 hours


async def notify_unavailable_competitions(
    bot: Bot,
    summary: RefreshSummary,
    repository: Any,
    *,
    force_unavailable_warnings: bool = False,
    unavailable_warning_chat_id: int | None = None,
) -> None:
    """Avisa por las competencias que vienen fallando al refrescarse.

    Los avisos de partidos (nuevos, cambios de cuota, recordatorios) ya NO pasan
    por acá: los resuelve `services.notifications` y los publica al EventBus.
    Esto se queda porque es una advertencia operativa sobre una liga rota, no un
    aviso por chat sobre un partido.
    """

    for unavailable in summary.unavailable_competitions:
        await notify_for_unavailable_competition(
            bot,
            unavailable,
            repository,
            force_notify=force_unavailable_warnings,
            target_chat_id=unavailable_warning_chat_id,
        )


async def notify_for_unavailable_competition(
    bot: Bot,
    unavailable: UnavailableCompetitionRefresh,
    repository: Any,
    *,
    force_notify: bool = False,
    target_chat_id: int | None = None,
) -> None:
    """Send a warning for a competition that keeps failing to refresh."""

    should_send = await asyncio.to_thread(
        repository.should_send_unavailable_refresh_warning,
        unavailable.tracked_league.id,
        minimum_failures=UNAVAILABLE_WARNING_FAILURE_THRESHOLD,
        cooldown_seconds=UNAVAILABLE_WARNING_COOLDOWN_SECONDS,
    )
    if not force_notify and not should_send:
        return

    subscriptions = await asyncio.to_thread(
        repository.get_subscriptions_for_competition,
        unavailable.tracked_league.id,
        only_enabled=True,
    )
    if not subscriptions:
        return

    sent_any_warning = False
    for subscription in subscriptions:
        if target_chat_id is not None and subscription.telegram_chat_id != target_chat_id:
            continue

        track_number = _get_track_number(
            repository,
            subscription.telegram_chat_id,
            unavailable.tracked_league.id,
        )
        if track_number is None:
            continue

        await _send_split_message(
            bot,
            subscription.telegram_chat_id,
            build_competition_unavailable_warning_message(
                unavailable.tracked_league,
                track_number=track_number,
            ),
            parse_mode=ParseMode.HTML,
        )
        sent_any_warning = True

    if sent_any_warning and not force_notify:
        await asyncio.to_thread(repository.mark_unavailable_refresh_warning_sent, unavailable.tracked_league.id)


async def notify_league_merges(bot: Bot, merges: list[dict], repository: Any) -> None:
    """Notify users about automatic league merges."""
    for merge in merges:
        def _get_chats_to_notify(into_id):
            chats: set[int] = set()
            for comp in repository.list_tracked_competitions_for_unified(into_id):
                for sub in repository.get_subscriptions_for_competition(comp.id, only_enabled=True):
                    chats.add(sub.telegram_chat_id)
            return chats

        chats = await asyncio.to_thread(_get_chats_to_notify, merge["into_id"])
        text = (
            f"🧠 Aprendí: «{merge['from_name']}» es la misma liga que «{merge['into_name']}» "
            f"({merge['matches']} partidos coincidentes en otra plataforma) — las unifiqué.\n"
            "Heredás sus links de odds y stats."
        )

        reply_markup = None
        moved_ids = merge.get("moved_competition_ids") or []
        if moved_ids:
            payload = f"undomrg:{merge['into_id']}:{','.join(str(i) for i in moved_ids)}"
            if len(payload.encode()) <= 60:
                reply_markup = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("↩️ Estuvo mal, separalas", callback_data=payload)]]
                )
        if reply_markup is None:
            text += "\nSi está mal, separala con /unlink_league."

        for chat_id in sorted(chats):
            try:
                await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
            except Exception:
                logger.warning("Could not notify chat %s about a league merge.", chat_id)


async def _send_split_message(
    bot: Bot,
    chat_id: int,
    text: str,
    *,
    parse_mode: str | None = None,
) -> None:
    for chunk in split_telegram_message(text):
        await bot.send_message(
            chat_id=chat_id,
            text=chunk,
            parse_mode=parse_mode,
        )


def _get_track_number(
    repository: Any,
    chat_id: int,
    tracked_competition_id: int,
) -> int | None:
    """Return the visible `/list_tracks` number for one tracked competition."""
    tracked_leagues = repository.list_confirmed_tracks(chat_id)
    for index, tracked_subscription in enumerate(tracked_leagues, start=1):
        if tracked_subscription.tracked_league.id == tracked_competition_id:
            return index
    return None

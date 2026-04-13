"""Bet365 tracking and monitoring service used by Telegram handlers and jobs.

This service coordinates the full Bet365 workflow without duplicating state
between chats:

1. `/track_url` extracts and stores a pending league
2. `/confirm_track` activates a chat subscription to a global tracked league
3. refresh operations scrape leagues once and update global active matches
4. notification dispatch fans out new events and odds changes to subscribers
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import logging

from telegram import Bot
from telegram.constants import ParseMode

from bot.alerts import (
    build_new_event_alert_message,
    build_odds_change_alert_message,
)
from services.bet365_extractor import Bet365LeagueExtraction, Bet365Match, extract_bet365_league
from storage.bet365_tracking import (
    ActiveMatchRecord,
    ActiveMatchUpsert,
    ConfirmedTrackRequest,
    PendingTrackRequest,
    TrackedLeague,
    TrackedLeagueSubscription,
    confirm_pending_track_request,
    create_pending_track_request,
    get_active_matches,
    get_subscriptions_for_league,
    get_tracked_league,
    get_tracked_league_subscription,
    list_globally_active_leagues,
    list_tracked_leagues,
    remove_missing_matches,
    remove_past_matches,
    remove_tracked_league_subscription,
    sanitize_tracking_state,
    set_odds_notifications,
    update_tracked_league,
    upsert_active_matches,
)

logger = logging.getLogger(__name__)

Bet365Extractor = Callable[[str], Awaitable[Bet365LeagueExtraction]]


@dataclass(frozen=True)
class CommandResult:
    """Represent a simple bot-facing command response."""

    ok: bool
    message: str


@dataclass(frozen=True)
class OddsChange:
    """Represent one odds change detected for a fixture."""

    before: ActiveMatchRecord
    after: ActiveMatchRecord


@dataclass(frozen=True)
class LeagueRefreshResult:
    """Summarize the result of refreshing one tracked Bet365 league."""

    tracked_league: TrackedLeague
    active_matches: list[ActiveMatchRecord]
    new_matches: list[ActiveMatchRecord]
    odds_changes: list[OddsChange]
    removed_missing_count: int
    removed_past_count: int


@dataclass(frozen=True)
class RefreshSummary:
    """Summarize a refresh pass over one or more tracked Bet365 leagues."""

    tracks_refreshed: int
    active_matches: int
    new_events: int
    odds_changes: int
    failed_leagues: list[str]
    league_results: list[LeagueRefreshResult]


class Bet365TrackingService:
    """Coordinate the Bet365 tracking, refresh, and notification workflow."""

    def __init__(
        self,
        extractor: Bet365Extractor | None = None,
        max_parallel_refreshes: int = 3,
    ) -> None:
        self.extractor = extractor or extract_bet365_league
        self.max_parallel_refreshes = max(1, max_parallel_refreshes)
        self._refresh_lock = asyncio.Lock()

    async def create_pending_track_from_url(self, chat_id: int, url: str) -> CommandResult:
        """Validate a Bet365 URL, extract metadata, and store a pending request."""

        try:
            extraction = await self.extractor(url)
            pending_request = create_pending_track_request(
                chat_id=chat_id,
                platform=extraction.platform,
                url=extraction.url,
                extracted_metadata={
                    "topic": extraction.topic,
                    "league_name": extraction.league_name,
                    "url": extraction.url,
                    "platform": extraction.platform,
                    "payload": extraction.payload,
                },
            )
        except ValueError as error:
            return CommandResult(ok=False, message=f"URL inválida: {error}")
        except RuntimeError as error:
            logger.exception("Bet365 extraction failed for chat_id=%s.", chat_id)
            return CommandResult(
                ok=False,
                message=(
                    "No pude extraer la liga desde Bet365.\n"
                    f"Detalle: {error}"
                ),
            )

        return CommandResult(
            ok=True,
            message=self._build_pending_confirmation_message(pending_request),
        )

    async def confirm_pending_track(self, chat_id: int) -> CommandResult:
        """Confirm the latest pending Bet365 request for one Telegram chat."""

        bootstrap_count: int | None = None
        bootstrap_error: str | None = None

        async with self._refresh_lock:
            sanitize_tracking_state()

            try:
                confirmed_request = confirm_pending_track_request(chat_id)
            except ValueError as error:
                return CommandResult(ok=False, message=str(error))

            if confirmed_request is None:
                return CommandResult(
                    ok=False,
                    message=(
                        "No hay ninguna liga pendiente para confirmar.\n"
                        "Primero usá /track_url <url_de_bet365>."
                    ),
                )

            if self._needs_baseline_seed(confirmed_request.tracked_league.id):
                try:
                    extraction = await self.extractor(confirmed_request.tracked_league.url)
                    bootstrap_count = self._seed_initial_snapshot(
                        confirmed_request.tracked_league.id,
                        extraction,
                    )
                except Exception as error:
                    logger.exception(
                        "Initial Bet365 bootstrap failed for tracked_league_id=%s.",
                        confirmed_request.tracked_league.id,
                    )
                    bootstrap_error = str(error)

        return CommandResult(
            ok=True,
            message=self._build_confirmation_message(
                confirmed_request,
                bootstrap_count=bootstrap_count,
                bootstrap_error=bootstrap_error,
            ),
        )

    def list_confirmed_tracks(self, chat_id: int) -> list[TrackedLeagueSubscription]:
        """List confirmed Bet365 tracks for one Telegram chat."""

        sanitize_tracking_state()
        return list_tracked_leagues(chat_id)

    def build_tracks_list_message(self, chat_id: int) -> CommandResult:
        """Build the `/list_tracks` response using Bet365 subscriptions."""

        tracked_leagues = self.list_confirmed_tracks(chat_id)

        if not tracked_leagues:
            return CommandResult(
                ok=True,
                message=(
                    "No tenés ligas trackeadas todavía.\n"
                    "Usá /track_url <url_de_bet365> y después /confirm_track."
                ),
            )

        lines = ["Ligas trackeadas:"]

        for index, item in enumerate(tracked_leagues, start=1):
            lines.append(
                f"{index}. {item.tracked_league.league_name} | "
                f"{item.tracked_league.platform} | "
                f"enabled={'on' if item.subscription.enabled else 'off'} | "
                f"odds={'on' if item.subscription.notify_odds_changes else 'off'}"
            )

        return CommandResult(ok=True, message="\n".join(lines))

    def set_odds_change_notifications(
        self,
        chat_id: int,
        tracked_league_id: int,
        enabled: bool,
    ) -> CommandResult:
        """Enable or disable odds-change notifications for one chat subscription."""

        try:
            subscription = set_odds_notifications(chat_id, tracked_league_id, enabled)
            tracked = get_tracked_league(tracked_league_id)
        except ValueError as error:
            return CommandResult(ok=False, message=str(error))

        if tracked is None:
            return CommandResult(ok=False, message="No encontré esa liga trackeada.")

        return CommandResult(
            ok=True,
            message=(
                f"Notificaciones de cambio de odds para {tracked.league_name}: "
                f"{'on' if subscription.notify_odds_changes else 'off'}"
            ),
        )

    def untrack_chat(self, chat_id: int, tracked_league_id: int) -> CommandResult:
        """Remove one chat subscription from a tracked Bet365 league."""

        try:
            result = remove_tracked_league_subscription(chat_id, tracked_league_id)
        except ValueError as error:
            return CommandResult(ok=False, message=str(error))

        lines = [f"Dejaste de trackear {result.tracked_league.league_name}."]

        if result.league_disabled:
            lines.append(
                "Como no quedaron más chats suscriptos, la liga se desactivó y se limpió su estado scrapeado."
            )
        else:
            lines.append(
                f"Suscripciones activas restantes para esa liga: {result.remaining_enabled_subscriptions}"
            )

        return CommandResult(ok=True, message="\n".join(lines))

    async def refresh_chat_tracks(self, chat_id: int) -> RefreshSummary:
        """Refresh the unique leagues currently subscribed by one chat."""

        tracked_leagues = self.list_confirmed_tracks(chat_id)
        tracked_league_ids = [item.tracked_league.id for item in tracked_leagues]
        return await self._refresh_leagues(tracked_league_ids)

    async def refresh_all_active_leagues(self) -> RefreshSummary:
        """Refresh all globally active Bet365 leagues once."""

        tracked_league_ids = [league.id for league in list_globally_active_leagues()]
        return await self._refresh_leagues(tracked_league_ids)

    async def refresh_tracked_league(self, tracked_league_id: int) -> LeagueRefreshResult:
        """Refresh active match state for one globally tracked Bet365 league."""

        async with self._refresh_lock:
            tracked_league = get_tracked_league(tracked_league_id)

            if tracked_league is None:
                raise ValueError(f"No tracked Bet365 league found with id={tracked_league_id}.")

            extraction = await self.extractor(tracked_league.url)
            return self._apply_extraction_to_tracked_league(tracked_league_id, extraction)

    async def monitor_once(self, bot: Bot) -> RefreshSummary:
        """Run one global monitoring cycle and dispatch notifications."""

        summary = await self.refresh_all_active_leagues()
        await self.dispatch_notifications(bot, summary)
        return summary

    async def dispatch_notifications(self, bot: Bot, summary: RefreshSummary) -> None:
        """Send new-event and odds-change notifications to matching subscribers."""

        for result in summary.league_results:
            await self.notify_for_refresh_result(bot, result)

    async def notify_for_refresh_result(self, bot: Bot, result: LeagueRefreshResult) -> None:
        """Send notifications for one refreshed league to all matching chats."""

        subscriptions = get_subscriptions_for_league(result.tracked_league.id, only_enabled=True)

        if not subscriptions:
            return

        for subscription in subscriptions:
            if subscription.notify_new_matches:
                for match in result.new_matches:
                    await bot.send_message(
                        chat_id=subscription.telegram_chat_id,
                        text=build_new_event_alert_message(result.tracked_league, match),
                        parse_mode=ParseMode.HTML,
                    )

            if subscription.notify_odds_changes:
                for change in result.odds_changes:
                    await bot.send_message(
                        chat_id=subscription.telegram_chat_id,
                        text=build_odds_change_alert_message(
                            result.tracked_league,
                            change.before,
                            change.after,
                        ),
                        parse_mode=ParseMode.HTML,
                    )

    def get_matches_for_track(
        self,
        chat_id: int,
        tracked_league_id: int,
    ) -> tuple[TrackedLeagueSubscription, list[ActiveMatchRecord]]:
        """Load current active matches for one tracked league and chat."""

        tracked_subscription = get_tracked_league_subscription(chat_id, tracked_league_id)

        if tracked_subscription is None:
            raise ValueError(
                f"No tracked Bet365 league found for chat_id={chat_id} and tracked_league_id={tracked_league_id}."
            )

        return tracked_subscription, get_active_matches(tracked_league_id, only_future=True)

    def build_refresh_summary_message(self, summary: RefreshSummary) -> CommandResult:
        """Build the user-facing summary for `/refresh_tracks` or monitor logs."""

        if summary.tracks_refreshed == 0:
            return CommandResult(
                ok=True,
                message=(
                    "No tenés ligas trackeadas todavía.\n"
                    "Usá /track_url <url_de_bet365> y después /confirm_track."
                ),
            )

        lines = [
            "Refresh completado.",
            f"Ligas revisadas: {summary.tracks_refreshed}",
            f"Partidos activos guardados: {summary.active_matches}",
            f"Nuevos eventos detectados: {summary.new_events}",
            f"Cambios de odds detectados: {summary.odds_changes}",
        ]

        if summary.failed_leagues:
            lines.append(f"Ligas con error: {', '.join(summary.failed_leagues)}")

        return CommandResult(ok=True, message="\n".join(lines))

    def _build_pending_confirmation_message(self, pending_request: PendingTrackRequest) -> str:
        """Build the Telegram message shown after `/track_url` succeeds."""

        return (
            f"Encontré la liga {pending_request.league_name}.\n"
            f"Platform: {pending_request.platform}\n"
            f"Topic: {pending_request.topic}\n"
            "Respondé /confirm_track para agregarla al tracking."
        )

    def _build_confirmation_message(
        self,
        confirmed_request: ConfirmedTrackRequest,
        *,
        bootstrap_count: int | None,
        bootstrap_error: str | None,
    ) -> str:
        """Build the Telegram message shown after `/confirm_track`."""

        tracked_league = confirmed_request.tracked_league
        subscription = confirmed_request.subscription

        lines = [
            f"Tracking activado para {tracked_league.league_name}.\n"
            f"Platform: {tracked_league.platform}\n"
            f"Topic: {tracked_league.topic}\n"
            f"Tracked League ID: {tracked_league.id}\n"
            f"notify_new_matches={'on' if subscription.notify_new_matches else 'off'}\n"
            f"notify_odds_changes={'on' if subscription.notify_odds_changes else 'off'}"
        ]

        if bootstrap_count is not None:
            lines.append(f"Estado inicial guardado: {bootstrap_count} partidos activos.")

        if bootstrap_error is not None:
            lines.append(
                "No pude guardar el estado inicial ahora mismo. "
                "El monitor lo volverá a intentar automáticamente."
            )

        return "\n".join(lines)

    async def _refresh_leagues(self, tracked_league_ids: Sequence[int]) -> RefreshSummary:
        """Refresh a deduplicated set of tracked leagues under one shared lock."""

        unique_ids = list(dict.fromkeys(tracked_league_ids))

        if not unique_ids:
            return RefreshSummary(
                tracks_refreshed=0,
                active_matches=0,
                new_events=0,
                odds_changes=0,
                failed_leagues=[],
                league_results=[],
            )

        league_results: list[LeagueRefreshResult] = []
        failed_leagues: list[str] = []

        tracked_leagues = [
            tracked_league
            for tracked_league_id in unique_ids
            for tracked_league in [get_tracked_league(tracked_league_id)]
            if tracked_league is not None
        ]

        async with self._refresh_lock:
            for batch in _batched(tracked_leagues, self.max_parallel_refreshes):
                extracted_batch = await asyncio.gather(
                    *(self.extractor(tracked_league.url) for tracked_league in batch),
                    return_exceptions=True,
                )

                for tracked_league, extraction_or_error in zip(batch, extracted_batch, strict=True):
                    if isinstance(extraction_or_error, Exception):
                        failed_leagues.append(tracked_league.league_name)
                        logger.error(
                            "Failed to refresh tracked Bet365 league id=%s.",
                            tracked_league.id,
                            exc_info=(
                                type(extraction_or_error),
                                extraction_or_error,
                                extraction_or_error.__traceback__,
                            ),
                        )
                        continue

                    result = self._apply_extraction_to_tracked_league(
                        tracked_league.id,
                        extraction_or_error,
                    )
                    logger.info(
                        "Refreshed Bet365 league id=%s name=%s active=%s new=%s odds_changes=%s removed_missing=%s removed_past=%s",
                        result.tracked_league.id,
                        result.tracked_league.league_name,
                        len(result.active_matches),
                        len(result.new_matches),
                        len(result.odds_changes),
                        result.removed_missing_count,
                        result.removed_past_count,
                    )
                    league_results.append(result)

        return RefreshSummary(
            tracks_refreshed=len(league_results),
            active_matches=sum(len(result.active_matches) for result in league_results),
            new_events=sum(len(result.new_matches) for result in league_results),
            odds_changes=sum(len(result.odds_changes) for result in league_results),
            failed_leagues=failed_leagues,
            league_results=league_results,
        )

    def _apply_extraction_to_tracked_league(
        self,
        tracked_league_id: int,
        extraction: Bet365LeagueExtraction,
    ) -> LeagueRefreshResult:
        """Apply one extracted Bet365 league snapshot to global stored state."""

        scraped_at = _utc_now_iso()

        tracked_league = update_tracked_league(
            tracked_league_id,
            url=extraction.url,
            topic=extraction.topic,
            league_name=extraction.league_name,
            last_scraped_at=scraped_at,
        )

        existing_by_fixture = {
            match.fixture_id: match
            for match in get_active_matches(tracked_league_id, only_future=False)
        }

        future_matches = [match for match in extraction.matches if not _is_past_match(match)]
        current_fixture_ids = [match.fixture_id for match in future_matches]
        new_fixture_ids = {
            match.fixture_id
            for match in future_matches
            if match.fixture_id not in existing_by_fixture
        }
        changed_fixture_ids = {
            match.fixture_id
            for match in future_matches
            if match.fixture_id in existing_by_fixture
            and _odds_tuple_from_record(existing_by_fixture[match.fixture_id]) != _odds_tuple_from_match(match)
        }

        upsert_payload = [
            ActiveMatchUpsert(
                fixture_id=match.fixture_id,
                home=match.home,
                away=match.away,
                kickoff_label_date=match.kickoff_label_date,
                kickoff_label_time=match.kickoff_label_time,
                kickoff_at=match.kickoff_at,
                odds_home=match.odds_home,
                odds_draw=match.odds_draw,
                odds_away=match.odds_away,
            )
            for match in future_matches
        ]

        if upsert_payload:
            upsert_active_matches(tracked_league_id, upsert_payload)

        removed_missing_count = remove_missing_matches(tracked_league_id, current_fixture_ids)
        removed_past_count = remove_past_matches(tracked_league_id)
        active_matches = get_active_matches(tracked_league_id, only_future=True)
        active_by_fixture = {match.fixture_id: match for match in active_matches}

        new_matches = [
            active_by_fixture[fixture_id]
            for fixture_id in current_fixture_ids
            if fixture_id in new_fixture_ids and fixture_id in active_by_fixture
        ]
        odds_changes = [
            OddsChange(
                before=existing_by_fixture[fixture_id],
                after=active_by_fixture[fixture_id],
            )
            for fixture_id in current_fixture_ids
            if fixture_id in changed_fixture_ids and fixture_id in active_by_fixture
        ]

        return LeagueRefreshResult(
            tracked_league=tracked_league,
            active_matches=active_matches,
            new_matches=new_matches,
            odds_changes=odds_changes,
            removed_missing_count=removed_missing_count,
            removed_past_count=removed_past_count,
        )

    def _seed_initial_snapshot(
        self,
        tracked_league_id: int,
        extraction: Bet365LeagueExtraction,
    ) -> int:
        """Store a baseline snapshot for a league without generating diff events."""

        scraped_at = _utc_now_iso()

        update_tracked_league(
            tracked_league_id,
            url=extraction.url,
            topic=extraction.topic,
            league_name=extraction.league_name,
            last_scraped_at=scraped_at,
        )

        future_matches = [match for match in extraction.matches if not _is_past_match(match)]
        current_fixture_ids = [match.fixture_id for match in future_matches]
        upsert_payload = [
            ActiveMatchUpsert(
                fixture_id=match.fixture_id,
                home=match.home,
                away=match.away,
                kickoff_label_date=match.kickoff_label_date,
                kickoff_label_time=match.kickoff_label_time,
                kickoff_at=match.kickoff_at,
                odds_home=match.odds_home,
                odds_draw=match.odds_draw,
                odds_away=match.odds_away,
            )
            for match in future_matches
        ]

        if upsert_payload:
            upsert_active_matches(tracked_league_id, upsert_payload)

        remove_missing_matches(tracked_league_id, current_fixture_ids)
        remove_past_matches(tracked_league_id)

        active_count = len(get_active_matches(tracked_league_id, only_future=True))
        logger.info(
            "Seeded initial Bet365 baseline for tracked_league_id=%s league=%s active=%s",
            tracked_league_id,
            extraction.league_name,
            active_count,
        )
        return active_count

    def _needs_baseline_seed(self, tracked_league_id: int) -> bool:
        """Return whether a tracked league still lacks a usable initial snapshot."""

        tracked_league = get_tracked_league(tracked_league_id)

        if tracked_league is None or tracked_league.last_scraped_at is None:
            return True

        active_matches = get_active_matches(tracked_league_id, only_future=False)

        if not active_matches:
            return True

        return any(
            match.odds_home is None and match.odds_draw is None and match.odds_away is None
            for match in active_matches
        )


def _is_past_match(match: Bet365Match) -> bool:
    """Return whether a normalized Bet365 match already kicked off in the past."""

    if match.kickoff_at is None:
        return False

    try:
        kickoff = datetime.fromisoformat(match.kickoff_at)
    except ValueError:
        return False

    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)

    return kickoff < datetime.now(timezone.utc)


def _odds_tuple_from_match(match: Bet365Match) -> tuple[float | None, float | None, float | None]:
    """Extract the comparable 1/X/2 odds tuple from a normalized match."""

    return (match.odds_home, match.odds_draw, match.odds_away)


def _odds_tuple_from_record(
    match: ActiveMatchRecord,
) -> tuple[float | None, float | None, float | None]:
    """Extract the comparable 1/X/2 odds tuple from a stored active match."""

    return (match.odds_home, match.odds_draw, match.odds_away)


def _batched(items: Sequence[TrackedLeague], batch_size: int) -> list[list[TrackedLeague]]:
    """Split a sequence of tracked leagues into small ordered batches."""

    return [list(items[index:index + batch_size]) for index in range(0, len(items), batch_size)]


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""

    return datetime.now(timezone.utc).isoformat()

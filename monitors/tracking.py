"""Generic tracking and monitoring service used by Telegram handlers and jobs.

This service coordinates the full tracking workflow without duplicating state
between chats:

1. `/track_url` extracts and stores a pending competition
2. `/confirm_track` activates a chat subscription to a global tracked competition
3. refresh operations scrape competitions once and update global active events
4. notification dispatch fans out new events and odds changes to subscribers
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging

from telegram import Bot
from telegram.constants import ParseMode

from bot.alerts import (
    build_match_reminder_alert_message,
    build_new_event_alert_message,
    build_odds_change_alert_message,
)
from core.models import CompetitionExtraction, EventSnapshot, PlatformDescriptor
from core.registry import ExtractorRegistry, extractor_registry as global_extractor_registry
from storage.tracking_repository import (
    ActiveEventRecord,
    ActiveEventUpsert,
    CompetitionSubscription,
    ConfirmedCompetitionTrackRequest,
    EventBaseline,
    PendingCompetitionTrackRequest,
    SmallChangeRecord,
    SqliteTrackingRepository,
    TrackedCompetition,
    TrackedCompetitionSubscription,
    tracking_repository as default_tracking_repository,
)

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class CommandResult:
    """Represent a simple bot-facing command response."""

    ok: bool
    message: str


@dataclass(frozen=True)
class OddsChange:
    """Represent one odds change detected for a fixture."""

    before: ActiveEventRecord
    after: ActiveEventRecord


@dataclass(frozen=True)
class SubscriptionOddsAlert:
    """Represent one odds alert decision for a specific chat baseline."""

    match: ActiveEventRecord
    baseline: EventBaseline
    max_percent_change: float


@dataclass(frozen=True)
class CompetitionRefreshResult:
    """Summarize the result of refreshing one tracked competition."""

    tracked_league: TrackedCompetition
    active_matches: list[ActiveEventRecord]
    new_matches: list[ActiveEventRecord]
    odds_changes: list[OddsChange]
    reminder_matches: list[ActiveEventRecord]
    removed_missing_count: int
    removed_past_count: int


@dataclass(frozen=True)
class RefreshSummary:
    """Summarize a refresh pass over one or more tracked competitions."""

    tracks_requested: int
    tracks_refreshed: int
    active_matches: int
    new_events: int
    odds_changes: int
    failed_leagues: list[str]
    league_results: list[CompetitionRefreshResult]


class TrackingService:
    """Coordinate tracking, refresh, and notification workflows across platforms."""

    def __init__(
        self,
        extractor_registry: ExtractorRegistry | None = None,
        repository: SqliteTrackingRepository | None = None,
        max_parallel_refreshes: int = 3,
    ) -> None:
        # This service keeps its legacy name for compatibility with the current
        # bot wiring, but it now consumes generic extractor and repository
        # contracts so future sportsbooks can plug into the same flow.
        self.extractor_registry = extractor_registry or global_extractor_registry
        self.repository = repository or default_tracking_repository
        self.max_parallel_refreshes = max(1, max_parallel_refreshes)
        self._refresh_lock = asyncio.Lock()

    async def _extract_league(self, url: str) -> CompetitionExtraction:
        """Resolve the right extractor for a competition URL and delegate extraction."""

        extractor = self.extractor_registry.get_for_url(url)
        extraction = await extractor.extract_league(url)

        if not isinstance(extraction, CompetitionExtraction):
            raise TypeError(
                "TrackingService received an unexpected competition extraction payload type."
            )

        return extraction

    async def create_pending_track_from_url(self, chat_id: int, url: str) -> CommandResult:
        """Validate a supported URL, extract metadata, and store a pending request."""

        try:
            extraction = await self._extract_league(url)
        except ValueError as error:
            return CommandResult(
                ok=False,
                message=(
                    "No tengo soporte para esa plataforma todavía.\n"
                    "Usá /platforms para ver las disponibles.\n"
                    f"Detalle: {error}"
                ),
            )
        except RuntimeError as error:
            logger.exception("Competition extraction failed for chat_id=%s.", chat_id)
            return CommandResult(
                ok=False,
                message=(
                    "No pude extraer la liga desde la plataforma indicada.\n"
                    f"Detalle: {error}"
                ),
            )

        existing_subscription = self.repository.get_tracked_competition_subscription_by_identity(
            chat_id,
            platform=extraction.platform,
            competition_external_id=extraction.competition_external_id,
        )

        if existing_subscription is not None:
            return CommandResult(
                ok=False,
                message=(
                    "Esa liga ya está trackeada en este chat.\n"
                    f"🌐 Plataforma: {existing_subscription.tracked_league.platform_display_name}\n"
                    f"🏷️ Liga: {existing_subscription.tracked_league.league_name}"
                ),
            )

        try:
            pending_request = self.repository.create_pending_competition_request(
                chat_id=chat_id,
                platform=extraction.platform,
                source_url=extraction.source_url,
                competition_external_id=extraction.competition_external_id,
                competition_name=extraction.competition_name,
                requires_empty_confirmation=extraction.is_empty,
                needs_name_resolution=extraction.is_provisional_name,
                payload=extraction.raw_payload,
            )
        except ValueError as error:
            return CommandResult(ok=False, message=f"No pude guardar el tracking pendiente.\nDetalle: {error}")

        if extraction.is_empty:
            return CommandResult(
                ok=True,
                message=self._build_empty_pending_confirmation_message(pending_request),
            )

        return CommandResult(ok=True, message=self._build_pending_confirmation_message(pending_request))

    async def confirm_pending_track(self, chat_id: int) -> CommandResult:
        """Confirm the latest pending tracking request for one Telegram chat."""

        bootstrap_count: int | None = None
        bootstrap_error: str | None = None

        async with self._refresh_lock:
            self.repository.sanitize_tracking_state()
            pending_request = self.repository.get_latest_pending_competition_request(chat_id)

            if pending_request is not None and pending_request.requires_empty_confirmation:
                return CommandResult(
                    ok=False,
                    message=(
                        "La última liga pendiente está vacía por ahora.\n"
                        "Usá /confirm_empty_track para guardarla igual o /cancel para cancelar."
                    ),
                )

            try:
                confirmed_request = self.repository.confirm_pending_competition_request(chat_id)
            except ValueError as error:
                return CommandResult(ok=False, message=str(error))

            if confirmed_request is None:
                return CommandResult(
                    ok=False,
                    message=(
                        "No hay ninguna liga pendiente para confirmar.\n"
                        "Primero usá /track_url <url_de_plataforma>."
                    ),
                )

            if self._needs_baseline_seed(confirmed_request.tracked_competition.id):
                try:
                    extraction = await self._extract_league(confirmed_request.tracked_competition.source_url)
                    bootstrap_count = self._seed_initial_snapshot(
                        confirmed_request.tracked_competition.id,
                        extraction,
                    )
                except Exception as error:
                    logger.exception(
                        "Initial competition bootstrap failed for tracked_league_id=%s.",
                        confirmed_request.tracked_competition.id,
                    )
                    bootstrap_error = str(error)

            try:
                self.repository.initialize_event_baselines(
                    chat_id,
                    confirmed_request.tracked_competition.id,
                    self.repository.get_active_events(
                        confirmed_request.tracked_competition.id,
                        only_future=True,
                    ),
                )
            except Exception:
                logger.exception(
                    "Failed to initialize per-chat baselines for chat_id=%s tracked_league_id=%s.",
                    chat_id,
                    confirmed_request.tracked_competition.id,
                )

        return CommandResult(
            ok=True,
            message=self._build_confirmation_message(
                confirmed_request,
                bootstrap_count=bootstrap_count,
                bootstrap_error=bootstrap_error,
            ),
        )

    async def confirm_empty_pending_track(self, chat_id: int) -> CommandResult:
        """Confirm the latest empty-league pending request for one Telegram chat."""

        async with self._refresh_lock:
            self.repository.sanitize_tracking_state()
            pending_request = self.repository.get_latest_pending_competition_request(chat_id)

            if pending_request is None:
                return CommandResult(
                ok=False,
                message=(
                    "No hay ninguna liga pendiente para confirmar.\n"
                    "Primero usá /track_url <url_de_plataforma>."
                ),
            )

            if not pending_request.requires_empty_confirmation:
                return CommandResult(
                    ok=False,
                    message=(
                        "La última liga pendiente ya tiene partidos disponibles.\n"
                        "Usá /confirm_track para confirmarla."
                    ),
                )

            try:
                confirmed_request = self.repository.confirm_pending_competition_request(chat_id)
            except ValueError as error:
                return CommandResult(ok=False, message=str(error))

        return CommandResult(
            ok=True,
            message=self._build_empty_confirmation_message(confirmed_request),
        )

    def list_confirmed_tracks(self, chat_id: int) -> list[TrackedCompetitionSubscription]:
        """List confirmed tracked competitions for one Telegram chat."""

        self.repository.sanitize_tracking_state()
        return self.repository.list_tracked_competitions(chat_id)

    def list_supported_platforms(self) -> list[PlatformDescriptor]:
        """Return the currently registered betting platforms."""

        return self.extractor_registry.list_platforms()

    def build_platforms_message(self) -> CommandResult:
        """Build the `/platforms` response from the extractor registry."""

        platforms = self.list_supported_platforms()

        if not platforms:
            return CommandResult(
                ok=True,
                message="No hay plataformas registradas en este momento.",
            )

        lines = ["🌐 Plataformas disponibles"]

        for platform in platforms:
            lines.append("")
            prefix = "✅" if platform.implemented else "⚪️"
            lines.append(f"{prefix} {platform.display_name}")
            lines.append(f"Key: {platform.key}")
            if platform.domains:
                lines.append(f"Dominios: {', '.join(platform.domains)}")
            if platform.supports:
                lines.append(f"Soporta: {', '.join(platform.supports)}")

        return CommandResult(ok=True, message="\n".join(lines))

    def build_tracks_list_message(self, chat_id: int) -> CommandResult:
        """Build the `/list_tracks` response using tracked subscriptions."""

        tracked_leagues = self.list_confirmed_tracks(chat_id)

        if not tracked_leagues:
            return CommandResult(
                ok=True,
                message=(
                    "No tenés ligas trackeadas todavía.\n"
                    "Usá /track_url <url_de_plataforma> y después /confirm_track."
                ),
            )

        lines = ["Ligas trackeadas:"]
        current_platform: str | None = None
        platform_index = 0

        for item in tracked_leagues:
            platform_name = item.tracked_league.platform_display_name

            if platform_name != current_platform:
                if current_platform is not None:
                    lines.append("")
                lines.append(f"🌐 {platform_name}")
                current_platform = platform_name
                platform_index = 0

            platform_index += 1
            lines.append(
                f"{platform_index}. {item.tracked_league.league_name} | "
                f"enabled={'on' if item.subscription.enabled else 'off'} | "
                f"odds={'on' if item.subscription.notify_odds_changes else 'off'} | "
                f"threshold={item.subscription.change_percent_threshold:.1f}%"
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
            subscription = self.repository.set_odds_notifications(chat_id, tracked_league_id, enabled)
            tracked = self.repository.get_tracked_competition(tracked_league_id)
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

    def set_change_percent(
        self,
        chat_id: int,
        tracked_league_id: int,
        percent: float,
    ) -> CommandResult:
        """Update the odds-alert sensitivity for one chat and tracked league."""

        try:
            subscription = self.repository.set_change_percent_threshold(chat_id, tracked_league_id, percent)
            tracked = self.repository.get_tracked_competition(tracked_league_id)
        except ValueError as error:
            return CommandResult(ok=False, message=str(error))

        if tracked is None:
            return CommandResult(ok=False, message="No encontré esa liga trackeada.")

        return CommandResult(
            ok=True,
            message=(
                f"Umbral de cambio para {tracked.league_name}: "
                f"{subscription.change_percent_threshold:.1f}%"
            ),
        )

    def get_pending_little_changes(self, chat_id: int) -> list[SmallChangeRecord]:
        """Load pending little changes for one chat."""

        self.repository.sanitize_tracking_state()
        return self.repository.list_pending_small_changes(chat_id)

    def confirm_little_change_by_index(self, chat_id: int, index: int) -> CommandResult:
        """Confirm one pending little change by its visible list index."""

        pending_changes = self.get_pending_little_changes(chat_id)

        if not pending_changes:
            return CommandResult(ok=False, message="No tenés little changes pendientes.")

        if index < 0 or index >= len(pending_changes):
            return CommandResult(ok=False, message="Elegí un número válido de little change.")

        change = self.repository.confirm_small_change(chat_id, pending_changes[index].id)
        return CommandResult(
            ok=True,
            message=(
                f"Actualicé la baseline para {change.league_name} | "
                f"{change.home} vs {change.away}."
            ),
        )

    def confirm_all_pending_little_changes(self, chat_id: int) -> CommandResult:
        """Confirm every pending little change for one chat."""

        confirmed = self.repository.confirm_all_small_changes(chat_id)

        if not confirmed:
            return CommandResult(ok=False, message="No tenés little changes pendientes.")

        return CommandResult(
            ok=True,
            message=f"Confirmé {len(confirmed)} little changes y actualicé sus baselines.",
        )

    def cancel_pending_empty_track(self, chat_id: int) -> bool:
        """Cancel the latest pending empty-league tracking request for one chat."""

        pending_request = self.repository.get_latest_pending_competition_request(chat_id)
        if pending_request is None or not pending_request.requires_empty_confirmation:
            return False

        return self.repository.delete_pending_competition_request(chat_id)

    def untrack_chat(self, chat_id: int, tracked_league_id: int) -> CommandResult:
        """Remove one chat subscription from a tracked competition."""

        try:
            result = self.repository.remove_tracked_competition_subscription(chat_id, tracked_league_id)
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
        """Refresh all globally active tracked competitions once."""

        tracked_league_ids = [
            competition.id for competition in self.repository.list_globally_active_competitions()
        ]
        return await self._refresh_leagues(tracked_league_ids)

    async def refresh_tracked_league(self, tracked_league_id: int) -> CompetitionRefreshResult:
        """Refresh active event state for one globally tracked competition."""

        async with self._refresh_lock:
            tracked_league = self.repository.get_tracked_competition(tracked_league_id)

            if tracked_league is None:
                raise ValueError(f"No tracked competition found with id={tracked_league_id}.")

            extraction = await self._extract_league(tracked_league.url)
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

    async def notify_for_refresh_result(self, bot: Bot, result: CompetitionRefreshResult) -> None:
        """Send notifications for one refreshed league to all matching chats."""

        subscriptions = self.repository.get_subscriptions_for_competition(
            result.tracked_league.id,
            only_enabled=True,
        )

        if not subscriptions:
            return

        for subscription in subscriptions:
            self.repository.initialize_event_baselines(
                subscription.telegram_chat_id,
                result.tracked_league.id,
                result.active_matches,
            )

            if subscription.notify_new_matches:
                for match in result.new_matches:
                    if self.repository.has_sent_alert(
                        subscription.telegram_chat_id,
                        result.tracked_league.id,
                        match.fixture_id,
                        "new_event",
                    ):
                        continue

                    await bot.send_message(
                        chat_id=subscription.telegram_chat_id,
                        text=build_new_event_alert_message(result.tracked_league, match),
                        parse_mode=ParseMode.HTML,
                    )
                    self.repository.mark_sent_alert(
                        subscription.telegram_chat_id,
                        result.tracked_league.id,
                        match.fixture_id,
                        "new_event",
                    )

            for change in result.odds_changes:
                alert = _evaluate_subscription_odds_change(
                    self.repository,
                    subscription,
                    result.tracked_league,
                    change.after,
                )

                if alert is not None and subscription.notify_odds_changes:
                    await bot.send_message(
                        chat_id=subscription.telegram_chat_id,
                        text=build_odds_change_alert_message(
                            result.tracked_league,
                            alert.baseline,
                            alert.match,
                            alert.max_percent_change,
                        ),
                        parse_mode=ParseMode.HTML,
                    )
                    self.repository.upsert_event_baseline(
                        subscription.telegram_chat_id,
                        result.tracked_league.id,
                        alert.match.fixture_id,
                        baseline_home=alert.match.odds_home,
                        baseline_draw=alert.match.odds_draw,
                        baseline_away=alert.match.odds_away,
                    )
                    self.repository.resolve_small_change_with_current_baseline(
                        subscription.telegram_chat_id,
                        result.tracked_league.id,
                        alert.match.fixture_id,
                    )

            for match in result.reminder_matches:
                await bot.send_message(
                    chat_id=subscription.telegram_chat_id,
                    text=build_match_reminder_alert_message(result.tracked_league, match),
                    parse_mode=ParseMode.HTML,
                )

        if result.reminder_matches:
            self.repository.mark_events_alerted(
                result.tracked_league.id,
                [match.fixture_id for match in result.reminder_matches],
            )

    def get_matches_for_track(
        self,
        chat_id: int,
        tracked_league_id: int,
    ) -> tuple[TrackedCompetitionSubscription, list[ActiveEventRecord]]:
        """Load current active matches for one tracked league and chat."""

        tracked_subscription = self.repository.get_tracked_competition_subscription(
            chat_id,
            tracked_league_id,
        )

        if tracked_subscription is None:
            raise ValueError(
                f"No tracked competition found for chat_id={chat_id} and tracked_league_id={tracked_league_id}."
            )

        return tracked_subscription, self.repository.get_active_events(
            tracked_league_id,
            only_future=True,
        )

    def build_refresh_summary_message(self, summary: RefreshSummary) -> CommandResult:
        """Build the user-facing summary for `/refresh_tracks` or monitor logs."""

        if summary.tracks_requested == 0:
            return CommandResult(
                ok=True,
                message=(
                    "No tenés ligas trackeadas todavía.\n"
                    "Usá /track_url <url_de_plataforma> y después /confirm_track."
                ),
            )

        lines = [
            "Refresh completado." if not summary.failed_leagues else "Refresh completado con errores.",
            f"Ligas intentadas: {summary.tracks_requested}",
            f"Ligas actualizadas: {summary.tracks_refreshed}",
            f"Partidos activos guardados: {summary.active_matches}",
            f"Nuevos eventos detectados: {summary.new_events}",
            f"Cambios de odds detectados: {summary.odds_changes}",
        ]

        if summary.failed_leagues:
            lines.append(
                f"Ligas con error ({len(summary.failed_leagues)}): {', '.join(summary.failed_leagues)}"
            )

        return CommandResult(ok=True, message="\n".join(lines))

    def _build_pending_confirmation_message(self, pending_request: PendingCompetitionTrackRequest) -> str:
        """Build the Telegram message shown after `/track_url` succeeds."""

        return (
            f"Encontré la liga {pending_request.league_name}.\n"
            f"🌐 Plataforma: {pending_request.platform_display_name}\n"
            f"🔑 Key: {pending_request.platform}\n"
            f"🏷️ Competencia: {pending_request.topic}\n"
            "Respondé /confirm_track para agregarla al tracking."
        )

    def _build_empty_pending_confirmation_message(
        self,
        pending_request: PendingCompetitionTrackRequest,
    ) -> str:
        """Build the Telegram message shown after detecting a valid empty league."""

        return (
            "⚠️ La liga fue detectada, pero actualmente no tiene partidos o cuotas disponibles.\n\n"
            f"Liga: {pending_request.league_name}\n"
            f"Plataforma: {pending_request.platform_display_name}\n"
            f"URL: {pending_request.url}\n\n"
            "¿Querés almacenarla igual para empezar a trackearla?\n"
            "Respondé:\n"
            "- /confirm_empty_track para guardarla igualmente\n"
            "- /cancel para cancelar"
        )

    def _build_confirmation_message(
        self,
        confirmed_request: ConfirmedCompetitionTrackRequest,
        *,
        bootstrap_count: int | None,
        bootstrap_error: str | None,
    ) -> str:
        """Build the Telegram message shown after `/confirm_track`."""

        tracked_league = confirmed_request.tracked_league
        subscription = confirmed_request.subscription

        lines = [
            "✅ Liga trackeada",
            f"🌐 Plataforma: {tracked_league.platform_display_name}",
            f"🏷️ Liga: {tracked_league.league_name}",
            f"🔑 Competencia: {tracked_league.topic}",
            f"🆔 Track ID: {tracked_league.id}",
            f"notify_new_matches={'on' if subscription.notify_new_matches else 'off'}",
            f"notify_odds_changes={'on' if subscription.notify_odds_changes else 'off'}",
        ]

        if bootstrap_count is not None:
            lines.append(f"Estado inicial guardado: {bootstrap_count} partidos activos.")

        if bootstrap_error is not None:
            lines.append(
                "No pude guardar el estado inicial ahora mismo. "
                "El monitor lo volverá a intentar automáticamente."
            )

        return "\n".join(lines)

    def _build_empty_confirmation_message(
        self,
        confirmed_request: ConfirmedCompetitionTrackRequest,
    ) -> str:
        """Build the Telegram message shown after confirming an empty league."""

        tracked_league = confirmed_request.tracked_league
        subscription = confirmed_request.subscription

        lines = [
            "✅ Liga trackeada",
            f"🌐 Plataforma: {tracked_league.platform_display_name}",
            f"🏷️ Liga: {tracked_league.league_name}",
            f"🔑 Competencia: {tracked_league.topic}",
            f"🆔 Track ID: {tracked_league.id}",
            f"notify_new_matches={'on' if subscription.notify_new_matches else 'off'}",
            f"notify_odds_changes={'on' if subscription.notify_odds_changes else 'off'}",
            "La liga quedó guardada aunque todavía no tenga partidos activos.",
        ]

        if tracked_league.needs_name_resolution:
            lines.append(
                "Se usó un nombre provisorio y se reemplazará automáticamente cuando la plataforma muestre eventos reales."
            )

        return "\n".join(lines)

    async def _refresh_leagues(self, tracked_league_ids: Sequence[int]) -> RefreshSummary:
        """Refresh a deduplicated set of tracked leagues under one shared lock."""

        unique_ids = list(dict.fromkeys(tracked_league_ids))

        if not unique_ids:
            return RefreshSummary(
                tracks_requested=0,
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
            for tracked_league in [self.repository.get_tracked_competition(tracked_league_id)]
            if tracked_league is not None
        ]

        async with self._refresh_lock:
            for batch in _batched(tracked_leagues, self.max_parallel_refreshes):
                extracted_batch = await asyncio.gather(
                    *(self._extract_league(tracked_league.url) for tracked_league in batch),
                    return_exceptions=True,
                )

                for tracked_league, extraction_or_error in zip(batch, extracted_batch, strict=True):
                    if isinstance(extraction_or_error, Exception):
                        failed_leagues.append(tracked_league.league_name)
                        logger.error(
                            "Failed to refresh tracked competition id=%s, continuing with remaining competitions.",
                            tracked_league.id,
                            exc_info=(
                                type(extraction_or_error),
                                extraction_or_error,
                                extraction_or_error.__traceback__,
                            ),
                        )
                        continue

                    try:
                        result = self._apply_extraction_to_tracked_league(
                            tracked_league.id,
                            extraction_or_error,
                        )
                    except Exception as error:
                        failed_leagues.append(tracked_league.league_name)
                        logger.error(
                            "Failed to refresh tracked competition id=%s, continuing with remaining competitions.",
                            tracked_league.id,
                            exc_info=(type(error), error, error.__traceback__),
                        )
                        continue

                    logger.info(
                        "Refreshed competition id=%s platform=%s name=%s active=%s new=%s odds_changes=%s reminders=%s removed_missing=%s removed_past=%s",
                        result.tracked_league.id,
                        result.tracked_league.platform,
                        result.tracked_league.league_name,
                        len(result.active_matches),
                        len(result.new_matches),
                        len(result.odds_changes),
                        len(result.reminder_matches),
                        result.removed_missing_count,
                        result.removed_past_count,
                    )
                    league_results.append(result)

        return RefreshSummary(
            tracks_requested=len(tracked_leagues),
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
        extraction: CompetitionExtraction,
    ) -> CompetitionRefreshResult:
        """Apply one extracted competition snapshot to global stored state."""

        scraped_at = _utc_now_iso()
        league_name, needs_name_resolution = self._resolve_league_name_for_update(
            tracked_league_id,
            extraction,
        )

        tracked_league = self.repository.update_tracked_competition(
            tracked_league_id,
            source_url=extraction.source_url,
            competition_external_id=extraction.competition_external_id,
            competition_name=league_name,
            needs_name_resolution=needs_name_resolution,
            last_synced_at=scraped_at,
        )

        existing_by_fixture = {
            match.fixture_id: match
            for match in self.repository.get_active_events(tracked_league_id, only_future=False)
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
            ActiveEventUpsert(
                external_event_id=match.external_event_id,
                home=match.home,
                away=match.away,
                scheduled_label_date=match.scheduled_label_date,
                scheduled_label_time=match.scheduled_label_time,
                scheduled_at=match.scheduled_at,
                odds_home=match.odds_home,
                odds_draw=match.odds_draw,
                odds_away=match.odds_away,
                event_url=match.source_url,
                markets_payload=_markets_payload_from_event(match),
                raw_payload=match.raw_payload,
            )
            for match in future_matches
        ]

        if upsert_payload:
            self.repository.upsert_active_events(tracked_league_id, upsert_payload)

        removed_missing_count = self.repository.remove_missing_events(
            tracked_league_id,
            current_fixture_ids,
        )
        removed_past_count = self.repository.remove_past_events(tracked_league_id)
        active_matches = self.repository.get_active_events(tracked_league_id, only_future=True)
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
        reminder_matches = _select_due_reminders(active_matches)

        return CompetitionRefreshResult(
            tracked_league=tracked_league,
            active_matches=active_matches,
            new_matches=new_matches,
            odds_changes=odds_changes,
            reminder_matches=reminder_matches,
            removed_missing_count=removed_missing_count,
            removed_past_count=removed_past_count,
        )

    def _seed_initial_snapshot(
        self,
        tracked_league_id: int,
        extraction: CompetitionExtraction,
    ) -> int:
        """Store a baseline snapshot for a league without generating diff events."""

        scraped_at = _utc_now_iso()
        league_name, needs_name_resolution = self._resolve_league_name_for_update(
            tracked_league_id,
            extraction,
        )

        self.repository.update_tracked_competition(
            tracked_league_id,
            source_url=extraction.source_url,
            competition_external_id=extraction.competition_external_id,
            competition_name=league_name,
            needs_name_resolution=needs_name_resolution,
            last_synced_at=scraped_at,
        )

        future_matches = [match for match in extraction.matches if not _is_past_match(match)]
        current_fixture_ids = [match.fixture_id for match in future_matches]
        upsert_payload = [
            ActiveEventUpsert(
                external_event_id=match.external_event_id,
                home=match.home,
                away=match.away,
                scheduled_label_date=match.scheduled_label_date,
                scheduled_label_time=match.scheduled_label_time,
                scheduled_at=match.scheduled_at,
                odds_home=match.odds_home,
                odds_draw=match.odds_draw,
                odds_away=match.odds_away,
                event_url=match.source_url,
                markets_payload=_markets_payload_from_event(match),
                raw_payload=match.raw_payload,
            )
            for match in future_matches
        ]

        if upsert_payload:
            self.repository.upsert_active_events(tracked_league_id, upsert_payload)

        self.repository.remove_missing_events(tracked_league_id, current_fixture_ids)
        self.repository.remove_past_events(tracked_league_id)

        active_count = len(self.repository.get_active_events(tracked_league_id, only_future=True))
        logger.info(
            "Seeded initial competition baseline for tracked_league_id=%s league=%s active=%s",
            tracked_league_id,
            league_name,
            active_count,
        )
        return active_count

    def _resolve_league_name_for_update(
        self,
        tracked_league_id: int,
        extraction: CompetitionExtraction,
    ) -> tuple[str, bool]:
        """Resolve a safe league name for persistence during refreshes."""

        extracted_name = extraction.league_name.strip() if extraction.league_name else ""

        if extracted_name and extracted_name.lower() != "none":
            return extracted_name, extraction.is_provisional_name

        tracked_league = self.repository.get_tracked_competition(tracked_league_id)
        if tracked_league is None:
            raise ValueError(f"No tracked competition found with id={tracked_league_id}.")

        logger.info(
            "Preserving existing league_name for tracked_league_id=%s because extractor returned empty name.",
            tracked_league_id,
        )
        return tracked_league.league_name, tracked_league.needs_name_resolution

    def _needs_baseline_seed(self, tracked_league_id: int) -> bool:
        """Return whether a tracked league still lacks a usable initial snapshot."""

        tracked_league = self.repository.get_tracked_competition(tracked_league_id)

        if tracked_league is None or tracked_league.last_scraped_at is None:
            return True

        active_matches = self.repository.get_active_events(tracked_league_id, only_future=False)

        if not active_matches:
            return True

        return any(
            match.odds_home is None and match.odds_draw is None and match.odds_away is None
            for match in active_matches
        )


def _is_past_match(match: EventSnapshot) -> bool:
    """Return whether a normalized event already kicked off in the past."""

    if match.kickoff_at is None:
        return False

    try:
        kickoff = datetime.fromisoformat(match.kickoff_at)
    except ValueError:
        return False

    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)

    return kickoff < datetime.now(timezone.utc)


def _odds_tuple_from_match(match: EventSnapshot) -> tuple[float | None, float | None, float | None]:
    """Extract the comparable 1/X/2 odds tuple from a normalized event."""

    return (match.odds_home, match.odds_draw, match.odds_away)


def _odds_tuple_from_record(
    match: ActiveEventRecord,
) -> tuple[float | None, float | None, float | None]:
    """Extract the comparable 1/X/2 odds tuple from a stored active match."""

    return (match.odds_home, match.odds_draw, match.odds_away)


def _markets_payload_from_event(match: EventSnapshot) -> dict[str, dict[str, float | None]] | None:
    """Build the current normalized market payload stored with one active event."""

    if match.odds_home is None and match.odds_draw is None and match.odds_away is None:
        return None

    return {
        "1x2": {
            "home": match.odds_home,
            "draw": match.odds_draw,
            "away": match.odds_away,
        }
    }


def _evaluate_subscription_odds_change(
    repository: SqliteTrackingRepository,
    subscription: CompetitionSubscription,
    tracked_league: TrackedCompetition,
    match: ActiveEventRecord,
) -> SubscriptionOddsAlert | None:
    """Evaluate one global odds change against a specific chat baseline."""

    baseline = repository.get_event_baseline(
        subscription.telegram_chat_id,
        tracked_league.id,
        match.fixture_id,
    )

    if baseline is None:
        repository.initialize_event_baselines(
            subscription.telegram_chat_id,
            tracked_league.id,
            [match],
        )
        return None

    max_percent_change = _compute_max_percent_change(baseline, match)

    if max_percent_change is None:
        repository.upsert_event_baseline(
            subscription.telegram_chat_id,
            tracked_league.id,
            match.fixture_id,
            baseline_home=match.odds_home,
            baseline_draw=match.odds_draw,
            baseline_away=match.odds_away,
        )
        repository.resolve_small_change_with_current_baseline(
            subscription.telegram_chat_id,
            tracked_league.id,
            match.fixture_id,
        )
        return None

    should_notify = (
        subscription.notify_odds_changes
        and max_percent_change >= subscription.change_percent_threshold
    )

    if should_notify:
        return SubscriptionOddsAlert(
            match=match,
            baseline=baseline,
            max_percent_change=max_percent_change,
        )

    repository.upsert_small_change(
        subscription.telegram_chat_id,
        tracked_league.id,
        match.fixture_id,
        home=match.home,
        away=match.away,
        scheduled_label_date=match.kickoff_label_date,
        scheduled_label_time=match.kickoff_label_time,
        baseline_home=baseline.baseline_home,
        baseline_draw=baseline.baseline_draw,
        baseline_away=baseline.baseline_away,
        current_home=match.odds_home,
        current_draw=match.odds_draw,
        current_away=match.odds_away,
        max_percent_change=max_percent_change,
        status="pending",
    )
    return None


def _compute_max_percent_change(
    baseline: EventBaseline,
    match: ActiveEventRecord,
) -> float | None:
    """Return the maximum valid percent change between baseline and current odds."""

    changes = [
        _compute_percent_change(baseline.baseline_home, match.odds_home),
        _compute_percent_change(baseline.baseline_draw, match.odds_draw),
        _compute_percent_change(baseline.baseline_away, match.odds_away),
    ]
    valid_changes = [change for change in changes if change is not None]

    if not valid_changes:
        return None

    return max(valid_changes)


def _compute_percent_change(
    baseline_value: float | None,
    current_value: float | None,
) -> float | None:
    """Compute absolute percent change for one odds selection."""

    if baseline_value is None or current_value is None:
        return None

    if baseline_value <= 0:
        return None

    return abs(current_value - baseline_value) / baseline_value * 100


def _select_due_reminders(matches: Sequence[ActiveEventRecord]) -> list[ActiveEventRecord]:
    """Return matches that should trigger the 5-minute reminder now."""

    now = datetime.now(timezone.utc)
    due_matches: list[ActiveEventRecord] = []

    for match in matches:
        if match.alerted:
            continue

        time_label = (match.kickoff_label_time or "").strip()
        if not time_label:
            continue

        kickoff = _parse_match_kickoff(match)
        if kickoff is None:
            continue

        reminder_time = kickoff - timedelta(minutes=5)
        if reminder_time <= now <= kickoff:
            due_matches.append(match)

    return due_matches


def _parse_match_kickoff(match: ActiveEventRecord) -> datetime | None:
    """Parse the stored kickoff timestamp into an aware UTC datetime."""

    if match.kickoff_at is None:
        return None

    try:
        kickoff = datetime.fromisoformat(match.kickoff_at)
    except ValueError:
        return None

    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)

    return kickoff.astimezone(timezone.utc)


def _batched(items: Sequence[TrackedCompetition], batch_size: int) -> list[list[TrackedCompetition]]:
    """Split a sequence of tracked leagues into small ordered batches."""

    return [list(items[index:index + batch_size]) for index in range(0, len(items), batch_size)]


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""

    return datetime.now(timezone.utc).isoformat()


# Legacy aliases kept during the transition from Bet365-specific naming to
# neutral tracking terminology.
LeagueRefreshResult = CompetitionRefreshResult
Bet365TrackingService = TrackingService

__all__ = [
    "Bet365TrackingService",
    "CommandResult",
    "CompetitionRefreshResult",
    "LeagueRefreshResult",
    "OddsChange",
    "RefreshSummary",
    "SubscriptionOddsAlert",
    "TrackingService",
]

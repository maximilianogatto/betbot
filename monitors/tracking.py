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
from dataclasses import replace
from datetime import datetime, timezone
import json
import logging
import time

from telegram import Bot
from telegram.constants import ParseMode

from bot.alerts import (
    build_competition_unavailable_warning_message,
    build_competition_url_message,
    build_event_stats_message,
    build_event_url_message,
    build_grouped_new_event_alert_message,
    build_grouped_odds_change_alert_message,
    build_match_reminder_alert_message,
    build_new_event_alert_message,
    build_odds_change_alert_message,
    split_telegram_message,
)
from core.extractor_base import CompetitionUnavailableError, LeagueDiscoveryOption
from monitors.change_detection import (
    evaluate_subscription_odds_change,
    select_due_reminders,
)
from monitors.models import (
    CommandResult,
    CompetitionRefreshResult,
    OddsChange,
    RefreshSummary,
    SubscriptionOddsAlert,
    UnavailableCompetitionRefresh,
)
from core.models import CompetitionExtraction, EventSnapshot, PlatformDescriptor
from core.registry import ExtractorRegistry, extractor_registry as global_extractor_registry
from storage.tracking_repository import (
    ActiveEventRecord,
    ActiveEventUpsert,
    ConfirmedCompetitionTrackRequest,
    PendingCompetitionTrackRequest,
    SmallChangeRecord,
    SqliteTrackingRepository,
    TrackedCompetition,
    TrackedCompetitionSubscription,
    tracking_repository as default_tracking_repository,
)

logger = logging.getLogger(__name__)

UNAVAILABLE_COMPETITION_MESSAGE = (
    "Competition could not be refreshed because the source currently has no active events "
    "or the URL may have changed."
)
UNAVAILABLE_WARNING_FAILURE_THRESHOLD = 2
UNAVAILABLE_WARNING_COOLDOWN_SECONDS = 12 * 60 * 60


def format_duration(seconds: float) -> str:
    """Format one elapsed duration in a compact user-facing representation."""

    whole_seconds = max(0, int(seconds))
    hours, remainder = divmod(whole_seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


class TrackingService:
    """Coordinate tracking, refresh, and notification workflows across platforms."""

    def __init__(
        self,
        extractor_registry: ExtractorRegistry | None = None,
        repository: SqliteTrackingRepository | None = None,
        max_parallel_refreshes: int = 3,
        remove_missing_after_cycles: int = 3,
        odds_change_confirmation_refreshes: int = 2,
        odds_flap_window_minutes: int = 10,
        odds_flap_epsilon: float = 0.01,
    ) -> None:
        self.extractor_registry = extractor_registry or global_extractor_registry
        self.repository = repository or default_tracking_repository
        self.max_parallel_refreshes = max(1, max_parallel_refreshes)
        self.remove_missing_after_cycles = max(1, remove_missing_after_cycles)
        self.odds_change_confirmation_refreshes = max(1, odds_change_confirmation_refreshes)
        self.odds_flap_window_minutes = max(1, odds_flap_window_minutes)
        self.odds_flap_epsilon = max(0.0, odds_flap_epsilon)
        self._refresh_lock = asyncio.Lock()
        self._refresh_slot_lock = asyncio.Lock()
        self._active_refresh_trigger: str | None = None

    async def _extract_league(self, url: str) -> CompetitionExtraction:
        """Resolve the right extractor for a competition URL and delegate extraction."""

        extractor = self.extractor_registry.get_for_url(url)
        extraction = await extractor.extract_league(url)

        if not isinstance(extraction, CompetitionExtraction):
            raise TypeError(
                "TrackingService received an unexpected competition extraction payload type."
            )

        return extraction

    async def create_pending_track_from_url(
        self, chat_id: int, url: str, *, custom_name: str | None = None
    ) -> CommandResult:
        """Validate a supported URL, extract metadata, and store a pending request.

        ``custom_name`` overrides the competition name (useful for platforms like
        Mystake whose API does not expose league names).
        """

        try:
            extraction = await self._extract_league(url)
        except ValueError as error:
            logger.warning(
                "Competition extraction validation failed for chat_id=%s url=%s: %s",
                chat_id,
                url,
                error,
            )
            return CommandResult(
                ok=False,
                message=(
                    "No pude validar la URL de la competencia.\n\n"
                    "Verificá que el link sea válido y que pertenezca a una plataforma soportada.\n"
                    "Usá /platforms para ver las disponibles."
                ),
            )
        except CompetitionUnavailableError as error:
            logger.warning(
                "Competition extraction unavailable for chat_id=%s url=%s: %s",
                chat_id,
                url,
                error,
            )
            return CommandResult(
                ok=False,
                message=(
                    "No pude validar la competencia en este momento.\n\n"
                    "La competencia puede estar temporalmente vacía, los eventos pueden haber sido removidos "
                    "o el link puede haber cambiado.\n\n"
                    "Verificá la competencia en el navegador y volvé a intentar en unos minutos."
                ),
            )
        except RuntimeError as error:
            logger.exception("Competition extraction failed for chat_id=%s.", chat_id)
            return CommandResult(
                ok=False,
                message=(
                    "No pude extraer la liga desde la plataforma indicada.\n\n"
                    "Verificá la competencia en el navegador y volvé a intentar."
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
                competition_name=(custom_name or extraction.competition_name),
                requires_empty_confirmation=extraction.is_empty,
                needs_name_resolution=extraction.is_provisional_name and not custom_name,
                payload=extraction.raw_payload,
            )
        except ValueError as error:
            logger.warning(
                "Pending competition request could not be stored for chat_id=%s: %s",
                chat_id,
                error,
            )
            return CommandResult(
                ok=False,
                message=(
                    "No pude guardar el tracking pendiente.\n\n"
                    "Volvé a intentar en unos minutos."
                ),
            )

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
        active_events: list[ActiveEventRecord] = []

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
                except CompetitionUnavailableError as error:
                    logger.warning(
                        "Initial competition bootstrap unavailable for tracked_league_id=%s: %s",
                        confirmed_request.tracked_competition.id,
                        error,
                    )
                    bootstrap_error = str(error)
                except Exception as error:
                    logger.exception(
                        "Initial competition bootstrap failed for tracked_league_id=%s.",
                        confirmed_request.tracked_competition.id,
                    )
                    bootstrap_error = str(error)

            try:
                active_events = self.repository.get_active_events(
                    confirmed_request.tracked_competition.id,
                    only_future=True,
                )
                self._initialize_subscription_state(
                    chat_id,
                    confirmed_request.tracked_competition.id,
                    active_events,
                )
            except Exception:
                logger.exception(
                    "Failed to initialize per-chat subscription state for chat_id=%s tracked_league_id=%s.",
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

            active_events = self.repository.get_active_events(
                confirmed_request.tracked_competition.id,
                only_future=True,
            )
            self._initialize_subscription_state(
                chat_id,
                confirmed_request.tracked_competition.id,
                active_events,
            )

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

    def list_league_discovery_platforms(self) -> list[PlatformDescriptor]:
        """Return platforms that can discover leagues without a pasted URL."""

        return [
            extractor.describe_platform()
            for extractor in self.extractor_registry.list_registered()
            if extractor.supports_league_discovery
        ]

    async def search_discoverable_leagues(
        self,
        *,
        platform: str,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[LeagueDiscoveryOption]:
        """Search trackable leagues for one discovery-capable platform."""

        extractor = self.extractor_registry.get_for_platform(platform)
        if not extractor.supports_league_discovery:
            raise ValueError(f"La plataforma {platform} no soporta /track_league.")
        return await extractor.search_leagues(
            country_name=country_name,
            query=query,
            limit=limit,
        )

    async def track_discovered_league(
        self,
        chat_id: int,
        option: LeagueDiscoveryOption,
    ) -> CommandResult:
        """Create and confirm a track from a discovery option in one step."""

        pending_result = await self.create_pending_track_from_url(chat_id, option.source_url)
        if not pending_result.ok:
            return pending_result

        pending_request = self.repository.get_latest_pending_competition_request(chat_id)
        if pending_request is not None and pending_request.requires_empty_confirmation:
            return await self.confirm_empty_pending_track(chat_id)

        return await self.confirm_pending_track(chat_id)

    async def bulk_track_leagues(
        self,
        chat_id: int,
        leagues_text: str,
    ) -> CommandResult:
        """Process a bulk track list of leagues, searching and tracking matches across all platforms."""
        import re
        import html
        from monitors.stats import _league_name_similarity

        # 1. Parse the text block
        lines = leagues_text.strip().split("\n")
        queries = []
        for line in lines:
            line_clean = line.strip()
            if not line_clean or line_clean.lower().startswith("ligas:"):
                continue
            # Remove common bullet points, emoji, etc.
            line_clean = re.sub(r"^[📍\-*•+\s]+", "", line_clean).strip()
            if not line_clean:
                continue
            if "." in line_clean:
                parts = line_clean.split(".", 1)
                country = parts[0].strip()
                league = parts[1].strip()
                queries.append((country, league))
            else:
                queries.append(("", line_clean))

        if not queries:
            return CommandResult(ok=False, message="No se encontraron líneas válidas después de 'Ligas:'.")

        platforms = self.list_league_discovery_platforms()
        results = []

        for country, query in queries:
            found_any = False
            platform_matches = []
            
            # Search across all platforms
            for platform_desc in platforms:
                platform_key = platform_desc.key
                try:
                    # Try searching with country filter first
                    options = await self.search_discoverable_leagues(
                        platform=platform_key,
                        country_name=country,
                        query=query if country else None,
                    )
                    # Fallback to search without country filter if not found
                    if not options and country:
                        options = await self.search_discoverable_leagues(
                            platform=platform_key,
                            country_name="",
                            query=query,
                        )
                    
                    for opt in options:
                        target_name = query
                        score = _league_name_similarity(opt.league_name, target_name)
                        if score >= 0.85:
                            platform_matches.append((platform_desc.display_name, opt, score))
                except Exception as e:
                    logger.warning("Error searching leagues on platform %s: %s", platform_key, e)
                    
            if platform_matches:
                seen_platforms = set()
                tracked_platforms = []
                for plat_name, opt, score in sorted(platform_matches, key=lambda x: x[2], reverse=True):
                    if opt.platform in seen_platforms:
                        continue
                    seen_platforms.add(opt.platform)
                    
                    track_res = await self.track_discovered_league(chat_id, opt)
                    if track_res.ok:
                        tracked_platforms.append(f"{plat_name} ({score:.0%})")
                
                if tracked_platforms:
                    found_any = True
                    results.append(
                        f"✅ <b>{html.escape(country + '.' if country else '')} {html.escape(query)}</b> -> Vigilando en: {html.escape(', '.join(tracked_platforms))}"
                    )
            
            if not found_any:
                results.append(
                    f"❌ <b>{html.escape(country + '.' if country else '')} {html.escape(query)}</b> -> No se encontró coincidencia confiable (>=85%)"
                )

        msg = "📊 <b>Resultado de Importación Masiva:</b>\n\n" + "\n".join(results)
        return CommandResult(ok=True, message=msg)

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
        visible_index = 0

        for item in tracked_leagues:
            platform_name = item.tracked_league.platform_display_name

            if platform_name != current_platform:
                if current_platform is not None:
                    lines.append("")
                lines.append(f"🌐 {platform_name}")
                current_platform = platform_name

            visible_index += 1
            lines.append(
                f"{visible_index}. {item.tracked_league.league_name} | "
                f"enabled={'on' if item.subscription.enabled else 'off'} | "
                f"odds={'on' if item.subscription.notify_odds_changes else 'off'} | "
                f"threshold={item.subscription.change_percent_threshold:.1f}%"
            )

        return CommandResult(ok=True, message="\n".join(lines))

    async def update_tracked_competition_url(
        self,
        chat_id: int,
        *,
        track_number: int,
        new_url: str,
    ) -> CommandResult:
        """Validate and replace the source URL for one tracked competition."""

        tracked_subscription = self._get_track_by_number(chat_id, track_number)
        if tracked_subscription is None:
            return CommandResult(
                ok=False,
                message="No encontré ese número de liga en /list_tracks.",
            )

        tracked_competition = tracked_subscription.tracked_league

        if self.repository.get_enabled_subscription_count(tracked_competition.id) > 1:
            return CommandResult(
                ok=False,
                message=(
                    "Esta competencia está compartida por múltiples chats y no puede actualizarse automáticamente."
                ),
            )

        try:
            extraction = await self._extract_league(new_url)
        except ValueError as error:
            logger.warning(
                "Tracked competition URL update validation failed for tracked_league_id=%s url=%s: %s",
                tracked_competition.id,
                new_url,
                error,
            )
            return CommandResult(
                ok=False,
                message=(
                    "No pude validar la nueva URL.\n\n"
                    "Verificá que el link sea válido y que pertenezca a una plataforma soportada.\n"
                    "Usá /platforms para ver las disponibles."
                ),
            )
        except CompetitionUnavailableError as error:
            logger.warning(
                "Tracked competition URL update unavailable for tracked_league_id=%s url=%s: %s",
                tracked_competition.id,
                new_url,
                error,
            )
            return CommandResult(
                ok=False,
                message=(
                    "No pude validar la nueva URL en este momento.\n\n"
                    "La competencia puede estar temporalmente vacía, los eventos pueden haber sido removidos "
                    "o el link puede haber cambiado.\n\n"
                    "Verificá el link en el navegador y volvé a intentar."
                ),
            )
        except RuntimeError as error:
            logger.exception(
                "Tracked competition URL update failed for tracked_league_id=%s.",
                tracked_competition.id,
            )
            return CommandResult(
                ok=False,
                message=(
                    "No pude actualizar la URL trackeada.\n\n"
                    "Verificá el link en el navegador y volvé a intentar."
                ),
            )

        if extraction.platform != tracked_competition.platform:
            return CommandResult(
                ok=False,
                message="La nueva URL pertenece a otra plataforma y no puede reutilizar este tracking.",
            )

        if extraction.is_empty:
            return CommandResult(
                ok=False,
                message=(
                    "La nueva URL es válida, pero actualmente no muestra partidos activos.\n"
                    "No actualicé la liga para evitar dejarla en un estado ambiguo."
                ),
            )

        conflicting_competition = self.repository.get_tracked_competition_by_identity(
            platform=extraction.platform,
            competition_external_id=extraction.competition_external_id,
        )
        if conflicting_competition is not None and conflicting_competition.id != tracked_competition.id:
            return CommandResult(
                ok=False,
                message="La nueva URL apunta a una competencia que ya existe en el tracking.",
            )

        async with self._refresh_lock:
            updated_competition = self.repository.update_tracked_competition_source(
                tracked_competition.id,
                source_url=extraction.source_url,
                competition_external_id=extraction.competition_external_id,
                competition_name=extraction.competition_name,
                needs_name_resolution=extraction.is_provisional_name,
                payload=extraction.raw_payload,
            )
            seeded_count = self._seed_initial_snapshot(updated_competition.id, extraction)

        return CommandResult(
            ok=True,
            message=(
                "✅ URL de tracking actualizada\n"
                f"🌐 Plataforma: {updated_competition.platform_display_name}\n"
                f"🏷️ Liga: {updated_competition.league_name}\n"
                f"🔑 Competencia: {updated_competition.topic}\n\n"
                f"Estado actual sincronizado: {seeded_count} partidos activos."
            ),
        )

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
        """Remove the chat's subscription to the whole unified league (all platforms)."""

        try:
            tracked = self.repository.get_tracked_competition(tracked_league_id)
            unified_id = tracked.unified_competition_id if tracked is not None else None
            if unified_id is not None:
                results = self.repository.remove_unified_subscription(chat_id, unified_id)
            else:
                results = [
                    self.repository.remove_tracked_competition_subscription(chat_id, tracked_league_id)
                ]
        except ValueError as error:
            return CommandResult(ok=False, message=str(error))

        platforms = sorted({r.tracked_league.platform for r in results})
        league_name = results[0].tracked_league.league_name
        if len(platforms) > 1:
            lines = [
                f"Dejaste de trackear {league_name} en {len(platforms)} plataformas: {', '.join(platforms)}."
            ]
        else:
            lines = [f"Dejaste de trackear {league_name}."]

        if all(r.league_disabled for r in results):
            lines.append(
                "Como no quedaron más chats suscriptos, la liga se desactivó y se limpió su estado scrapeado."
            )
        else:
            remaining = max(r.remaining_enabled_subscriptions for r in results)
            lines.append(f"Suscripciones activas restantes para esa liga: {remaining}")

        return CommandResult(ok=True, message="\n".join(lines))

    def learn_unified_merges(self) -> list[dict]:
        """Fusiona ligas unificadas que comparten partidos físicos en otra plataforma.

        Aprendizaje automático del registro (decisión: ejecutar; /unlink_league
        repara). Umbral deliberadamente alto para evitar falsos positivos:
        equipos >=0.85 de similitud, kickoffs a <=30 min (o >=0.92 sin horario),
        plataformas distintas y >=2 partidos coincidentes entre ambas ligas.
        """

        repository = self.repository
        events_by_unified: dict[int, list] = {}
        league_names: dict[int, str] = {}
        for comp in repository.list_globally_active_competitions():
            unified_id = comp.unified_competition_id
            if unified_id is None:
                continue
            try:
                events = repository.get_active_events(comp.id, only_future=True)
            except Exception:
                continue
            events_by_unified.setdefault(unified_id, []).extend(events)
            league_names.setdefault(unified_id, comp.league_name)

        merges: list[dict] = []
        unified_ids = sorted(events_by_unified)
        merged_away: set[int] = set()
        for i, target_id in enumerate(unified_ids):
            if target_id in merged_away:
                continue
            for source_id in unified_ids[i + 1:]:
                if source_id in merged_away:
                    continue
                coincidences = self._coinciding_matches(
                    events_by_unified[target_id], events_by_unified[source_id]
                )
                if coincidences < 2:
                    continue
                try:
                    repository.merge_unified_competitions(source_id, target_id)
                except ValueError:
                    continue
                merged_away.add(source_id)
                events_by_unified[target_id].extend(events_by_unified[source_id])
                merges.append({
                    "into_id": target_id,
                    "into_name": league_names.get(target_id, str(target_id)),
                    "from_name": league_names.get(source_id, str(source_id)),
                    "matches": coincidences,
                })
                logger.info(
                    "League learning: merged unified %s («%s») into %s («%s») on %s coinciding matches.",
                    source_id, merges[-1]["from_name"], target_id, merges[-1]["into_name"], coincidences,
                )
        return merges

    @staticmethod
    def _coinciding_matches(events_a: list, events_b: list) -> int:
        """Count physical matches shared by two leagues across DIFFERENT platforms."""

        from bot.alerts import _physical_match_similarity

        def _parse(raw):
            try:
                return datetime.fromisoformat(str(raw).strip())
            except (TypeError, ValueError):
                return None

        count = 0
        used_b: set[int] = set()
        for event_a in events_a:
            for j, event_b in enumerate(events_b):
                if j in used_b or event_a.platform == event_b.platform:
                    continue
                similarity = _physical_match_similarity(event_a, event_b)
                if similarity < 0.85:
                    continue
                dt_a, dt_b = _parse(event_a.scheduled_at), _parse(event_b.scheduled_at)
                if dt_a is not None and dt_b is not None:
                    if abs((dt_a - dt_b).total_seconds()) > 1800:
                        continue
                elif similarity < 0.92:
                    continue  # sin horario confiable, exigir similitud más alta
                used_b.add(j)
                count += 1
                break
        return count

    async def learn_and_notify_league_merges(self, bot: Bot) -> None:
        """Run league-merge learning and tell the merged league's subscribers."""

        try:
            merges = await asyncio.to_thread(self.learn_unified_merges)
        except Exception:
            logger.exception("League-merge learning failed.")
            return
        for merge in merges:
            chats: set[int] = set()
            for comp in self.repository.list_tracked_competitions_for_unified(merge["into_id"]):
                for sub in self.repository.get_subscriptions_for_competition(comp.id, only_enabled=True):
                    chats.add(sub.telegram_chat_id)
            text = (
                f"🧠 Aprendí: «{merge['from_name']}» es la misma liga que «{merge['into_name']}» "
                f"({merge['matches']} partidos coincidentes en otra plataforma) — las unifiqué.\n"
                "Heredás sus links de odds y stats. Si está mal, separala con /unlink_league."
            )
            for chat_id in sorted(chats):
                try:
                    await bot.send_message(chat_id=chat_id, text=text)
                except Exception:
                    logger.warning("Could not notify chat %s about a league merge.", chat_id)

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

            try:
                extraction = await self._extract_league(tracked_league.url)
            except CompetitionUnavailableError:
                self.repository.record_unavailable_refresh(
                    tracked_league.id,
                    reason=UNAVAILABLE_COMPETITION_MESSAGE,
                )
                raise

            if extraction.is_empty:
                self.repository.record_unavailable_refresh(
                    tracked_league.id,
                    reason=UNAVAILABLE_COMPETITION_MESSAGE,
                )
                raise CompetitionUnavailableError(
                    UNAVAILABLE_COMPETITION_MESSAGE,
                    platform=tracked_league.platform,
                    source_url=tracked_league.url,
                    reason_code="competition_unavailable",
                )

            return self._apply_extraction_to_tracked_league(tracked_league_id, extraction)

    async def monitor_once(self, bot: Bot) -> RefreshSummary:
        """Run one global monitoring cycle and dispatch notifications."""

        if not await self.try_start_refresh("automatic"):
            logger.info(
                "Skipping automatic refresh because another refresh is already running: trigger=%s",
                self.current_refresh_trigger,
            )
            return self._build_empty_refresh_summary()

        try:
            summary = await self.refresh_all_active_leagues()
            await self.dispatch_notifications(
                bot,
                summary,
                notify_failures=False,
            )
            # Registry learning: leagues sharing physical matches across
            # platforms get merged automatically (subscribers are notified).
            await self.learn_and_notify_league_merges(bot)
            return summary
        finally:
            await self.finish_refresh("automatic")

    async def dispatch_notifications(
        self,
        bot: Bot,
        summary: RefreshSummary,
        *,
        notify_failures: bool = False,
        force_unavailable_warnings: bool = False,
        unavailable_warning_chat_id: int | None = None,
    ) -> None:
        """Send new-event and odds-change notifications to matching subscribers."""

        for result in summary.league_results:
            await self.notify_for_refresh_result(bot, result)

        if not notify_failures:
            return

        for unavailable in summary.unavailable_competitions:
            await self.notify_for_unavailable_competition(
                bot,
                unavailable,
                force_notify=force_unavailable_warnings,
                target_chat_id=unavailable_warning_chat_id,
            )

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
                unsent_new_matches = [
                    match
                    for match in result.new_matches
                    if not self.repository.has_sent_alert(
                        subscription.telegram_chat_id,
                        result.tracked_league.id,
                        match.fixture_id,
                        "new_event",
                    )
                ]

                if unsent_new_matches:
                    if len(unsent_new_matches) == 1:
                        await self._send_split_message(
                            bot,
                            subscription.telegram_chat_id,
                            build_new_event_alert_message(
                                result.tracked_league,
                                unsent_new_matches[0],
                            ),
                            parse_mode=ParseMode.HTML,
                        )
                    else:
                        await self._send_split_message(
                            bot,
                            subscription.telegram_chat_id,
                            build_grouped_new_event_alert_message(
                                result.tracked_league,
                                unsent_new_matches,
                            ),
                            parse_mode=ParseMode.HTML,
                        )

                    self.repository.mark_sent_alerts(
                        subscription.telegram_chat_id,
                        result.tracked_league.id,
                        [match.fixture_id for match in unsent_new_matches],
                        "new_event",
                    )

            pending_odds_alerts: list[SubscriptionOddsAlert] = []

            for change in result.odds_changes:
                alert = evaluate_subscription_odds_change(
                    self.repository,
                    subscription,
                    result.tracked_league,
                    change.after,
                    confirmation_refreshes=self.odds_change_confirmation_refreshes,
                    flap_window_minutes=self.odds_flap_window_minutes,
                    flap_epsilon=self.odds_flap_epsilon,
                )

                if alert is not None and subscription.notify_odds_changes:
                    pending_odds_alerts.append(alert)

            if pending_odds_alerts:
                if len(pending_odds_alerts) == 1:
                    alert = pending_odds_alerts[0]
                    await self._send_split_message(
                        bot,
                        subscription.telegram_chat_id,
                        build_odds_change_alert_message(
                            result.tracked_league,
                            alert,
                        ),
                        parse_mode=ParseMode.HTML,
                    )
                else:
                    await self._send_split_message(
                        bot,
                        subscription.telegram_chat_id,
                        build_grouped_odds_change_alert_message(
                            result.tracked_league,
                            pending_odds_alerts,
                        ),
                        parse_mode=ParseMode.HTML,
                    )

                for alert in pending_odds_alerts:
                    self.repository.upsert_event_baseline(
                        subscription.telegram_chat_id,
                        result.tracked_league.id,
                        alert.match.fixture_id,
                        baseline_home=alert.match.odds_home,
                        baseline_draw=alert.match.odds_draw,
                        baseline_away=alert.match.odds_away,
                        baseline_markets_json=(
                            alert.match.markets_json
                            if alert.confirmed_baseline_markets_payload is None
                            else json.dumps(
                                alert.confirmed_baseline_markets_payload,
                                ensure_ascii=False,
                                sort_keys=True,
                            )
                        ),
                    )
                    self.repository.resolve_small_change_with_current_baseline(
                        subscription.telegram_chat_id,
                        result.tracked_league.id,
                        alert.match.fixture_id,
                    )

            for match in result.reminder_matches:
                await self._send_split_message(
                    bot,
                    subscription.telegram_chat_id,
                    build_match_reminder_alert_message(result.tracked_league, match),
                    parse_mode=ParseMode.HTML,
                )

        if result.reminder_matches:
            self.repository.mark_events_alerted(
                result.tracked_league.id,
                [match.fixture_id for match in result.reminder_matches],
            )

    async def notify_for_unavailable_competition(
        self,
        bot: Bot,
        unavailable: UnavailableCompetitionRefresh,
        *,
        force_notify: bool = False,
        target_chat_id: int | None = None,
    ) -> None:
        """Send a warning for a competition that keeps failing to refresh."""

        if not force_notify and not self.repository.should_send_unavailable_refresh_warning(
            unavailable.tracked_league.id,
            minimum_failures=UNAVAILABLE_WARNING_FAILURE_THRESHOLD,
            cooldown_seconds=UNAVAILABLE_WARNING_COOLDOWN_SECONDS,
        ):
            return

        subscriptions = self.repository.get_subscriptions_for_competition(
            unavailable.tracked_league.id,
            only_enabled=True,
        )
        if not subscriptions:
            return

        sent_any_warning = False
        for subscription in subscriptions:
            if target_chat_id is not None and subscription.telegram_chat_id != target_chat_id:
                continue

            track_number = self._get_track_number(
                subscription.telegram_chat_id,
                unavailable.tracked_league.id,
            )
            if track_number is None:
                continue

            await self._send_split_message(
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
            self.repository.mark_unavailable_refresh_warning_sent(unavailable.tracked_league.id)

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

    def build_competition_url_message(
        self,
        chat_id: int,
        track_number: int,
    ) -> CommandResult:
        """Build the user-facing message with the current competition URL."""

        tracked_subscription = self._get_track_by_number(chat_id, track_number)
        if tracked_subscription is None:
            return CommandResult(
                ok=False,
                message="No encontré ese número de liga en /list_tracks.",
            )

        extractor = self.extractor_registry.get_for_platform(
            tracked_subscription.tracked_league.platform
        )
        competition_url = extractor.build_competition_url(
            competition_external_id=tracked_subscription.tracked_league.competition_external_id,
            source_url=tracked_subscription.tracked_league.source_url,
            metadata=_loads_optional_json(tracked_subscription.tracked_league.metadata_json),
        )

        if not competition_url:
            return CommandResult(
                ok=False,
                message="⚠️ Esta plataforma no soporta links directos a competiciones.",
            )

        return CommandResult(
            ok=True,
            message=build_competition_url_message(
                tracked_subscription.tracked_league,
                competition_url,
            ),
        )

    def build_event_url_message(
        self,
        tracked_subscription: TrackedCompetitionSubscription,
        matches: Sequence[ActiveEventRecord],
        event_number: int,
    ) -> CommandResult:
        """Build the user-facing message with one direct event URL."""

        if event_number <= 0 or event_number > len(matches):
            return CommandResult(
                ok=False,
                message="Elegí un número válido de partido de la última lista mostrada.",
            )

        match = matches[event_number - 1]
        extractor = self.extractor_registry.get_for_platform(
            tracked_subscription.tracked_league.platform
        )
        event_url = extractor.build_event_url(
            competition_external_id=tracked_subscription.tracked_league.competition_external_id,
            external_event_id=match.external_event_id,
            source_url=tracked_subscription.tracked_league.source_url,
            event_url=match.event_url,
            competition_metadata=_loads_optional_json(tracked_subscription.tracked_league.metadata_json),
            event_metadata=_loads_optional_json(match.raw_payload_json),
        )

        if not event_url:
            return CommandResult(
                ok=False,
                message="⚠️ Esta plataforma no soporta links directos a eventos.",
            )

        return CommandResult(
            ok=True,
            message=build_event_url_message(match, event_url),
        )

    def build_event_stats_message(
        self,
        tracked_subscription: TrackedCompetitionSubscription,
        matches: Sequence[ActiveEventRecord],
        event_number: int,
    ) -> CommandResult:
        """Build the user-facing message with one direct Bet365Stats / Sportradar URL."""

        del tracked_subscription

        if event_number <= 0 or event_number > len(matches):
            return CommandResult(
                ok=False,
                message="Elegí un número válido de partido de la última lista mostrada.",
            )

        match = matches[event_number - 1]

        if not match.stats_url:
            return CommandResult(
                ok=False,
                message="No encontré URL de stats para ese evento.",
            )

        return CommandResult(
            ok=True,
            message=build_event_stats_message(match, match.stats_url),
        )

    def build_refresh_summary_message(self, summary: RefreshSummary) -> CommandResult:
        """Build the user-facing summary for `/refresh_tracks` or monitor logs."""

        if summary.tracks_requested == 0:
            return CommandResult(
                ok=True,
                message=(
                    "No tenés ligas trackeadas todavía.\n"
                    "Usá /track_url <url_de_plataforma> y después /confirm_track."
                    f"\n\n⏱️ Tiempo total: {format_duration(summary.elapsed_seconds)}"
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
                f"Ligas con problemas ({len(summary.failed_leagues)}): {', '.join(summary.failed_leagues)}"
            )
        if summary.degraded_leagues:
            lines.append(
                f"Ligas degradadas ({len(summary.degraded_leagues)}): {', '.join(summary.degraded_leagues)}"
            )
        lines.append(f"⏱️ Tiempo total: {format_duration(summary.elapsed_seconds)}")

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
            "",
            "📈 Notificaciones de cambios de cuotas: "
            f"{'activadas' if subscription.notify_odds_changes else 'desactivadas'}",
            f"🎯 {'Threshold por defecto' if confirmed_request.subscription_created else 'Threshold configurado'}: "
            f"{subscription.change_percent_threshold:.1f}%",
        ]

        if bootstrap_count is not None:
            lines.append(f"Estado inicial guardado: {bootstrap_count} partidos activos.")

        if bootstrap_error is not None:
            lines.append(
                "No pude guardar el estado inicial ahora mismo. "
                "El monitor lo volverá a intentar automáticamente."
            )

        lines.extend(self._build_known_league_lines(tracked_league))

        return "\n".join(lines)

    def _build_known_league_lines(self, tracked_league) -> list[str]:
        """Registry card: what the bot already knows about this unified league.

        When the league exists in the registry with other platforms or stats
        links, the new subscriber inherits everything automatically — tell them.
        """

        unified_id = getattr(tracked_league, "unified_competition_id", None)
        if unified_id is None:
            return []
        try:
            siblings = self.repository.list_tracked_competitions_for_unified(unified_id)
            stats_links = self.repository.list_stats_league_links(tracked_league.id)
        except Exception:
            return []
        others = [s for s in siblings if s.id != tracked_league.id]
        if not others and not stats_links:
            return []
        lines = ["", "✨ Liga conocida en el registro — heredás automáticamente:"]
        for sibling in others:
            lines.append(f"  🏦 {sibling.platform}: {sibling.league_name}")
        for link in stats_links:
            lines.append(f"  📊 {link.stats_provider}: {link.stats_league_name}")
        return lines

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
            "",
            "📈 Notificaciones de cambios de cuotas: "
            f"{'activadas' if subscription.notify_odds_changes else 'desactivadas'}",
            f"🎯 {'Threshold por defecto' if confirmed_request.subscription_created else 'Threshold configurado'}: "
            f"{subscription.change_percent_threshold:.1f}%",
            "",
            "La liga quedó guardada aunque todavía no tenga partidos activos.",
        ]

        if tracked_league.needs_name_resolution:
            lines.append(
                "Se usó un nombre provisorio y se reemplazará automáticamente cuando la plataforma muestre eventos reales."
            )

        lines.extend(self._build_known_league_lines(tracked_league))

        return "\n".join(lines)

    async def _refresh_leagues(self, tracked_league_ids: Sequence[int]) -> RefreshSummary:
        """Refresh a deduplicated set of tracked leagues under one shared lock."""

        started_at = time.monotonic()
        unique_ids = list(dict.fromkeys(tracked_league_ids))

        if not unique_ids:
            return RefreshSummary(
                tracks_requested=0,
                tracks_refreshed=0,
                active_matches=0,
                new_events=0,
                odds_changes=0,
                failed_leagues=[],
                degraded_leagues=[],
                league_results=[],
                unavailable_competitions=[],
                elapsed_seconds=time.monotonic() - started_at,
            )

        league_results: list[CompetitionRefreshResult] = []
        failed_leagues: list[str] = []
        degraded_leagues: list[str] = []
        unavailable_competitions: list[UnavailableCompetitionRefresh] = []

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
                    if isinstance(extraction_or_error, CompetitionUnavailableError):
                        failed_leagues.append(tracked_league.league_name)
                        unavailable_tracked_league = self.repository.record_unavailable_refresh(
                            tracked_league.id,
                            reason=str(extraction_or_error),
                        )
                        logger.warning(
                            "Competition refresh unavailable id=%s platform=%s name=%s reason=%s",
                            unavailable_tracked_league.id,
                            unavailable_tracked_league.platform,
                            unavailable_tracked_league.league_name,
                            extraction_or_error,
                        )
                        unavailable_competitions.append(
                            UnavailableCompetitionRefresh(
                                tracked_league=unavailable_tracked_league,
                                reason=str(extraction_or_error),
                            )
                        )
                        continue

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

                    if extraction_or_error.is_empty:
                        failed_leagues.append(tracked_league.league_name)
                        unavailable_tracked_league = self.repository.record_unavailable_refresh(
                            tracked_league.id,
                            reason=UNAVAILABLE_COMPETITION_MESSAGE,
                        )
                        logger.warning(
                            "Competition refresh unavailable id=%s platform=%s name=%s reason=%s",
                            unavailable_tracked_league.id,
                            unavailable_tracked_league.platform,
                            unavailable_tracked_league.league_name,
                            UNAVAILABLE_COMPETITION_MESSAGE,
                        )
                        unavailable_competitions.append(
                            UnavailableCompetitionRefresh(
                                tracked_league=unavailable_tracked_league,
                                reason=UNAVAILABLE_COMPETITION_MESSAGE,
                            )
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
                    if result.degraded:
                        degraded_leagues.append(result.tracked_league.league_name)
                        failed_leagues.append(result.tracked_league.league_name)

        return RefreshSummary(
            tracks_requested=len(tracked_leagues),
            tracks_refreshed=sum(1 for result in league_results if not result.degraded),
            active_matches=sum(len(result.active_matches) for result in league_results),
            new_events=sum(len(result.new_matches) for result in league_results),
            odds_changes=sum(len(result.odds_changes) for result in league_results),
            failed_leagues=failed_leagues,
            degraded_leagues=degraded_leagues,
            league_results=league_results,
            unavailable_competitions=unavailable_competitions,
            elapsed_seconds=time.monotonic() - started_at,
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

        future_matches = [
            _normalize_extracted_match_for_persistence(
                match,
                existing_by_fixture.get(match.external_event_id),
                extraction,
            )
            for match in extraction.events
            if not _is_past_match(match)
        ]
        current_event_ids = [match.external_event_id for match in future_matches]
        new_fixture_ids = {
            match.external_event_id
            for match in future_matches
            if match.external_event_id not in existing_by_fixture
        }
        changed_fixture_ids = {
            match.external_event_id
            for match in future_matches
            if match.external_event_id in existing_by_fixture
            and _has_market_payload_changed(
                existing_by_fixture[match.external_event_id],
                match,
            )
        }

        upsert_payload = [
            ActiveEventUpsert(
                external_event_id=match.external_event_id,
                home=match.home,
                away=match.away,
                scheduled_label_date=match.scheduled_label_date,
                scheduled_label_time=match.scheduled_label_time,
                scheduled_at=match.scheduled_at,
                odds_home=match.odds_1x2.home,
                odds_draw=match.odds_1x2.draw,
                odds_away=match.odds_1x2.away,
                event_url=match.source_url,
                markets_payload=_markets_payload_from_event(match),
                raw_payload=match.raw_payload,
            )
            for match in future_matches
        ]

        if upsert_payload:
            self.repository.upsert_active_events(tracked_league_id, upsert_payload)

        if _is_degraded_extraction(extraction):
            removed_missing_count = 0
        else:
            removed_missing_count = self.repository.remove_missing_events(
                tracked_league_id,
                current_event_ids,
                remove_after_cycles=self.remove_missing_after_cycles,
            )
        removed_past_count = self.repository.remove_past_events(tracked_league_id)
        active_matches = self.repository.get_active_events(tracked_league_id, only_future=True)
        active_by_fixture = {match.fixture_id: match for match in active_matches}

        new_matches = [
            active_by_fixture[fixture_id]
            for fixture_id in current_event_ids
            if fixture_id in new_fixture_ids and fixture_id in active_by_fixture
        ]
        odds_changes = [
            OddsChange(
                before=existing_by_fixture[fixture_id],
                after=active_by_fixture[fixture_id],
            )
            for fixture_id in current_event_ids
            if fixture_id in changed_fixture_ids and fixture_id in active_by_fixture
        ]
        # Reminders are opt-in (default OFF): only fire for matches whose league
        # has reminders enabled, or which were individually enabled.
        reminder_matches = select_due_reminders(active_matches)
        if reminder_matches and not self.repository.competition_reminders_enabled(tracked_league_id):
            enabled_ids = self.repository.event_reminder_enabled_ids(tracked_league_id)
            reminder_matches = [m for m in reminder_matches if m.fixture_id in enabled_ids]

        return CompetitionRefreshResult(
            tracked_league=tracked_league,
            active_matches=active_matches,
            new_matches=new_matches,
            odds_changes=odds_changes,
            reminder_matches=reminder_matches,
            removed_missing_count=removed_missing_count,
            removed_past_count=removed_past_count,
            degraded=_is_degraded_extraction(extraction),
            degraded_reason=_degraded_reason_from_extraction(extraction),
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

        future_matches = [match for match in extraction.events if not _is_past_match(match)]
        current_event_ids = [match.external_event_id for match in future_matches]
        upsert_payload = [
            ActiveEventUpsert(
                external_event_id=match.external_event_id,
                home=match.home,
                away=match.away,
                scheduled_label_date=match.scheduled_label_date,
                scheduled_label_time=match.scheduled_label_time,
                scheduled_at=match.scheduled_at,
                odds_home=match.odds_1x2.home,
                odds_draw=match.odds_1x2.draw,
                odds_away=match.odds_1x2.away,
                event_url=match.source_url,
                markets_payload=_markets_payload_from_event(match),
                raw_payload=match.raw_payload,
            )
            for match in future_matches
        ]

        if upsert_payload:
            self.repository.upsert_active_events(tracked_league_id, upsert_payload)

        self.repository.remove_missing_events(
            tracked_league_id,
            current_event_ids,
            remove_after_cycles=self.remove_missing_after_cycles,
        )
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

        extracted_name = extraction.competition_name.strip() if extraction.competition_name else ""

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

    def _initialize_subscription_state(
        self,
        chat_id: int,
        tracked_competition_id: int,
        active_events: Sequence[ActiveEventRecord],
    ) -> None:
        """Initialize per-chat baseline and seen-event state for current active events."""

        self.repository.initialize_event_baselines(
            chat_id,
            tracked_competition_id,
            active_events,
        )
        self.repository.mark_sent_alerts(
            chat_id,
            tracked_competition_id,
            [event.fixture_id for event in active_events],
            "new_event",
        )

    def _get_track_by_number(
        self,
        chat_id: int,
        track_number: int,
    ) -> TrackedCompetitionSubscription | None:
        """Resolve one tracked competition from the visible `/list_tracks` number."""

        if track_number <= 0:
            return None

        tracked_leagues = self.list_confirmed_tracks(chat_id)
        index = track_number - 1

        if index < 0 or index >= len(tracked_leagues):
            return None

        return tracked_leagues[index]

    def _get_track_number(
        self,
        chat_id: int,
        tracked_competition_id: int,
    ) -> int | None:
        """Return the visible `/list_tracks` number for one tracked competition."""

        tracked_leagues = self.list_confirmed_tracks(chat_id)

        for index, tracked_subscription in enumerate(tracked_leagues, start=1):
            if tracked_subscription.tracked_league.id == tracked_competition_id:
                return index

        return None

    async def _send_split_message(
        self,
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

    @property
    def current_refresh_trigger(self) -> str | None:
        return self._active_refresh_trigger

    async def try_start_refresh(self, trigger: str) -> bool:
        normalized_trigger = trigger.strip().lower()
        if not normalized_trigger:
            normalized_trigger = "unknown"

        async with self._refresh_slot_lock:
            if self._active_refresh_trigger is not None:
                return False
            self._active_refresh_trigger = normalized_trigger
            return True

    async def finish_refresh(self, trigger: str) -> None:
        normalized_trigger = trigger.strip().lower()
        if not normalized_trigger:
            normalized_trigger = "unknown"

        async with self._refresh_slot_lock:
            if self._active_refresh_trigger == normalized_trigger:
                self._active_refresh_trigger = None

    def _build_empty_refresh_summary(self) -> RefreshSummary:
        return RefreshSummary(
            tracks_requested=0,
            tracks_refreshed=0,
            active_matches=0,
            new_events=0,
            odds_changes=0,
            failed_leagues=[],
            degraded_leagues=[],
            league_results=[],
            unavailable_competitions=[],
            elapsed_seconds=0.0,
        )


def _is_past_match(match: EventSnapshot) -> bool:
    """Return whether a normalized event already kicked off in the past."""

    if match.scheduled_at is None:
        return False

    try:
        kickoff = datetime.fromisoformat(match.scheduled_at)
    except ValueError:
        return False

    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)

    return kickoff <= datetime.now(timezone.utc)


def _is_degraded_extraction(extraction: CompetitionExtraction) -> bool:
    return bool(extraction.metadata.get("degraded"))


def _degraded_reason_from_extraction(extraction: CompetitionExtraction) -> str | None:
    raw_reason = extraction.metadata.get("degraded_reason")
    return raw_reason.strip() if isinstance(raw_reason, str) and raw_reason.strip() else None


def _normalize_extracted_match_for_persistence(
    match: EventSnapshot,
    existing_match: ActiveEventRecord | None,
    extraction: CompetitionExtraction,
) -> EventSnapshot:
    if not _is_degraded_extraction(extraction):
        return match

    normalized_markets = _merge_existing_non_1x2_markets(
        existing_match,
        _markets_payload_from_event(match),
    )
    raw_payload = dict(match.raw_payload or {})
    raw_payload["degraded"] = True
    raw_payload["degraded_reason"] = _degraded_reason_from_extraction(extraction) or "legacy_fallback"
    raw_payload["markets_complete"] = False

    return replace(
        match,
        markets_payload=normalized_markets,
        raw_payload=raw_payload,
    )


def _merge_existing_non_1x2_markets(
    existing_match: ActiveEventRecord | None,
    current_payload: dict[str, object] | None,
) -> dict[str, object] | None:
    normalized_payload = json.loads(json.dumps(current_payload or {}))
    existing_payload = _loads_optional_json(existing_match.markets_json) if existing_match else None

    if not isinstance(existing_payload, dict):
        return normalized_payload or None

    for market_key in ("asian_handicap", "goal_line", "alternative_markets"):
        if market_key in normalized_payload:
            continue
        if market_key in existing_payload:
            normalized_payload[market_key] = existing_payload[market_key]

    return normalized_payload or None


def _markets_payload_from_event(match: EventSnapshot) -> dict[str, object] | None:
    """Build the current normalized market payload stored with one active event."""

    if match.markets_payload:
        return _merge_1x2_into_markets_payload(
            match.markets_payload,
            home=match.odds_1x2.home,
            draw=match.odds_1x2.draw,
            away=match.odds_1x2.away,
        )

    if (
        match.odds_1x2.home is None
        and match.odds_1x2.draw is None
        and match.odds_1x2.away is None
    ):
        return None

    return {
        "1x2": {
            "home": match.odds_1x2.home,
            "draw": match.odds_1x2.draw,
            "away": match.odds_1x2.away,
        }
    }


def _has_market_payload_changed(
    stored_match: ActiveEventRecord,
    extracted_match: EventSnapshot,
) -> bool:
    """Return whether any normalized market payload changed for one event."""

    return _normalized_market_payload_from_record(stored_match) != _normalized_market_payload_from_match(
        extracted_match
    )


def _normalized_market_payload_from_match(match: EventSnapshot) -> dict[str, object] | None:
    return _merge_1x2_into_markets_payload(
        _markets_payload_from_event(match),
        home=match.odds_1x2.home,
        draw=match.odds_1x2.draw,
        away=match.odds_1x2.away,
    )


def _normalized_market_payload_from_record(match: ActiveEventRecord) -> dict[str, object] | None:
    return _merge_1x2_into_markets_payload(
        _loads_optional_json(match.markets_json),
        home=match.odds_home,
        draw=match.odds_draw,
        away=match.odds_away,
    )


def _merge_1x2_into_markets_payload(
    payload: dict[str, object] | None,
    *,
    home: float | None,
    draw: float | None,
    away: float | None,
) -> dict[str, object] | None:
    normalized_payload = json.loads(json.dumps(payload or {}))

    if home is None and draw is None and away is None:
        return normalized_payload or None

    normalized_payload["1x2"] = {
        "home": home,
        "draw": draw,
        "away": away,
    }
    return normalized_payload


def _loads_optional_json(value: str | None) -> dict[str, object] | None:
    """Decode one optional JSON payload for generic extractor helpers."""

    normalized_value = (value or "").strip()
    if not normalized_value:
        return None

    try:
        payload = json.loads(normalized_value)
    except json.JSONDecodeError:
        return None

    return payload if isinstance(payload, dict) else None


def _batched(items: Sequence[TrackedCompetition], batch_size: int) -> list[list[TrackedCompetition]]:
    """Split a sequence of tracked leagues into small ordered batches."""

    return [list(items[index:index + batch_size]) for index in range(0, len(items), batch_size)]


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""

    return datetime.now(timezone.utc).isoformat()


tracking_service = TrackingService()


__all__ = [
    "CommandResult",
    "CompetitionRefreshResult",
    "OddsChange",
    "RefreshSummary",
    "SubscriptionOddsAlert",
    "TrackingService",
    "tracking_service",
]

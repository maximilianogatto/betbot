"""Application service for external match statistics.

This layer is intentionally separate from `TrackingService`. Tracking owns odds
collection and active events; this service links those events to a stats provider
and returns compact user-facing reports.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from core.stats_models import (
    MatchIdentityCandidate,
    MatchStatsReport,
    StatsLeagueOption,
    StatsProviderDescriptor,
)
from core.stats_provider_base import StatsProviderRegistry, stats_provider_registry
from monitors.models import CommandResult
from storage.tracking_repository import (
    ActiveEventRecord,
    SqliteTrackingRepository,
    TrackedCompetitionSubscription,
    tracking_repository as default_tracking_repository,
)

logger = logging.getLogger(__name__)


class StatsService:
    """Coordinate stats provider discovery, linking and report generation."""

    def __init__(
        self,
        *,
        provider_registry: StatsProviderRegistry | None = None,
        repository: SqliteTrackingRepository | None = None,
    ) -> None:
        self.provider_registry = provider_registry or stats_provider_registry
        self.repository = repository or default_tracking_repository

    def list_providers(self) -> list[StatsProviderDescriptor]:
        """Return providers that support stats league discovery."""

        return [
            provider
            for provider in self.provider_registry.list_providers()
            if provider.implemented and provider.capabilities.supports_league_discovery
        ]

    async def search_leagues(
        self,
        *,
        provider_key: str,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[StatsLeagueOption]:
        """Search provider-native leagues that can be linked to an odds track."""

        provider = self.provider_registry.get(provider_key)
        return await provider.search_leagues(country_name=country_name, query=query, limit=limit)

    def link_league(
        self,
        *,
        tracked_competition_id: int,
        option: StatsLeagueOption,
        confidence: float = 1.0,
    ) -> CommandResult:
        """Persist one odds tracked competition -> stats league mapping."""

        self.repository.upsert_stats_league_link(
            tracked_competition_id,
            stats_provider=option.provider,
            stats_league_id=option.league_id,
            stats_league_name=option.league_name,
            stats_country_name=option.country_name,
            confidence=confidence,
            payload=_league_option_payload(option),
        )
        return CommandResult(
            ok=True,
            message=(
                "✅ Liga de stats vinculada.\n"
                f"Provider: {option.provider_display_name}\n"
                f"Liga stats: {option.league_name}\n"
                f"ID stats: {option.league_id}"
            ),
        )

    async def build_match_stats_report(
        self,
        *,
        tracked_subscription: TrackedCompetitionSubscription,
        matches: Sequence[ActiveEventRecord],
        event_number: int,
    ) -> CommandResult:
        """Resolve a listed odds event to stats and return a compact report."""

        if event_number <= 0 or event_number > len(matches):
            return CommandResult(ok=False, message="Elegí un número válido de partido de la última lista mostrada.")

        match = matches[event_number - 1]
        direct_provider_key = _provider_key_from_stats_url(match.stats_url)
        stored_link = self.repository.get_stats_match_link(match.id)
        league_link = self.repository.get_stats_league_link(tracked_subscription.tracked_league.id)

        provider_key = direct_provider_key or (stored_link.stats_provider if stored_link else None)
        if provider_key is None and league_link is not None:
            provider_key = league_link.stats_provider
        if provider_key is None:
            return CommandResult(
                ok=False,
                message=(
                    "No encontré stats para ese evento.\n"
                    "Si la plataforma no trae URL de stats directa, primero vinculá la liga con /link_stats."
                ),
            )

        try:
            provider = self.provider_registry.get(provider_key)
        except ValueError:
            return CommandResult(ok=False, message=f"El provider de stats `{provider_key}` no está registrado.")

        if stored_link is not None and stored_link.stats_provider == provider_key:
            stats_match_id = stored_link.stats_match_id
            confidence = stored_link.confidence
            method = stored_link.method
        else:
            candidate = MatchIdentityCandidate(
                home=match.home,
                away=match.away,
                scheduled_at=match.scheduled_at,
                league_name=tracked_subscription.tracked_league.competition_name,
                stats_url=match.stats_url,
                platform=match.platform,
                external_event_id=match.external_event_id,
            )
            resolved = await provider.resolve_match(
                candidate,
                league_id=league_link.stats_league_id if league_link is not None else None,
            )
            if resolved is None:
                return CommandResult(
                    ok=False,
                    message=(
                        "No pude vincular ese partido con el provider de stats.\n"
                        "Probá primero vincular la liga correcta con /link_stats."
                    ),
                )
            self.repository.upsert_stats_match_link(
                match.id,
                stats_provider=resolved.provider,
                stats_match_id=resolved.stats_match_id,
                stats_url=resolved.stats_url,
                confidence=resolved.confidence,
                method=resolved.method,
                payload=resolved.raw_payload,
            )
            stats_match_id = resolved.stats_match_id
            confidence = resolved.confidence
            method = resolved.method

        try:
            report = await provider.build_match_report(stats_match_id)
        except Exception as exc:  # defensive Telegram boundary
            logger.exception("Stats report failed provider=%s match_id=%s", provider_key, stats_match_id)
            return CommandResult(
                ok=False,
                message=f"No pude generar el reporte de stats en este momento: {exc}",
            )

        return CommandResult(
            ok=True,
            message=_render_report_message(match=match, report=report, confidence=confidence, method=method),
        )


def _provider_key_from_stats_url(stats_url: str | None) -> str | None:
    normalized = (stats_url or "").lower()
    if "sportradar.com" in normalized or "sir.sportradar.com" in normalized:
        return "sportradar_statshub"
    return None


def _render_report_message(
    *,
    match: ActiveEventRecord,
    report: MatchStatsReport,
    confidence: float,
    method: str,
) -> str:
    header = (
        f"📊 Stats: {match.home} vs {match.away}\n"
        f"Provider: {report.provider}\n"
        f"Match ID stats: {report.match_id}\n"
        f"Link confidence: {confidence:.2f} ({method})"
    )
    return f"{header}\n\n{report.markdown.strip()}"


def _league_option_payload(option: StatsLeagueOption) -> dict[str, Any]:
    return {
        "provider": option.provider,
        "provider_display_name": option.provider_display_name,
        "country_name": option.country_name,
        "league_id": option.league_id,
        "league_name": option.league_name,
        "season_id": option.season_id,
        "source_url": option.source_url,
        "raw_payload": option.raw_payload,
    }


__all__ = ["StatsService"]

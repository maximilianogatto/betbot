"""Application service for external match statistics.

This layer is intentionally separate from `TrackingService`. Tracking owns odds
collection and active events; this service links those events to a stats provider
and returns compact user-facing reports.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from core.stats_models import (
    MatchIdentityCandidate,
    MatchStatsReport,
    StatsLeagueOption,
    StatsMatchLink,
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


@dataclass(frozen=True)
class StatsMatchCandidate:
    """One ranked stats fixture offered for manual disambiguation."""

    label: str
    link: StatsMatchLink


@dataclass(frozen=True)
class StatsResolution:
    """Outcome of resolving one odds event to a stats match.

    `kind` is one of:
    - "report": `result` holds a ready CommandResult report.
    - "choose": `candidates` must be shown for manual selection; `event_index`
      and `provider_key` are carried so the chosen link can be persisted later.
    - "error": `result` holds the user-facing error CommandResult.
    """

    kind: str
    result: CommandResult | None = None
    candidates: tuple[StatsMatchCandidate, ...] = ()
    event_index: int = 0
    provider_key: str | None = None


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

    async def ensure_provider_sessions_fresh(self, *, min_ttl_seconds: float = 3600.0) -> None:
        """Proactively refresh provider sessions/tokens nearing expiry.

        Run from a background job so any browser-based token bootstrap happens off
        the user-facing request path instead of during a `/stats` call.
        """

        for provider in self.provider_registry.list_registered():
            ensure = getattr(provider, "ensure_session_fresh", None)
            if not callable(ensure):
                continue
            try:
                refreshed = await ensure(min_ttl_seconds=min_ttl_seconds)
                if refreshed:
                    logger.info("Stats provider session refreshed provider=%s", provider.name)
            except Exception:
                logger.exception("Stats provider session refresh failed provider=%s", getattr(provider, "name", "?"))

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

    async def search_and_rank_leagues(
        self,
        *,
        provider_key: str,
        country_name: str,
        odds_league_name: str | None,
        sample_events: Sequence[MatchIdentityCandidate] = (),
        query: str | None = None,
        limit: int = 80,
        validate_top: int = 6,
    ) -> list[StatsLeagueOption]:
        """Search stats leagues and order them by relevance to the odds league.

        First options are ordered by name similarity to the odds competition. Then
        the top `validate_top` candidates are validated by checking how many of the
        tracked events actually exist as fixtures, so a same-named-but-wrong league
        (a common Statshub duplicate) sinks below the one holding the real teams.
        """

        provider = self.provider_registry.get(provider_key)
        options = await provider.search_leagues(country_name=country_name, query=query, limit=limit)
        if not options:
            return options

        if odds_league_name:
            options = sorted(
                options,
                key=lambda option: _league_name_similarity(odds_league_name, option.league_name),
                reverse=True,
            )

        if sample_events and hasattr(provider, "count_matching_events"):
            sample = list(sample_events)
            validation: dict[str, int] = {}
            for option in options[:validate_top]:
                try:
                    validation[option.league_id] = await provider.count_matching_events(option.league_id, sample)
                except Exception:  # defensive: a bad candidate must not break discovery
                    logger.exception("League validation failed league_id=%s", option.league_id)
                    validation[option.league_id] = 0
            # Stable sort keeps the name-similarity order within equal match counts.
            options = sorted(options, key=lambda option: validation.get(option.league_id, 0), reverse=True)

        return options

    async def describe_league(self, *, provider_key: str, league_id: str) -> StatsLeagueOption | None:
        """Resolve a provider-native league id (e.g. from a pasted URL) to an option."""

        provider = self.provider_registry.get(provider_key)
        describe = getattr(provider, "describe_league", None)
        if not callable(describe):
            return None
        return await describe(league_id)

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

    def build_links_message(
        self,
        tracked_subscriptions: Sequence[TrackedCompetitionSubscription],
    ) -> CommandResult:
        """Render stored stats links for the given tracked odds competitions."""

        if not tracked_subscriptions:
            return CommandResult(
                ok=True,
                message=(
                    "No tenés ligas trackeadas todavía.\n"
                    "Primero usá /track_league o /track_url."
                ),
            )

        lines = ["Vínculos de stats:"]
        for index, subscription in enumerate(tracked_subscriptions, start=1):
            tracked = subscription.tracked_league
            link = self.repository.get_stats_league_link(tracked.id)
            lines.append(f"{index} - [{tracked.platform}] {tracked.competition_name}")
            if link is None:
                lines.append("    Stats: sin vincular")
                continue
            provider_name = _provider_display_name(self.provider_registry, link.stats_provider)
            country = f" | {link.stats_country_name}" if link.stats_country_name else ""
            lines.append(
                "    "
                f"Stats: {provider_name}{country} | {link.stats_league_name} "
                f"| id={link.stats_league_id} | confidence={link.confidence:.2f}"
            )

        lines.append("")
        lines.append("Para corregir un vínculo, corré /link_stats de nuevo sobre esa liga.")
        return CommandResult(ok=True, message="\n".join(lines))

    async def build_match_stats_report(
        self,
        *,
        tracked_subscription: TrackedCompetitionSubscription,
        matches: Sequence[ActiveEventRecord],
        event_number: int,
    ) -> CommandResult:
        """Resolve a listed odds event to stats and return a compact report.

        Non-interactive entry point (`/stats <n>`). When the match cannot be
        auto-resolved but plausible candidates exist, it asks the user to run the
        interactive `/stats` flow, which can show a selectable list.
        """

        resolution = await self.resolve_event(
            tracked_subscription=tracked_subscription,
            matches=matches,
            event_number=event_number,
        )
        if resolution.kind == "choose":
            return CommandResult(
                ok=False,
                message=(
                    "Encontré varios partidos de stats posibles para ese evento.\n"
                    "Corré /stats (sin número) y elegí de la lista para confirmar el vínculo."
                ),
            )
        return resolution.result or CommandResult(ok=False, message="No pude generar el reporte de stats.")

    async def resolve_event(
        self,
        *,
        tracked_subscription: TrackedCompetitionSubscription,
        matches: Sequence[ActiveEventRecord],
        event_number: int,
    ) -> StatsResolution:
        """Resolve one listed odds event to a stats match.

        Returns a `StatsResolution` describing whether a report is ready, a manual
        choice is needed, or resolution failed.
        """

        if event_number <= 0 or event_number > len(matches):
            return StatsResolution(
                kind="error",
                result=CommandResult(ok=False, message="Elegí un número válido de partido de la última lista mostrada."),
            )

        match = matches[event_number - 1]
        direct_provider_key = _provider_key_from_stats_url(match.stats_url)
        stored_link = self.repository.get_stats_match_link(match.id)
        league_link = self.repository.get_stats_league_link(tracked_subscription.tracked_league.id)

        provider_key = direct_provider_key or (stored_link.stats_provider if stored_link else None)
        if provider_key is None and league_link is not None:
            provider_key = league_link.stats_provider
        if provider_key is None:
            return StatsResolution(
                kind="error",
                result=CommandResult(
                    ok=False,
                    message=(
                        "No encontré stats para ese evento.\n"
                        "Si la plataforma no trae URL de stats directa, primero vinculá la liga con /link_stats."
                    ),
                ),
            )

        try:
            provider = self.provider_registry.get(provider_key)
        except ValueError:
            return StatsResolution(
                kind="error",
                result=CommandResult(ok=False, message=f"El provider de stats `{provider_key}` no está registrado."),
            )

        # 1) A confirmed link for this exact event always wins.
        if stored_link is not None and stored_link.stats_provider == provider_key:
            return StatsResolution(
                kind="report",
                result=await self._render_report(
                    provider_key=provider_key,
                    provider=provider,
                    match=match,
                    stats_match_id=stored_link.stats_match_id,
                    confidence=stored_link.confidence,
                    method=stored_link.method,
                ),
            )

        candidate = MatchIdentityCandidate(
            home=match.home,
            away=match.away,
            scheduled_at=match.scheduled_at,
            league_name=tracked_subscription.tracked_league.competition_name,
            stats_url=match.stats_url,
            platform=match.platform,
            external_event_id=match.external_event_id,
        )
        league_id = league_link.stats_league_id if league_link is not None else None

        # 2) Confident, unambiguous auto-link: persist and report straight away.
        resolved = await provider.resolve_match(candidate, league_id=league_id)
        if resolved is not None:
            self._persist_match_link(match.id, resolved)
            return StatsResolution(
                kind="report",
                result=await self._render_report(
                    provider_key=provider_key,
                    provider=provider,
                    match=match,
                    stats_match_id=resolved.stats_match_id,
                    confidence=resolved.confidence,
                    method=resolved.method,
                ),
            )

        # 3) Ambiguous or low confidence: offer ranked candidates if any exist.
        ranked: list[StatsMatchLink] = []
        if league_id is not None and hasattr(provider, "rank_match_candidates"):
            ranked = await provider.rank_match_candidates(candidate, league_id=league_id)
        if ranked:
            return StatsResolution(
                kind="choose",
                candidates=tuple(
                    StatsMatchCandidate(label=_candidate_label(link), link=link) for link in ranked
                ),
                event_index=event_number - 1,
                provider_key=provider_key,
            )

        current_link = ""
        if league_link is not None:
            provider_name = _provider_display_name(self.provider_registry, league_link.stats_provider)
            current_link = (
                "\n\n"
                f"Vínculo actual: {provider_name} | "
                f"{league_link.stats_league_name} | id={league_link.stats_league_id}"
            )
        return StatsResolution(
            kind="error",
            result=CommandResult(
                ok=False,
                message=(
                    "No pude vincular ese partido con el provider de stats.\n"
                    "Probá primero vincular la liga correcta con /link_stats."
                    f"{current_link}"
                ),
            ),
        )

    async def build_report_for_chosen_candidate(
        self,
        *,
        match: ActiveEventRecord,
        provider_key: str,
        link: StatsMatchLink,
    ) -> CommandResult:
        """Persist a manually chosen stats candidate and render its report."""

        try:
            provider = self.provider_registry.get(provider_key)
        except ValueError:
            return CommandResult(ok=False, message=f"El provider de stats `{provider_key}` no está registrado.")
        self._persist_match_link(match.id, link)
        return await self._render_report(
            provider_key=provider_key,
            provider=provider,
            match=match,
            stats_match_id=link.stats_match_id,
            confidence=link.confidence,
            method="manual_selection",
        )

    def _persist_match_link(self, active_event_id: int, link: StatsMatchLink) -> None:
        self.repository.upsert_stats_match_link(
            active_event_id,
            stats_provider=link.provider,
            stats_match_id=link.stats_match_id,
            stats_url=link.stats_url,
            confidence=link.confidence,
            method=link.method,
            payload=link.raw_payload,
        )

    async def _render_report(
        self,
        *,
        provider_key: str,
        provider: Any,
        match: ActiveEventRecord,
        stats_match_id: str,
        confidence: float,
        method: str,
    ) -> CommandResult:
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


def _league_name_similarity(left: str, right: str) -> float:
    """Loose similarity between two league names, ignoring case and punctuation."""

    import re
    from difflib import SequenceMatcher

    def norm(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    left_norm = norm(left)
    right_norm = norm(right)
    ratio = SequenceMatcher(a=left_norm, b=right_norm).ratio()
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    if not left_tokens or not right_tokens:
        return ratio
    overlap = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
    return max(ratio, overlap)


def _candidate_label(link: StatsMatchLink) -> str:
    """Build a short human label for one ranked stats candidate."""

    payload = link.raw_payload or {}
    home = payload.get("stats_home") or "?"
    away = payload.get("stats_away") or "?"
    scheduled = payload.get("stats_scheduled_at") or ""
    when = ""
    if isinstance(scheduled, str) and len(scheduled) >= 16:
        when = f" | {scheduled[8:10]}/{scheduled[5:7]} {scheduled[11:16]}"
    return f"{home} vs {away}{when} (match {link.confidence:.2f})"


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
    divider = "━━━━━━━━━━━━━━━━━━━━"
    header = (
        f"📊 STATS — {match.home} vs {match.away}\n"
        f"{divider}\n"
        f"🔗 {report.provider}  ·  match {report.match_id}\n"
        f"🎯 confianza {confidence:.0%} ({method})\n"
        f"{divider}"
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


def _provider_display_name(registry: StatsProviderRegistry, provider_key: str) -> str:
    try:
        return registry.get(provider_key).display_name
    except ValueError:
        return provider_key


__all__ = ["StatsService"]

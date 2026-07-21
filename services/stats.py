"""Application service for external match statistics.

This layer is intentionally separate from `TrackingService`. Tracking owns odds
collection and active events; this service links those events to a stats provider
and returns compact user-facing reports.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from types import SimpleNamespace
from typing import Any

from core.stats_models import (
    MatchIdentityCandidate,
    MatchStatsReport,
    StatsLeagueOption,
    StatsMatchLink,
    StatsProviderDescriptor,
)
from core.stats_provider_base import StatsProviderRegistry, stats_provider_registry
from core.league_naming import league_name_similarity
from services.models import CommandResult
from adapters.storage import SqliteStorage, get_storage
from core.models import (
    ActiveEventRecord,
    StatsLeagueSubscription,
    TrackedCompetitionSubscription,
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


@dataclass(frozen=True)
class ExplorableStatsLeague:
    """One provider-native league available in `/explore_stats`."""

    provider_key: str
    league_id: str
    league_name: str
    country_name: str | None
    label: str
    source_url: str | None = None


class StatsService:
    """Coordinate stats provider discovery, linking and report generation."""

    def __init__(
        self,
        *,
        provider_registry: StatsProviderRegistry | None = None,
        repository: SqliteStorage | None = None,
    ) -> None:
        self.provider_registry = provider_registry or stats_provider_registry
        self.repository = repository or get_storage()

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
                key=lambda option: league_name_similarity(odds_league_name, option.league_name),
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

    async def get_league_overview(self, *, provider_key: str, league_id: str) -> dict[str, Any] | None:
        """Return a cached league overview (standings/fixtures/scorers/teams)."""

        provider = self.provider_registry.get(provider_key)
        getter = getattr(provider, "get_league_overview", None)
        if not callable(getter):
            return None
        return await getter(league_id)

    async def list_fixtures(
        self,
        *,
        provider_key: str,
        league_id: str,
        limit: int | None = 30,
    ):
        """List provider-native fixtures without requiring an odds league link."""

        provider = self.provider_registry.get(provider_key)
        return await provider.list_fixtures(league_id, limit=limit)

    async def warm_tracked_leagues(self, *, ttl_seconds: float = 90000.0) -> dict[str, int]:
        """Prefetch and cache stats for every stats-linked tracked league (daily job).

        For each linked league: caches the league overview, then resolves and
        prewarms the match report for each active/upcoming odds event with a long
        TTL. So `/stats` and `/explore_stats` serve from the DB and the provider is
        only hit once per day (anti-ban). Ambiguous matches are left for manual /stats.
        """

        summary = {"leagues": 0, "reports": 0, "skipped": 0, "errors": 0}
        warmed_leagues: set[tuple[str, str]] = set()
        try:
            competitions = self.repository.list_globally_active_competitions()
        except Exception:
            logger.exception("Prefetch could not list tracked competitions")
            return summary

        for tracked in competitions:
            links = self.repository.list_stats_league_links(tracked.id)
            if not links:
                continue
            for link in links:
                try:
                    provider = self.provider_registry.get(link.stats_provider)
                except ValueError:
                    continue
                league_key = (link.stats_provider, link.stats_league_id)
                if league_key not in warmed_leagues:
                    warmed_leagues.add(league_key)
                    summary["leagues"] += 1
                    getter = getattr(provider, "get_league_overview", None)
                    if callable(getter):
                        try:
                            await getter(link.stats_league_id, cache_ttl=ttl_seconds)
                        except TypeError:
                            await getter(link.stats_league_id)
                        except Exception:
                            logger.exception("Prefetch league overview failed competition=%s provider=%s", tracked.id, link.stats_provider)
                            summary["errors"] += 1

                try:
                    events = self.repository.get_active_events(tracked.id, only_future=True)
                except Exception:
                    logger.exception("Prefetch could not load active events competition=%s", tracked.id)
                    events = []
                for event in events:
                    try:
                        warmed = await self._warm_event_report(provider, link, tracked, event, ttl_seconds)
                        summary["reports" if warmed else "skipped"] += 1
                    except Exception:
                        logger.exception("Prefetch report failed event=%s provider=%s", getattr(event, "id", "?"), link.stats_provider)
                        summary["errors"] += 1

        list_standalone = getattr(self.repository, "list_globally_active_stats_leagues", None)
        standalone = list_standalone() if callable(list_standalone) else []
        for subscription in standalone:
            league_key = (subscription.stats_provider, subscription.stats_league_id)
            if league_key in warmed_leagues:
                continue
            try:
                provider = self.provider_registry.get(subscription.stats_provider)
            except ValueError:
                continue
            warmed_leagues.add(league_key)
            summary["leagues"] += 1
            getter = getattr(provider, "get_league_overview", None)
            if not callable(getter):
                summary["skipped"] += 1
                continue
            try:
                await getter(subscription.stats_league_id, cache_ttl=ttl_seconds)
            except TypeError:
                await getter(subscription.stats_league_id)
            except Exception:
                logger.exception(
                    "Prefetch standalone stats league failed provider=%s league=%s",
                    subscription.stats_provider,
                    subscription.stats_league_id,
                )
                summary["errors"] += 1
        return summary

    async def _warm_event_report(self, provider, link, tracked, event, ttl_seconds: float) -> bool:
        """Resolve one odds event to a stats match and prewarm its report. True if warmed."""

        stored = self.repository.get_stats_match_link(event.id, stats_provider=link.stats_provider)
        if stored is not None and stored.stats_provider == link.stats_provider:
            stats_match_id = stored.stats_match_id
        else:
            candidate = MatchIdentityCandidate(
                home=event.home,
                away=event.away,
                scheduled_at=event.scheduled_at,
                league_name=tracked.competition_name,
                stats_url=event.stats_url,
                platform=event.platform,
                external_event_id=event.external_event_id,
            )
            resolved = await provider.resolve_match(candidate, league_id=link.stats_league_id)
            if resolved is None:
                return False  # ambiguous / no confident match -> leave for manual /stats
            self._persist_match_link(event.id, resolved)
            stats_match_id = resolved.stats_match_id

        build = getattr(provider, "build_match_report", None)
        if not callable(build):
            return False
        try:
            await build(stats_match_id, cache_ttl=ttl_seconds)
        except TypeError:
            await build(stats_match_id)
        return True

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

    def track_stats_league(self, *, chat_id: int, option: StatsLeagueOption) -> CommandResult:
        """Persist one provider-native stats league independently from odds tracks."""

        self.repository.upsert_stats_league_subscription(
            chat_id,
            stats_provider=option.provider,
            stats_league_id=option.league_id,
            stats_league_name=option.league_name,
            stats_country_name=option.country_name,
            source_url=option.source_url,
            payload=_league_option_payload(option),
        )
        return CommandResult(
            ok=True,
            message=(
                "✅ Liga agregada al tracking de stats.\n"
                f"Provider: {option.provider_display_name}\n"
                f"Liga stats: {option.league_name}\n"
                f"ID stats: {option.league_id}\n\n"
                "El cache diario incluirá esta liga aunque no esté vinculada a cuotas."
            ),
        )

    def build_stats_tracks_message(self, *, chat_id: int) -> CommandResult:
        """Render standalone stats leagues followed by one chat."""

        subscriptions = self.repository.list_stats_league_subscriptions(chat_id)
        if not subscriptions:
            return CommandResult(
                ok=True,
                message="No tenés ligas seguidas solo para stats. Usá /track_stats para agregar una.",
            )
        lines = ["Ligas seguidas para stats:"]
        for index, subscription in enumerate(subscriptions, start=1):
            provider_name = _provider_display_name(self.provider_registry, subscription.stats_provider)
            country = f" | {subscription.stats_country_name}" if subscription.stats_country_name else ""
            lines.append(
                f"{index} - {provider_name}{country} | {subscription.stats_league_name} "
                f"| id={subscription.stats_league_id}"
            )
        lines.append("")
        lines.append("Estas ligas se precargan una vez por día aunque no estén vinculadas a cuotas.")
        return CommandResult(ok=True, message="\n".join(lines))

    def list_explorable_leagues(
        self,
        *,
        chat_id: int,
        tracked_subscriptions: Sequence[TrackedCompetitionSubscription],
    ) -> list[ExplorableStatsLeague]:
        """Combine odds-linked and standalone stats leagues without duplicates."""

        leagues: list[ExplorableStatsLeague] = []
        seen: set[tuple[str, str]] = set()
        for subscription in tracked_subscriptions:
            tracked = subscription.tracked_league
            links = self.repository.list_stats_league_links(tracked.id)
            for link in links:
                key = (link.stats_provider, link.stats_league_id)
                if key in seen:
                    continue
                seen.add(key)
                leagues.append(
                    ExplorableStatsLeague(
                        provider_key=link.stats_provider,
                        league_id=link.stats_league_id,
                        league_name=link.stats_league_name,
                        country_name=link.stats_country_name,
                        label=f"{tracked.competition_name} → {link.stats_league_name}",
                    )
                )
        for subscription in self.repository.list_stats_league_subscriptions(chat_id):
            key = (subscription.stats_provider, subscription.stats_league_id)
            if key in seen:
                continue
            seen.add(key)
            leagues.append(
                ExplorableStatsLeague(
                    provider_key=subscription.stats_provider,
                    league_id=subscription.stats_league_id,
                    league_name=subscription.stats_league_name,
                    country_name=subscription.stats_country_name,
                    source_url=subscription.source_url,
                    label=f"{subscription.stats_league_name} (solo stats)",
                )
            )
        return leagues

    async def build_direct_match_report(
        self,
        *,
        provider_key: str,
        stats_match_id: str,
    ) -> CommandResult:
        """Build a provider-native report without requiring a sportsbook event link."""

        try:
            provider = self.provider_registry.get(provider_key)
            report = await provider.build_match_report(stats_match_id)
        except Exception as exc:
            logger.exception("Direct stats report failed provider=%s match_id=%s", provider_key, stats_match_id)
            return CommandResult(ok=False, message=f"No pude generar el reporte de stats en este momento: {exc}")
        return CommandResult(ok=True, message=report.markdown)

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
            links = self.repository.list_stats_league_links(tracked.id)
            lines.append(f"{index} - [{tracked.platform}] {tracked.competition_name}")
            if not links:
                lines.append("    Stats: sin vincular")
                continue
            for link in links:
                provider_name = _provider_display_name(self.provider_registry, link.stats_provider)
                country = f" | {link.stats_country_name}" if link.stats_country_name else ""
                lines.append(
                    "    "
                    f"Stats: {provider_name}{country} | {link.stats_league_name} "
                    f"| id={link.stats_league_id} | confidence={link.confidence:.2f}"
                )

        lines.append("")
        lines.append("Para agregar o corregir un vínculo, corré /link_stats de nuevo sobre esa liga.")
        return CommandResult(ok=True, message="\n".join(lines))

    async def build_match_stats_report(
        self,
        *,
        tracked_subscription: TrackedCompetitionSubscription,
        matches: Sequence[ActiveEventRecord],
        event_number: int,
        provider_filter: str | None = None,
    ) -> CommandResult:
        """Resolve a listed odds event to stats and return a compact report.

        Non-interactive entry point (`/stats <n> [provider]`). Without a provider
        the report combines every linked provider; with one, only that provider is
        queried. When the match cannot be auto-resolved but plausible candidates
        exist, it asks the user to run the interactive `/stats` flow.
        """

        resolution = await self.resolve_event(
            tracked_subscription=tracked_subscription,
            matches=matches,
            event_number=event_number,
            provider_filter=provider_filter,
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
        provider_filter: str | None = None,
    ) -> StatsResolution:
        """Resolve one listed odds event to a stats match.

        Returns a `StatsResolution` describing whether a report is ready, a manual
        choice is needed, or resolution failed. ``provider_filter`` narrows the
        report to one provider (by key or display-name substring); without it the
        report combines every provider linked to the league.
        """

        if event_number <= 0 or event_number > len(matches):
            return StatsResolution(
                kind="error",
                result=CommandResult(ok=False, message="Elegí un número válido de partido de la última lista mostrada."),
            )

        match = matches[event_number - 1]

        # 1. Collect all providers we should query
        direct_provider_key = _provider_key_from_stats_url(match.stats_url)
        league_links = self.repository.list_stats_league_links(tracked_subscription.tracked_league.id)

        providers_to_query: list[tuple[str, str | None]] = []
        if direct_provider_key:
            providers_to_query.append((direct_provider_key, None))

        for link in league_links:
            if not any(p[0] == link.stats_provider for p in providers_to_query):
                providers_to_query.append((link.stats_provider, link.stats_league_id))

        if provider_filter:
            wanted = provider_filter.strip().lower()
            filtered = [
                entry for entry in providers_to_query
                if wanted in entry[0].lower()
                or wanted in _provider_display_name(self.provider_registry, entry[0]).lower()
            ]
            if not filtered and providers_to_query:
                available = ", ".join(
                    _provider_display_name(self.provider_registry, key)
                    for key, _ in providers_to_query
                )
                return StatsResolution(
                    kind="error",
                    result=CommandResult(
                        ok=False,
                        message=(
                            f"Esa liga no tiene el provider «{provider_filter}».\n"
                            f"Providers disponibles: {available}.\n"
                            "Sin provider, /stats <n> combina todos."
                        ),
                    ),
                )
            providers_to_query = filtered

        if not providers_to_query:
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

        candidate = MatchIdentityCandidate(
            home=match.home,
            away=match.away,
            scheduled_at=match.scheduled_at,
            league_name=tracked_subscription.tracked_league.competition_name,
            stats_url=match.stats_url,
            platform=match.platform,
            external_event_id=match.external_event_id,
        )

        successful_reports: list[str] = []
        ambiguous_candidates: list[tuple[str, list[StatsMatchLink]]] = []
        failed_providers: list[str] = []

        for provider_key, league_id in providers_to_query:
            try:
                provider = self.provider_registry.get(provider_key)
            except ValueError:
                failed_providers.append(provider_key)
                continue

            # a) A confirmed link for this exact event and provider always wins.
            stored_link = self.repository.get_stats_match_link(match.id, stats_provider=provider_key)
            if stored_link is not None:
                report_res = await self._render_report(
                    provider_key=provider_key,
                    provider=provider,
                    match=match,
                    stats_match_id=stored_link.stats_match_id,
                    confidence=stored_link.confidence,
                    method=stored_link.method,
                )
                if report_res.ok:
                    successful_reports.append(report_res.message)
                else:
                    failed_providers.append(provider_key)
                continue

            # b) Confident, unambiguous auto-link: persist and report.
            resolved = await provider.resolve_match(candidate, league_id=league_id)
            if resolved is not None:
                self._persist_match_link(match.id, resolved)
                report_res = await self._render_report(
                    provider_key=provider_key,
                    provider=provider,
                    match=match,
                    stats_match_id=resolved.stats_match_id,
                    confidence=resolved.confidence,
                    method=resolved.method,
                )
                if report_res.ok:
                    successful_reports.append(report_res.message)
                else:
                    failed_providers.append(provider_key)
                continue

            # c) Ambiguous or low confidence: check if candidates exist for disambiguation.
            ranked: list[StatsMatchLink] = []
            if league_id is not None and hasattr(provider, "rank_match_candidates"):
                ranked = await provider.rank_match_candidates(candidate, league_id=league_id)
            if ranked:
                ambiguous_candidates.append((provider_key, ranked))
            else:
                failed_providers.append(provider_key)

        # 2. Return the aggregated result
        if successful_reports:
            # Combine successful reports using a nice visual separator
            combined_message = "\n\n━━━━━━━━━━━━━━━━━━━━\n\n".join(successful_reports)
            
            # If any provider was ambiguous or failed, append a non-intrusive footnote
            footnotes = []
            for p_key, _ in ambiguous_candidates:
                p_name = _provider_display_name(self.provider_registry, p_key)
                footnotes.append(f"• *{p_name}*: No se pudo vincular automáticamente por ambigüedad. Usá `/stats` interactivo para confirmar.")
            for p_key in failed_providers:
                p_name = _provider_display_name(self.provider_registry, p_key)
                footnotes.append(f"• *{p_name}*: No se encontraron datos para este partido.")
                
            if footnotes:
                combined_message += "\n\n⚠️ *Proveedores adicionales:*\n" + "\n".join(footnotes)
                
            return StatsResolution(
                kind="report",
                result=CommandResult(ok=True, message=combined_message)
            )

        # If zero reports succeeded, check if we have ambiguous candidates to let the user choose
        if ambiguous_candidates:
            # Pick the first ambiguous provider to prompt the user
            provider_key, ranked = ambiguous_candidates[0]
            return StatsResolution(
                kind="choose",
                candidates=tuple(
                    StatsMatchCandidate(label=_candidate_label(link), link=link) for link in ranked
                ),
                event_index=event_number - 1,
                provider_key=provider_key,
            )

        # If everything failed completely
        current_links_str = ""
        if league_links:
            lines = ["\n\nVínculos actuales:"]
            for link in league_links:
                p_name = _provider_display_name(self.provider_registry, link.stats_provider)
                lines.append(f"• {p_name} | {link.stats_league_name} | id={link.stats_league_id}")
            current_links_str = "\n".join(lines)
            
        return StatsResolution(
            kind="error",
            result=CommandResult(
                ok=False,
                message=(
                    "No pude vincular ese partido con ningún provider de stats.\n"
                    "Probá primero vincular la liga correcta con /link_stats."
                    f"{current_links_str}"
                ),
            ),
        )

    async def resolve_unified_event(
        self,
        *,
        league_name: str,
        match_group: Sequence[ActiveEventRecord],
        provider_filter: str | None = None,
    ) -> tuple[StatsResolution, ActiveEventRecord]:
        """Resolve stats for a cross-book match group (the union of platforms).

        A group is the same physical match seen on several books. Stats links live
        at the unified-league level, so any platform of the league resolves the
        same providers; we pick a representative event (preferring one that carries
        a stats URL) and reuse the per-event resolver. Returns the resolution plus
        the representative event (so the caller can persist a manual choice).
        """

        representative = _pick_representative_event(match_group)
        # Duck-typed stand-in: resolve_event only reads .tracked_league.id (to fetch
        # the unified-level links) and .tracked_league.competition_name.
        shim = SimpleNamespace(
            tracked_league=SimpleNamespace(
                id=representative.tracked_competition_id,
                competition_name=league_name,
            )
        )
        resolution = await self.resolve_event(
            tracked_subscription=shim,  # type: ignore[arg-type]
            matches=[representative],
            event_number=1,
            provider_filter=provider_filter,
        )
        return resolution, representative

    async def build_unified_match_stats_report(
        self,
        *,
        league_name: str,
        match_group: Sequence[ActiveEventRecord],
        provider_filter: str | None = None,
    ) -> CommandResult:
        """Non-interactive stats report for a cross-book match group."""

        resolution, _ = await self.resolve_unified_event(
            league_name=league_name,
            match_group=match_group,
            provider_filter=provider_filter,
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





def _overview_header(overview: dict[str, Any]) -> str:
    name = overview.get("league_name") or "Liga"
    url = overview.get("source_url") or ""
    season = overview.get("season_id") or ""
    head = f"🏆 {name}" + (f" · temporada {season}" if season else "")
    return f"{head}\n🔗 {url}" if url else head


def render_league_table(overview: dict[str, Any], *, top_rows: int = 12) -> str:
    """Render standings (one block per division) compactly: pos team — PJ Pts Dif."""

    standings = overview.get("standings") or {}
    tables = standings.get("tables") if isinstance(standings, dict) else None
    lines = [_overview_header(overview), ""]
    if not tables:
        lines.append("Sin tabla de posiciones disponible.")
        return "\n".join(lines)
    for table in tables:
        lines.append(f"📊 {table.get('name') or 'Tabla'}")
        lines.append("  #  Equipo                PJ  Pts  Dif")
        for row in (table.get("rows") or [])[:top_rows]:
            team = row.get("team") or {}
            name = (team.get("name") or "?")[:20]
            lines.append(
                f"  {str(row.get('position','')).rjust(2)} {name.ljust(20)} "
                f"{str(row.get('played','')).rjust(2)} {str(row.get('points','')).rjust(3)} "
                f"{str(row.get('goal_difference','')).rjust(4)}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def render_league_fixtures(overview: dict[str, Any], *, limit: int = 15) -> str:
    """Render upcoming fixtures (future only) sorted by kickoff."""

    fixtures = overview.get("fixtures") or []
    now = datetime.now(UTC).isoformat()
    upcoming = []
    for fixture in fixtures:
        iso = (fixture.get("time") or {}).get("iso_utc")
        if iso and iso >= now:
            upcoming.append((iso, fixture))
    upcoming.sort(key=lambda item: item[0])
    lines = [_overview_header(overview), "", "🗓️ Próximos partidos"]
    if not upcoming:
        lines.append("No hay partidos futuros cargados.")
        return "\n".join(lines)
    for _, fixture in upcoming[:limit]:
        time_info = fixture.get("time") or {}
        when = f"{time_info.get('date','')} {time_info.get('time','')}".strip()
        home = (fixture.get("home") or {}).get("name") or "?"
        away = (fixture.get("away") or {}).get("name") or "?"
        lines.append(f"🕒 {when} — {home} vs {away}")
    return "\n".join(lines)


def render_top_scorers(overview: dict[str, Any], *, limit: int = 10) -> str:
    """Render top scorers, if the provider exposes them for this league."""

    scorers = overview.get("top_goals") or []
    lines = [_overview_header(overview), "", "👟 Goleadores"]
    if not scorers:
        lines.append("Sin datos de goleadores para esta liga.")
        return "\n".join(lines)
    for index, scorer in enumerate(scorers[:limit], start=1):
        player = scorer.get("player") if isinstance(scorer.get("player"), dict) else {}
        name = scorer.get("player_name") or player.get("name") or "?"
        goals = scorer.get("goals") or scorer.get("total") or scorer.get("value") or ""
        team = scorer.get("team_name") or (scorer.get("team") or {}).get("name") or ""
        team_suffix = f" ({team})" if team else ""
        lines.append(f"{index}. {name}{team_suffix} — {goals}")
    return "\n".join(lines)


def render_team_row(overview: dict[str, Any], query: str) -> str:
    """Find a team by fuzzy name across divisions and render its standings row."""

    standings = overview.get("standings") or {}
    tables = standings.get("tables") if isinstance(standings, dict) else None
    best = None  # (score, division_name, row)
    q = _normalize_team_query(query)
    for table in tables or []:
        for row in table.get("rows") or []:
            name = (row.get("team") or {}).get("name") or ""
            score = _team_match_score(q, _normalize_team_query(name))
            if best is None or score > best[0]:
                best = (score, table.get("name") or "", row)
    if best is None or best[0] < 0.34:
        return f"No encontré un equipo parecido a “{query}” en esta liga."
    _, division, row = best
    team = row.get("team") or {}
    home = row.get("home") or {}
    away = row.get("away") or {}
    lines = [
        _overview_header(overview),
        "",
        f"⚽ {team.get('name') or '?'}  ·  {division}",
        f"Posición: {row.get('position','?')}  ·  {row.get('points','?')} pts ({row.get('played','?')} PJ)",
        f"Récord: {row.get('wins','?')}G {row.get('draws','?')}E {row.get('losses','?')}P",
        f"Goles: {row.get('goals_for','?')} a favor · {row.get('goals_against','?')} en contra (dif {row.get('goal_difference','?')})",
        f"Local: {home.get('points','?')} pts ({home.get('goals_for','?')}-{home.get('goals_against','?')})"
        f"  ·  Visitante: {away.get('points','?')} pts ({away.get('goals_for','?')}-{away.get('goals_against','?')})",
    ]
    return "\n".join(lines)


def _normalize_team_query(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (value or "").lower()).strip()


def _team_match_score(query: str, name: str) -> float:
    if not query or not name:
        return 0.0
    if query in name or name in query:
        return 0.95
    return SequenceMatcher(a=query, b=name).ratio()


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


def _pick_representative_event(match_group: Sequence[ActiveEventRecord]) -> ActiveEventRecord:
    """Pick the event that best represents a cross-book group for stats resolution.

    Prefer one carrying a direct stats URL (it can resolve without a league link),
    then any with a stats URL fallback, else the first event.
    """

    if not match_group:
        raise ValueError("match_group vacío")
    for event in match_group:
        if getattr(event, "stats_url", None):
            return event
    return match_group[0]


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


stats_service = StatsService()

__all__ = ["StatsService", "stats_service"]

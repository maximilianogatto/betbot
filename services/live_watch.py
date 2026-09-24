"""Live-watch service: alert when a watched fixture goes in-play.

The user loads fixtures (home/away, optional league hint). This service polls
every live-capable extractor, fuzzy-matches in-play events against the active
watchlist, and fires a one-shot Telegram alert the first time a fixture appears
live (with the current minute/score) — the opening seconds are when the books
misprice. Matching is per-side: both home and away must clear a similarity floor.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
import json
import logging
import re
from types import SimpleNamespace
import unicodedata
from typing import Iterable, Any
from zoneinfo import ZoneInfo

from core.extractor_base import Extractor
from core.event_bus import event_bus
from core.events import MatchLiveEvent
# LiveWatchHit se re-exporta: nació acá y varios módulos lo importan de este
# nombre, pero ahora vive en core para que MatchLiveEvent pueda transportarlo.
from core.models import (  # noqa: F401
    LiveEventSnapshot,
    LiveWatchEntry,
    LiveWatchHit,
    LiveWatchSettings,
    LiveWatchTombstone,
    MatchResult,
)
from core.timezones import default_timezone
from services.timezones import resolve_chat_timezone
from core.registry import ExtractorRegistry, extractor_registry as global_extractor_registry
from core.league_naming import team_name_similarity, normalize_team_name
from core.match_identity import age_groups as _extract_u_groups, is_womens as _has_gender_indicator
from adapters.storage import SqliteStorage, get_storage

logger = logging.getLogger(__name__)

# Per-side similarity floor and combined floor for a confident auto-match.
SIDE_FLOOR = 0.62
COMBINED_FLOOR = 0.70
# A match is considered finished (and not worth adding/keeping) this long after
# kickoff: 90' + halftime + stoppage. Kept in sync with the 2h purge grace in
# SQLiteLiveWatchAdapter.purge_expired_live_watches.
_MATCH_OVER_GRACE = timedelta(hours=2)
# Cuánto tiempo un partido que salió de la vigilancia queda en la papelera
# bloqueando su re-importación desde la planilla. Dos días cubre el caso real:
# el partido se jugó, la fila sigue en el Excel, y el usuario la limpia recién
# días después.
TOMBSTONE_RETENTION_DAYS = 2.0
# Mismo piso que la deduplicación contra la watchlist activa.
_DUPLICATE_FLOOR = 0.85





def _same_fixture_in(home: str, away: str, candidates: Iterable[Any]) -> bool:
    """¿Alguno de `candidates` (watches o tombstones) es este mismo partido?

    Compara por nombre de equipo con el mismo piso que la deduplicación de la
    watchlist: los dos lados tienen que parecerse, así "River - Boca" no colisiona
    con "Boca - River".
    """

    for candidate in candidates:
        if (
            team_name_similarity(home, candidate.home) >= _DUPLICATE_FLOOR
            and team_name_similarity(away, candidate.away) >= _DUPLICATE_FLOOR
        ):
            return True
    return False


def _parse_iso_datetime(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(str(dt_str).strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def match_score(entry: Any, event: Any) -> float:
    """Per-side combined score for one watch entry vs one event (live or prematch/active_event)."""

    # 1. Kickoff time mismatch check (if both are present)
    entry_ko_str = getattr(entry, "kickoff_at", None)
    event_ko_str = getattr(event, "scheduled_at", None)
    
    if entry_ko_str and event_ko_str:
        entry_ko = _parse_iso_datetime(entry_ko_str)
        event_ko = _parse_iso_datetime(event_ko_str)
        if entry_ko and event_ko:
            diff_seconds = abs((entry_ko - event_ko).total_seconds())
            # Enforce max 3 hours (10800 seconds) difference
            if diff_seconds > 10800:
                return 0.0

    # 2. Category mismatch checks (Age Group, Gender)
    # Extract age groups and gender info from entry (league_hint and note)
    entry_hint = getattr(entry, "league_hint", None) or ""
    entry_note = getattr(entry, "note", None) or ""
    entry_home = getattr(entry, "home", "")
    entry_away = getattr(entry, "away", "")
    entry_text = f"{entry_hint} {entry_note} {entry_home} {entry_away}"
    entry_u_groups = _extract_u_groups(entry_text)
    entry_is_female = _has_gender_indicator(entry_text)

    # Extract age groups and gender info from event (competition_name, country_name, teams)
    event_comp = getattr(event, "competition_name", None) or getattr(event, "league_name", None) or ""
    event_country = getattr(event, "country_name", None) or ""
    event_home = getattr(event, "home", "")
    event_away = getattr(event, "away", "")
    
    event_home_str = event_home if isinstance(event_home, str) else getattr(event_home, "name", "")
    event_away_str = event_away if isinstance(event_away, str) else getattr(event_away, "name", "")

    event_text = f"{event_comp} {event_country} {event_home_str} {event_away_str}"
    event_u_groups = _extract_u_groups(event_text)
    event_is_female = _has_gender_indicator(event_text)

    # Check Age Group mismatch (e.g. entry has 'u20', but event has no U-groups or has 'u17')
    if entry_u_groups != event_u_groups:
        return 0.0

    # Check Gender mismatch (e.g. one is female, the other is not)
    if entry_is_female != event_is_female:
        return 0.0

    # 3. Team name similarity checks
    home = team_name_similarity(entry_home, event_home_str)
    away = team_name_similarity(entry_away, event_away_str)
    if home < SIDE_FLOOR or away < SIDE_FLOOR:
        return 0.0
    return (home + away) / 2.0


class LiveWatchService:
    """Polls live feeds and detects when watched fixtures go in-play."""

    def __init__(
        self,
        *,
        extractor_registry: ExtractorRegistry | None = None,
        repository: SqliteStorage | None = None,
        status_sources: Iterable[Any] = (),
    ) -> None:
        self.extractor_registry = extractor_registry or global_extractor_registry
        self.repository = repository or get_storage()
        # Fuentes del estado oficial del partido (federación, Statshub), en orden de
        # prioridad: la propia de la liga primero porque trae más información.
        # Cada una expone `name`, `day_for(datetime)` y `async matches_on(date)`.
        self.status_sources = list(status_sources)
        # Prematch changes slowly; cache it so the (fast) live poll doesn't re-pull
        # the whole-day lists every cycle (lighter for a VPS).
        self._prematch_cache: list[LiveEventSnapshot] | None = None
        self._prematch_cached_at = 0.0
        self._prematch_ttl_seconds = 120.0
        # Resultados archivados / entretiempos detectados desde la última vez que
        # alguien preguntó: el job liquida en el momento en vez de esperar su turno.
        self._settlement_triggers = 0

    def consume_settlement_trigger(self) -> bool:
        """True si desde la última consulta se archivó un resultado o hubo un entretiempo."""

        triggered, self._settlement_triggers = self._settlement_triggers > 0, 0
        return triggered

    # ----- watchlist management (used by the bot commands) -----

    def add_fixture_lines(
        self,
        chat_id: int,
        lines: Iterable[str],
        *,
        times_tz: ZoneInfo | None = None,
        skip_recently_removed: bool = False,
    ) -> list[LiveWatchEntry]:
        """Parse pasted fixture lines and add each as a watch entry.

        Accepted per line (one match per line):
          - "Home - Away"
          - "Home vs Away" / "Home vs. Away"
          - "League | Home - Away"  (the part before '|' becomes the league hint)

        ``times_tz`` is the wall-clock zone of any leading "HH:MM": pasted lines
        default to the chat's display timezone, while sheet imports must pass
        :func:`sheet_timezone` because the shared sheet is written in Argentina
        time regardless of where each chat lives. Kickoffs are stored in UTC.

        ``skip_recently_removed`` consulta la papelera además de la watchlist
        activa. Lo usa el auto-import de la planilla: una fila que ya se jugó
        sigue en el Excel, su entrada original ya fue purgada, y sin la papelera
        el import la volvía a cargar. Un pegado manual NO lo usa a propósito —
        si el usuario re-pega un partido a mano, lo quiere.
        """

        added: list[LiveWatchEntry] = []
        existing_watches = self.repository.list_live_watches(chat_id, status="watching")
        tombstones = (
            self.repository.list_live_watch_tombstones(chat_id)
            if skip_recently_removed
            else []
        )
        chat_tz = times_tz or resolve_chat_timezone(chat_id)

        for raw in lines:
            parsed = parse_fixture_line(raw, tz=chat_tz)
            if parsed is None:
                continue
            league_hint, home, away, kickoff_at = parsed

            # 1. Skip only matches that are already OVER (kickoff + full match
            # window). A match that kicked off recently is still worth watching
            # (it's in play). The grace matches purge_expired_live_watches so an
            # added entry isn't immediately purged.
            if kickoff_at:
                try:
                    ko = datetime.fromisoformat(kickoff_at)
                    if ko.tzinfo is None:
                        ko = ko.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    if ko < now - _MATCH_OVER_GRACE:
                        logger.info("Skipping watch entry because match %s already finished", kickoff_at)
                        continue
                except Exception:
                    pass

            # 2. Skip duplicates
            if _same_fixture_in(home, away, existing_watches):
                logger.info("Skipping watch entry %s vs %s because it is a duplicate", home, away)
                continue

            # 3. Skip lo que está en la papelera (ya se jugó o se borró hace poco)
            if _same_fixture_in(home, away, tombstones):
                logger.info(
                    "Skipping watch entry %s vs %s: está en la papelera del live-watch",
                    home,
                    away,
                )
                continue

            new_entry = self.repository.add_live_watch(
                chat_id,
                home=home,
                away=away,
                league_hint=league_hint,
                note=raw.strip(),
                kickoff_at=kickoff_at,
            )
            added.append(new_entry)
            existing_watches.append(new_entry)

        return added


    def watch_bet(self, chat_id: int, bet: Any) -> list[LiveWatchEntry]:
        """Vigila los partidos de una apuesta que el bot no pudo enlazar.

        Cuando el watch lo ve terminar archiva el resultado y el ledger lo enlaza
        y liquida. Hacen falta los dos equipos para armar la línea del fixture.
        """

        lines: list[str] = []
        for leg in getattr(bet, "legs", None) or []:
            if leg.external_event_id or not leg.home or not leg.away:
                continue
            line = f"{leg.home} - {leg.away}"
            if line not in lines:
                lines.append(line)
        return self.add_fixture_lines(chat_id, lines) if lines else []

    def list_watches(self, chat_id: int, *, status: str | None = None) -> list[LiveWatchEntry]:
        return self.repository.list_live_watches(chat_id, status=status)

    def remove_watch(self, chat_id: int, watch_id: int) -> bool:
        entry = self.repository.get_live_watch(chat_id, watch_id)
        removed = self.repository.remove_live_watch(chat_id, watch_id)
        if removed and entry is not None:
            self._send_to_trash(entry, reason="removed")
        return removed

    def remove_watch_by_local_id(self, chat_id: int, local_id: int) -> bool:
        entry = self.repository.get_live_watch_by_local_id(chat_id, local_id)
        removed = self.repository.remove_live_watch_by_local_id(chat_id, local_id)
        if removed and entry is not None:
            self._send_to_trash(entry, reason="removed")
        return removed

    def list_trash(self, chat_id: int) -> list[LiveWatchTombstone]:
        """Partidos en la papelera del chat (los vencidos ya no aparecen)."""

        return self.repository.list_live_watch_tombstones(chat_id)

    async def _official_status(self, watches: list[LiveWatchEntry], now: datetime) -> dict[int, Any]:
        """El partido de cada watch en las fuentes oficiales, por prioridad.

        Sólo para los que están en su ventana (desde un rato antes del inicio hasta
        ~3 h y media después) o no tienen horario (la fuente se los da). Cada fuente
        baja el día entero en una llamada y lo cachea.
        """

        if not self.status_sources:
            return {}
        due = [entry for entry in watches if _in_status_window(entry, now)]
        found: dict[int, Any] = {}
        for source in self.status_sources:
            pending = [entry for entry in due if entry.id not in found]
            if not pending:
                break
            days = {source.day_for(_parse_iso_datetime(entry.kickoff_at) or now) for entry in pending}
            matches: list[Any] = []
            for day in sorted(days):
                try:
                    matches += await source.matches_on(day)
                except Exception:
                    logger.exception("Fuente de estado %s falló", getattr(source, "name", "?"))
            for entry in pending:
                best = self._best_match(entry, [m for m in matches if m.phase != "cancelled"])
                if best is not None:
                    found[entry.id] = best[1]
        return found

    def _record_official(self, entry: LiveWatchEntry, entry_state: dict[str, Any], official: Any,
                         now: datetime) -> None:
        """Guarda el estado oficial como una "casa" más del watch."""

        if not entry.kickoff_at and official.scheduled_at:
            self.repository.set_live_watch_kickoff_if_missing(entry.id, official.scheduled_at)
        if official.phase not in {"live", "halftime", "ended"}:
            return
        previous = entry_state.get(official.source)
        state = _with_halftime(previous if isinstance(previous, dict) else None, {
            "event_id": str(official.match_id), "home": official.home, "away": official.away,
            "home_score": official.home_score, "away_score": official.away_score,
            "minute": official.minute, "phase": official.phase, "official": True,
            "ht_home_score": official.ht_home_score, "ht_away_score": official.ht_away_score,
            "observed_at": now.isoformat(),
        })
        if state.get("ht_home_score") is None:
            state.pop("ht_home_score", None)
            state.pop("ht_away_score", None)
        had_halftime = isinstance(previous, dict) and previous.get("ht_home_score") is not None
        if state.get("ht_home_score") is not None and not had_halftime:
            self._settlement_triggers += 1  # entretiempo oficial: se liquidan las del 1er tiempo
        self.repository.update_live_watch_platform_state(entry.id, platform=official.source, state=state)
        entry_state[official.source] = state

    def _mark_missing(self, entry: LiveWatchEntry, platform: str, entry_state: dict[str, Any],
                      answering_platforms: set[str], now: datetime) -> None:
        """Anota desde cuándo una casa que sí responde dejó de listar el partido."""

        state = entry_state.get(platform)
        if not isinstance(state, dict) or state.get("missing_since") or platform not in answering_platforms:
            return
        state = {**state, "missing_since": now.isoformat()}
        self.repository.update_live_watch_platform_state(entry.id, platform=platform, state=state)
        entry_state[platform] = state

    def _finish_entry(self, entry: LiveWatchEntry, entry_state: dict[str, Any]) -> None:
        """Archiva el resultado de un partido terminado y lo saca de la vigilancia."""

        finished = replace(entry, live_state_json=json.dumps(entry_state, ensure_ascii=False, sort_keys=True))
        try:
            self._archive_expired_entry(finished)
        except Exception:
            logger.exception("No pude archivar el resultado del watch id=%s", entry.id)
        self.repository.remove_live_watch(entry.chat_id, entry.id)
        self._send_to_trash(entry, reason="finished")
        logger.info("Live-watch: %s vs %s terminó, resultado archivado (watch id=%s)",
                    entry.home, entry.away, entry.id)

    def _send_to_trash(self, entry: LiveWatchEntry, *, reason: str) -> None:
        """Deja constancia de que este fixture salió de la vigilancia.

        Best-effort: si la papelera falla, el borrado igual ya ocurrió y no tiene
        sentido romper la purga ni el comando del usuario por eso.
        """

        try:
            self.repository.record_live_watch_tombstone(
                entry.chat_id,
                entry.home,
                entry.away,
                league_hint=entry.league_hint,
                kickoff_at=entry.kickoff_at,
                reason=reason,
                retention_days=TOMBSTONE_RETENTION_DAYS,
            )
        except Exception:
            logger.exception(
                "No pude mandar a la papelera el watch id=%s (%s vs %s)",
                entry.id,
                entry.home,
                entry.away,
            )

    def clear_watches(self, chat_id: int, *, status: str | None = None) -> int:
        return self.repository.clear_live_watches(chat_id, status=status)

    def get_alert_settings(self, chat_id: int) -> LiveWatchSettings:
        return self.repository.get_live_watch_settings(chat_id)

    def update_alert_settings(
        self,
        chat_id: int,
        *,
        alert_goals: bool | None = None,
        alert_red_cards: bool | None = None,
        alert_yellow_cards: bool | None = None,
    ) -> LiveWatchSettings:
        return self.repository.set_live_watch_settings(
            chat_id,
            alert_goals=alert_goals,
            alert_red_cards=alert_red_cards,
            alert_yellow_cards=alert_yellow_cards,
        )

    # ----- polling -----

    def _live_extractors(self) -> list[Extractor]:
        return [e for e in self.extractor_registry.list_registered() if getattr(e, "supports_live_detection", False)]

    def _prematch_extractors(self) -> list[Extractor]:
        return [e for e in self.extractor_registry.list_registered() if getattr(e, "supports_prematch_listing", False)]

    async def collect_live_events(self) -> list[LiveEventSnapshot]:
        """Gather in-play soccer events from every live-capable extractor."""

        return await self._collect_events_parallel(
            self._live_extractors(),
            method_name="list_live_events",
            label="Live",
        )

    async def collect_prematch_events(self) -> list[LiveEventSnapshot]:
        """Gather currently-listed prematch soccer events (cached ~120s)."""

        import time as _time

        now = _time.monotonic()
        if self._prematch_cache is not None and (now - self._prematch_cached_at) < self._prematch_ttl_seconds:
            return self._prematch_cache
        events = await self._collect_events_parallel(
            self._prematch_extractors(),
            method_name="list_prematch_events",
            label="Prematch",
        )
        if events:
            self._prematch_cache = events
            self._prematch_cached_at = now
        return events

    async def _collect_events_parallel(
        self,
        extractors: list[Extractor],
        *,
        method_name: str,
        label: str,
    ) -> list[LiveEventSnapshot]:
        """Fetch one live/prematch feed per platform concurrently."""

        async def _fetch(extractor: Extractor) -> list[LiveEventSnapshot]:
            try:
                method = getattr(extractor, method_name)
                raw_events = await method()
                if raw_events is None:
                    logger.warning("%s extractor returned no events platform=%s", label, extractor.name)
                    return []
                return list(raw_events)
            except Exception as error:
                import httpx
                if isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (403, 503):
                    logger.warning(
                        "%s fetch failed with HTTP %d (WAF/Cloud IP Block) platform=%s. Running from a cloud provider (GCP/AWS) often causes this. Consider using a proxy.",
                        label, error.response.status_code, extractor.name
                    )
                else:
                    logger.exception("%s fetch failed platform=%s", label, extractor.name)
                return []

        if not extractors:
            return []
        batches = await asyncio.gather(*(_fetch(extractor) for extractor in extractors))
        return [event for batch in batches for event in batch]

    @staticmethod
    def _best_match(entry: LiveWatchEntry, events: list[LiveEventSnapshot]) -> tuple[float, LiveEventSnapshot] | None:
        best: tuple[float, LiveEventSnapshot] | None = None
        for event in events:
            score = match_score(entry, event)
            if score >= COMBINED_FLOOR and (best is None or score > best[0]):
                best = (score, event)
        return best

    async def poll_once(self) -> list[LiveWatchHit]:
        """Detect watched fixtures going live (terminal) or being listed in prematch.

        - A live match fires a one-shot LIVE alert and ends the watch.
        - A prematch listing fires a one-shot PRE alert (per book) without ending
          the watch — the entry keeps waiting to go live.
        Expired entries are pruned first.
        """

        self.purge_expired()
        watches = self.repository.list_all_active_live_watches()
        if not watches:
            return []

        live_events = await self.collect_live_events()
        prematch_events = await self.collect_prematch_events()

        hits: list[LiveWatchHit] = []
        # Partidos trackeados por chat (cada chat ve sólo sus suscripciones).
        active_events_by_chat: dict[int, list[Any]] = {}
        # Casas que respondieron este ciclo: que un partido falte en una casa caída
        # no dice nada sobre si terminó.
        answering_platforms = {event.platform for event in live_events}
        now = datetime.now(timezone.utc)
        settings_cache: dict[int, LiveWatchSettings] = {}
        official_by_entry = await self._official_status(watches, now)

        for entry in watches:
            settings = settings_cache.get(entry.chat_id)
            if settings is None:
                settings = self.repository.get_live_watch_settings(entry.chat_id)
                settings_cache[entry.chat_id] = settings

            # 1. Process score/card changes from platforms where this fixture is already live.
            entry_state = entry.live_state
            official = official_by_entry.get(entry.id)
            if official is not None:
                self._record_official(entry, entry_state, official, now)
            alert_state = entry_state.get("_alerts") if isinstance(entry_state.get("_alerts"), dict) else {}
            alert_state_changed = False
            for platform in entry.fired_platforms_list:
                platform_event = self._best_known_platform_match(
                    entry,
                    platform=platform,
                    events=live_events,
                    state_by_platform=entry_state,
                )
                if platform_event is None:
                    self._mark_missing(entry, platform, entry_state, answering_platforms, now)
                    continue
                previous_state = entry_state.get(platform)
                current_state = _with_halftime(previous_state, _event_live_state(platform_event),
                                               kickoff=_parse_iso_datetime(entry.kickoff_at), now=now)
                had_halftime = (previous_state or {}).get("ht_home_score") is not None
                if current_state.get("ht_home_score") is not None and not had_halftime:
                    self._settlement_triggers += 1  # entretiempo: se liquidan las del 1er tiempo
                if previous_state:
                    transition_hits = _transition_hits(
                        entry,
                        platform_event,
                        previous_state=previous_state,
                        current_state=current_state,
                        settings=settings,
                        alert_state=alert_state,
                    )
                    if transition_hits:
                        alert_state_changed = True
                    for hit in transition_hits:
                        hits.append(hit)
                self.repository.update_live_watch_platform_state(
                    entry.id,
                    platform=platform_event.platform,
                    state=current_state,
                )
                entry_state[platform_event.platform] = current_state
            if alert_state_changed:
                self.repository.update_live_watch_platform_state(
                    entry.id,
                    platform="_alerts",
                    state=alert_state,
                )
            if (entry.fired_platforms_list or official is not None) and _match_finished(entry_state, now):
                # Terminó: se archiva ya (y se liquidan sus apuestas) en vez de esperar
                # a que el watch venza, 2-3 h después del inicio.
                self._finish_entry(entry, entry_state)
                continue

            # 2. Process first LIVE detection per platform.
            eligible_live_events = (
                [ev for ev in live_events if ev.platform not in entry.fired_platforms_list]
                if live_events
                else []
            )
            live_best = self._best_match(entry, eligible_live_events) if eligible_live_events else None
            if live_best is not None:
                score, event = live_best
                self.repository.mark_live_watch_fired(
                    entry.id, platform=event.platform, event_id=event.external_event_id, minute=event.minute
                )
                self.repository.update_live_watch_platform_state(
                    entry.id,
                    platform=event.platform,
                    state=_with_halftime(None, _event_live_state(event)),
                )
                self._auto_track_matched_event_league(event, entry.chat_id)
                hits.append(LiveWatchHit(entry=entry, event=event, score=score, phase="live"))
                continue

            # 3. Process Kickoff Countdown alerts (5 min before kickoff)
            if entry.kickoff_at and not entry.countdown_fired_at:
                try:
                    ko = datetime.fromisoformat(entry.kickoff_at)
                    if ko.tzinfo is None:
                        ko = ko.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    diff_seconds = (ko - now).total_seconds()
                    # Fire alert exactly if starts in 4 to 6 minutes (240 to 360 seconds)
                    if 240 <= diff_seconds <= 360:
                        active_events = active_events_by_chat.get(entry.chat_id)
                        if active_events is None:
                            active_events = _active_event_views(
                                self.repository.get_all_active_events_with_league(entry.chat_id)
                            )
                            active_events_by_chat[entry.chat_id] = active_events

                        matched_prematch = []
                        for ev in active_events:
                            if match_score(entry, ev) >= COMBINED_FLOOR:
                                matched_prematch.append(ev)

                        if matched_prematch:
                            msg = render_countdown_alert(entry, matched_prematch)
                            self.repository.mark_live_watch_countdown_fired(entry.id)
                            hits.append(LiveWatchHit(entry=entry, phase="countdown", custom_message=msg))
                except Exception:
                    logger.exception("Error checking kickoff countdown for entry_id=%s", entry.id)

            # 4. Process Prematch events (per platform alert)
            eligible_prematch_events = (
                [ev for ev in prematch_events if ev.platform not in entry.prematch_fired_platforms_list]
                if prematch_events
                else []
            )
            pre_best = self._best_match(entry, eligible_prematch_events) if eligible_prematch_events else None
            if pre_best is not None:
                score, event = pre_best
                self.repository.mark_live_watch_prematch_fired(
                    entry.id, platform=event.platform, event_id=event.external_event_id
                )
                if not entry.kickoff_at and getattr(event, "scheduled_at", None):
                    # Sin horario el watch vence a las 16 h (p. ej. el que abre /bet):
                    # el de la casa lo mantiene vivo hasta el partido.
                    self.repository.set_live_watch_kickoff_if_missing(entry.id, event.scheduled_at)
                self._auto_track_matched_event_league(event, entry.chat_id)
                hits.append(LiveWatchHit(entry=entry, event=event, score=score, phase="pre"))

        await self._publish_hits(hits)
        return hits

    async def _publish_hits(self, hits: list[LiveWatchHit]) -> None:
        """Publica cada hit al bus para que las interfaces suscritas avisen.

        Los hits se siguen devolviendo además de publicarse: quien llama puede
        querer el resultado (los tests lo usan) sin depender de que haya un
        listener registrado.
        """

        if not hits:
            return

        undelivered = 0
        for hit in hits:
            result = await event_bus.publish(MatchLiveEvent(hit=hit))
            undelivered += result.failed

        if undelivered:
            logger.warning(
                "Live-watch: %s de %s aviso(s) no se pudieron entregar.",
                undelivered,
                len(hits),
            )

    @staticmethod
    def _best_known_platform_match(
        entry: LiveWatchEntry,
        *,
        platform: str,
        events: list[LiveEventSnapshot],
        state_by_platform: dict[str, Any],
    ) -> LiveEventSnapshot | None:
        candidates = [event for event in events if event.platform == platform]
        if not candidates:
            return None
        known_state = state_by_platform.get(platform)
        if isinstance(known_state, dict):
            known_event_id = str(known_state.get("event_id") or "")
            if known_event_id:
                direct = next(
                    (event for event in candidates if str(event.external_event_id) == known_event_id),
                    None,
                )
                if direct is not None:
                    return direct
        best = LiveWatchService._best_match(entry, candidates)
        return best[1] if best is not None else None


    def purge_expired(self) -> int:
        """Delete watch entries whose time has passed (kickoff+grace, or stale).

        Antes de borrarlas, archiva el último estado en vivo observado: es la
        única oportunidad de dejar registro de cómo terminó el partido. Además
        las manda a la papelera, para que el auto-import de la planilla no las
        vuelva a cargar mientras la fila siga en el Excel.
        """

        expired = self.repository.pop_expired_live_watches()
        for entry in expired:
            try:
                self._archive_expired_entry(entry)
            except Exception:
                # Archivar es best-effort: no puede romper la purga ni el ciclo.
                logger.exception("No pude archivar el resultado del watch id=%s", entry.id)
            self._send_to_trash(entry, reason="expired")

        # La papelera se vacía sola acá: este ciclo ya corre seguido y así no
        # hace falta un job aparte.
        try:
            self.repository.purge_expired_live_watch_tombstones()
        except Exception:
            logger.exception("No pude vaciar la papelera vencida del live-watch")

        return len(expired)

    def _archive_expired_entry(self, entry: LiveWatchEntry) -> None:
        """Guarda en el archivo histórico el último estado visto de un fixture."""

        state = _last_observed_state(entry)
        if state is None:
            # Nunca se lo vio en vivo: no hay nada que archivar.
            return

        platform, observed = state
        minute = observed.get("minute")
        halftime = _halftime_score(entry)
        self.repository.record_match_result(
            MatchResult(
                # Los nombres de la casa y no los del watch: los de la planilla traen
                # notas ("ASA Tel Aviv (Visitantes +4/5)") y no dicen la categoría.
                home=observed.get("home") or entry.home,
                away=observed.get("away") or entry.away,
                competition_name=entry.league_hint,
                # El minuto decide si esto es un resultado final o una foto
                # parcial. Marcarlo mal haría que un 1-0 del minuto 20 entrara
                # a los análisis como resultado definitivo.
                status="FINISHED" if _looks_finished(minute) else "UNKNOWN",
                source="live_watch",
                recorded_at=datetime.now(timezone.utc).isoformat(),
                platform=platform,
                external_event_id=str(observed.get("event_id") or "") or None,
                kickoff_at=entry.kickoff_at,
                final_home_score=observed.get("home_score"),
                final_away_score=observed.get("away_score"),
                ht_home_score=halftime[0] if halftime else None,
                ht_away_score=halftime[1] if halftime else None,
                red_cards_home=observed.get("home_red_cards"),
                red_cards_away=observed.get("away_red_cards"),
                # Los ids del mismo partido en cada casa donde se lo vio: una apuesta
                # enlazada a otra casa (con otros nombres) encuentra este resultado.
                raw_payload_json=json.dumps(
                    {**observed, "_event_ids": _event_ids_by_platform(entry)},
                    ensure_ascii=False, sort_keys=True),
            )
        )
        self._settlement_triggers += 1

    def get_recommended_poll_interval(self, default_normal: float = 15.0, default_fast: float = 10.0) -> float:
        """Determine the next sleep interval based on active watch state.

        Returns default_fast while a watched fixture is plausibly in play, so
        goals/cards are caught quickly for the WHOLE match (not just the first
        minutes). Fast applies when a watch is:
          - in the kickoff window [kickoff-2m, kickoff+140m] (covers 90' + HT +
            stoppage + extra time), or
          - already detected live on some platform (fired_platforms) without a
            known kickoff time.
        Otherwise the normal cadence is used.
        """

        watches = self.repository.list_all_active_live_watches()
        if not watches:
            return default_normal

        now = datetime.now(timezone.utc)
        for w in watches:
            if w.kickoff_at:
                try:
                    ko = datetime.fromisoformat(w.kickoff_at)
                    # Fast for the full match: [ko - 2 min, ko + 140 min].
                    if (ko - timedelta(minutes=2)) <= now <= (ko + timedelta(minutes=140)):
                        return default_fast
                    continue
                except Exception:
                    pass
            if w.fired_platforms_list:
                # No usable kickoff time but already live on a book -> poll fast.
                return default_fast
        return default_normal

    def _auto_track_matched_event_league(self, event: LiveEventSnapshot, chat_id: int) -> None:
        """Helper to extract competition external ID and automatically track/subscribe it."""
        url = event.source_url or ""
        external_id = None
        if url.startswith("bz:tournament:"):
            external_id = url.replace("bz:tournament:", "")
        elif url.startswith("solcasino:tournament:"):
            external_id = url.replace("solcasino:tournament:", "")
        elif url.startswith("mrpunter:league:"):
            external_id = url.replace("mrpunter:league:", "")
        elif url.startswith("betwarrior:group:"):
            external_id = url.replace("betwarrior:group:", "")
        elif url.startswith("betovo:champ:"):
            external_id = url.replace("betovo:champ:", "")
        elif url.startswith("mystake:champ:"):
            external_id = url.replace("mystake:champ:", "")
        elif url.startswith("betsson:competition:"):
            external_id = url.replace("betsson:competition:", "")
        elif event.platform == "1xbet_http":
            if event.raw_payload:
                external_id = event.raw_payload.get("league_id")

        if not external_id:
            return

        try:
            extractor = self.extractor_registry.get_for_platform(event.platform)
            source_url = extractor.build_competition_url(competition_external_id=external_id)
        except Exception:
            source_url = url

        if not source_url:
            source_url = f"{event.platform}:competition:{external_id}"

        try:
            comp_name = event.competition_name or f"Liga {external_id}"
            self.repository.auto_track_live_detected_league(
                chat_id=chat_id,
                platform=event.platform,
                competition_external_id=external_id,
                competition_name=comp_name,
                source_url=source_url,
            )
        except Exception as e:
            logger.exception(
                "Failed to auto-track live matched league: platform=%s external_id=%s error=%s",
                event.platform,
                external_id,
                e,
            )



# Minuto desde el cual se considera que un marcador observado es final.
# 85' deja margen para descuento sin tomar por final una foto del minuto 70.
FULL_TIME_MINUTE_FLOOR = 85


#: Partido que una casa que responde dejó de listar pasado este minuto, durante
#: FINISH_MISSING_SECONDS, se da por terminado: las casas lo sacan del vivo al final.
FINISH_MINUTE_FLOOR = 88
FINISH_MISSING_SECONDS = 6 * 60
#: Una observación más vieja que esto no cuenta como "sigue en vivo".
STILL_LIVE_SECONDS = 3 * 60

_HALFTIME_RE = re.compile(
    r"\b(?:ht|descanso|entretiempo|medio\s*tiempo|half[\s-]?time|pausa|intervalo|1st\s+half\s+ended)\b",
    re.IGNORECASE)
_FULLTIME_RE = re.compile(
    r"\b(?:ft|fin|final|finalizado|terminado|ended|full[\s-]?time|after\s+pen|aet)\b", re.IGNORECASE)


def _minute_number(minute: Any) -> int | None:
    """Primer número del minuto ("45+2" -> 45, "67'" -> 67, "21:51" -> 21)."""

    match = re.search(r"\d+", str(minute or ""))
    return int(match.group()) if match else None


#: El 2º tiempo no puede estar en juego antes de esto desde el horario de inicio
#: (45' + 15' de descanso; el descuento y las demoras sólo lo corren para después).
SECOND_HALF_EARLIEST = timedelta(minutes=60)


def _with_halftime(previous: dict[str, Any] | None, current: dict[str, Any], *,
                   kickoff: datetime | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Arrastra o detecta el marcador del entretiempo en el estado de una casa.

    Se toma cuando la casa marca el descanso ("HT", "Descanso") o, si no lo marca,
    del último marcador visto a los 45' cuando aparece el 2º tiempo. Algunas casas
    cuentan el descuento del 1er tiempo como 46', 47'...: con el horario de inicio,
    ese salto no cuenta como 2º tiempo hasta SECOND_HALF_EARLIEST.
    """

    if previous and previous.get("ht_home_score") is not None:
        return {**current, "ht_home_score": previous["ht_home_score"],
                "ht_away_score": previous["ht_away_score"]}
    if current.get("home_score") is None:
        return current
    if _HALFTIME_RE.search(str(current.get("minute") or "")):
        return {**current, "ht_home_score": current["home_score"], "ht_away_score": current["away_score"]}
    if previous and previous.get("home_score") is not None:
        before, after = _minute_number(previous.get("minute")), _minute_number(current.get("minute"))
        if before == 45 and after is not None and after >= 46:
            if kickoff is not None and now is not None and now - kickoff < SECOND_HALF_EARLIEST:
                return current  # descuento del 1er tiempo, no el 2º
            return {**current, "ht_home_score": previous["home_score"],
                    "ht_away_score": previous["away_score"]}
    return current


def halftime_states(live_state: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    """Las casas que tienen el marcador del entretiempo, la fuente oficial primero.

    El de una casa puede venir de la regla de los 45'; el oficial lo da la fuente.
    """
    found = [(platform, state) for platform, state in (live_state or {}).items()
             if platform != "_alerts" and isinstance(state, dict)
             and state.get("ht_home_score") is not None]
    return sorted(found, key=lambda item: not item[1].get("official"))


def _halftime_score(entry: LiveWatchEntry) -> tuple[int, int] | None:
    for _, state in halftime_states(entry.live_state):
        return int(state["ht_home_score"]), int(state["ht_away_score"])
    return None


#: Ventana en la que se consulta el estado oficial de un partido con horario.
STATUS_WINDOW_BEFORE = timedelta(minutes=15)
STATUS_WINDOW_AFTER = timedelta(hours=3, minutes=30)


def _in_status_window(entry: LiveWatchEntry, now: datetime) -> bool:
    kickoff = _parse_iso_datetime(entry.kickoff_at)
    if kickoff is None:
        return True  # la fuente le da el horario (y si ya se juega, el estado)
    return kickoff - STATUS_WINDOW_BEFORE <= now <= kickoff + STATUS_WINDOW_AFTER


def _match_finished(states: dict[str, Any], now: datetime) -> bool:
    """El partido terminó: una casa lo marca final, o lo sacó del vivo pasado el 88'.

    Y ninguna otra casa lo sigue mostrando en juego antes del 88' (una casa que se
    atrasa o lo pierde de vista no alcanza para darlo por terminado).
    """

    seen = [state for platform, state in states.items()
            if platform != "_alerts" and isinstance(state, dict) and state.get("event_id")]
    if any(state.get("official") and state.get("phase") == "ended" for state in seen):
        return True  # la federación / Statshub lo dan por terminado: manda sobre las casas
    finished_somewhere = False
    for state in seen:
        minute_label = str(state.get("minute") or "")
        minute = _minute_number(minute_label)
        missing_since = _parse_iso_datetime(state.get("missing_since"))
        observed_at = _parse_iso_datetime(state.get("observed_at"))
        if state.get("home_score") is not None and not missing_since and _FULLTIME_RE.search(minute_label):
            finished_somewhere = True
        elif (state.get("home_score") is not None and missing_since is not None and minute is not None
              and minute >= FINISH_MINUTE_FLOOR
              and (now - missing_since).total_seconds() >= FINISH_MISSING_SECONDS):
            finished_somewhere = True
        elif (missing_since is None and observed_at is not None
              and (now - observed_at).total_seconds() <= STILL_LIVE_SECONDS
              and (minute is None or minute < FINISH_MINUTE_FLOOR)
              and not _FULLTIME_RE.search(minute_label)):
            return False  # otra casa lo muestra en juego
    return finished_somewhere


def _event_ids_by_platform(entry: LiveWatchEntry) -> dict[str, str]:
    """{plataforma: id del evento} de cada casa donde el watch vio el partido."""

    return {
        platform: str(state["event_id"])
        for platform, state in (entry.live_state or {}).items()
        if platform != "_alerts" and isinstance(state, dict) and state.get("event_id")
    }


def _last_observed_state(entry: LiveWatchEntry) -> tuple[str, dict[str, Any]] | None:
    """Devuelve (plataforma, estado) de la observación más reciente del fixture.

    `live_state` está indexado por plataforma y puede tener varias si el partido
    se vio en más de una casa. Se elige la observación más nueva, que es la más
    cerca del final.
    """

    states = entry.live_state or {}
    candidates = [
        (platform, state)
        for platform, state in states.items()
        # "_alerts" no es una plataforma: es el registro de avisos ya enviados.
        if platform != "_alerts" and isinstance(state, dict) and state.get("home_score") is not None
    ]
    if not candidates:
        return None
    # El final oficial manda: una casa atrasada puede no tener el último gol.
    return max(candidates, key=lambda item: (bool(item[1].get("official") and item[1].get("phase") == "ended"),
                                             str(item[1].get("observed_at") or "")))


def _looks_finished(minute: Any) -> bool:
    """True si el minuto observado indica que el partido ya había terminado.

    Los feeds usan etiquetas humanas ("88'", "90+3", "FT", "Finalizado"). Sin un
    minuto lo bastante avanzado NO se puede afirmar que el marcador sea final:
    puede ser la última foto antes de perder el partido de vista. En ese caso el
    resultado se archiva como UNKNOWN y queda fuera de los análisis.
    """

    if not isinstance(minute, str):
        return False
    label = minute.strip().lower()
    if any(token in label for token in ("ft", "final", "terminado", "fin")):
        return True
    match = re.search(r"\d+", label)
    return bool(match) and int(match.group()) >= FULL_TIME_MINUTE_FLOOR


def _event_live_state(event: LiveEventSnapshot) -> dict[str, Any]:
    """Compact persisted state used to detect score/card deltas per platform."""

    odds_dict = None
    if event.odds_1x2:
        odds_dict = {
            "home": event.odds_1x2.home,
            "draw": event.odds_1x2.draw,
            "away": event.odds_1x2.away,
        }

    return {
        "event_id": str(event.external_event_id),
        "minute": event.minute,
        "home": event.home,
        "away": event.away,
        "home_score": event.home_score,
        "away_score": event.away_score,
        "home_red_cards": event.home_red_cards,
        "away_red_cards": event.away_red_cards,
        "home_yellow_cards": event.home_yellow_cards,
        "away_yellow_cards": event.away_yellow_cards,
        "live_stats": event.live_stats or {},
        "odds": odds_dict,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def _state_int(state: dict[str, Any], key: str) -> int | None:
    value = state.get(key)
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _increased(previous_state: dict[str, Any], current_state: dict[str, Any], key: str) -> bool:
    previous = _state_int(previous_state, key)
    current = _state_int(current_state, key)
    return previous is not None and current is not None and current > previous


def _transition_hits(
    entry: LiveWatchEntry,
    event: LiveEventSnapshot,
    *,
    previous_state: dict[str, Any],
    current_state: dict[str, Any],
    settings: LiveWatchSettings,
    alert_state: dict[str, Any],
) -> list[LiveWatchHit]:
    """Build high-priority live alerts from one state transition."""

    hits: list[LiveWatchHit] = []
    goal_changed = (
        _increased(previous_state, current_state, "home_score")
        or _increased(previous_state, current_state, "away_score")
    )
    score_key = _score_key_from_state(current_state)
    if settings.alert_goals and goal_changed and score_key and alert_state.get("score_key") != score_key:
        hits.append(
            LiveWatchHit(
                entry=entry,
                event=event,
                phase="goal",
                custom_message=_render_goal_alert(event, previous_state, current_state),
            )
        )
        alert_state["score_key"] = score_key

    red_changed = (
        _increased(previous_state, current_state, "home_red_cards")
        or _increased(previous_state, current_state, "away_red_cards")
    )
    red_key = _card_key_from_state(current_state, color="red")
    if settings.alert_red_cards and red_changed and red_key and alert_state.get("red_key") != red_key:
        hits.append(
            LiveWatchHit(
                entry=entry,
                event=event,
                phase="red_card",
                custom_message=_render_red_card_alert(event, previous_state, current_state),
            )
        )
        alert_state["red_key"] = red_key

    yellow_changed = (
        _increased(previous_state, current_state, "home_yellow_cards")
        or _increased(previous_state, current_state, "away_yellow_cards")
    )
    yellow_key = _card_key_from_state(current_state, color="yellow")
    if settings.alert_yellow_cards and yellow_changed and yellow_key and alert_state.get("yellow_key") != yellow_key:
        hits.append(
            LiveWatchHit(
                entry=entry,
                event=event,
                phase="yellow_card",
                custom_message=_render_yellow_card_alert(event, previous_state, current_state),
            )
        )
        alert_state["yellow_key"] = yellow_key
    return hits


def _score_key_from_state(state: dict[str, Any]) -> str | None:
    home = _state_int(state, "home_score")
    away = _state_int(state, "away_score")
    if home is None or away is None:
        return None
    return f"{home}-{away}"


def _card_key_from_state(state: dict[str, Any], *, color: str) -> str | None:
    home_key = f"home_{color}_cards"
    away_key = f"away_{color}_cards"
    home = _state_int(state, home_key)
    away = _state_int(state, away_key)
    if home is None or away is None:
        return None
    return f"{home}-{away}"


def _platform_label(platform: str) -> str:
    return platform.replace("_http", "").replace("_", " ")


def _score_label(event: LiveEventSnapshot) -> str:
    if event.home_score is not None and event.away_score is not None:
        return f"{event.home_score}-{event.away_score}"
    return "score no informado"


def _render_goal_alert(
    event: LiveEventSnapshot,
    previous_state: dict[str, Any],
    current_state: dict[str, Any],
) -> str:
    scorers: list[str] = []
    if _increased(previous_state, current_state, "home_score"):
        scorers.append(event.home)
    if _increased(previous_state, current_state, "away_score"):
        scorers.append(event.away)
    scorer_text = ", ".join(scorers) if scorers else "Equipo no identificado"
    lines = [
        "⚽ GOL DETECTADO",
        "",
        f"🏦 {_platform_label(event.platform)}",
        f"⚽ {event.home} vs {event.away}",
        f"📌 Gol: {scorer_text}",
        f"🔢 Marcador: {_score_label(event)}",
    ]
    if event.minute:
        lines.append(f"⏱️ {event.minute}")
    lines.extend(_live_stats_lines(event))
    return "\n".join(lines)


def _render_red_card_alert(
    event: LiveEventSnapshot,
    previous_state: dict[str, Any],
    current_state: dict[str, Any],
) -> str:
    teams: list[str] = []
    if _increased(previous_state, current_state, "home_red_cards"):
        count = _state_int(current_state, "home_red_cards")
        teams.append(f"{event.home} ({count})")
    if _increased(previous_state, current_state, "away_red_cards"):
        count = _state_int(current_state, "away_red_cards")
        teams.append(f"{event.away} ({count})")
    team_text = ", ".join(teams) if teams else "Equipo no identificado"
    lines = [
        "🟥 TARJETA ROJA",
        "",
        f"🏦 {_platform_label(event.platform)}",
        f"⚽ {event.home} vs {event.away}",
        f"📌 Roja: {team_text}",
        f"🔢 Marcador: {_score_label(event)}",
    ]
    if event.minute:
        lines.append(f"⏱️ {event.minute}")
    lines.extend(_live_stats_lines(event))
    return "\n".join(lines)


def _render_yellow_card_alert(
    event: LiveEventSnapshot,
    previous_state: dict[str, Any],
    current_state: dict[str, Any],
) -> str:
    teams: list[str] = []
    if _increased(previous_state, current_state, "home_yellow_cards"):
        count = _state_int(current_state, "home_yellow_cards")
        teams.append(f"{event.home} ({count})")
    if _increased(previous_state, current_state, "away_yellow_cards"):
        count = _state_int(current_state, "away_yellow_cards")
        teams.append(f"{event.away} ({count})")
    team_text = ", ".join(teams) if teams else "Equipo no identificado"
    lines = [
        "🟨 TARJETA AMARILLA",
        "",
        f"🏦 {_platform_label(event.platform)}",
        f"⚽ {event.home} vs {event.away}",
        f"📌 Amarilla: {team_text}",
        f"🔢 Marcador: {_score_label(event)}",
    ]
    if event.minute:
        lines.append(f"⏱️ {event.minute}")
    lines.extend(_live_stats_lines(event))
    return "\n".join(lines)


def _live_stats_lines(event: LiveEventSnapshot) -> list[str]:
    """Render optional live stats when a provider exposes them."""

    stats = event.live_stats or {}
    if not isinstance(stats, dict):
        return []
    labels = [
        ("Posesión", "possession_home", "possession_away"),
        ("Ataques", "attacks_home", "attacks_away"),
        ("Ataques peligrosos", "dangerous_attacks_home", "dangerous_attacks_away"),
        ("Tiros al arco", "shots_on_target_home", "shots_on_target_away"),
        ("Corners", "corners_home", "corners_away"),
    ]
    lines: list[str] = []
    for label, home_key, away_key in labels:
        home = stats.get(home_key)
        away = stats.get(away_key)
        if home is None and away is None:
            continue
        lines.append(f"📊 {label}: {home if home is not None else '-'} / {away if away is not None else '-'}")
    return lines


def _event_markets_dict(event: Any) -> dict[str, Any] | None:
    """Return an event's markets as a dict, from markets_json (str) or markets_payload (dict)."""

    raw = getattr(event, "markets_json", None)
    if raw:
        try:
            parsed = json.loads(raw)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None
    payload = getattr(event, "markets_payload", None)
    return payload if isinstance(payload, dict) else None


def _format_handicap(event: Any) -> str | None:
    markets = _event_markets_dict(event)
    if markets is None:
        return None
    return _format_handicap_from_markets(
        markets, home=getattr(event, "home", ""), away=getattr(event, "away", "")
    )


def _format_handicap_from_markets(markets: dict[str, Any], *, home: str, away: str) -> str | None:
    ah = markets.get("asian_handicap") if isinstance(markets, dict) else None
    if not ah or not isinstance(ah, dict):
        return None
    selections = ah.get("selections")
    if not isinstance(selections, list) or not selections:
        return None

    home_sel = None
    away_sel = None
    home_norm = normalize_team_name(home)
    away_norm = normalize_team_name(away)
    for sel in selections:
        if not isinstance(sel, dict):
            continue
        sel_name = normalize_team_name(sel.get("selection"))
        if sel_name == home_norm:
            home_sel = sel
        elif sel_name == away_norm:
            away_sel = sel

    if not home_sel or not away_sel:
        if len(selections) >= 2:
            home_sel, away_sel = selections[0], selections[1]
        else:
            return None

    try:
        h_line = home_sel.get("line")
        h_odds = home_sel.get("odds")
        a_line = away_sel.get("line")
        a_odds = away_sel.get("odds")
        if h_line is not None and h_odds is not None and a_line is not None and a_odds is not None:
            return f"📐 AH L({h_line}):{float(h_odds):.2f} | V({a_line}):{float(a_odds):.2f}"
    except Exception:
        pass
    return None


def _format_goals(event: Any) -> str | None:
    markets = _event_markets_dict(event)
    if markets is None:
        return None
    return _format_goals_from_markets(markets)


def _format_goals_from_markets(markets: dict[str, Any]) -> str | None:
    gl = markets.get("goal_line") if isinstance(markets, dict) else None
    if not gl or not isinstance(gl, dict):
        return None
    selections = gl.get("selections")
    if not isinstance(selections, list) or not selections:
        return None
    parts = []
    for sel in selections[:4]:
        name = sel.get("selection")
        line = sel.get("line")
        odds = sel.get("odds")
        if name and odds is not None:
            line_str = f" {line}" if line else ""
            parts.append(f"{name}{line_str}={float(odds):.2f}")
    if parts:
        return f"📏 GL {' | '.join(parts)}"
    return None


def _active_event_views(rows: Iterable[Any]) -> list[Any]:
    """Filas de ``get_all_active_events_with_league`` (dict) -> objetos con los mismos
    campos como atributos, que es lo que leen ``match_score`` y ``render_countdown_alert``
    (home, away, scheduled_at, league_name, platform, odds_*, markets_json)."""

    return [SimpleNamespace(**row) if isinstance(row, dict) else row for row in rows]


def render_countdown_alert(entry: LiveWatchEntry, matched: list[Any]) -> str:
    lines = [
        "⏰ PRÓXIMO INICIO (5 min)",
        "",
        f"⚽ {entry.home} vs {entry.away}"
    ]
    league_name = None
    for ev in matched:
        if getattr(ev, "league_name", None):
            league_name = ev.league_name
            break
    if league_name:
        lines.append(f"🏆 {league_name}")

    if entry.note and entry.note.strip() not in (f"{entry.home} - {entry.away}",):
        lines.append("")
        lines.append(f"📝 {entry.note.strip()}")

    lines.append("")
    lines.append("💰 ODDS POR CASA:")

    for ev in matched:
        book = ev.platform.replace("_http", "")
        lines.append("")
        lines.append(f"🏦 {book}")

        # 1X2
        h = f"{ev.odds_home:.2f}" if ev.odds_home is not None else "-"
        d = f"{ev.odds_draw:.2f}" if ev.odds_draw is not None else "-"
        a = f"{ev.odds_away:.2f}" if ev.odds_away is not None else "-"
        lines.append(f"• 1X2: {h} / {d} / {a}")

        # Handicap
        handicap_str = _format_handicap(ev)
        if handicap_str:
            lines.append(f"• {handicap_str}")

        # Goals
        goals_str = _format_goals(ev)
        if goals_str:
            lines.append(f"• {goals_str}")

    return "\n".join(lines)


def render_live_hit(hit: LiveWatchHit) -> str:
    """Build the Telegram alert for a watched fixture (live, prematch, or countdown)."""

    if hit.phase in ("countdown", "goal", "red_card", "yellow_card"):
        return hit.custom_message or ""

    event = hit.event
    book = event.platform.replace("_http", "")
    if hit.phase == "pre":
        lines = [
            "📋 LISTADO EN PRE",
            "",
            f"⚽ {event.home} vs {event.away}"
        ]
        league_bits = " · ".join(b for b in (event.country_name, event.competition_name) if b)
        if league_bits:
            lines.append(f"🏆 {league_bits}")
        lines.append("")
        lines.append(f"🏦 {book} (prematch) — sigo vigilando para el vivo")
        if hit.entry.note and hit.entry.note.strip() not in (f"{event.home} - {event.away}",):
            lines.append(f"📝 {hit.entry.note.strip()}")
        return "\n".join(lines)

    # Phase is "live"
    lines = [
        "🔴 EN VIVO",
        "",
        f"⚽ {event.home} vs {event.away}"
    ]
    league_bits = " · ".join(b for b in (event.country_name, event.competition_name) if b)
    if league_bits:
        lines.append(f"🏆 {league_bits}")
    lines.append(f"🏦 {book}")
    lines.append("")
    clock = event.minute or "en juego"
    if event.home_score is not None and event.away_score is not None:
        clock += f"  |  {event.home_score}-{event.away_score}"
    lines.append(f"⏱️ {clock}")

    card_parts = []
    if event.home_red_cards is not None or event.away_red_cards is not None:
        card_parts.append(
            f"🟥 {event.home_red_cards if event.home_red_cards is not None else 0}/"
            f"{event.away_red_cards if event.away_red_cards is not None else 0}"
        )
    if event.home_yellow_cards is not None or event.away_yellow_cards is not None:
        card_parts.append(
            f"🟨 {event.home_yellow_cards if event.home_yellow_cards is not None else 0}/"
            f"{event.away_yellow_cards if event.away_yellow_cards is not None else 0}"
        )
    if card_parts:
        lines.append(" ".join(card_parts))

    stats_lines = _live_stats_lines(event)
    if stats_lines:
        lines.append("")
        lines.extend(stats_lines)

    if hit.entry.note and hit.entry.note.strip() not in (f"{event.home} - {event.away}",):
        lines.append("")
        lines.append(f"📝 {hit.entry.note.strip()}")

    odds_lines: list[str] = []
    if event.odds_1x2 and any(v is not None for v in (event.odds_1x2.home, event.odds_1x2.draw, event.odds_1x2.away)):
        o = event.odds_1x2
        h = str(o.home) if o.home is not None else "-"
        d = str(o.draw) if o.draw is not None else "-"
        a = str(o.away) if o.away is not None else "-"
        odds_lines.append(f"💰 1X2: {h} / {d} / {a}")

    markets = event.markets_payload if isinstance(event.markets_payload, dict) else {}
    handicap_str = _format_handicap_from_markets(markets, home=event.home, away=event.away)
    if handicap_str:
        odds_lines.append(handicap_str)
    goals_str = _format_goals_from_markets(markets)
    if goals_str:
        odds_lines.append(goals_str)

    if odds_lines:
        lines.append("")
        lines.extend(odds_lines)

    return "\n".join(lines)



_FIXTURE_SEPARATORS = (" - ", " – ", " vs. ", " vs ", " v ", " x ")
# Optional leading "HH:MM" (local wall-clock time), e.g. "21:00 Olympia - Ballard".
_LEADING_TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s+(.*)$")
# Backwards-compatible alias; the actual zone is now resolved per chat.
_ARG_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _kickoff_from_arg_time(hour: int, minute: int, tz: ZoneInfo | None = None) -> str | None:
    """Build today's (or tomorrow's if past) kickoff in ``tz`` as a UTC ISO timestamp.

    ``tz`` is the chat's display timezone (defaults to the configured default,
    Argentina), i.e. the wall-clock the user typed the time in.
    """

    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    local_tz = tz or default_timezone()
    now_local = datetime.now(local_tz)
    kickoff = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # If the kickoff is in the past by more than 2.5 hours, it belongs to tomorrow.
    if kickoff < now_local and (now_local - kickoff) > timedelta(hours=2.5):
        kickoff += timedelta(days=1)
    return kickoff.astimezone(timezone.utc).isoformat()


def parse_fixture_line(
    raw: str, tz: ZoneInfo | None = None
) -> tuple[str | None, str, str, str | None] | None:
    """Parse one fixture line into (league_hint, home, away, kickoff_utc) or None.

    Accepts an optional leading ``HH:MM`` (interpreted in ``tz``, the chat's
    display timezone) and an optional ``League | Home - Away`` prefix.
    Separators: ' - ', ' vs ', ' vs. ', etc.
    """

    text = (raw or "").strip()
    if not text:
        return None
    kickoff_at: str | None = None
    time_match = _LEADING_TIME_RE.match(text)
    if time_match:
        kickoff_at = _kickoff_from_arg_time(
            int(time_match.group(1)), int(time_match.group(2)), tz=tz
        )
        text = time_match.group(3).strip()
    league_hint: str | None = None
    if "|" in text:
        head, _, tail = text.partition("|")
        league_hint, text = head.strip() or None, tail.strip()
    for sep in _FIXTURE_SEPARATORS:
        if sep in text:
            home, _, away = text.partition(sep)
            home, away = home.strip(), away.strip()
            if home and away:
                return league_hint, home, away, kickoff_at
    return None


# --------------------------------------------------------------------------- #
# Google Sheet import (shared by /import_sheet and the auto-import job)
# --------------------------------------------------------------------------- #
def sheet_timezone() -> ZoneInfo:
    """Wall-clock zone of the Horario column in the shared Google Sheet.

    The sheet is always written in Argentina time, no matter which display
    timezone each chat picked. Overridable via LIVE_WATCH_SHEET_TIMEZONE.
    """

    import os

    from core.timezones import get_zoneinfo

    name = (os.getenv("LIVE_WATCH_SHEET_TIMEZONE") or "").strip()
    return get_zoneinfo(name) or _ARG_TZ


def parse_sheet_fixture_lines(csv_text: str) -> list[str]:
    """Parse the shared Google Sheet CSV into watch fixture lines.

    Expects columns Horario / Competición / Partido / Detalle (accent-insensitive).
    Returns the same "HH:MM Liga | Home vs Away (detalle)" lines that
    ``LiveWatchService.add_fixture_lines`` consumes. Empty/invalid rows skipped.
    Raises ValueError when the required columns are missing.
    """

    import csv as _csv
    from io import StringIO

    reader = _csv.DictReader(StringIO(csv_text))
    headers = reader.fieldnames or []

    def _clean(h: str) -> str:
        folded = "".join(c for c in unicodedata.normalize("NFD", h) if unicodedata.category(c) != "Mn")
        return folded.lower().strip()

    clean_map = {_clean(h): h for h in headers}
    required = {"horario", "competicion", "partido", "detalle"}
    if not required.issubset(set(clean_map)):
        raise ValueError(
            "La planilla debe tener las columnas Horario, Competición, Partido, Detalle. "
            f"Encontradas: {', '.join(headers)}"
        )

    col_h, col_c = clean_map["horario"], clean_map["competicion"]
    col_p, col_d = clean_map["partido"], clean_map["detalle"]
    lines: list[str] = []
    for row in reader:
        partido = (row.get(col_p) or "").strip()
        if not partido:
            continue
        horario = (row.get(col_h) or "").strip()
        competicion = (row.get(col_c) or "").strip()
        detalle = (row.get(col_d) or "").strip()
        line = ""
        if horario:
            line += f"{horario} "
        if competicion:
            line += f"{competicion} | "
        line += partido
        if detalle:
            line += f" ({detalle})"
        lines.append(line)
    return lines


live_watch_service = LiveWatchService()

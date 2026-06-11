"""Live-watch service: alert when a watched fixture goes in-play.

The user loads fixtures (home/away, optional league hint). This service polls
every live-capable extractor, fuzzy-matches in-play events against the active
watchlist, and fires a one-shot Telegram alert the first time a fixture appears
live (with the current minute/score) — the opening seconds are when the books
misprice. Matching is per-side: both home and away must clear a similarity floor.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
import json
import logging
import re
import unicodedata
from typing import Iterable, Any
from zoneinfo import ZoneInfo

from core.extractor_base import Extractor
from core.models import LiveEventSnapshot
from core.registry import ExtractorRegistry, extractor_registry as global_extractor_registry
from storage.tracking_repository import (
    LiveWatchEntry,
    LiveWatchSettings,
    SqliteTrackingRepository,
    tracking_repository as default_tracking_repository,
)

logger = logging.getLogger(__name__)

# Per-side similarity floor and combined floor for a confident auto-match.
SIDE_FLOOR = 0.62
COMBINED_FLOOR = 0.70


_TEAM_TRANSLATION_MAP = {
    "femenino": "women",
    "femenil": "women",
    "mujeres": "women",
    "fem": "women",
    "reserva": "reserves",
    "reservas": "reserves",
    "sub": "u",
    "youth": "youth",
    "juvenil": "youth",
}


def _normalize(value: str) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "").lower())
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = re.sub(r"\bsub[- ]?(\d+)\b", r"u\1", raw)
    tokens = raw.split()
    translated = [_TEAM_TRANSLATION_MAP.get(t, t) for t in tokens]
    raw = " ".join(translated)
    return re.sub(r"[^a-z0-9]+", " ", raw).strip()


# Generic tokens that should not, on their own, make two team names match.
_STOPWORDS = {
    "fc", "afc", "sc", "cf", "ca", "ac", "if", "sk", "club", "de", "the",
    "women", "w", "u20", "u23", "u19", "u17", "reserves", "reserva", "reservas",
    "femenino", "femenil", "sub", "fem", "youth", "u21", "u18", "u16", "u15"
}


def _name_similarity(left: str, right: str) -> float:
    left_norm, right_norm = _normalize(left), _normalize(right)
    if not left_norm or not right_norm:
        return 0.0
    ratio = SequenceMatcher(a=left_norm, b=right_norm).ratio()
    lt = set(left_norm.split()) - _STOPWORDS
    rt = set(right_norm.split()) - _STOPWORDS
    if lt and rt:
        overlap = len(lt & rt) / min(len(lt), len(rt))
        return max(ratio, overlap)
    return ratio


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


def _extract_u_groups(text: str) -> set[str]:
    if not text:
        return set()
    text = text.lower()
    res = set()
    for m in re.finditer(r"\b(?:sub|under|u)[- ]?(\d+)", text):
        res.add(f"u{m.group(1)}")
    return res


_GENDER_KEYWORDS = {"women", "femenino", "femenil", "mujeres", "fem", "dames", "damas", "frauen", "kvinder", "kvinner"}


def _has_gender_indicator(text: str) -> bool:
    if not text:
        return False
    text = text.lower()
    tokens = set(re.findall(r"\b[a-z0-9]+\b", text))
    if tokens & _GENDER_KEYWORDS:
        return True
    if re.search(r"\b(f|w)\b", text):
        return True
    if re.search(r"\b(?:sub|under|u)[- ]?\d+(f|w)\b", text):
        return True
    return False


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
    home = _name_similarity(entry_home, event_home_str)
    away = _name_similarity(entry_away, event_away_str)
    if home < SIDE_FLOOR or away < SIDE_FLOOR:
        return 0.0
    return (home + away) / 2.0


@dataclass(frozen=True)
class LiveWatchHit:
    """A watch entry that just matched an event (live, prematch, or countdown)."""

    entry: LiveWatchEntry
    event: LiveEventSnapshot | None = None
    score: float = 0.0
    phase: str = "live"  # "live" | "pre" | "countdown" | "goal" | "red_card" | "yellow_card"
    custom_message: str | None = None


class LiveWatchService:
    """Polls live feeds and detects when watched fixtures go in-play."""

    def __init__(
        self,
        *,
        extractor_registry: ExtractorRegistry | None = None,
        repository: SqliteTrackingRepository | None = None,
    ) -> None:
        self.extractor_registry = extractor_registry or global_extractor_registry
        self.repository = repository or default_tracking_repository
        # Prematch changes slowly; cache it so the (fast) live poll doesn't re-pull
        # the whole-day lists every cycle (lighter for a VPS).
        self._prematch_cache: list[LiveEventSnapshot] | None = None
        self._prematch_cached_at = 0.0
        self._prematch_ttl_seconds = 120.0

    # ----- watchlist management (used by the bot commands) -----

    def add_fixture_lines(self, chat_id: int, lines: Iterable[str]) -> list[LiveWatchEntry]:
        """Parse pasted fixture lines and add each as a watch entry.

        Accepted per line (one match per line):
          - "Home - Away"
          - "Home vs Away" / "Home vs. Away"
          - "League | Home - Away"  (the part before '|' becomes the league hint)
        """

        added: list[LiveWatchEntry] = []
        existing_watches = self.repository.list_live_watches(chat_id, status="watching")

        for raw in lines:
            parsed = parse_fixture_line(raw)
            if parsed is None:
                continue
            league_hint, home, away, kickoff_at = parsed

            # 1. Skip past kickoff times
            if kickoff_at:
                try:
                    ko = datetime.fromisoformat(kickoff_at)
                    if ko.tzinfo is None:
                        ko = ko.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    if ko < now:
                        logger.info("Skipping watch entry because kickoff %s is in the past", kickoff_at)
                        continue
                except Exception:
                    pass

            # 2. Skip duplicates
            is_dup = False
            for entry in existing_watches:
                sim_home = _name_similarity(home, entry.home)
                sim_away = _name_similarity(away, entry.away)
                if sim_home >= 0.85 and sim_away >= 0.85:
                    is_dup = True
                    break
            if is_dup:
                logger.info("Skipping watch entry %s vs %s because it is a duplicate", home, away)
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


    def list_watches(self, chat_id: int, *, status: str | None = None) -> list[LiveWatchEntry]:
        return self.repository.list_live_watches(chat_id, status=status)

    def remove_watch(self, chat_id: int, watch_id: int) -> bool:
        return self.repository.remove_live_watch(chat_id, watch_id)

    def remove_watch_by_local_id(self, chat_id: int, local_id: int) -> bool:
        return self.repository.remove_live_watch_by_local_id(chat_id, local_id)

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
            except Exception:
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
        active_events = None
        settings_cache: dict[int, LiveWatchSettings] = {}

        for entry in watches:
            settings = settings_cache.get(entry.chat_id)
            if settings is None:
                settings = self.repository.get_live_watch_settings(entry.chat_id)
                settings_cache[entry.chat_id] = settings

            # 1. Process score/card changes from platforms where this fixture is already live.
            entry_state = entry.live_state
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
                    continue
                current_state = _event_live_state(platform_event)
                previous_state = entry_state.get(platform)
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
                    state=_event_live_state(event),
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
                        if active_events is None:
                            active_events = self.repository.get_all_active_events_with_league()

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
                self._auto_track_matched_event_league(event, entry.chat_id)
                hits.append(LiveWatchHit(entry=entry, event=event, score=score, phase="pre"))

        return hits

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
        """Delete watch entries whose time has passed (kickoff+grace, or stale)."""

        return self.repository.purge_expired_live_watches()

    def get_recommended_poll_interval(self, default_normal: float = 30.0, default_fast: float = 10.0) -> float:
        """Determine the next sleep interval based on active watch kickoffs.

        Returns default_fast (10s) if any watched fixture is in the
        [kickoff-2m, kickoff+15m] window. After +15m, entries fall back to the
        normal cadence (30s by default) even if a platform never listed them live.
        """

        watches = self.repository.list_all_active_live_watches()
        if not watches:
            return default_normal

        now = datetime.now(timezone.utc)
        for w in watches:
            if w.kickoff_at:
                try:
                    ko = datetime.fromisoformat(w.kickoff_at)
                    # Fast window: [ko - 2 min, ko + 15 min]
                    start_fast = ko - timedelta(minutes=2)
                    end_fast = ko + timedelta(minutes=15)
                    if start_fast <= now <= end_fast:
                        return default_fast
                except Exception:
                    pass
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


def _format_handicap(event: Any) -> str | None:
    if not getattr(event, "markets_json", None):
        return None
    try:
        markets = json.loads(event.markets_json)
    except Exception:
        return None
    ah = markets.get("asian_handicap")
    if not ah or not isinstance(ah, dict):
        return None
    selections = ah.get("selections")
    if not isinstance(selections, list) or not selections:
        return None

    home_sel = None
    away_sel = None
    home_norm = _normalize(event.home)
    away_norm = _normalize(event.away)
    for sel in selections:
        if not isinstance(sel, dict):
            continue
        sel_name = _normalize(sel.get("selection"))
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
    if not getattr(event, "markets_json", None):
        return None
    try:
        markets = json.loads(event.markets_json)
    except Exception:
        return None
    gl = markets.get("goal_line")
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

    if event.odds_1x2 and any(v is not None for v in (event.odds_1x2.home, event.odds_1x2.draw, event.odds_1x2.away)):
        o = event.odds_1x2
        h = str(o.home) if o.home is not None else "-"
        d = str(o.draw) if o.draw is not None else "-"
        a = str(o.away) if o.away is not None else "-"
        lines.append("")
        lines.append(f"💰 1X2: {h} / {d} / {a}")

    return "\n".join(lines)



_FIXTURE_SEPARATORS = (" - ", " – ", " vs. ", " vs ", " v ", " x ")
# Optional leading "HH:MM" (Argentina local time), e.g. "21:00 Olympia - Ballard".
_LEADING_TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s+(.*)$")
_ARG_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _kickoff_from_arg_time(hour: int, minute: int) -> str | None:
    """Build today's (or tomorrow's if in the past) Argentina kickoff as a UTC ISO timestamp."""

    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    now_arg = datetime.now(_ARG_TZ)
    kickoff = now_arg.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # If the kickoff is in the past by more than 2.5 hours, it belongs to tomorrow.
    if kickoff < now_arg and (now_arg - kickoff) > timedelta(hours=2.5):
        kickoff += timedelta(days=1)
    return kickoff.astimezone(timezone.utc).isoformat()


def parse_fixture_line(raw: str) -> tuple[str | None, str, str, str | None] | None:
    """Parse one fixture line into (league_hint, home, away, kickoff_utc) or None.

    Accepts an optional leading ``HH:MM`` (Argentina time) and an optional
    ``League | Home - Away`` prefix. Separators: ' - ', ' vs ', ' vs. ', etc.
    """

    text = (raw or "").strip()
    if not text:
        return None
    kickoff_at: str | None = None
    time_match = _LEADING_TIME_RE.match(text)
    if time_match:
        kickoff_at = _kickoff_from_arg_time(int(time_match.group(1)), int(time_match.group(2)))
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

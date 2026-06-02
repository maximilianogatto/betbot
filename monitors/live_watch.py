"""Live-watch service: alert when a watched fixture goes in-play.

The user loads fixtures (home/away, optional league hint). This service polls
every live-capable extractor, fuzzy-matches in-play events against the active
watchlist, and fires a one-shot Telegram alert the first time a fixture appears
live (with the current minute/score) — the opening seconds are when the books
misprice. Matching is per-side: both home and away must clear a similarity floor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
import logging
import re
import unicodedata
from typing import Iterable
from zoneinfo import ZoneInfo

from core.extractor_base import Extractor
from core.models import LiveEventSnapshot
from core.registry import ExtractorRegistry, extractor_registry as global_extractor_registry
from storage.tracking_repository import (
    LiveWatchEntry,
    SqliteTrackingRepository,
    tracking_repository as default_tracking_repository,
)

logger = logging.getLogger(__name__)

# Per-side similarity floor and combined floor for a confident auto-match.
SIDE_FLOOR = 0.62
COMBINED_FLOOR = 0.70


def _normalize(value: str) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "").lower())
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", raw).strip()


# Generic tokens that should not, on their own, make two team names match.
_STOPWORDS = {"fc", "afc", "sc", "cf", "ca", "ac", "if", "sk", "club", "de", "the", "women", "w", "u20", "u23", "u19", "u17"}


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


def match_score(entry: LiveWatchEntry, event: LiveEventSnapshot) -> float:
    """Per-side combined score for one watch entry vs one live event (0..1)."""

    home = _name_similarity(entry.home, event.home)
    away = _name_similarity(entry.away, event.away)
    if home < SIDE_FLOOR or away < SIDE_FLOOR:
        return 0.0
    return (home + away) / 2.0


@dataclass(frozen=True)
class LiveWatchHit:
    """A watch entry that just matched an event (live or prematch)."""

    entry: LiveWatchEntry
    event: LiveEventSnapshot
    score: float
    phase: str = "live"  # "live" (in-play, terminal) | "pre" (listed prematch, one-shot)


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
        for raw in lines:
            parsed = parse_fixture_line(raw)
            if parsed is None:
                continue
            league_hint, home, away, kickoff_at = parsed
            added.append(
                self.repository.add_live_watch(
                    chat_id,
                    home=home,
                    away=away,
                    league_hint=league_hint,
                    note=raw.strip(),
                    kickoff_at=kickoff_at,
                )
            )
        return added

    def list_watches(self, chat_id: int, *, status: str | None = None) -> list[LiveWatchEntry]:
        return self.repository.list_live_watches(chat_id, status=status)

    def remove_watch(self, chat_id: int, watch_id: int) -> bool:
        return self.repository.remove_live_watch(chat_id, watch_id)

    def remove_watch_by_local_id(self, chat_id: int, local_id: int) -> bool:
        return self.repository.remove_live_watch_by_local_id(chat_id, local_id)

    def clear_watches(self, chat_id: int, *, status: str | None = None) -> int:
        return self.repository.clear_live_watches(chat_id, status=status)

    # ----- polling -----

    def _live_extractors(self) -> list[Extractor]:
        return [e for e in self.extractor_registry.list_registered() if getattr(e, "supports_live_detection", False)]

    def _prematch_extractors(self) -> list[Extractor]:
        return [e for e in self.extractor_registry.list_registered() if getattr(e, "supports_prematch_listing", False)]

    async def collect_live_events(self) -> list[LiveEventSnapshot]:
        """Gather in-play soccer events from every live-capable extractor."""

        events: list[LiveEventSnapshot] = []
        for extractor in self._live_extractors():
            try:
                events.extend(await extractor.list_live_events())
            except Exception:
                logger.exception("Live fetch failed platform=%s", extractor.name)
        return events

    async def collect_prematch_events(self) -> list[LiveEventSnapshot]:
        """Gather currently-listed prematch soccer events (cached ~120s)."""

        import time as _time

        now = _time.monotonic()
        if self._prematch_cache is not None and (now - self._prematch_cached_at) < self._prematch_ttl_seconds:
            return self._prematch_cache
        events: list[LiveEventSnapshot] = []
        for extractor in self._prematch_extractors():
            try:
                events.extend(await extractor.list_prematch_events())
            except Exception:
                logger.exception("Prematch fetch failed platform=%s", extractor.name)
        if events:
            self._prematch_cache = events
            self._prematch_cached_at = now
        return events

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
        if not live_events and not prematch_events:
            return []

        hits: list[LiveWatchHit] = []
        for entry in watches:
            live_best = self._best_match(entry, live_events) if live_events else None
            if live_best is not None:
                score, event = live_best
                self.repository.mark_live_watch_fired(
                    entry.id, platform=event.platform, event_id=event.external_event_id, minute=event.minute
                )
                hits.append(LiveWatchHit(entry=entry, event=event, score=score, phase="live"))
                continue
            # Not live: surface a one-shot prematch listing (only once per entry).
            if entry.prematch_seen_at:
                continue
            pre_best = self._best_match(entry, prematch_events) if prematch_events else None
            if pre_best is None:
                continue
            score, event = pre_best
            self.repository.mark_live_watch_prematch_seen(
                entry.id, platform=event.platform, event_id=event.external_event_id
            )
            hits.append(LiveWatchHit(entry=entry, event=event, score=score, phase="pre"))
        return hits

    def purge_expired(self) -> int:
        """Delete watch entries whose time has passed (kickoff+grace, or stale)."""

        return self.repository.purge_expired_live_watches()

    def get_recommended_poll_interval(self, default_normal: float = 60.0, default_fast: float = 15.0) -> float:
        """Determine the next sleep interval based on active watch kickoffs.

        Returns default_fast (15s) if any watched fixture starts in <= 2 min
        or started <= 15 min ago, otherwise default_normal (60s).
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



def render_live_hit(hit: LiveWatchHit) -> str:
    """Build the Telegram alert for a watched fixture (live or prematch listing)."""

    event = hit.event
    book = event.platform.replace("_http", "")
    if hit.phase == "pre":
        lines = ["📋 LISTADO EN PRE — apareció tu partido", f"⚽ {event.home} vs {event.away}"]
        league_bits = " · ".join(b for b in (event.country_name, event.competition_name) if b)
        if league_bits:
            lines.append(f"🏆 {league_bits}")
        lines.append(f"🏦 ya está en {book} (prematch) — sigo vigilando para el vivo")
        if hit.entry.note and hit.entry.note.strip() not in (f"{event.home} - {event.away}",):
            lines.append(f"📝 {hit.entry.note.strip()}")
        return "\n".join(lines)

    lines = ["🔴 EN VIVO — salió tu partido", f"⚽ {event.home} vs {event.away}"]
    league_bits = " · ".join(b for b in (event.country_name, event.competition_name) if b)
    if league_bits:
        lines.append(f"🏆 {league_bits}")
    clock = event.minute or "en juego"
    if event.home_score is not None and event.away_score is not None:
        clock += f"  |  {event.home_score}-{event.away_score}"
    lines.append(f"⏱️ {clock}")
    if event.odds_1x2 and any(v is not None for v in (event.odds_1x2.home, event.odds_1x2.draw, event.odds_1x2.away)):
        o = event.odds_1x2
        lines.append(f"💰 1X2: {o.home} / {o.draw} / {o.away}")
    lines.append(f"🏦 {book}")
    if hit.entry.note and hit.entry.note.strip() not in (f"{event.home} - {event.away}",):
        lines.append(f"📝 {hit.entry.note.strip()}")
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

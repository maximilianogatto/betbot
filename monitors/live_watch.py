"""Live-watch service: alert when a watched fixture goes in-play.

The user loads fixtures (home/away, optional league hint). This service polls
every live-capable extractor, fuzzy-matches in-play events against the active
watchlist, and fires a one-shot Telegram alert the first time a fixture appears
live (with the current minute/score) — the opening seconds are when the books
misprice. Matching is per-side: both home and away must clear a similarity floor.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import logging
import re
import unicodedata
from typing import Iterable

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
    """A watch entry that just matched a live event."""

    entry: LiveWatchEntry
    event: LiveEventSnapshot
    score: float


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
            league_hint, home, away = parsed
            added.append(
                self.repository.add_live_watch(
                    chat_id, home=home, away=away, league_hint=league_hint, note=raw.strip()
                )
            )
        return added

    def list_watches(self, chat_id: int, *, status: str | None = None) -> list[LiveWatchEntry]:
        return self.repository.list_live_watches(chat_id, status=status)

    def remove_watch(self, chat_id: int, watch_id: int) -> bool:
        return self.repository.remove_live_watch(chat_id, watch_id)

    def clear_watches(self, chat_id: int, *, status: str | None = None) -> int:
        return self.repository.clear_live_watches(chat_id, status=status)

    # ----- polling -----

    def _live_extractors(self) -> list[Extractor]:
        return [e for e in self.extractor_registry.list_registered() if e.supports_live_detection]

    async def collect_live_events(self) -> list[LiveEventSnapshot]:
        """Gather in-play soccer events from every live-capable extractor."""

        events: list[LiveEventSnapshot] = []
        for extractor in self._live_extractors():
            try:
                events.extend(await extractor.list_live_events())
            except Exception:
                logger.exception("Live fetch failed platform=%s", extractor.name)
        return events

    async def poll_once(self) -> list[LiveWatchHit]:
        """Match active watches against current live events; mark hits fired."""

        watches = self.repository.list_all_active_live_watches()
        if not watches:
            return []
        live_events = await self.collect_live_events()
        if not live_events:
            return []

        hits: list[LiveWatchHit] = []
        for entry in watches:
            best: tuple[float, LiveEventSnapshot] | None = None
            for event in live_events:
                score = match_score(entry, event)
                if score >= COMBINED_FLOOR and (best is None or score > best[0]):
                    best = (score, event)
            if best is None:
                continue
            score, event = best
            self.repository.mark_live_watch_fired(
                entry.id, platform=event.platform, event_id=event.external_event_id, minute=event.minute
            )
            hits.append(LiveWatchHit(entry=entry, event=event, score=score))
        return hits


def render_live_hit(hit: LiveWatchHit) -> str:
    """Build the Telegram alert text for a fixture that just went live."""

    event = hit.event
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
    lines.append(f"🏦 {event.platform.replace('_http', '')}")
    if hit.entry.note and hit.entry.note.strip() not in (f"{event.home} - {event.away}",):
        lines.append(f"📝 {hit.entry.note.strip()}")
    return "\n".join(lines)


_FIXTURE_SEPARATORS = (" - ", " – ", " vs. ", " vs ", " v ", " x ")


def parse_fixture_line(raw: str) -> tuple[str | None, str, str] | None:
    """Parse one fixture line into (league_hint, home, away), or None if unusable."""

    text = (raw or "").strip()
    if not text:
        return None
    league_hint: str | None = None
    if "|" in text:
        head, _, tail = text.partition("|")
        league_hint, text = head.strip() or None, tail.strip()
    for sep in _FIXTURE_SEPARATORS:
        if sep in text:
            home, _, away = text.partition(sep)
            home, away = home.strip(), away.strip()
            if home and away:
                return league_hint, home, away
    return None

"""Canonical (physical) league reconstruction + rendering.

A canonical league groups the per-platform `tracked_competitions` that are the
same real-world league. Everything the user wants to see — which platforms track
it, the league id/name on each, and the linked stats providers — is RECONSTRUCTED
here from the grouped tracked competitions + their stats links (nothing extra is
stored). The "league card" is rendered in a fixed platform order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import Any, Optional

# Fixed presentation order of odds platforms (user preference); unknown
# platforms are appended after these.
PLATFORM_ORDER: list[str] = [
    "1xbet_http",
    "betovo_http",
    "solcasino_http",
    "betwarrior_http",
    "bz_http",
    "bet365",
    "mystake_http",
    "mrpunter_http",
    "betsson_http",
]

_DISPLAY_NAMES: dict[str, str] = {
    "1xbet_http": "1xBet",
    "betovo_http": "Betovo",
    "solcasino_http": "Solcasino",
    "betwarrior_http": "BetWarrior",
    "bz_http": "BZ",
    "bet365": "Bet365",
    "mystake_http": "Mystake",
    "mrpunter_http": "MrPunter",
    "betsson_http": "Betsson",
}


@dataclass
class PlatformEntry:
    platform: str
    display_name: str
    tracking: bool
    league_id: Optional[str] = None
    league_name: Optional[str] = None


@dataclass
class StatsEntry:
    provider: str
    stats_league_id: str
    stats_league_name: str = ""


@dataclass
class LeagueCard:
    id: int
    name: str
    platforms: list[PlatformEntry] = field(default_factory=list)
    stats: list[StatsEntry] = field(default_factory=list)

    @property
    def has_stats(self) -> bool:
        return bool(self.stats)

    @property
    def tracked_count(self) -> int:
        return sum(1 for p in self.platforms if p.tracking)


def _ordered_platforms(present: set[str]) -> list[str]:
    extras = [p for p in sorted(present) if p not in PLATFORM_ORDER]
    return PLATFORM_ORDER + extras


def _display(platform: str) -> str:
    return _DISPLAY_NAMES.get(platform, platform.replace("_http", "").capitalize())


def build_league_card(repo: Any, canonical_league_id: int) -> Optional[LeagueCard]:
    """Reconstruct the league card from the grouped tracked competitions + stats."""

    meta = repo.get_unified_competition(canonical_league_id)
    if not meta:
        return None
    comps = repo.list_tracked_competitions_for_unified(canonical_league_id)
    by_platform = {c.platform: c for c in comps}

    platforms: list[PlatformEntry] = []
    for key in _ordered_platforms(set(by_platform)):
        comp = by_platform.get(key)
        platforms.append(PlatformEntry(
            platform=key,
            display_name=_display(key),
            tracking=comp is not None,
            league_id=getattr(comp, "competition_external_id", None) if comp else None,
            league_name=getattr(comp, "competition_name", None) if comp else None,
        ))

    stats: list[StatsEntry] = []
    seen: set[tuple[str, str]] = set()
    for comp in comps:
        try:
            links = repo.list_stats_league_links(comp.id)
        except Exception:
            links = []
        for link in links:
            key = (link.stats_provider, link.stats_league_id)
            if key in seen:
                continue
            seen.add(key)
            stats.append(StatsEntry(
                provider=link.stats_provider,
                stats_league_id=link.stats_league_id,
                stats_league_name=getattr(link, "stats_league_name", "") or "",
            ))

    return LeagueCard(id=canonical_league_id, name=meta["name"], platforms=platforms, stats=stats)


def render_league_card(card: LeagueCard) -> str:
    """HTML league card: name + per-platform tracking/id + stats."""

    lines = [
        f"🏆 <b>{escape(card.name)}</b>  <code>#{card.id}</code>",
        f"📡 <b>Plataformas</b> ({card.tracked_count} trackeadas):",
    ]
    for p in card.platforms:
        if p.tracking:
            lid = f" — id <code>{escape(str(p.league_id))}</code>" if p.league_id else ""
            name = f"  <i>{escape(str(p.league_name))}</i>" if p.league_name else ""
            lines.append(f"  ✅ <b>{escape(p.display_name)}</b>{lid}{name}")
        else:
            lines.append(f"  ⚪️ {escape(p.display_name)} <i>(sin trackear)</i>")

    if card.has_stats:
        lines.append(f"📊 <b>Stats</b>: ✅ ({len(card.stats)})")
        for s in card.stats:
            nm = f" — {escape(s.stats_league_name)}" if s.stats_league_name else ""
            lines.append(f"  • {escape(s.provider)}: <code>{escape(str(s.stats_league_id))}</code>{nm}")
    else:
        lines.append("📊 <b>Stats</b>: ⚪️ sin linkear")

    return "\n".join(lines)


def render_leagues_list(cards: list[LeagueCard]) -> str:
    """Compact numbered list of canonical leagues for selection."""

    if not cards:
        return (
            "📭 Todavía no hay ligas canónicas armadas.\n"
            "Trackeá una liga en varias plataformas y se irán linkeando (o usá /link_league)."
        )
    from core.league_naming import name_country_flag

    lines = ["🏆 <b>Ligas canónicas</b>", "━━━━━━━━━━━━━━━━━━━━"]
    for i, card in enumerate(cards, start=1):
        stat = "📊" if card.has_stats else "  "
        _, flag = name_country_flag(card.name)
        prefix = f"{flag} " if flag else ""
        lines.append(f"{i}. {prefix}{escape(card.name)} — {card.tracked_count} plat. {stat}")
    lines.append("")
    lines.append("👉 Ver detalle: <code>/league [N]</code>")
    return "\n".join(lines)

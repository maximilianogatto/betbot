"""League discovery from the Betovo (Altenar) GetEvents feed.

Each ``category`` (country) carries a ``champIds`` list; champ names come from the
``champs`` dict; prematch match counts are derived from the ``events`` list.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from typing import Any

from core.extractor_base import LeagueDiscoveryOption


def _normalize_text(value: object | None) -> str:
    raw = str(value or "").strip().lower()
    decomposed = unicodedata.normalize("NFKD", raw)
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _matches_country(country_name: str, country_filter: str) -> bool:
    if not country_filter:
        return True
    normalized = _normalize_text(country_name)
    return country_filter == normalized or country_filter in normalized


def build_league_options(
    events_payload: dict[str, Any],
    *,
    platform: str,
    platform_display_name: str,
    country_name: str,
    query: str | None = None,
    limit: int = 80,
) -> list[LeagueDiscoveryOption]:
    """Return leagues whose country matches, with prematch match counts."""

    champs = {c["id"]: c for c in events_payload.get("champs") or [] if isinstance(c, dict) and "id" in c}
    categories = [c for c in events_payload.get("categories") or [] if isinstance(c, dict)]
    counts = Counter(
        e.get("champId") for e in events_payload.get("events") or [] if isinstance(e, dict) and e.get("champId") is not None
    )

    country_filter = _normalize_text(country_name)
    query_filter = _normalize_text(query)

    options: list[LeagueDiscoveryOption] = []
    seen: set[str] = set()
    for category in categories:
        country = str(category.get("name") or "Desconocido")
        if not _matches_country(country, country_filter):
            continue
        for champ_id in category.get("champIds") or []:
            champ = champs.get(champ_id)
            if not champ:
                continue
            league_name = str(champ.get("name") or champ_id)
            if query_filter and query_filter not in _normalize_text(league_name):
                continue
            key = str(champ_id)
            if key in seen:
                continue
            seen.add(key)
            options.append(
                LeagueDiscoveryOption(
                    platform=platform,
                    platform_display_name=platform_display_name,
                    country_id=str(category.get("id")) if category.get("id") is not None else None,
                    country_name=country,
                    league_id=key,
                    league_name=league_name,
                    source_url=f"betovo:champ:{key}",
                    games_count=int(counts.get(champ_id, 0)),
                    raw_payload={"source": "altenar_GetEvents", "champ_id": key},
                )
            )

    options.sort(key=lambda option: (option.country_name.lower(), option.league_name.lower()))
    return options[:limit]

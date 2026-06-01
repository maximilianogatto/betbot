"""Parsers for Flashscore's proprietary ``~ / ¬ / ÷`` feed format.

Format: records are separated by ``~``, fields within a record by ``¬``, and each
field is ``KEY÷value``. The day-fixtures feed interleaves league-header records
(key ``ZA`` = "COUNTRY: League") with the match records that follow them
(``AA`` = event id, ``AE``/``AF`` = home/away, ``AD`` = unix kickoff, ``AG``/``AH``
= scores, ``AB`` = status). Decoded here into compact dicts; external ids are kept
verbatim so a future provider can normalize them at its boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Status codes seen in the day feed (AB): 1=scheduled, 2=live-ish, 3=finished.
_STATUS = {"1": "scheduled", "2": "live", "3": "finished"}


def parse_records(text: str) -> list[dict[str, str]]:
    """Split a raw feed body into a list of {KEY: value} records."""

    records: list[dict[str, str]] = []
    for raw in text.split("~"):
        raw = raw.strip("¬").strip()
        if not raw:
            continue
        fields: dict[str, str] = {}
        for token in raw.split("¬"):
            key, sep, value = token.partition("÷")
            if sep:
                fields[key] = value
        if fields:
            records.append(fields)
    return records


def _kickoff_iso(raw: str | None) -> str | None:
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def _split_country_league(za: str) -> tuple[str | None, str]:
    """'ARGENTINA: Liga Profesional' -> ('Argentina', 'Liga Profesional')."""

    if ":" in za:
        country, _, name = za.partition(":")
        return country.strip().title(), name.strip()
    return None, za.strip()


def parse_day_fixtures(text: str) -> list[dict[str, Any]]:
    """Return leagues with their matches from a ``f_<sport>_<day>_...`` feed."""

    leagues: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for rec in parse_records(text):
        if "ZA" in rec:  # league header
            country, name = _split_country_league(rec.get("ZA", ""))
            current = {
                "league_id": rec.get("ZEE") or rec.get("ZC"),
                "tournament_stage_id": rec.get("ZC"),
                "country": country,
                "league_name": name,
                "raw_name": rec.get("ZA"),
                "matches": [],
            }
            leagues.append(current)
        elif "AA" in rec and "AE" in rec and current is not None:  # match
            current["matches"].append(
                {
                    "match_id": rec.get("AA"),
                    "home": rec.get("AE"),
                    "away": rec.get("AF"),
                    "kickoff_utc": _kickoff_iso(rec.get("AD")),
                    "home_score": rec.get("AG") or None,
                    "away_score": rec.get("AH") or None,
                    "status": _STATUS.get(rec.get("AB", ""), rec.get("AB")),
                }
            )
    return leagues


def leagues_by_country(text: str, country_name: str) -> list[dict[str, Any]]:
    """Day-feed leagues whose country matches (case-insensitive substring)."""

    target = (country_name or "").strip().lower()
    out = []
    for league in parse_day_fixtures(text):
        country = (league.get("country") or "").lower()
        raw = (league.get("raw_name") or "").lower()
        if not target or target in country or target in raw:
            out.append(league)
    return out


def parse_statistics(text: str) -> list[dict[str, str]]:
    """Return statistic rows: {name, home, away} from a ``df_st`` feed.

    Field codes: ``SG`` = stat name, ``SH`` = home value, ``SI`` = away value
    (grouped under ``SE`` period sections / ``SF`` group titles).
    """

    stats: list[dict[str, str]] = []
    for rec in parse_records(text):
        if "SG" in rec and ("SH" in rec or "SI" in rec):
            stats.append({"name": rec.get("SG", ""), "home": rec.get("SH", ""), "away": rec.get("SI", "")})
    return stats


def parse_incidents(text: str) -> list[dict[str, str]]:
    """Return timeline incidents: {minute, type, side, player} from a ``df_sui`` feed.

    ``IB`` = minute label, ``IE`` = incident type, ``IO?/IN?`` = running score,
    ``IF``/player fields = participant. Side inferred from which score field moves.
    """

    incidents: list[dict[str, str]] = []
    for rec in parse_records(text):
        if "IB" in rec:
            incidents.append(
                {
                    "minute": rec.get("IB", ""),
                    "type": rec.get("IE", ""),
                    "home_score": rec.get("IOX") or rec.get("INX") or "",
                    "away_score": rec.get("IOY") or rec.get("INY") or "",
                    "player": rec.get("IF") or rec.get("IK") or "",
                }
            )
    return incidents

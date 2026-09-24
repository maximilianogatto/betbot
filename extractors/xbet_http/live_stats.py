"""Panel de estadísticas de un partido en vivo de 1xBet (el mismo que muestra Melbet).

`LiveFeed/GetGameZip?id=<evento>` trae en `SC.ST` las estadísticas del partido
(bloque Key=0) y en `SC` el marcador (`FS`, omite los ceros), el período (`CP`/`CPS`),
los tiempos (`PS`) y los segundos jugados (`TS`).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from core.live_stats import LiveStatsSnapshot
from extractors.xbet_http.client import XBetHttpClient, normalize_linefeed_base_url

SOURCE = "1xbet"
#: ID de estadística de 1xBet -> clave del panel.
_STAT_IDS = {45: "attacks", 58: "dangerous_attacks", 29: "possession", 59: "shots_on_target",
             60: "shots_off_target", 26: "yellow_cards", 70: "corners", 71: "red_cards",
             72: "penalties", 92: "substitutions"}
_PERIODS = {"1st half": "1T", "2nd half": "2T", "half-time": "Entretiempo", "halftime": "Entretiempo",
            "extra time": "Alargue", "penalties": "Penales", "game finished": "Final",
            "match finished": "Final"}


def build_live_game_url(*, base_url: str, event_id: str, language: str) -> str:
    live_base = normalize_linefeed_base_url(base_url).replace("/LineFeed", "/LiveFeed")
    return f"{live_base}/GetGameZip?{urlencode({'id': event_id, 'lng': language})}"


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_game_stats(payload: dict[str, Any]) -> LiveStatsSnapshot | None:
    """El panel de un GetGameZip de LiveFeed, o None si el partido ya no está."""

    value = payload.get("Value") if isinstance(payload, dict) else None
    if not isinstance(value, dict) or not value.get("O1"):
        return None
    sc = value.get("SC") if isinstance(value.get("SC"), dict) else {}
    stats: dict[str, tuple[int | None, int | None]] = {}
    for block in sc.get("ST") or []:
        if not isinstance(block, dict) or block.get("Key") != 0:
            continue  # 0 = el partido entero; los otros bloques son por tiempo
        for item in block.get("Value") or []:
            if not isinstance(item, dict):
                continue
            key = _STAT_IDS.get(item.get("ID")) or str(item.get("N") or "").strip()
            if key:
                stats[key] = (_int(item.get("S1")), _int(item.get("S2")))
    score = sc.get("FS") if isinstance(sc.get("FS"), dict) else {}
    ht_score = None
    if (_int(sc.get("CP")) or 0) >= 2:  # ya terminó el 1er tiempo
        for period in sc.get("PS") or []:
            if isinstance(period, dict) and period.get("Key") == 1:
                first = period.get("Value") or {}
                ht_score = (_int(first.get("S1")) or 0, _int(first.get("S2")) or 0)
    status = str(sc.get("CPS") or "").strip()
    seconds = _int(sc.get("TS"))
    return LiveStatsSnapshot(
        source=SOURCE, home=str(value["O1"]), away=str(value.get("O2") or ""), stats=stats,
        home_score=_int(score.get("S1")) or 0, away_score=_int(score.get("S2")) or 0,
        ht_score=ht_score, period=_PERIODS.get(status.lower(), status or None),
        minute=f"{seconds // 60}'" if seconds else None,
        competition=str(value.get("L") or "") or None,
    )


async def fetch_game_stats(client: XBetHttpClient, event_id: str) -> LiveStatsSnapshot | None:
    url = build_live_game_url(base_url=client.settings.base_url, event_id=str(event_id),
                              language=client.settings.language)
    return parse_game_stats(await client.fetch_game_zip(url))

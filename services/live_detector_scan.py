"""Orquestación viva del detector de Producto B (plan §9).

Toma los eventos vivos que ya recolecta el bot (``LiveEventSnapshot`` de las
casas), y por cada uno ensambla los tres inputs del detector:
  1. línea justa PRE-MATCH del modelo (vía ``PredictionService``),
  2. estado en vivo (minuto/marcador/rojas/frescura) del snapshot,
  3. cuotas 1X2 en vivo de la casa,
y corre ``services.live_detector``. Devuelve TODOS los resultados (disparó o no,
o por qué no se pudo) para poder medir la tasa de falsos positivos, no
estimarla de memoria. Python puro (capa services); no toca el esquema.

La resolución de identidad sale directo del snapshot: ``competition_name`` +
``country_name`` → league_code, y ``home``/``away`` → team_ids (alias/fuzzy).
Fuera de las ligas del modelo, el ítem queda 'unavailable' con motivo — nunca se
inventa una línea.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from services.live_detector import (
    DetectionResult, DetectorParams, LiveState, evaluate_from_prediction)

_HT = {"ht", "half", "medio tiempo", "descanso", "entretiempo", "2a parte", "2ª parte"}
_FT = {"ft", "final", "finalizado", "full time"}


@dataclass(frozen=True)
class LiveScanItem:
    platform: str
    external_event_id: str
    home: str
    away: str
    league_code: str | None
    status: str                      # 'fired' | 'no_edge' | 'unavailable' | 'no_state'
    reason: str
    detection: DetectionResult | None = None


def parse_minute(label: object) -> int | None:
    """Minuto (int) desde el label del feed ('12'', 'HT', '2ª parte', '45+2')."""
    if label is None:
        return None
    s = str(label).strip().lower()
    if not s:
        return None
    if s in _HT:
        return 45
    if s in _FT:
        return 90
    m = re.match(r"\s*(\d+)", s)
    if not m:
        return None
    base = int(m.group(1))
    extra = re.search(r"\+(\d+)", s)          # tiempo añadido: 45+2, 90+3
    if extra:
        base += int(extra.group(1))
    return min(base, 90)


def _staleness_seconds(extracted_at: str, now: datetime) -> float:
    if not extracted_at:
        return 0.0
    try:
        iso = extracted_at.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (now - dt).total_seconds())
    except (ValueError, TypeError):
        return 0.0


def _book_odds(snapshot) -> tuple[float, float, float] | None:
    o = getattr(snapshot, "odds_1x2", None)
    if o is None or None in (o.home, o.draw, o.away):
        return None
    return (o.home, o.draw, o.away)


def scan_live_events(snapshots, svc, params: DetectorParams | None = None,
                     now: datetime | None = None) -> list[LiveScanItem]:
    """Corre el detector sobre una lista de LiveEventSnapshot. Devuelve todos los ítems."""
    now = now or datetime.now(timezone.utc)
    items: list[LiveScanItem] = []
    for s in snapshots:
        if not getattr(s, "is_soccer", True):
            continue
        pred, reason = svc.predict_for_fixture(
            s.competition_name or "", s.home, s.away, country=s.country_name)
        if pred is None:
            items.append(LiveScanItem(s.platform, s.external_event_id, s.home, s.away,
                                      None, "unavailable", reason))
            continue
        minute = parse_minute(s.minute)
        if minute is None:
            items.append(LiveScanItem(s.platform, s.external_event_id, s.home, s.away,
                                      pred.league_code, "no_state",
                                      f"minuto no parseable: {s.minute!r}"))
            continue
        state = LiveState(
            minute=minute,
            current_home=s.home_score or 0,
            current_away=s.away_score or 0,
            red_home=s.home_red_cards or 0,
            red_away=s.away_red_cards or 0,
            state_age_seconds=_staleness_seconds(getattr(s, "extracted_at", ""), now),
        )
        det = evaluate_from_prediction(pred, state, _book_odds(s), params)
        items.append(LiveScanItem(
            s.platform, s.external_event_id, s.home, s.away, pred.league_code,
            "fired" if det.fired else "no_edge", det.reason, det))
    return items


def format_alert(item: LiveScanItem) -> str:
    """Alerta legible para un ítem que disparó (para cuando se cablee la notificación)."""
    d = item.detection
    return (f"⚠️ Posible error de la casa — {item.home} vs {item.away} "
            f"[{item.league_code} · {item.platform}]\n{d.reason}\n"
            f"modelo H/D/A: {d.model_probs[0]:.0%}/{d.model_probs[1]:.0%}/{d.model_probs[2]:.0%}"
            + (f" · casa: {d.book_probs[0]:.0%}/{d.book_probs[1]:.0%}/{d.book_probs[2]:.0%}"
               if d.book_probs else ""))


async def scan_live(live_watch_service, svc, params: DetectorParams | None = None
                    ) -> list[LiveScanItem]:
    """Wrapper vivo: recolecta los eventos vivos del bot y corre el scan.

    ``live_watch_service`` = ``services.live_watch.LiveWatchService`` (o cualquier
    objeto con ``collect_live_events()`` async). Este es el único punto que toca
    la red; ``scan_live_events`` es puro y se testea con snapshots sintéticos.
    """
    snapshots = await live_watch_service.collect_live_events()
    return scan_live_events(snapshots, svc, params)

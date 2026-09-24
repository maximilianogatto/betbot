"""Estadísticas en vivo de un partido: el panel de ataques, posesión, tiros... de las casas.

Cada fuente (1xBet, Statshub) se traduce a las mismas claves; `merge_live_stats`
arma un solo panel tomando cada estadística de la primera fuente que la tenga.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: (clave, etiqueta, sufijo) en el orden en que se muestran.
LIVE_STAT_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("attacks", "Ataques", ""),
    ("dangerous_attacks", "Ataques peligrosos", ""),
    ("possession", "Posesión", "%"),
    ("shots_on_target", "Tiros al arco", ""),
    ("shots_off_target", "Tiros afuera", ""),
    ("shots_blocked", "Tiros bloqueados", ""),
    ("corners", "Córners", ""),
    ("yellow_cards", "Amarillas", ""),
    ("red_cards", "Rojas", ""),
    ("penalties", "Penales", ""),
    ("fouls", "Faltas", ""),
    ("offsides", "Offsides", ""),
    ("saves", "Atajadas", ""),
    ("free_kicks", "Tiros libres", ""),
    ("goal_kicks", "Saques de arco", ""),
    ("throw_ins", "Laterales", ""),
    ("substitutions", "Cambios", ""),
)
_FIELD_ORDER = {key: index for index, (key, _, _) in enumerate(LIVE_STAT_FIELDS)}
_FIELD_INFO = {key: (label, suffix) for key, label, suffix in LIVE_STAT_FIELDS}

Pair = tuple[int | None, int | None]


@dataclass(frozen=True)
class LiveStatsSnapshot:
    """Lo que una fuente dice de un partido en este momento."""

    source: str
    home: str
    away: str
    stats: dict[str, Pair] = field(default_factory=dict)
    home_score: int | None = None
    away_score: int | None = None
    ht_score: tuple[int, int] | None = None
    period: str | None = None  # "1T", "Entretiempo", "2T", "Final"...
    minute: str | None = None
    competition: str | None = None


@dataclass(frozen=True)
class LiveStatRow:
    key: str
    label: str
    suffix: str
    home: int | None
    away: int | None
    source: str


@dataclass(frozen=True)
class LiveStatsView:
    """El panel listo para mostrar: encabezado de la fuente principal + filas unidas."""

    home: str
    away: str
    rows: tuple[LiveStatRow, ...]
    sources: tuple[str, ...]
    home_score: int | None = None
    away_score: int | None = None
    ht_score: tuple[int, int] | None = None
    period: str | None = None
    minute: str | None = None
    competition: str | None = None


def merge_live_stats(snapshots: list[LiveStatsSnapshot]) -> LiveStatsView | None:
    """Une las fuentes en orden de prioridad: cada fila sale de la primera que la tenga.

    El encabezado (marcador, período) también sale de la primera que lo tenga. Las
    estadísticas que no están en LIVE_STAT_FIELDS van al final con su nombre original.
    """
    snapshots = [snapshot for snapshot in snapshots if snapshot is not None]
    if not snapshots:
        return None
    rows: dict[str, LiveStatRow] = {}
    for snapshot in snapshots:
        for key, (home, away) in snapshot.stats.items():
            if key in rows or (home is None and away is None):
                continue
            label, suffix = _FIELD_INFO.get(key, (key, ""))
            rows[key] = LiveStatRow(key, label, suffix, home, away, snapshot.source)
    ordered = sorted(rows.values(), key=lambda row: (_FIELD_ORDER.get(row.key, len(_FIELD_ORDER)), row.label))
    used = tuple(dict.fromkeys(row.source for row in ordered))

    def first(attribute: str):
        return next((getattr(s, attribute) for s in snapshots if getattr(s, attribute) is not None), None)

    scored = next((s for s in snapshots if s.home_score is not None and s.away_score is not None), None)
    main = snapshots[0]
    return LiveStatsView(
        home=main.home, away=main.away, rows=tuple(ordered),
        sources=used or (main.source,),
        home_score=scored.home_score if scored else None,
        away_score=scored.away_score if scored else None,
        ht_score=first("ht_score"), period=first("period"), minute=first("minute"),
        competition=first("competition"),
    )

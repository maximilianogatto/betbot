"""Puente modelo → bot: sirve la línea justa desde el artefacto del modelo.

Carga ``models/prediction_fit.json`` (producido por ``research/peak_models/
export_fit.py``) y, dado un partido, deriva λ_home/λ_away y la línea justa
(``core.fair_line``). **No importa research/** — el runtime del bot no tiene
numpy; el entrenamiento vive en research, el bot sólo consume el artefacto.

Regla §10 del plan: si la liga o alguno de los equipos no está en el fit, la
predicción es **no disponible** (``None`` + motivo). Nunca se extrapola en
silencio una línea inventada.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from core.fair_line import FairLine, fair_line
from core.league_naming import (
    normalize_league_name, normalize_team_name, team_name_similarity)

_MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
_DEFAULT_ARTIFACT = _MODELS_DIR / "prediction_fit.json"
_DEFAULT_ALIASES = _MODELS_DIR / "team_aliases.json"
_DEFAULT_LEAGUE_MAP = _MODELS_DIR / "league_map.json"
_RESOLVE_THRESHOLD = 0.85    # confianza mínima (igual que el merge de ligas)
_RESOLVE_MARGIN = 0.05       # el mejor debe superar al segundo por esto (anti-ambigüedad)


@dataclass(frozen=True)
class Prediction:
    """Línea justa de un partido + metadatos de trazabilidad."""

    league_code: str
    home_team_id: str
    away_team_id: str
    line: FairLine
    model_version: str
    trained_through: str


class PredictionUnavailable(Exception):
    """La línea no puede calcularse (liga/equipo fuera del fit). No es un error."""


class PredictionService:
    def __init__(self, artifact_path: str | Path | None = None,
                 aliases_path: str | Path | None = None,
                 league_map_path: str | Path | None = None) -> None:
        self._path = Path(artifact_path) if artifact_path else _DEFAULT_ARTIFACT
        self._aliases_path = Path(aliases_path) if aliases_path else _DEFAULT_ALIASES
        self._league_map_path = Path(league_map_path) if league_map_path else _DEFAULT_LEAGUE_MAP
        self._artifact: dict | None = None
        self._aliases: dict | None = None
        self._league_map: list | None = None
        self._index: dict[str, dict] = {}   # league_code -> {"exact": {norm: id}, "cands": [(id, name)]}

    def _load_league_map(self) -> list:
        """Lista de (league_code, country, gender, [patrones_normalizados])."""
        if self._league_map is None:
            try:
                raw = json.loads(self._league_map_path.read_text())
            except (FileNotFoundError, ValueError):
                raw = {}
            self._league_map = [
                (lg, spec.get("country"), spec.get("gender"),
                 [normalize_league_name(p) for p in spec.get("patterns", [])])
                for lg, spec in raw.items()
                if not lg.startswith("_") and isinstance(spec, dict)
            ]
        return self._league_map

    def _load_aliases(self) -> dict:
        """Alias por liga {league: {alias: team_id}}. Archivo de datos, no esquema.

        Puentea el hueco entre el nombre de la casa (p.ej. 'HJK Helsinki') y el
        nombre legal de la federación con el que se entrenó ('Helsingin
        Jalkapalloklubin Liiga-HJK'), que el fuzzy no cubre. Extensible (curado o
        aprendido); vacío si no existe el archivo.
        """
        if self._aliases is None:
            try:
                raw = json.loads(self._aliases_path.read_text())
            except (FileNotFoundError, ValueError):
                raw = {}
            self._aliases = {
                lg: {normalize_team_name(a): tid for a, tid in amap.items()}
                for lg, amap in raw.items()
                if not lg.startswith("_") and isinstance(amap, dict)
            }
        return self._aliases

    def _load(self) -> dict:
        if self._artifact is None:
            self._artifact = json.loads(self._path.read_text())
        return self._artifact

    @property
    def model_version(self) -> str:
        return self._load().get("model_version", "unknown")

    @property
    def trained_through(self) -> str:
        return self._load().get("trained_through", "")

    def available_leagues(self) -> list[str]:
        return sorted(self._load().get("leagues", {}))

    def predict_or_reason(self, league_code: str, home_team_id, away_team_id):
        """Devuelve (Prediction | None, motivo). motivo="" si hay predicción."""
        art = self._load()
        lg = art.get("leagues", {}).get(league_code)
        if lg is None:
            return None, f"liga '{league_code}' no está en el fit ({self.model_version})"
        teams = lg["teams"]
        h, a = str(home_team_id), str(away_team_id)
        missing = [t for t in (h, a) if t not in teams]
        if missing:
            return None, f"equipo(s) sin fit en {league_code}: {missing}"
        mu, ga = lg["mu"], lg["home_adv"]
        lam_h = math.exp(mu + ga + teams[h]["atk"] - teams[a]["def"])
        lam_a = math.exp(mu + teams[a]["atk"] - teams[h]["def"])
        pred = Prediction(
            league_code=league_code, home_team_id=h, away_team_id=a,
            line=fair_line(lam_h, lam_a),
            model_version=art.get("model_version", "unknown"),
            trained_through=art.get("trained_through", ""),
        )
        return pred, ""

    def predict(self, league_code: str, home_team_id, away_team_id) -> Prediction:
        pred, reason = self.predict_or_reason(league_code, home_team_id, away_team_id)
        if pred is None:
            raise PredictionUnavailable(reason)
        return pred

    # -------- resolución de identidad: nombre del bot -> team_id del modelo ----

    def _league_index(self, league_code: str) -> dict | None:
        if league_code in self._index:
            return self._index[league_code]
        lg = self._load().get("leagues", {}).get(league_code)
        if lg is None:
            return None
        cands = [(tid, meta.get("name", "")) for tid, meta in lg["teams"].items()]
        idx = {"exact": {normalize_team_name(name): tid for tid, name in cands if name},
               "cands": cands}
        self._index[league_code] = idx
        return idx

    def resolve_team(self, league_code: str, name: str) -> tuple[str | None, float]:
        """(team_id, score) del equipo del modelo que mejor matchea ``name``, o (None, score).

        Exacto normalizado primero; luego fuzzy ≥ umbral con margen sobre el
        segundo (evita confundir dos equipos parecidos de la misma liga). Sin
        match confiable devuelve None — un match equivocado es peor que ninguno.
        """
        idx = self._league_index(league_code)
        if idx is None or not name:
            return None, 0.0
        norm = normalize_team_name(name)
        if norm in idx["exact"]:
            return idx["exact"][norm], 1.0
        alias_id = self._load_aliases().get(league_code, {}).get(norm)
        if alias_id is not None and alias_id in dict(idx["cands"]):
            return alias_id, 1.0
        scored = sorted(
            ((team_name_similarity(name, cname), tid) for tid, cname in idx["cands"]),
            reverse=True,
        )
        if not scored:
            return None, 0.0
        best_score, best_id = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0.0
        if best_score >= _RESOLVE_THRESHOLD and (best_score - second) >= _RESOLVE_MARGIN:
            return best_id, best_score
        return None, best_score

    def predict_by_names(self, league_code: str, home_name: str, away_name: str):
        """Predice a partir de NOMBRES (los que trae el bot). (Prediction|None, motivo)."""
        if self._load().get("leagues", {}).get(league_code) is None:
            return None, f"liga '{league_code}' no está en el fit ({self.model_version})"
        hid, hs = self.resolve_team(league_code, home_name)
        aid, as_ = self.resolve_team(league_code, away_name)
        unresolved = []
        if hid is None:
            unresolved.append(f"local '{home_name}' (mejor score {hs:.2f})")
        if aid is None:
            unresolved.append(f"visita '{away_name}' (mejor score {as_:.2f})")
        if unresolved:
            return None, "no se resolvió: " + "; ".join(unresolved)
        return self.predict_or_reason(league_code, hid, aid)

    def resolve_league(self, competition_name: str, *, country: str | None = None,
                       gender: str | None = None) -> str | None:
        """Competición del bot -> league_code del modelo, o None si no matchea.

        Matchea patrones normalizados por substring; country/gender desambiguan
        cuando se proveen. Devuelve None si no hay match único (nunca adivina).
        """
        norm = normalize_league_name(competition_name)
        if not norm:
            return None
        hits = []
        for lg, c, g, patterns in self._load_league_map():
            if country and c and country.upper()[:3] != c.upper()[:3]:
                continue
            if gender and g and gender.upper()[:1] != g.upper()[:1]:
                continue
            if any(p and p in norm for p in patterns):
                hits.append((lg, max(len(p) for p in patterns if p and p in norm)))
        if not hits:
            return None
        hits.sort(key=lambda x: -x[1])          # patrón más largo = más específico
        if len(hits) > 1 and hits[0][1] == hits[1][1]:
            return None                          # ambiguo sin desempate -> no adivina
        return hits[0][0]

    def predict_for_fixture(self, competition_name: str, home_name: str,
                            away_name: str, *, country: str | None = None,
                            gender: str | None = None):
        """Flujo completo del bot: (competición, nombres) -> (Prediction|None, motivo)."""
        lg = self.resolve_league(competition_name, country=country, gender=gender)
        if lg is None:
            return None, f"competición '{competition_name}' no mapea a ninguna liga del modelo"
        return self.predict_by_names(lg, home_name, away_name)

    def resolve_league_for_unified(self, competition: dict | None) -> str | None:
        """unified_competition (dict con name/display_name/country/gender) -> league_code."""
        if not competition:
            return None
        name = competition.get("display_name") or competition.get("name") or ""
        return self.resolve_league(name, country=competition.get("country"),
                                   gender=competition.get("gender"))


def league_code_for_unified_id(store, unified_competition_id: int,
                               svc: "PredictionService") -> str | None:
    """Soldadura competition_id -> league_code: lee la unified_competition del store
    (``get_unified_competition``) y la resuelve. ``store`` = puerto de competiciones.

    Mantiene puro a ``PredictionService`` (no accede a la DB); la lectura la hace el
    store y la resolución el service. Devuelve None si no existe o no mapea.
    """
    if unified_competition_id is None:
        return None
    record = store.get_unified_competition(unified_competition_id)
    return svc.resolve_league_for_unified(record)

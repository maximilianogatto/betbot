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

_DEFAULT_ARTIFACT = Path(__file__).resolve().parents[1] / "models" / "prediction_fit.json"


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
    def __init__(self, artifact_path: str | Path | None = None) -> None:
        self._path = Path(artifact_path) if artifact_path else _DEFAULT_ARTIFACT
        self._artifact: dict | None = None

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

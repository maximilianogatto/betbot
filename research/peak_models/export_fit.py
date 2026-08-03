"""Serializa el fit del modelo de goles a un artefacto versionado que el bot consume.

El runtime del bot NO importa research/ (no tiene numpy). El puente es este
artefacto JSON: parámetros por liga (μ, localía) y por equipo (ataque, defensa),
de los que ``services.prediction`` deriva λ_home/λ_away y luego la línea justa
(``core.fair_line``).

Parametrización de PRODUCCIÓN: Dixon-Coles por liga, half-life 120d, σ=0.75,
**ρ=0** (recomendación de la Línea 4; ρ no afecta la línea justa). El modelo está
entrenado sólo sobre nórdicas: fuera de estas ligas la línea se marca "no
disponible" (regla §10 del plan), nunca se extrapola.

Correr:  research/.venv/bin/python research/peak_models/export_fit.py
Salida:  models/prediction_fit.json  (versionado; regenerable)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.peak_models import loader  # noqa: E402
from research.peak_models.models import fit_poisson  # noqa: E402
OUT = ROOT / "models" / "prediction_fit.json"
MODEL_VERSION = "dc-perleague-rho0-v1"
CONFIG = {"halflife_days": 120.0, "ridge_sigma": 0.75, "fit_rho": False}


def main() -> None:
    df = loader.load_all()
    asof = df["date"].max() + pd.Timedelta(days=1)
    # nombre más reciente por team_id (para legibilidad del artefacto)
    long = pd.concat([
        df[["home_team_id", "home_team", "date"]].rename(
            columns={"home_team_id": "tid", "home_team": "name"}),
        df[["away_team_id", "away_team", "date"]].rename(
            columns={"away_team_id": "tid", "away_team": "name"}),
    ])
    names = (long.sort_values("date").groupby("tid")["name"].last().to_dict())

    leagues = {}
    for lg, g in df.groupby("league_code"):
        fit = fit_poisson(g, asof=asof, **CONFIG)
        if fit is None:
            continue
        leagues[lg] = {
            "mu": round(fit.mu, 6),
            "home_adv": round(fit.home_adv, 6),
            "rho": 0.0,
            "n_matches": fit.n_matches,
            "teams": {
                str(t): {"atk": round(fit.attack[t], 6),
                         "def": round(fit.defence[t], 6),
                         "name": names.get(t, "")}
                for t in fit.teams
            },
        }

    artifact = {
        "model_version": MODEL_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "trained_through": str(df["date"].max().date()),
        "config": CONFIG,
        "note": ("Dixon-Coles por liga (ρ=0). Sólo nórdicas; fuera de estas ligas "
                 "la línea es 'no disponible'. λ_h=exp(μ+localía+atk_h−def_a), "
                 "λ_a=exp(μ+atk_a−def_h)."),
        "leagues": leagues,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(artifact, indent=1))
    n_teams = sum(len(v["teams"]) for v in leagues.values())
    print(f"→ {OUT.relative_to(ROOT)}  ({len(leagues)} ligas, {n_teams} equipos, "
          f"model_version={MODEL_VERSION}, trained_through={artifact['trained_through']})")


if __name__ == "__main__":
    main()

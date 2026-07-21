"""Genera y ejecuta research/peak_models/g2_multiliga.ipynb (estilo g0/g1)."""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "research" / "peak_models" / "g2_multiliga.ipynb"

md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell

cells = [
    md(
        "# G2 — Multi-país (FIN+SWE+NOR) y la pregunta del momentum\n\n"
        "**EXP-002**. Dataset: 4.941 partidos, 17 ligas, 3 países. Corrida pesada en\n"
        "`research/experiments/EXP-002-multiliga/run.py`; acá se analizan los artefactos.\n\n"
        "Preguntas: (1) ¿generaliza la escalera de EXP-001? (2) ¿las features de\n"
        "forma ajustada por rival (Elo, momentum, sobre-rendimiento, SoS, PPG vs\n"
        "más fuertes) agregan sobre Dixon-Coles? Informe completo con conclusiones:\n"
        "`../experiments/EXP-002-multiliga/report.md`."
    ),
    code(
        "import json, sys\n"
        "from pathlib import Path\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "import matplotlib.pyplot as plt\n\n"
        "here = Path.cwd()\n"
        "for p in [here, *here.parents]:\n"
        "    if (p / 'research').is_dir():\n"
        "        ROOT = p; sys.path.insert(0, str(p)); break\n"
        "from research.peak_models import loader\n"
        "from research.peak_models.evaluate import PCOLS, compare, rps_per_match, paired_bootstrap\n\n"
        "EXP = ROOT / 'research' / 'experiments' / 'EXP-002-multiliga'\n"
        "res = pd.read_csv(EXP / 'walkforward_2026.csv', parse_dates=['date'])\n"
        "res['match_id'] = res['match_id'].astype(str)\n"
        "meta = loader.load_all()[['match_id','country']].drop_duplicates('match_id')\n"
        "res = res.merge(meta, on='match_id', how='left')\n"
        "res['rps'] = rps_per_match(res[PCOLS].to_numpy(), res['result'].to_numpy())\n"
        "print('partidos 2026:', res.match_id.nunique(), '| modelos:', sorted(res.model.unique()))"
    ),
    md("## 1. Tabla principal (RPS primaria; bootstrap pareado vs Dixon-Coles)"),
    code("compare(res, baseline='dc_best').round(4)"),
    md(
        "**G2 superado**: G0 pierde contra DC con IC 95% (+0.0032, +0.0139), p<0.001\n"
        "en log-loss, 1.619 partidos. `stack_cal` (recalibración OOS) mejora log-loss\n"
        "con p≈0.998 y nunca empeora → capa estándar. `stack_full` (≈DC): las\n"
        "features de momentum **no pagan su lugar** — ver §3."
    ),
    md("## 2. RPS por país y por liga"),
    code(
        "print(res.groupby(['model','country'])['rps'].mean().unstack().round(4).to_string())\n"
        "by_lg = res.groupby(['model','league_code'])['rps'].mean().unstack().round(4)\n"
        "by_lg.reindex(['b0_base_rate','g0_logistic_dppg','dc_best','stack_cal','stack_full'])"
    ),
    md(
        "Las ligas **femeninas** (NL 0.151, SW-EE 0.177, SW-DA 0.187, NO-TS 0.193 con\n"
        "DC) son las más predecibles del dataset — candidatas #1 a buscar value.\n"
        "La anomalía M1 (Ykkönen) persiste (DC pierde vs G0 solo ahí) → EXP-003a."
    ),
    md("## 3. ¿'Viene ganando contra equipos buenos' aporta? (ablación)"),
    code(
        "pm = {m: g.set_index('match_id')['rps'] for m, g in res.groupby('model')}\n"
        "ids = pm['stack_cal'].index.intersection(pm['stack_full'].index)\n"
        "bs = paired_bootstrap(pm['stack_cal'].loc[ids].to_numpy(), pm['stack_full'].loc[ids].to_numpy())\n"
        "print('ΔRPS stack_full − stack_cal: %.4f  IC95%% (%.4f, %.4f)  P(features ayudan)=%.2f'\n"
        "      % (bs['delta_mean'], bs['ci_lo'], bs['ci_hi'], bs['p_better']))"
    ),
    md(
        "La señal **existe univariadamente** (28%→59% de victoria local entre quintiles\n"
        "de sobre-rendimiento; ver `fig/momentum_effect.png`) pero el DC con decaimiento\n"
        "de 120 días **ya la contiene**: la verosimilitud ponderada en el tiempo sobre el\n"
        "grafo de partidos ES forma ajustada por rival. Aditivamente: cero. Coeficientes\n"
        "del meta-modelo ≈0 para elo/mom5/SoS (fig/stack_coefficients.png)."
    ),
    md("## 4. Figuras del informe"),
    code(
        "from IPython.display import Image, display\n"
        "for f in ['model_comparison','rps_by_league','momentum_effect','calibration',\n"
        "          'cold_start','league_profiles','stack_coefficients']:\n"
        "    display(Image(filename=EXP / 'fig' / f'{f}.png'))"
    ),
    md(
        "## 5. Conclusiones y siguiente paso\n\n"
        "- Modelo candidato a producción: **DC(hl=120, σ=0.75, ρ) + recalibración OOS**.\n"
        "- Empates sobre-estimados en la cola alta → no jugarlos aún.\n"
        "- Features de forma lineales: descartadas con evidencia (protocolo §3.5).\n"
        "- Próximos: jerárquico bayesiano con clustering (perfiles listos), diagnóstico\n"
        "  M1, Islandia via sportradar, targets O/U-BTTS, y **Fase 0 de cuotas** para\n"
        "  pasar de RPS a EV/ROI/CLV."
    ),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={
    "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
    "language_info": {"name": "python"},
})
NotebookClient(nb, timeout=600, kernel_name="python3",
               resources={"metadata": {"path": str(OUT.parent)}}).execute()
nbf.write(nb, OUT)
print("notebook ejecutado →", OUT)

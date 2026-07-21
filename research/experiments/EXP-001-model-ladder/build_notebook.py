"""Genera y ejecuta research/peak_models/g1_poisson_dc.ipynb (estilo g0)."""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "research" / "peak_models" / "g1_poisson_dc.ipynb"

md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell

cells = [
    md(
        "# G1 — Modelos de goles: Poisson y Dixon-Coles vs baseline G0\n\n"
        "**EXP-001** del protocolo (`research/PROTOCOLO_INVESTIGACION.md`). Pregunta:\n"
        "¿un modelo de fuerzas ataque/defensa sobre goles supera a la logística de\n"
        "Δppg (G0) y a la tasa base, bajo **walk-forward semanal** en 2026?\n\n"
        "- Hiperparámetros (decaimiento temporal, shrinkage, ρ) elegidos **solo con 2025**\n"
        "  (ver `config.json`); 2026 es evaluación pura.\n"
        "- Métrica primaria: **RPS**; log-loss/Brier/ECE secundarias; bootstrap pareado.\n"
        "- Corrida pesada: `research/experiments/EXP-001-model-ladder/run.py` →\n"
        "  este notebook analiza `walkforward_2026.csv` (no reentrena)."
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
        "from research.peak_models.evaluate import (ORDER, PCOLS, compare,\n"
        "                                           rps_per_match, ece)\n\n"
        "EXP = ROOT / 'research' / 'experiments' / 'EXP-001-model-ladder'\n"
        "cfg = json.loads((EXP / 'config.json').read_text())\n"
        "res = pd.read_csv(EXP / 'walkforward_2026.csv', parse_dates=['date'])\n"
        "print('config tuning →', cfg['tuning']['best'])\n"
        "print('partidos 2026 evaluados:', res.match_id.nunique(), '| modelos:', list(res.model.unique()))"
    ),
    md("## 1. Tabla de comparación (RPS = métrica primaria; menor es mejor)"),
    code(
        "table = compare(res, baseline='g0_logistic_dppg')\n"
        "table.round(4)"
    ),
    md(
        "Lectura: `d_rps_vs_base` < 0 con IC que excluye 0 ⇒ mejora significativa "
        "sobre G0. `p_better_rps` ≈ probabilidad bootstrap de ser mejor que G0."
    ),
    md("## 2. RPS por liga — ¿dónde aporta el modelo de goles?"),
    code(
        "res['rps'] = rps_per_match(res[PCOLS].to_numpy(), res['result'].to_numpy())\n"
        "by_lg = res.groupby(['model','league_code'])['rps'].mean().unstack().round(4)\n"
        "print(by_lg.to_string())\n"
        "by_lg.T.plot(kind='bar', figsize=(9,4))\n"
        "plt.title('RPS por liga (menor = mejor)'); plt.ylabel('RPS')\n"
        "plt.tight_layout(); plt.show()"
    ),
    md("## 3. Calibración de P(local) — el requisito para hablar de value"),
    code(
        "from sklearn.calibration import calibration_curve\n"
        "plt.figure(figsize=(6,5))\n"
        "for mdl in ['g0_logistic_dppg','dc_best']:\n"
        "    g = res[res.model==mdl]\n"
        "    frac, mean = calibration_curve((g.result=='H').astype(int), g.p_home,\n"
        "                                   n_bins=8, strategy='quantile')\n"
        "    plt.plot(mean, frac, 'o-', label=f\"{mdl} (ECE={ece(g[PCOLS].to_numpy(), g.result.to_numpy()):.3f})\")\n"
        "plt.plot([0,1],[0,1],'--',c='gray'); plt.legend()\n"
        "plt.xlabel('P(local) predicha'); plt.ylabel('frecuencia observada')\n"
        "plt.title('Calibración P(local), 2026 walk-forward'); plt.tight_layout(); plt.show()"
    ),
    md("## 4. Sharpness y desacuerdos — proto-señales de value"),
    code(
        "wide = res.pivot_table(index='match_id', columns='model', values='p_home')\n"
        "meta = res.drop_duplicates('match_id').set_index('match_id')\n"
        "wide['disagree'] = (wide['dc_best'] - wide['g0_logistic_dppg']).abs()\n"
        "top = wide.nlargest(10,'disagree').join(meta[['date','league_code','home_team','away_team','result']])\n"
        "print('mayores desacuerdos dc_best vs G0 (candidatos a señal cuando haya cuotas):')\n"
        "top[['date','league_code','home_team','away_team','g0_logistic_dppg','dc_best','result']].round(3)"
    ),
    code(
        "plt.figure(figsize=(7,4))\n"
        "for mdl, g in res.groupby('model'):\n"
        "    plt.hist(g.p_home, bins=25, histtype='step', label=mdl, density=True)\n"
        "plt.legend(); plt.title('Histograma de P(local) — sharpness')\n"
        "plt.xlabel('P(local)'); plt.tight_layout(); plt.show()"
    ),
    md(
        "## 5. Conclusiones (completar tras leer §1-§4)\n\n"
        "- Si `dc_best` gana a G0 con IC excluyendo 0 → **G2 pasado** para Finlandia;\n"
        "  el siguiente escalón del protocolo es el jerárquico bayesiano multi-liga\n"
        "  y sumar ligas (Noruega/Suecia/Islandia).\n"
        "- Si la calibración (§3) es buena, el modelo ya produce probabilidades usables\n"
        "  para **comparar contra cuotas** en cuanto la Fase 0 (archivado) acumule datos.\n"
        "- Pendientes del protocolo: features de forma/momentum/SoS como capa logística\n"
        "  sobre λs (stacking), O/U y BTTS (el modelo ya emite `p_over25`/`p_btts`),\n"
        "  y CLV cuando existan cuotas archivadas."
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

"""Linkeo masivo de ligas trackeadas contra el catálogo de un proveedor de stats.

Recorre las ligas unificadas suscriptas por un chat, busca su equivalente en el
catálogo del proveedor (por país) y propone el link. Por defecto NO escribe:
imprime lo que haría. Con --apply persiste los links aceptados.

Un link equivocado envenena las stats de esa liga para siempre, así que el
matching es deliberadamente conservador:

- **Los traits mandan sobre el parecido textual.** Si el género o la categoría
  de edad difieren, se descarta aunque el nombre sea casi idéntico: "Primera
  División" y "Primera División Femenina" se parecen muchísimo y son ligas
  distintas.
- **Se exige margen sobre el segundo candidato.** Un 0.90 contra un 0.89 no es
  una coincidencia, es un empate: sin margen se reporta como ambiguo y no se
  linkea.
- **El catálogo se deduplica por league_id**, porque el proveedor repite la
  misma liga una vez por fase y temporada ("Primera Nacional, G1", ", G2"...).

Uso:
    python -m scripts.link_stats_bulk --chat-id 123            # dry-run
    python -m scripts.link_stats_bulk --chat-id 123 --apply
"""

from __future__ import annotations

import argparse
import asyncio
import re
from dataclasses import dataclass
from typing import Any

from adapters.storage import get_storage
from core.league_naming import extract_league_traits, league_name_similarity

# Entradas del catálogo que no son ligas sino mercados o registros internos.
_NOISE = re.compile(
    r"\b(dummy|goalscorer|goal scorer|specials?|outright|winner|top scorer|corners?|bookings?)\b",
    re.IGNORECASE,
)

# Calibrado contra 7 ligas reales del bot (ver docstring del test): el score
# absoluto solo no separa. "Liga Femenina" puntúa 0.667 y es la correcta —su
# segundo candidato está en 0.000—; "Swedish Cup. Women" puntúa igual pero
# empata con el segundo. El margen es la señal que los distingue.
ACCEPT_THRESHOLD = 0.60   # parecido mínimo para siquiera considerarlo
MARGIN = 0.15             # ventaja mínima sobre el segundo candidato


@dataclass
class Proposal:
    unified_id: int
    unified_name: str
    country: str | None
    competition_id: int
    league_id: str
    league_name: str
    score: float
    runner_up: float
    verdict: str          # 'link' | 'ambiguo' | 'sin_match' | 'ya_linkeada'


def _traits_compatible(left: str, right: str) -> bool:
    """Género y categoría deben coincidir; el resto es negociable."""

    a, b = extract_league_traits(left), extract_league_traits(right)
    return a["gender"] == b["gender"] and a["age_group"] == b["age_group"]


def _dedupe_catalog(options: list[Any]) -> list[Any]:
    """Una entrada por torneo, priorizando la temporada vigente.

    Dos campos del payload hacen el trabajo pesado, mejor que cualquier
    heurística sobre el nombre:

    - ``unique_tournament_id == 0`` marca lo que no es una liga real (mercados
      tipo "Dummy Goalscorer"). Filtrarlo eliminó el falso positivo que tenía
      "Bolivia Championship" contra "La Paz Championship".
    - ``is_current_season`` distingue la temporada vigente de las fases viejas,
      que es de donde salían los duplicados (el proveedor repite la liga una vez
      por fase: "Primera Nacional, G1", ", G2"...).
    """

    best: dict[int, Any] = {}
    for opt in options:
        payload = opt.raw_payload or {}
        tournament = payload.get("unique_tournament_id") or 0
        if tournament <= 0:
            continue
        if _NOISE.search(opt.league_name or ""):
            continue
        current = best.get(tournament)
        if current is None:
            best[tournament] = opt
            continue
        current_payload = current.raw_payload or {}
        gana_por_temporada = payload.get("is_current_season") and not current_payload.get("is_current_season")
        misma_temporada = bool(payload.get("is_current_season")) == bool(current_payload.get("is_current_season"))
        if gana_por_temporada or (
            misma_temporada and len(opt.league_name or "") < len(current.league_name or "")
        ):
            best[tournament] = opt
    return list(best.values())


def _best_match(name: str, catalog: list[Any]) -> tuple[Any | None, float, float]:
    """Mejor candidato, su score y el score del segundo."""

    scored = sorted(
        (
            (league_name_similarity(name, opt.league_name or ""), opt)
            for opt in catalog
            if _traits_compatible(name, opt.league_name or "")
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not scored:
        return None, 0.0, 0.0
    top_score, top = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    return top, top_score, runner_up


async def run(chat_id: int, provider_name: str, apply: bool, limit: int | None) -> None:
    from stats_providers import register_default_stats_providers
    from core.stats_provider_base import stats_provider_registry

    register_default_stats_providers(stats_provider_registry)
    provider = next(
        (p for p in stats_provider_registry.list_registered() if p.name == provider_name),
        None,
    )
    if provider is None:
        raise SystemExit(f"Proveedor '{provider_name}' no registrado.")
    await provider.start()

    storage = get_storage()
    unified = storage.list_subscribed_unified_competitions(chat_id)
    if limit:
        unified = unified[:limit]
    print(f"Ligas del chat {chat_id}: {len(unified)}\n")

    catalog_cache: dict[str, list[Any]] = {}
    proposals: list[Proposal] = []

    for row in unified:
        uid, name = row["id"], row["name"]
        country = row.get("country") or extract_league_traits(name)["country"]
        competitions = storage.list_tracked_competitions_for_unified(uid)
        if not competitions:
            continue

        # El adapter propaga la herencia: consultando por una competencia de la
        # liga unificada devuelve los links de todas sus plataformas.
        existing = storage.list_stats_league_links(competitions[0].id)
        if any(link.stats_provider == provider_name for link in existing):
            proposals.append(Proposal(uid, name, country, 0, "", "", 1.0, 0.0, "ya_linkeada"))
            continue

        if not country:
            proposals.append(Proposal(uid, name, None, 0, "", "", 0.0, 0.0, "sin_match"))
            continue

        if country not in catalog_cache:
            try:
                catalog_cache[country] = _dedupe_catalog(
                    await provider.search_leagues(country_name=country)
                )
            except Exception as err:
                print(f"  [!] catálogo de {country} falló: {err}")
                catalog_cache[country] = []

        top, score, runner_up = _best_match(name, catalog_cache[country])
        if top is None or score < ACCEPT_THRESHOLD:
            verdict = "sin_match"
        elif score - runner_up < MARGIN:
            verdict = "ambiguo"
        else:
            verdict = "link"

        proposals.append(
            Proposal(
                uid, name, country, competitions[0].id,
                getattr(top, "league_id", "") or "", getattr(top, "league_name", "") or "",
                score, runner_up, verdict,
            )
        )

    for verdict in ("link", "ambiguo", "sin_match", "ya_linkeada"):
        rows = [p for p in proposals if p.verdict == verdict]
        print(f"=== {verdict.upper()} ({len(rows)}) ===")
        for p in rows[:60]:
            if verdict == "link":
                print(f"  {p.unified_name!r} [{p.country}] -> {p.league_name!r} (id={p.league_id}) "
                      f"score={p.score:.3f} 2do={p.runner_up:.3f}")
            elif verdict == "ambiguo":
                print(f"  {p.unified_name!r} [{p.country}] ~ {p.league_name!r} "
                      f"score={p.score:.3f} vs 2do={p.runner_up:.3f}  (margen insuficiente)")
            elif verdict == "sin_match":
                print(f"  {p.unified_name!r} [{p.country or 'sin país'}]")
        if len(rows) > 60:
            print(f"  ... y {len(rows) - 60} más")
        print()

    aceptados = [p for p in proposals if p.verdict == "link"]
    if not apply:
        print(f"DRY-RUN: no se escribió nada. Con --apply se crearían {len(aceptados)} links.")
    else:
        creados = 0
        for p in aceptados:
            storage.upsert_stats_league_link(
                p.competition_id,
                provider_name,
                p.league_id,
                p.league_name,
                p.country,
                round(p.score, 3),
            )
            creados += 1
        print(f"APLICADO: {creados} links creados.")

    try:
        await provider.stop()
    except Exception:
        pass


def main() -> None:
    # El .env se carga acá y no al importar: el módulo lo importan los tests, y
    # cargar el entorno del disco al importarlo les cambia la configuración por
    # debajo (ya pasó con SPORTRADAR_BOOTSTRAP_MODE). Como programa sí hace
    # falta: sin SPORTRADAR_REPLAY_ONLY el proveedor intentaría mintear un token
    # con Chromium en una VM donde lo desactivamos por falta de RAM.
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat-id", type=int, required=True)
    parser.add_argument("--provider", default="sportradar_statshub")
    parser.add_argument("--apply", action="store_true", help="persistir (por defecto dry-run)")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(args.chat_id, args.provider, args.apply, args.limit))


if __name__ == "__main__":
    main()

"""Linkeo de ligas trackeadas a Statshub verificado por EQUIPOS, no sólo por nombre.

El linkeo por nombre (`scripts/link_stats_bulk.py`) confunde ligas que comparten
palabras: mandaba todas las ligas estaduales femeninas de Australia a "A-League,
Women" (score 1.000) y la NPSL de EE. UU. a la NWSL. Acá el nombre sólo elige
candidatos; lo que decide es si los equipos que el bot ya vio en esa liga (tabla
`events`) juegan en el fixture del candidato.

Criterio (conservador: un link malo envenena las stats de la liga):
- candidatos: catálogo completo de Statshub, misma categoría (género, sub-XX,
  reserva) y mismo país cuando se conoce; los mejores por nombre;
- una copa sólo compite con copas y una liga con ligas (los equipos de una liga
  juegan también la copa del país: sin esto toda liga "empataba" con su copa);
- dos fases de la misma liga ("Mineiro, Women" / "Mineiro, Women, Final Stage",
  Apertura / Clausura) no son un empate: se toma la que tiene más equipos;
- se linkea si el mejor candidato tiene >= 3 equipos del bot y >= la mitad de los
  que el bot conoce, y el segundo candidato no se le acerca (< 60 % de los equipos
  del mejor). Si el bot conoce sólo 2 equipos, tienen que estar los 2 y ningún otro
  candidato puede tener alguno: con tan poco, un parecido suelto ("Sydney U20" ~
  "Western Sydney Wanderers") ya engaña.

Uso:
    python -m scripts.link_stats_by_teams --chat-id 123            # dry-run
    python -m scripts.link_stats_by_teams --chat-id 123 --apply
    --cache /tmp/sr_fixtures.json guarda los equipos de cada torneo entre corridas.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
import json
import os
import re
from typing import Any

from adapters.storage import get_storage
from adapters.storage.connection import open_connection
from core.league_naming import extract_league_traits, league_name_similarity, team_name_similarity
from scripts.link_stats_bulk import _dedupe_catalog

PROVIDER = "sportradar_statshub"
CANDIDATES_PER_LEAGUE = 5
TEAM_SIMILARITY = 0.80
MIN_TEAMS = 3
MIN_RATIO = 0.5
RUNNER_UP_FACTOR = 0.6

# País en castellano (nombres de BetWarrior/Betsson) -> como lo nombra Statshub.
_COUNTRY_ES = {
    "alemania": "germany", "argentina": "argentina", "australia": "australia", "austria": "austria",
    "belgica": "belgium", "bielorrusia": "belarus", "birmania": "myanmar", "bolivia": "bolivia",
    "brasil": "brazil", "bulgaria": "bulgaria", "butan": "bhutan", "canada": "canada",
    "checa": "czech republic", "chequia": "czech republic", "chile": "chile", "colombia": "colombia",
    "croacia": "croatia", "dinamarca": "denmark", "ecuador": "ecuador", "escocia": "scotland",
    "eslovaquia": "slovakia", "eslovenia": "slovenia", "espana": "spain", "estados unidos": "usa",
    "estonia": "estonia", "finlandia": "finland", "francia": "france", "gales": "wales",
    "grecia": "greece", "hungria": "hungary", "inglaterra": "england", "irlanda": "ireland",
    "islandia": "iceland", "israel": "israel", "italia": "italy", "japon": "japan",
    "letonia": "latvia", "lituania": "lithuania", "mexico": "mexico", "noruega": "norway",
    "nueva zelanda": "new zealand", "paises bajos": "netherlands", "paraguay": "paraguay",
    "peru": "peru", "polonia": "poland", "portugal": "portugal", "rumania": "romania",
    "suecia": "sweden", "suiza": "switzerland", "tailandia": "thailand", "turquia": "turkey",
    "ucrania": "ukraine", "uruguay": "uruguay",
    # adjetivos en inglés que el extractor de país no toma
    "croatian": "croatia", "armenian": "armenia", "czech": "czech republic", "bhutan": "bhutan",
    "slovenian": "slovenia", "ontario": "canada", "myanmar": "myanmar",
}


def _plain(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", text)


def _country_of(name: str) -> str | None:
    country = extract_league_traits(name)["country"]
    if country:
        return country.replace("_", " ")
    plain = f" {_plain(name)} "
    for spanish, english in sorted(_COUNTRY_ES.items(), key=lambda item: -len(item[0])):
        if f" {spanish} " in plain:
            return english
    return None


def _is_reserves(name: str) -> bool:
    return bool(re.search(r"\b(reserves?|reservas?|reserve league|suplentes)\b", _plain(name)))


_CUP_RE = re.compile(r"\b(cup|copa|coppa|coupe|pokal|pokalen|pohar|taca|cupen|trophy|shield|puchar|kupa|beker)\b")
_PHASE_RE = re.compile(
    r"\b(qualification|qualifying|final|finals|final stage|playoffs?|play offs?|relegation|promotion|"
    r"championship round|regular season|knockout|stage|phase|round|group|gr|apertura|clausura|"
    r"torneo|serie [a-z]|[a-z]|\d+)\b")


def _is_cup(name: str) -> bool:
    return bool(_CUP_RE.search(_plain(name)))


def _base_name(name: str) -> str:
    """Nombre sin la fase: "Mineiro, Women, Final Stage" -> "mineiro women"."""
    return " ".join(_PHASE_RE.sub(" ", _plain(name)).split())


def _category_compatible(left: str, right: str) -> bool:
    a, b = extract_league_traits(left), extract_league_traits(right)
    if a["gender"] != b["gender"] or a["age_group"] != b["age_group"]:
        return False
    return _is_reserves(left) == _is_reserves(right) and _is_cup(left) == _is_cup(right)


_GENERIC_WORDS = {"league", "liga", "cup", "copa", "women", "woman", "division", "the", "de", "del",
                  "la", "el", "fc", "football", "soccer", "championship", "campeonato", "serie"}


def _word_overlap(left: str, right: str) -> float:
    """Palabras distintivas en común (sin "league", "cup"...): la otra forma de rankear."""
    a = {w for w in _plain(left).split() if w not in _GENERIC_WORDS and len(w) > 1}
    b = {w for w in _plain(right).split() if w not in _GENERIC_WORDS and len(w) > 1}
    return len(a & b) / len(a | b) if a and b else 0.0


def _country_compatible(country: str | None, option: Any) -> bool:
    if not country:
        return True
    option_country = _plain(getattr(option, "country_name", None) or "")
    return not option_country or country in option_country or option_country.strip() in country


@dataclass
class Candidate:
    option: Any
    name_score: float
    matched: list[tuple[str, str]] = field(default_factory=list)

    @property
    def league_id(self) -> str:
        return str(self.option.league_id)


@dataclass
class Proposal:
    unified_id: int
    name: str
    competition_id: int
    bot_teams: list[str]
    verdict: str                       # link | ambiguo | sin_match | sin_equipos | ya_linkeada
    best: Candidate | None = None
    runner_up: Candidate | None = None


def _bot_teams(competition_ids: list[int]) -> list[str]:
    if not competition_ids:
        return []
    marks = ",".join("?" * len(competition_ids))
    with open_connection() as conn:
        rows = conn.execute(
            f"SELECT home, away FROM events WHERE competition_id IN ({marks})", competition_ids).fetchall()
    teams: dict[str, str] = {}
    for home, away in rows:
        for team in (home, away):
            if team:
                teams.setdefault(_plain(team).strip(), team)
    return sorted(teams.values())


def _match_teams(bot_teams: list[str], provider_teams: set[str]) -> list[tuple[str, str]]:
    matched = []
    for team in bot_teams:
        best = max(provider_teams, key=lambda other: team_name_similarity(team, other), default=None)
        if best is not None and team_name_similarity(team, best) >= TEAM_SIMILARITY:
            matched.append((team, best))
    return matched


async def run(chat_id: int, apply: bool, limit: int | None, cache_path: str | None = None) -> None:
    from core.stats_provider_base import stats_provider_registry
    from stats_providers import register_default_stats_providers

    register_default_stats_providers(stats_provider_registry)
    provider = next(p for p in stats_provider_registry.list_registered() if p.name == PROVIDER)
    await provider.start()
    storage = get_storage()

    catalog = _dedupe_catalog(await provider.search_leagues(country_name="", limit=100_000))
    print(f"Catálogo Statshub: {len(catalog)} torneos")
    fixtures_cache: dict[str, set[str]] = {}
    if cache_path and os.path.exists(cache_path):
        fixtures_cache = {key: set(value) for key, value in json.load(open(cache_path)).items()}

    def save_cache() -> None:
        if cache_path:
            json.dump({key: sorted(value) for key, value in fixtures_cache.items()}, open(cache_path, "w"))

    async def provider_teams(league_id: str) -> set[str]:
        if league_id not in fixtures_cache:
            try:
                fixtures = await provider.list_fixtures(league_id)
                fixtures_cache[league_id] = {name for f in fixtures for name in (f.home, f.away) if name}
            except Exception as error:
                print(f"  [!] fixtures de {league_id}: {type(error).__name__}")
                return set()  # sin cachear: se reintenta en la próxima corrida
            if len(fixtures_cache) % 20 == 0:
                save_cache()
            await asyncio.sleep(0.2)
        return fixtures_cache[league_id]

    unified = storage.list_subscribed_unified_competitions(chat_id)
    if limit:
        unified = unified[:limit]
    print(f"Ligas del chat {chat_id}: {len(unified)}\n")
    proposals: list[Proposal] = []
    for row in unified:
        uid, name = row["id"], row["name"]
        competitions = storage.list_tracked_competitions_for_unified(uid)
        if not competitions:
            continue
        if any(link.stats_provider == PROVIDER for link in storage.list_stats_league_links(competitions[0].id)):
            proposals.append(Proposal(uid, name, competitions[0].id, [], "ya_linkeada"))
            continue
        bot_teams = _bot_teams([c.id for c in competitions])
        if len(bot_teams) < 2:
            proposals.append(Proposal(uid, name, competitions[0].id, bot_teams, "sin_equipos"))
            continue
        country = row.get("country") or _country_of(name)
        pool = [opt for opt in catalog
                if _category_compatible(name, opt.league_name or "") and _country_compatible(country, opt)]
        by_similarity = sorted(pool, key=lambda opt: -league_name_similarity(name, opt.league_name or ""))
        by_words = sorted(pool, key=lambda opt: -_word_overlap(
            name, f"{opt.league_name or ''} {getattr(opt, 'country_name', '') or ''}"))
        chosen: dict[str, Any] = {}
        for opt in by_similarity[:CANDIDATES_PER_LEAGUE] + by_words[:CANDIDATES_PER_LEAGUE]:
            chosen.setdefault(str(opt.league_id), opt)
        ranked = [Candidate(opt, league_name_similarity(name, opt.league_name or ""))
                  for opt in chosen.values()]
        for candidate in ranked:
            candidate.matched = _match_teams(bot_teams, await provider_teams(candidate.league_id))
        ranked.sort(key=lambda c: (-len(c.matched), -c.name_score))
        best = ranked[0] if ranked else None
        runner_up = ranked[1] if len(ranked) > 1 else None
        # La otra fase de la misma liga no compite: se busca el primer rival real.
        if best is not None:
            runner_up = next((c for c in ranked[1:]
                              if _base_name(c.option.league_name or "") != _base_name(best.option.league_name or "")),
                             None)
        few = len(bot_teams) < MIN_TEAMS
        needed = len(bot_teams) if few else MIN_TEAMS
        runner_up_teams = len(runner_up.matched) if runner_up else 0
        if best is None or len(best.matched) < needed or len(best.matched) / len(bot_teams) < MIN_RATIO:
            verdict = "sin_match"
        elif (few and runner_up_teams) or runner_up_teams >= RUNNER_UP_FACTOR * len(best.matched):
            verdict = "ambiguo"
        else:
            verdict = "link"
        proposals.append(Proposal(uid, name, competitions[0].id, bot_teams, verdict, best, runner_up))
        print(f"  {verdict:10} {name[:55]:55} -> "
              f"{(best.option.league_name if best else '-')[:40]} "
              f"({len(best.matched) if best else 0}/{len(bot_teams)})", flush=True)

    print()
    for verdict in ("link", "ambiguo", "sin_match", "sin_equipos", "ya_linkeada"):
        rows = [p for p in proposals if p.verdict == verdict]
        print(f"=== {verdict.upper()} ({len(rows)}) ===")
        for p in rows:
            if p.best is None:
                print(f"  {p.name!r} (equipos del bot: {len(p.bot_teams)})")
                continue
            sample = ", ".join(f"{a}={b}" for a, b in p.best.matched[:3])
            second = (f" | 2do {p.runner_up.option.league_name!r} {len(p.runner_up.matched)}"
                      if p.runner_up else "")
            print(f"  {p.name!r} -> {p.best.option.league_name!r} [{p.best.option.country_name}]"
                  f" id={p.best.league_id} equipos {len(p.best.matched)}/{len(p.bot_teams)}{second}"
                  f"  ej: {sample}")
        print()

    save_cache()
    accepted = [p for p in proposals if p.verdict == "link"]
    if not apply:
        print(f"DRY-RUN: no se escribió nada. Con --apply se crearían {len(accepted)} links.")
    else:
        for p in accepted:
            storage.upsert_stats_league_link(
                p.competition_id, PROVIDER, p.best.league_id, p.best.option.league_name,
                p.best.option.country_name, round(len(p.best.matched) / len(p.bot_teams), 3))
        print(f"APLICADO: {len(accepted)} links creados.")
    try:
        await provider.stop()
    except Exception:
        pass


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()  # SPORTRADAR_REPLAY_ONLY: en la VPS no se mintea token (ver link_stats_bulk)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true", help="persistir (por defecto dry-run)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--cache", default=None, help="json con los equipos por torneo (se reusa)")
    args = parser.parse_args()
    asyncio.run(run(args.chat_id, args.apply, args.limit, args.cache))


if __name__ == "__main__":
    main()

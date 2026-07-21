"""Build Sweden + Norway match datasets (same schema as the Finland master).

Sweden: svenskfotboll.se widget API (full played-match list per competition id).
Norway: fotball.no terminliste tables per tournament fiksId (full season).

Run from the repo root with the bot venv (needs httpx):

    PYTHONPATH=. betbot/bin/python research/peak_models/build_dataset_nordics.py

Outputs under ``data/``: sweden_matches_played.csv, norway_matches_played.csv
and per-league files in by_league_year/. Team ids are normalized team names
(these federations don't expose stable numeric ids in the endpoints we use).
"""

from __future__ import annotations

import csv
import os
import re
from typing import Any

from stats_providers.norway_http.client import NorwayNFFHTTPClient
from stats_providers.svenskfotboll_http.client import SvenskfotbollHTTPClient

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "data")
_BY = os.path.join(_DATA, "by_league_year")

FIELDS = [
    "season", "league_code", "league_name", "competition_id",
    "group_id", "group_name", "round",
    "match_id", "date", "time",
    "home_team_id", "home_team", "away_team_id", "away_team",
    "home_goals", "away_goals", "ht_home", "ht_away",
    "status", "result", "country",
]

# league_code -> season -> competition id (svenskfotboll comp id / NFF fiksId).
SWEDEN: dict[str, tuple[str, str, dict[int, str]]] = {
    "SW-AL": ("Allsvenskan", "Tier 1 M", {2025: "123864", 2026: "133348"}),
    "SW-SE": ("Superettan", "Tier 2 M", {2025: "123863", 2026: "133340"}),
    "SW-EN": ("Ettan Norra", "Tier 3 M", {2025: "123861", 2026: "133338"}),
    "SW-ES": ("Ettan Södra", "Tier 3 M", {2025: "123862", 2026: "133339"}),
    "SW-DA": ("Damallsvenskan", "Tier 1 F", {2025: "123860", 2026: "133440"}),
    "SW-EE": ("Elitettan", "Tier 2 F", {2025: "123859", 2026: "133439"}),
}

NORWAY: dict[str, tuple[str, str, dict[int, str]]] = {
    "NO-ELI": ("Eliteserien", "Tier 1 M", {2025: "199603", 2026: "206092"}),
    "NO-OBOS": ("OBOS-ligaen", "Tier 2 M", {2025: "199422", 2026: "206093"}),
    "NO-PN1": ("PostNord-ligaen avd. 1", "Tier 3 M", {2025: "199294", 2026: "206007"}),
    "NO-PN2": ("PostNord-ligaen avd. 2", "Tier 3 M", {2025: "199295", 2026: "206008"}),
    "NO-TS": ("Toppserien", "Tier 1 F", {2025: "199118", 2026: "206119"}),
    "NO-1DK": ("1. divisjon Kvinner", "Tier 2 F", {2025: "199120", 2026: "206107"}),
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def _result(h: int | None, a: int | None) -> str:
    if h is None or a is None:
        return ""
    return "H" if h > a else ("A" if a > h else "D")


def _row(season: int, code: str, name: str, cid: str, country: str, *,
         match_id: str, date: str, time_: str, home: str, away: str,
         hg: int | None, ag: int | None) -> dict[str, Any]:
    return {
        "season": season, "league_code": code, "league_name": name,
        "competition_id": cid, "group_id": 1, "group_name": "-", "round": "",
        "match_id": match_id, "date": date, "time": time_,
        "home_team_id": _slug(home), "home_team": home,
        "away_team_id": _slug(away), "away_team": away,
        "home_goals": hg if hg is not None else "",
        "away_goals": ag if ag is not None else "",
        "ht_home": "", "ht_away": "",
        "status": "Played" if hg is not None else "Scheduled",
        "result": _result(hg, ag), "country": country,
    }


def fetch_sweden() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with SvenskfotbollHTTPClient() as c:
        for code, (name, _tier, seasons) in SWEDEN.items():
            for season, cid in seasons.items():
                payload = c.get_latest_results(cid, limit=500)
                matches = (payload.get("matches") if isinstance(payload, dict)
                           else payload) or []
                n = 0
                for m in matches:
                    score = str(m.get("score") or "")
                    sm = re.match(r"\s*(\d+)\s*-\s*(\d+)", score)
                    if not sm:
                        continue
                    start = str(m.get("start_time_local") or "")
                    date, _, time_ = start.partition(" ")
                    out.append(_row(season, code, name, cid, "SWE",
                                    match_id=str(m.get("match_id")),
                                    date=date, time_=time_ or "",
                                    home=str(m.get("home")), away=str(m.get("away")),
                                    hg=int(sm.group(1)), ag=int(sm.group(2))))
                    n += 1
                print(f"  {code} {season}: {n} jugados")
    return out


def _norway_fixture_rows(tables: list[dict[str, Any]]) -> list[list[str]]:
    for t in tables:
        head = [c.get("text", "").lower() for c in t.get("rows", [[]])[0]]
        if "runde" in head and "dato" in head and "hjemmelag" in head:
            return [[c.get("text", "") for c in r] for r in t["rows"]]
    return []


def fetch_norway() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with NorwayNFFHTTPClient() as c:
        for code, (name, _tier, seasons) in NORWAY.items():
            for season, fid in seasons.items():
                url = f"https://www.fotball.no/fotballdata/turnering/terminliste/?fiksId={fid}"
                try:
                    rows = _norway_fixture_rows(c.get_tables(url))
                except Exception as exc:
                    print(f"  {code} {season}: ERROR {exc}")
                    continue
                n = 0
                for r in rows:
                    if len(r) < 7 or not r[0].strip().isdigit():
                        continue
                    # runde, dato(dd.mm.yyyy), dag, tid, hjemmelag, resultat, bortelag
                    dm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", r[1])
                    date = f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}" if dm else ""
                    sm = re.search(r"(\d+)\s*-\s*(\d+)", r[5] or "")
                    hg, ag = (int(sm.group(1)), int(sm.group(2))) if sm else (None, None)
                    if hg is None:
                        continue
                    out.append(_row(season, code, name, fid, "NOR",
                                    match_id=f"{fid}-{r[0]}-{_slug(r[4])}",
                                    date=date, time_=r[3].strip(),
                                    home=r[4].strip(), away=r[6].strip(),
                                    hg=hg, ag=ag))
                    n += 1
                print(f"  {code} {season}: {n} jugados")
    return out


def _write(path: str, rows: list[dict[str, Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    os.makedirs(_BY, exist_ok=True)
    print("Suecia:")
    swe = fetch_sweden()
    _write(os.path.join(_DATA, "sweden_matches_played.csv"), swe)
    print("Noruega:")
    nor = fetch_norway()
    _write(os.path.join(_DATA, "norway_matches_played.csv"), nor)
    for country_rows in (swe, nor):
        by: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for r in country_rows:
            by.setdefault((r["league_code"], r["season"]), []).append(r)
        for (code, season), rows in by.items():
            _write(os.path.join(_BY, f"{code}_{season}.csv"), rows)
    print(f"Total: SWE {len(swe)} + NOR {len(nor)} filas")


if __name__ == "__main__":
    main()

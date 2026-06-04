"""Build the Finland peak-modelling dataset.

Fetches the senior Finnish leagues for the current and previous season plus
today's fixtures, and writes tidy CSVs (one per league+year, a concatenated
master, and today's fixtures) under ``data/``.

Run from the repo root so ``stats_providers`` imports resolve, e.g.::

    PYTHONPATH=. ../BetBot/betbot/bin/python research/peak_models/build_dataset.py

(Adjust the python path to the main BetBot venv; this worktree shares its deps.)

Each row is one match. ``team_A`` is the HOME side, ``team_B`` the AWAY side.
Finished matches carry the score; today's fixtures do not.
"""

from __future__ import annotations

import csv
import os
from datetime import date
from typing import Any, Optional

from stats_providers.palloliitto.api_client import PalloliittoAPI

# Senior leagues to pull (category_id -> human name).
LEAGUES: dict[str, str] = {
    "VL": "Veikkausliiga (M1)",
    "M1L": "Ykkösliiga (M2)",
    "M1": "Ykkönen (M3)",
    "M2": "Miesten Kakkonen (M4)",
    "NL": "Kansallinen Liiga (women)",
}
SEASONS = ("2026", "2025")  # current + previous

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "data")
_BY = os.path.join(_DATA, "by_league_year")

FIELDS = [
    "season", "league_code", "league_name", "competition_id",
    "group_id", "group_name", "round",
    "match_id", "date", "time",
    "home_team_id", "home_team", "away_team_id", "away_team",
    "home_goals", "away_goals", "ht_home", "ht_away",
    "status", "result",
]


def _to_int(v: Any) -> Optional[int]:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _result(home: Any, away: Any) -> str:
    h, a = _to_int(home), _to_int(away)
    if h is None or a is None:
        return ""
    return "H" if h > a else "A" if a > h else "D"


def _row(m: dict[str, Any], season: str, code: str) -> dict[str, Any]:
    return {
        "season": season,
        "league_code": code,
        "league_name": LEAGUES.get(code, code),
        "competition_id": m.get("competition_id"),
        "group_id": m.get("group_id"),
        "group_name": m.get("group_name"),
        "round": m.get("week") or m.get("round_name"),
        "match_id": m.get("match_id"),
        "date": m.get("date"),
        "time": m.get("time"),
        "home_team_id": m.get("team_A_id"),
        "home_team": m.get("club_A_name") or m.get("team_A_name"),
        "away_team_id": m.get("team_B_id"),
        "away_team": m.get("club_B_name") or m.get("team_B_name"),
        "home_goals": m.get("fs_A"),
        "away_goals": m.get("fs_B"),
        "ht_home": m.get("hts_A"),
        "ht_away": m.get("hts_B"),
        "status": m.get("status"),
        "result": _result(m.get("fs_A"), m.get("fs_B")),
    }


def _write_csv(path: str, rows: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def main() -> None:
    api = PalloliittoAPI()
    master: list[dict[str, Any]] = []
    try:
        # competition_id per (season, category) via the season catalogue.
        comp_by_season: dict[str, dict[str, str]] = {}
        for season in SEASONS:
            cats = api.get_categories(season) or []
            comp_by_season[season] = {
                str(c.get("category_id")): str(c.get("competition_id"))
                for c in cats
            }

        for season in SEASONS:
            for code in LEAGUES:
                comp = comp_by_season.get(season, {}).get(code)
                if not comp:
                    print(f"  ! sin competition_id para {code} {season}")
                    continue
                try:
                    matches = api.get_matches_by_league(comp, code) or []
                except Exception as exc:  # noqa: BLE001
                    print(f"  ! error {code} {season}: {exc}")
                    continue
                rows = [_row(m, season, code) for m in matches]
                # Finished matches first (for modelling); keep all for reference.
                finished = [r for r in rows if r["status"] in ("Finished", "Played") and r["home_goals"] not in (None, "")]
                _write_csv(os.path.join(_BY, f"{code}_{season}.csv"), rows)
                master.extend(finished)
                print(f"  {code} {season}: {len(matches)} partidos ({len(finished)} jugados) -> {code}_{season}.csv")

        _write_csv(os.path.join(_DATA, "finland_matches_played.csv"), master)
        print(f"\nMaster (solo jugados): {len(master)} filas -> finland_matches_played.csv")

        # Today's fixtures (to predict).
        today = date.today().isoformat()
        try:
            today_matches = api.get_matches_by_date(today) or []
        except Exception:
            today_matches = []
        today_rows = [
            _row(m, "2026", str(m.get("category_id")))
            for m in today_matches
            if str(m.get("category_id")) in LEAGUES
            and m.get("status") not in ("Finished", "Played")
        ]
        _write_csv(os.path.join(_DATA, "today_fixtures.csv"), today_rows)
        print(f"Fixtures de hoy ({today}): {len(today_rows)} -> today_fixtures.csv")
    finally:
        api.close()


if __name__ == "__main__":
    main()

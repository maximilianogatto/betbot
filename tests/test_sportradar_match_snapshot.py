from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from sandbox.sportradar_stats.snapshot_builder import (
    build_common_opponents,
    build_match_snapshot_from_capture_dir,
    compute_scoring_derived_features,
)


def time_doc(uts: int) -> dict[str, object]:
    return {
        "_doc": "time",
        "uts": uts,
        "time": "17:00",
        "date": "17/05/26",
        "tz": "UTC",
        "tzoffset": 0,
    }


def make_filtered_record(
    endpoint_key: str,
    query_url: str,
    data: object,
) -> dict[str, object]:
    return {
        "captured_at": "2026-05-16T12:00:00+00:00",
        "elapsed_ms": 100.0,
        "status": 200,
        "url": f"https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/{query_url}",
        "host": "sh.fn.sportradar.com",
        "resource_type": "fetch",
        "content_type": "application/json; charset=UTF-8",
        "normalized_path": f"/{endpoint_key}/:id",
        "endpoint_key": endpoint_key,
        "query_url": query_url,
        "doc_event": endpoint_key,
        "maxage_seconds": 60,
        "body_json": {
            "queryUrl": query_url,
            "doc": [
                {
                    "event": endpoint_key,
                    "_maxage": 60,
                    "data": data,
                }
            ],
        },
        "preview": None,
        "body_size_bytes": 500,
        "top_level_keys": list(data.keys())[:10] if isinstance(data, dict) else [],
        "match_ids": [],
    }


class SportradarMatchSnapshotTests(unittest.TestCase):
    def test_compute_scoring_derived_features(self) -> None:
        features = compute_scoring_derived_features(
            {
                "scoring": {
                    "goalsscoredaverage": {"total": 1.5, "home": 2.0, "away": 1.0},
                    "failedtoscoreaverage": {"total": 0.2},
                    "bothteamsscoredaverage": {"total": 0.6},
                    "scoringathalftimeaverage": {"total": 0.4},
                    "goalsbyminutes": {"0-15": {"total": 0.2}},
                },
                "conceding": {
                    "goalsconcededaverage": {"total": 1.0, "home": 0.8, "away": 1.2},
                    "cleansheetsaverage": {"total": 0.3},
                    "goalsconcededfirsthalfaverage": {"total": 0.35},
                    "minutespergoalconceded": {"total": 90},
                    "goalsbyminutes": {"0-15": {"total": 0.1}},
                },
            }
        )
        self.assertEqual(features["goals_scored_avg_total"], 1.5)
        self.assertEqual(features["goals_conceded_avg_total"], 1.0)
        self.assertEqual(features["clean_sheet_rate"], 0.3)
        self.assertEqual(features["minutes_per_goal_scored"], 60.0)
        self.assertEqual(features["minutes_per_goal_conceded"], 90.0)

    def test_build_common_opponents_creates_edges(self) -> None:
        home_matches = [
            {
                "match_id": "1",
                "opponent_id": "9001",
                "opponent": "Mallorca",
                "venue": "home",
                "result": "W",
                "goals_for": 2,
                "goals_against": 0,
            }
        ]
        away_matches = [
            {
                "match_id": "2",
                "opponent_id": "9001",
                "opponent": "Mallorca",
                "venue": "away",
                "result": "L",
                "goals_for": 0,
                "goals_against": 1,
            }
        ]

        common_opponents, transitive_edges = build_common_opponents(
            home_matches,
            away_matches,
        )
        self.assertEqual(len(common_opponents), 1)
        self.assertEqual(common_opponents[0]["opponent_name"], "Mallorca")
        self.assertEqual(transitive_edges[0]["home_edge"]["score"], "2-0")
        self.assertEqual(transitive_edges[0]["away_edge"]["score"], "0-1")

    def test_build_match_snapshot_from_capture_dir(self) -> None:
        home_team = {
            "_doc": "team",
            "_id": 6669997,
            "uid": 2846,
            "name": "Elche",
            "abbr": "ELC",
        }
        away_team = {
            "_doc": "team",
            "_id": 368362,
            "uid": 2859,
            "name": "Getafe",
            "abbr": "GET",
        }

        records = [
            make_filtered_record(
                "match_info_statshub",
                "match_info_statshub/61624664",
                {
                    "match": {"_id": 61624664, "round": 37, "_dt": time_doc(1779037200)},
                    "tournament": {"name": "LaLiga"},
                    "season": {"name": "LaLiga 25/26"},
                },
            ),
            make_filtered_record(
                "stats_match_get",
                "stats_match_get/61624664",
                {
                    "_doc": "match",
                    "_id": 61624664,
                    "round": 37,
                    "_seasonid": 130805,
                    "teams": {"home": home_team, "away": away_team},
                    "time": time_doc(1779037200),
                    "tournament": {"name": "LaLiga", "year": "25/26"},
                    "result": {"home": None, "away": None, "winner": None},
                },
            ),
            make_filtered_record(
                "match_markets",
                "match_markets/61624664",
                {
                    "markets": [
                        {
                            "name": "1x2",
                            "outcomes": [
                                {"name": "{$competitor1}", "odds": 2.2, "active": True},
                                {"name": "draw", "odds": 3.0, "active": True},
                                {"name": "{$competitor2}", "odds": 3.4, "active": True},
                            ],
                        },
                        {
                            "name": "Handicap",
                            "specifiers": {"hcp": "-0.25"},
                            "outcomes": [
                                {"name": "{$competitor1} ({+hcp})", "odds": 1.925, "active": True},
                                {"name": "{$competitor2} ({-hcp})", "odds": 1.925, "active": True},
                            ],
                        },
                        {
                            "name": "Total",
                            "specifiers": {"total": "2.0"},
                            "outcomes": [
                                {"name": "over {total}", "odds": 2.025, "active": True},
                                {"name": "under {total}", "odds": 1.825, "active": True},
                            ],
                        },
                    ]
                },
            ),
            make_filtered_record(
                "stats_match_tableslice",
                "stats_match_tableslice/61624664",
                {
                    "seasonid": "130805",
                    "currentround": 36,
                    "maxrounds": 38,
                    "matchid": 61624664,
                    "tablerows": [
                        {
                            "team": home_team,
                            "pos": 17,
                            "pointsTotal": 39,
                            "total": 36,
                            "winTotal": 9,
                            "drawTotal": 12,
                            "lossTotal": 15,
                            "goalsForTotal": 47,
                            "goalsAgainstTotal": 56,
                            "goalDiffTotal": -9,
                        },
                        {
                            "team": away_team,
                            "pos": 7,
                            "pointsTotal": 48,
                            "total": 36,
                            "winTotal": 14,
                            "drawTotal": 6,
                            "lossTotal": 16,
                            "goalsForTotal": 31,
                            "goalsAgainstTotal": 37,
                            "goalDiffTotal": -6,
                        },
                    ],
                },
            ),
            make_filtered_record(
                "stats_team_lastx",
                "stats_team_lastx/2846/20",
                {
                    "team": {"_id": 2846, "name": "Elche"},
                    "matches": [
                        {
                            "_id": 7001,
                            "_tid": 36,
                            "round": 36,
                            "teams": {"home": home_team, "away": {"_id": 111, "uid": 9001, "name": "Mallorca"}},
                            "result": {"home": 2, "away": 0},
                            "time": time_doc(1778700000),
                        }
                    ],
                    "tournaments": {"36": {"name": "LaLiga"}},
                },
            ),
            make_filtered_record(
                "stats_team_lastx",
                "stats_team_lastx/2859/20",
                {
                    "team": {"_id": 2859, "name": "Getafe"},
                    "matches": [
                        {
                            "_id": 7002,
                            "_tid": 36,
                            "round": 36,
                            "teams": { "home": {"_id": 111, "uid": 9001, "name": "Mallorca"}, "away": away_team},
                            "result": {"home": 1, "away": 0},
                            "time": time_doc(1778700600),
                        }
                    ],
                    "tournaments": {"36": {"name": "LaLiga"}},
                },
            ),
            make_filtered_record(
                "stats_team_nextx",
                "stats_team_nextx/2846/1",
                {
                    "team": {"_id": 2846, "name": "Elche"},
                    "matches": [
                        {
                            "_id": 61624664,
                            "_tid": 36,
                            "round": 37,
                            "teams": {"home": home_team, "away": away_team},
                            "result": {"home": None, "away": None},
                            "time": time_doc(1779037200),
                        }
                    ],
                    "tournaments": {"36": {"name": "LaLiga"}},
                },
            ),
            make_filtered_record(
                "stats_team_nextx",
                "stats_team_nextx/2859/1",
                {
                    "team": {"_id": 2859, "name": "Getafe"},
                    "matches": [
                        {
                            "_id": 61624664,
                            "_tid": 36,
                            "round": 37,
                            "teams": {"home": home_team, "away": away_team},
                            "result": {"home": None, "away": None},
                            "time": time_doc(1779037200),
                        }
                    ],
                    "tournaments": {"36": {"name": "LaLiga"}},
                },
            ),
            make_filtered_record(
                "stats_team_streaks",
                "stats_team_streaks/2846",
                {
                    "team": {"_id": 2846, "name": "Elche"},
                    "streaks": {"nolosing": {"home": {"value": 3, "streak": [{"matchid": 7001}]}}},
                },
            ),
            make_filtered_record(
                "stats_team_streaks",
                "stats_team_streaks/2859",
                {
                    "team": {"_id": 2859, "name": "Getafe"},
                    "streaks": {"nodrawing": {"away": {"value": 2, "streak": [{"matchid": 7002}]}}},
                },
            ),
            make_filtered_record(
                "stats_h2h_versus",
                "stats_h2h_versus/2846/2859/61624664",
                {
                    "match": {"_id": 61624664},
                    "lastmatchesbetweenteams": [
                        {
                            "_id": 7003,
                            "homeuniqueteamid": 2859,
                            "awayuniqueteamid": 2846,
                            "result": {"home": 1, "away": 0, "winner": "home"},
                            "time": time_doc(1764360000),
                            "tournament": {"name": "LaLiga"},
                            "round": 14,
                        }
                    ],
                    "lastmatchesbetweenteamsonvenue": [],
                    "versusmatchstats": {
                        "2846": {
                            "totalmatches": {"total": 1},
                            "teamwins": {"total": 0},
                            "teamdraws": {"total": 0},
                            "averagegoals": {"total": 0.0},
                        },
                        "2859": {
                            "teamwins": {"total": 1},
                            "averagegoals": {"total": 1.0},
                        },
                    },
                },
            ),
            make_filtered_record(
                "stats_season_teamscoringconceding",
                "stats_season_teamscoringconceding/130805/2846/-1",
                {
                    "team": {"_id": 2846, "name": "Elche"},
                    "stats": {
                        "totalmatches": {"total": 36, "home": 18, "away": 18},
                        "totalwins": {"total": 9, "home": 8, "away": 1},
                        "scoring": {
                            "goalsscored": {"total": 47, "home": 29, "away": 18},
                            "goalsscoredaverage": {"total": 1.3, "home": 1.6, "away": 1.0},
                            "failedtoscoreaverage": {"total": 0.14},
                            "bothteamsscoredaverage": {"total": 0.72},
                            "scoringathalftimeaverage": {"total": 0.44},
                            "goalsbyminutes": {"0-15": {"total": 0.16}},
                        },
                        "conceding": {
                            "goalsconceded": {"total": 56, "home": 19, "away": 37},
                            "goalsconcededaverage": {"total": 1.55, "home": 1.05, "away": 2.05},
                            "cleansheetsaverage": {"total": 0.19},
                            "goalsconcededfirsthalfaverage": {"total": 0.33},
                            "minutespergoalconceded": {"total": 58.0},
                            "goalsbyminutes": {"0-15": {"total": 0.12}},
                        },
                        "averagegoalsbyminutes": {"0-15": 0.28},
                    },
                },
            ),
            make_filtered_record(
                "stats_season_teamscoringconceding",
                "stats_season_teamscoringconceding/130805/2859/-1",
                {
                    "team": {"_id": 2859, "name": "Getafe"},
                    "stats": {
                        "totalmatches": {"total": 36, "home": 18, "away": 18},
                        "totalwins": {"total": 14, "home": 7, "away": 7},
                        "scoring": {
                            "goalsscored": {"total": 31, "home": 17, "away": 14},
                            "goalsscoredaverage": {"total": 0.86, "home": 0.94, "away": 0.78},
                            "failedtoscoreaverage": {"total": 0.25},
                            "bothteamsscoredaverage": {"total": 0.42},
                            "scoringathalftimeaverage": {"total": 0.20},
                            "goalsbyminutes": {"0-15": {"total": 0.08}},
                        },
                        "conceding": {
                            "goalsconceded": {"total": 37, "home": 16, "away": 21},
                            "goalsconcededaverage": {"total": 1.02, "home": 0.88, "away": 1.16},
                            "cleansheetsaverage": {"total": 0.31},
                            "goalsconcededfirsthalfaverage": {"total": 0.19},
                            "minutespergoalconceded": {"total": 88.0},
                            "goalsbyminutes": {"0-15": {"total": 0.09}},
                        },
                        "averagegoalsbyminutes": {"0-15": 0.17},
                    },
                },
            ),
            make_filtered_record(
                "stats_season_injuries",
                "stats_season_injuries/130805",
                [
                    {
                        "player": {"_id": 1, "name": "Jugador Local", "position": {"name": "Forward"}},
                        "status": {"status": "Missing", "name": "Injured", "start": time_doc(1778000000), "end": None},
                        "uniqueteam": {"_id": 2846},
                    }
                ],
            ),
            make_filtered_record(
                "stats_season_topgoals",
                "stats_season_topgoals/130805/2846",
                {
                    "players": [
                        {
                            "playerid": 10,
                            "player": {"_id": 10, "name": "Goleador", "position": {"name": "Forward"}, "jerseynumber": 9},
                            "total": {"goals": 10},
                        }
                    ]
                },
            ),
            make_filtered_record(
                "match_timeline",
                "match_timeline/61624664",
                {
                    "match": {
                        "_id": 61624664,
                        "_dt": time_doc(1779037200),
                        "round": 37,
                        "teams": {"home": home_team, "away": away_team},
                        "status": {"name": "Not started", "shortName": "NS"},
                        "result": {"home": None, "away": None, "winner": None},
                        "timeinfo": {"played": None, "running": False},
                        "cards": {"home": {"yellow_count": 0, "red_count": 0}, "away": {"yellow_count": 0, "red_count": 0}},
                    },
                    "events": [],
                },
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp_dir_name:
            capture_dir = Path(tmp_dir_name)
            (capture_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "stats_url": "https://s5.sir.sportradar.com/bet365/en/match/61624664",
                        "bootstrap_url": "https://www.bet365.bet.ar/#/AC/B1/C1/D8/E193003460/F3/I1/",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with (capture_dir / "filtered_fetch.ndjson").open("w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False))
                    handle.write("\n")

            snapshot = build_match_snapshot_from_capture_dir(capture_dir)

        self.assertEqual(snapshot["match_id"], "61624664")
        self.assertEqual(snapshot["bet365_event_id"], "193003460")
        self.assertEqual(snapshot["home"], "Elche")
        self.assertEqual(snapshot["away"], "Getafe")
        self.assertEqual(snapshot["competition"], "LaLiga")
        self.assertEqual(snapshot["season"], "LaLiga 25/26")
        self.assertEqual(snapshot["snapshot_metadata"]["snapshot_version"], 1)
        self.assertEqual(snapshot["snapshot_metadata"]["capture_type"], "prematch")
        self.assertEqual(
            snapshot["snapshot_metadata"]["missing_important_endpoints"],
            ["match_timelinedelta", "stats_season_topassists", "stats_season_topcards"],
        )
        self.assertIn("match_markets", snapshot["snapshot_metadata"]["endpoints_used"])
        self.assertEqual(snapshot["odds"]["markets"]["1x2"]["home"], 2.2)
        self.assertEqual(snapshot["team_standing"]["home"]["position"], 17)
        self.assertEqual(snapshot["team_standing"]["away"]["position"], 7)
        self.assertEqual(len(snapshot["traceable_matches"]["common_opponents"]), 1)
        self.assertTrue(snapshot["feature_quality"]["has_match_metadata"])
        self.assertTrue(snapshot["feature_quality"]["has_odds"])
        self.assertTrue(snapshot["feature_quality"]["has_team_scoring"])
        self.assertTrue(snapshot["feature_quality"]["has_injuries"])
        self.assertEqual(len(snapshot["raw_refs"]["source_records"]), len(records))

    def test_build_match_snapshot_reads_useful_fetch_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            capture_dir = Path(tmp_dir_name)
            (capture_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "stats_url": "https://s5.sir.sportradar.com/bet365/en/match/61624664",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            record = make_filtered_record(
                "stats_match_get",
                "stats_match_get/61624664",
                {
                    "_doc": "match",
                    "_id": 61624664,
                    "teams": {
                        "home": {"_id": 1, "uid": 1001, "name": "Elche"},
                        "away": {"_id": 2, "uid": 1002, "name": "Getafe"},
                    },
                    "time": time_doc(1779037200),
                },
            )
            with (capture_dir / "useful_fetch.ndjson").open("w", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False))
                handle.write("\n")

            snapshot = build_match_snapshot_from_capture_dir(capture_dir)

        self.assertEqual(snapshot["match_id"], "61624664")
        self.assertEqual(snapshot["home"], "Elche")
        self.assertEqual(snapshot["away"], "Getafe")


if __name__ == "__main__":
    unittest.main()

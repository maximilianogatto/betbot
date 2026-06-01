from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

SANDBOX_DIR = Path(__file__).resolve().parents[1] / "sandbox" / "1xbet_http"
if str(SANDBOX_DIR) not in sys.path:
    sys.path.insert(0, str(SANDBOX_DIR))

import xbet_discovery
import xbet_http


SPORTS_VALUE = [
    {
        "IT": 1,
        "N": "Fútbol",
        "E": "Football",
        "L": [
            {
                "L": "Australia",
                "LI": 83,
                "SC": [
                    {
                        "L": "Australia. A League",
                        "LE": "Australia. A League",
                        "LI": 2905446,
                        "CI": 4,
                        "CN": "Australia",
                        "CE": "Australia",
                        "GC": 1,
                    },
                    {
                        "L": "Australia. NPL Victoria",
                        "LE": "Australia. NPL Victorian",
                        "LI": 2664249,
                        "CI": 4,
                        "CN": "Australia",
                        "CE": "Australia",
                        "GC": 3,
                    },
                ],
            },
            {
                "L": "Partidos del día",
                "LE": "Matches of the Day",
                "LI": 2989655,
                "CI": 225,
                "CN": "Mundo",
                "GC": 1,
            },
        ],
    }
]

CHAMPS_VALUE = [
    {
        "SI": 1,
        "SN": "Fútbol",
        "SE": "Football",
        "L": "Australia. A League",
        "LE": "Australia. A League",
        "LI": 2905446,
        "CI": 4,
        "GC": 1,
    },
    {
        "SI": 1,
        "SN": "Fútbol",
        "SE": "Football",
        "L": "Australia. NPL Victoria",
        "LE": "Australia. NPL Victorian",
        "LI": 2664249,
        "CI": 4,
        "GC": 3,
    },
    {
        "SI": 1,
        "SN": "Fútbol",
        "SE": "Football",
        "L": "Australia. NPL Victoria",
        "LE": "Australia. NPL Victorian Duplicate",
        "LI": 2664249,
        "CI": 4,
        "GC": 3,
    },
    {
        "SI": 1,
        "SN": "Fútbol",
        "SE": "Football",
        "L": "England. Premier League",
        "LI": 88637,
        "CI": 33,
        "GC": 10,
    },
]


class OneXBetDiscoveryTests(unittest.TestCase):
    def test_normalize_linefeed_base_url_accepts_host(self) -> None:
        self.assertEqual(
            xbet_http.normalize_linefeed_base_url("spinbetter.com"),
            "https://spinbetter.com/service-api/LineFeed",
        )
        self.assertEqual(
            xbet_http.normalize_linefeed_base_url("https://spinbetter.com/service-api"),
            "https://spinbetter.com/service-api/LineFeed",
        )

    def test_parse_countries_and_leagues(self) -> None:
        tree = xbet_discovery.build_discovery_tree(
            sports_short_value=SPORTS_VALUE,
            champs_value=CHAMPS_VALUE,
            sport_id="1",
        )
        countries_index = xbet_discovery.build_countries_index(tree)
        leagues_index = xbet_discovery.build_leagues_index(tree)

        self.assertEqual(countries_index["countries_count"], 3)
        australia = next(country for country in tree["countries"] if country["country_name"] == "Australia")
        self.assertEqual(australia["country_id"], "4")
        self.assertIn("83", australia["country_group_ids"])
        self.assertEqual(len(australia["leagues"]), 2)
        self.assertEqual(leagues_index["leagues_count"], 4)

    def test_filter_by_country_and_search(self) -> None:
        tree = xbet_discovery.build_discovery_tree(
            sports_short_value=SPORTS_VALUE,
            champs_value=CHAMPS_VALUE,
            sport_id="1",
            filters={"country_name": "Australia", "country_id": None, "search": "NPL Victoria"},
        )
        leagues_index = xbet_discovery.build_leagues_index(tree)
        self.assertEqual(leagues_index["leagues_count"], 1)
        self.assertEqual(leagues_index["leagues"][0]["champ_id"], "2664249")

    def test_filter_by_country_group_id(self) -> None:
        tree = xbet_discovery.build_discovery_tree(
            sports_short_value=SPORTS_VALUE,
            champs_value=CHAMPS_VALUE,
            sport_id="1",
            filters={"country_name": None, "country_id": "83", "search": None},
        )
        leagues_index = xbet_discovery.build_leagues_index(tree)
        self.assertEqual(leagues_index["leagues_count"], 2)

    def test_deduplicate_champs(self) -> None:
        sports_candidates, country_names, sport_name = xbet_discovery.extract_candidates_from_sports_short(
            SPORTS_VALUE,
            sport_id="1",
        )
        champ_candidates = xbet_discovery.extract_candidates_from_champs(
            CHAMPS_VALUE,
            sport_id="1",
            country_names_by_id=country_names,
        )
        deduped, duplicates = xbet_discovery.deduplicate_league_candidates(sports_candidates + champ_candidates)
        champ_ids = {item["champ_id"] for item in deduped}
        self.assertIn("2664249", champ_ids)
        self.assertTrue(any(item["champ_id"] == "2664249" for item in duplicates))
        self.assertEqual(sport_name, "Fútbol")

    def test_tree_is_json_serializable(self) -> None:
        tree = xbet_discovery.build_discovery_tree(
            sports_short_value=SPORTS_VALUE,
            champs_value=CHAMPS_VALUE,
            sport_id="1",
        )
        json.dumps(tree, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest

from extractors.mystake_http import header as header_module


def _header_tree() -> str:
    """Double-encoded header tree, mirroring getheader/<region> shape."""

    tree = {
        "AS": {
            "Language": 100,
            "Sports": {
                "1": {
                    "ID": 1,
                    "KeyName": "Soccer",
                    "Name": "Fútbol",
                    "Regions": {
                        "8": {
                            "ID": 8,
                            "Name": "Australia",
                            "Champs": {
                                "37364": {
                                    "ID": 37364,
                                    "Name": "NSW League Two",
                                    "GameSmallItems": {
                                        "71": {"ID": 71, "Champ": 37364, "StartTime": "2026-06-01T09:00:00"},
                                        "72": {"ID": 72, "Champ": 37364, "StartTime": "2026-06-01T11:00:00"},
                                    },
                                },
                            },
                        },
                        "1": {
                            "ID": 1,
                            "Name": "Inglaterra",
                            "Champs": {
                                # Outright only -> negative ids -> excluded from discovery.
                                "39681": {
                                    "ID": 39681,
                                    "Name": "Premier League Outright",
                                    "GameSmallItems": {
                                        "-100": {"ID": -100, "Champ": 39681},
                                    },
                                },
                            },
                        },
                    },
                },
                "2": {
                    "ID": 2,
                    "Name": "Baloncesto",
                    "Regions": {
                        "9": {
                            "ID": 9,
                            "Name": "Estados Unidos",
                            "Champs": {
                                "500": {
                                    "ID": 500,
                                    "Name": "NBA",
                                    "GameSmallItems": {"900": {"ID": 900, "Champ": 500}},
                                }
                            },
                        }
                    },
                },
            },
        }
    }
    return json.dumps(tree)


class MystakeHeaderTests(unittest.TestCase):
    def setUp(self) -> None:
        # Header arrives double-encoded; the client decodes one layer, leaving a str.
        self.tree = json.loads(_header_tree())

    def test_parse_leagues_keeps_only_real_matches(self) -> None:
        leagues = header_module.parse_leagues(self.tree, sport_id=1)
        # England's outright-only champ is dropped; only NSW League Two remains.
        self.assertEqual(len(leagues), 1)
        league = leagues[0]
        self.assertEqual(league.champ_id, "37364")
        self.assertEqual(league.champ_name, "NSW League Two")
        self.assertEqual(league.region_name, "Australia")
        self.assertEqual(league.game_ids, (71, 72))
        self.assertEqual(league.games_count, 2)

    def test_build_league_options_filters_by_country(self) -> None:
        options = header_module.build_league_options(
            self.tree,
            platform="mystake_http",
            platform_display_name="Mystake",
            sport_id=1,
            country_name="australia",  # case/accent-insensitive
        )
        self.assertEqual(len(options), 1)
        opt = options[0]
        self.assertEqual(opt.league_name, "Australia · NSW League Two")
        self.assertEqual(opt.source_url, "mystake:champ:37364")
        self.assertEqual(opt.games_count, 2)

    def test_build_league_options_unknown_country_empty(self) -> None:
        options = header_module.build_league_options(
            self.tree,
            platform="mystake_http",
            platform_display_name="Mystake",
            sport_id=1,
            country_name="Marte",
        )
        self.assertEqual(options, [])

    def test_find_champ_resolves_name_and_ids(self) -> None:
        league = header_module.find_champ(self.tree, champ_id="37364", sport_id=1)
        self.assertIsNotNone(league)
        assert league is not None
        self.assertEqual(league.champ_name, "NSW League Two")
        self.assertEqual(league.game_ids, (71, 72))

    def test_find_champ_searches_all_sports_when_sport_unknown(self) -> None:
        league = header_module.find_champ(self.tree, champ_id="500")  # NBA, sport 2
        self.assertIsNotNone(league)
        assert league is not None
        self.assertEqual(league.champ_name, "NBA")

    def test_find_champ_missing_returns_none(self) -> None:
        self.assertIsNone(header_module.find_champ(self.tree, champ_id="999999", sport_id=1))


if __name__ == "__main__":
    unittest.main()

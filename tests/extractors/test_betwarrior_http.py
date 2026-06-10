from __future__ import annotations

import unittest

from extractors.betwarrior_http import discovery as discovery_module
from extractors.betwarrior_http.extractor import BetWarriorHttpExtractor, _group_id_from_url
from extractors.betwarrior_http.parser import build_competition_extraction
from extractors.betwarrior_http.settings import BetWarriorHttpSettings

_PATH = [
    {"id": 1, "name": "Fútbol", "termKey": "football"},
    {"id": 100, "name": "Uruguay", "termKey": "uruguay"},
    {"id": 1000450453, "name": "Campeonato Uruguayo", "termKey": "campeonato_uruguayo"},
]


def _list_view() -> dict:
    return {
        "events": [
            {"event": {"id": 11, "name": "A - B", "group": "Campeonato Uruguayo", "groupId": 1000450453, "path": _PATH}},
            {"event": {"id": 12, "name": "C - D", "group": "Campeonato Uruguayo", "groupId": 1000450453, "path": _PATH}},
            {
                "event": {
                    "id": 20,
                    "name": "E - F",
                    "group": "Premier League",
                    "groupId": 999,
                    "path": [
                        {"id": 1, "name": "Fútbol", "termKey": "football"},
                        {"id": 200, "name": "Inglaterra", "termKey": "england"},
                        {"id": 999, "name": "Premier League", "termKey": "premier_league"},
                    ],
                }
            },
        ]
    }


def _group_payload() -> dict:
    return {
        "events": [
            {
                "id": 11,
                "name": "Boston River - Liverpool",
                "homeName": "CA Boston River",
                "awayName": "Liverpool FC Montevideo",
                "start": "2026-06-01T18:00:00Z",
                "group": "Campeonato Uruguayo",
                "groupId": 1000450453,
                "path": _PATH,
            }
        ],
        "betOffers": [
            {
                "eventId": 11,
                "betOfferType": {"id": 2},
                "criterion": {"englishLabel": "Full Time"},
                "outcomes": [
                    {"type": "OT_ONE", "odds": 3000},
                    {"type": "OT_CROSS", "odds": 3150},
                    {"type": "OT_TWO", "odds": 2280},
                ],
            },
            {
                "eventId": 11,
                "betOfferType": {"id": 7},
                "criterion": {"englishLabel": "Asian Handicap"},
                "outcomes": [
                    {"label": "CA Boston River", "odds": 1580, "line": 500},
                    {"label": "Liverpool FC Montevideo", "odds": 2880, "line": -500},
                ],
            },
            {
                "eventId": 11,
                "betOfferType": {"id": 6},
                "criterion": {"englishLabel": "Total Goals"},
                "outcomes": [
                    {"type": "OT_OVER", "odds": 2040, "line": 2500},
                    {"type": "OT_UNDER", "odds": 1670, "line": 2500},
                ],
            },
            {  # noise: team total, must be ignored
                "eventId": 11,
                "betOfferType": {"id": 6},
                "criterion": {"englishLabel": "Total Goals by Norway"},
                "outcomes": [{"type": "OT_OVER", "odds": 1140, "line": 500}],
            },
        ],
    }


class BetWarriorParserTests(unittest.TestCase):
    def test_build_competition_maps_all_markets(self) -> None:
        extraction = build_competition_extraction(
            group_id="1000450453", group_payload=_group_payload(), source_url="betwarrior:group:1000450453"
        )
        self.assertEqual(extraction.platform, "betwarrior_http")
        self.assertEqual(extraction.competition_name, "Uruguay · Campeonato Uruguayo")
        self.assertEqual(len(extraction.events), 1)

        event = extraction.events[0]
        self.assertEqual(event.home, "CA Boston River")
        self.assertEqual(event.odds_1x2.home, 3.0)
        self.assertEqual(event.odds_1x2.draw, 3.15)
        self.assertEqual(event.odds_1x2.away, 2.28)
        self.assertTrue(event.scheduled_at.startswith("2026-06-01"))

        ah = event.markets_payload["asian_handicap"]["selections"]
        self.assertEqual({s["selection"] for s in ah}, {"CA Boston River", "Liverpool FC Montevideo"})
        self.assertEqual(ah[0], {"selection": "CA Boston River", "line": "+0.5", "odds": 1.58})

        gl = event.markets_payload["goal_line"]["selections"]
        self.assertEqual(gl[0], {"selection": "Over", "line": "2.5", "odds": 2.04})
        self.assertEqual(gl[1], {"selection": "Under", "line": "2.5", "odds": 1.67})

    def test_empty_group_is_empty(self) -> None:
        extraction = build_competition_extraction(
            group_id="424242", group_payload={"events": [], "betOffers": []}, source_url="betwarrior:group:424242"
        )
        self.assertTrue(extraction.is_empty)


class BetWarriorDiscoveryTests(unittest.TestCase):
    def test_build_league_options_by_country(self) -> None:
        options = discovery_module.build_league_options(
            _list_view(),
            platform="betwarrior_http",
            platform_display_name="BetWarrior HTTP",
            country_name="uruguay",
        )
        self.assertEqual(len(options), 1)
        opt = options[0]
        self.assertEqual(opt.league_name, "Campeonato Uruguayo")
        self.assertEqual(opt.country_name, "Uruguay")
        self.assertEqual(opt.source_url, "betwarrior:group:1000450453")
        self.assertEqual(opt.games_count, 2)  # two events grouped

    def test_unknown_country_empty(self) -> None:
        options = discovery_module.build_league_options(
            _list_view(),
            platform="betwarrior_http",
            platform_display_name="BetWarrior HTTP",
            country_name="Narnia",
        )
        self.assertEqual(options, [])


def _group_tree() -> dict:
    return {
        "group": {
            "id": 1,
            "groups": [
                {
                    "termKey": "football",
                    "name": "Fútbol",
                    "groups": [
                        {
                            "id": 100,
                            "name": "Australia",
                            "eventCount": 14,
                            "groups": [
                                {"id": 2000079748, "name": "Ligas juveniles Sub-20", "eventCount": 5},
                                {"id": 2000064679, "name": "NPL NSW", "eventCount": 10},
                                {"id": 9, "name": "Liga vacía", "eventCount": 0},  # no events -> skip
                            ],
                        },
                        {
                            "id": 200,
                            "name": "Inglaterra",
                            "eventCount": 1,
                            "groups": [
                                {"id": 999, "name": "Premier League", "eventCount": 1},
                            ],
                        },
                    ],
                },
                {"termKey": "tennis", "name": "Tenis", "groups": []},
            ],
        }
    }


class BetWarriorTreeDiscoveryTests(unittest.TestCase):
    def test_tree_includes_leagues_listview_would_drop(self) -> None:
        options = discovery_module.build_league_options_from_tree(
            _group_tree(),
            platform="betwarrior_http",
            platform_display_name="BetWarrior HTTP",
            country_name="australia",
        )
        names = {o.league_name for o in options}
        # The Sub-20 youth league must be discovered (listView omitted it).
        self.assertIn("Ligas juveniles Sub-20", names)
        self.assertIn("NPL NSW", names)
        self.assertNotIn("Liga vacía", names)  # eventCount 0 -> excluded
        sub20 = next(o for o in options if o.league_name == "Ligas juveniles Sub-20")
        self.assertEqual(sub20.source_url, "betwarrior:group:2000079748")
        self.assertEqual(sub20.games_count, 5)
        self.assertEqual(sub20.country_name, "Australia")

    def test_tree_filters_by_query(self) -> None:
        options = discovery_module.build_league_options_from_tree(
            _group_tree(),
            platform="betwarrior_http",
            platform_display_name="BetWarrior HTTP",
            country_name="australia",
            query="sub-20",
        )
        self.assertEqual([o.league_name for o in options], ["Ligas juveniles Sub-20"])

    def test_tree_unknown_country_empty(self) -> None:
        options = discovery_module.build_league_options_from_tree(
            _group_tree(),
            platform="betwarrior_http",
            platform_display_name="BetWarrior HTTP",
            country_name="Narnia",
        )
        self.assertEqual(options, [])


class BetWarriorUrlTests(unittest.TestCase):
    def test_group_id_from_scheme(self) -> None:
        self.assertEqual(_group_id_from_url("betwarrior:group:1000450453"), "1000450453")

    def test_group_id_from_url(self) -> None:
        self.assertEqual(_group_id_from_url("https://caba.betwarrior.bet.ar/...filter/1000450453"), "1000450453")

    def test_group_id_missing(self) -> None:
        self.assertIsNone(_group_id_from_url("https://caba.betwarrior.bet.ar/es-ar/sports"))

    def test_can_handle_url(self) -> None:
        self.assertTrue(BetWarriorHttpExtractor.can_handle_url("betwarrior:group:1000450453"))
        self.assertTrue(BetWarriorHttpExtractor.can_handle_url("https://caba.betwarrior.bet.ar/es-ar/sports"))
        self.assertFalse(BetWarriorHttpExtractor.can_handle_url("https://m.bz.com/x"))

    def test_api_base(self) -> None:
        settings = BetWarriorHttpSettings(api_host="h.kambicdn.com", offering="bwargbac")
        self.assertEqual(settings.api_base, "https://h.kambicdn.com/offering/v2018/bwargbac")


if __name__ == "__main__":
    unittest.main()

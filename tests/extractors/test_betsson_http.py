from __future__ import annotations

import asyncio
import unittest

from extractors.betsson_http import discovery as discovery_module
from extractors.betsson_http.extractor import BetssonHttpExtractor
from extractors.betsson_http.parser import (
    build_competition_extraction,
    live_events_from_table,
    prematch_events_from_tree,
)
from extractors.betsson_http.settings import BetssonHttpSettings


def _events_table() -> dict:
    """Shape mirrors /widgets/events-table/v2 -> data.{events,markets,selections}."""

    return {
        "events": [
            {
                "id": "f-AAA",
                "label": "Inglaterra - Croacia",
                "eventType": "Fixture",
                "competitionId": "30899",
                "competitionName": "Copa del Mundo",
                "regionName": "Mundial",
                "slug": "futbol/mundial/copa-del-mundo/inglaterra-croacia",
                "phase": "Prematch",
                "startDate": "2026-06-17T20:00:00Z",
                "participants": [
                    {"label": "Inglaterra", "id": "1", "side": 1},
                    {"label": "Croacia", "id": "2", "side": 2},
                ],
            },
            {  # outrights must be skipped
                "id": "f-OUT",
                "label": "Ganador del torneo",
                "eventType": "Outright",
                "competitionId": "30899",
                "participants": [],
            },
        ],
        "markets": [
            {"id": "m-AAA-MW3W", "eventId": "f-AAA", "marketTemplateId": "MW3W", "lineValue": ""},
            {"id": "m-AAA-MTG2W-2.5", "eventId": "f-AAA", "marketTemplateId": "MTG2W25", "lineValue": "2.5"},
            {"id": "m-AAA-MTG2W-3", "eventId": "f-AAA", "marketTemplateId": "MTG2W", "lineValue": "3"},
            {"id": "m-AAA-1HTG-1.5", "eventId": "f-AAA", "marketTemplateId": "1HTG", "lineValue": "1.5"},  # 1st half: skip
            {"id": "m-AAA-BTTS", "eventId": "f-AAA", "marketTemplateId": "BTTS", "lineValue": ""},
            {"id": "m-AAA-M3WHCP-1", "eventId": "f-AAA", "marketTemplateId": "M3WHCP", "lineValue": "1 - 0"},
        ],
        "selections": [
            {"marketId": "m-AAA-MW3W", "selectionTemplateId": "HOME", "odds": 1.25, "sortOrder": 1, "label": "Inglaterra"},
            {"marketId": "m-AAA-MW3W", "selectionTemplateId": "DRAW", "odds": 5.4, "sortOrder": 2, "label": "Empate"},
            {"marketId": "m-AAA-MW3W", "selectionTemplateId": "AWAY", "odds": 9.3, "sortOrder": 3, "label": "Croacia"},
            {"marketId": "m-AAA-MTG2W-2.5", "selectionTemplateId": "OVER", "odds": 1.92, "sortOrder": 1, "label": "más de 2.5"},
            {"marketId": "m-AAA-MTG2W-2.5", "selectionTemplateId": "UNDER", "odds": 1.9, "sortOrder": 2, "label": "menos de 2.5"},
            {"marketId": "m-AAA-MTG2W-3", "selectionTemplateId": "OVER", "odds": 2.6, "sortOrder": 1, "label": "más de 3"},
            {"marketId": "m-AAA-MTG2W-3", "selectionTemplateId": "UNDER", "odds": 1.5, "sortOrder": 2, "label": "menos de 3"},
            {"marketId": "m-AAA-1HTG-1.5", "selectionTemplateId": "OVER", "odds": 2.0, "sortOrder": 1, "label": "más de 1.5"},
            {"marketId": "m-AAA-BTTS", "selectionTemplateId": "YES", "odds": 1.6, "sortOrder": 1, "label": "Sí"},
            {"marketId": "m-AAA-BTTS", "selectionTemplateId": "NO", "odds": 2.05, "sortOrder": 2, "label": "No"},
            {"marketId": "m-AAA-M3WHCP-1", "selectionTemplateId": "HANDICAPHOME", "odds": 1.5, "sortOrder": 1, "label": "1 (+1)"},
            {"marketId": "m-AAA-M3WHCP-1", "selectionTemplateId": "HANDICAPDRAW", "odds": 4.0, "sortOrder": 2, "label": "X (-1)"},
            {"marketId": "m-AAA-M3WHCP-1", "selectionTemplateId": "HANDICAPAWAY", "odds": 6.5, "sortOrder": 3, "label": "2 (-1)"},
        ],
        "scoreboards": [],
    }


def _live_table() -> dict:
    return {
        "events": [
            {
                "id": "f-LIVE",
                "label": "Monsoon - SERC",
                "eventType": "Fixture",
                "competitionId": "23487",
                "competitionName": "Brasil Recopa Gaúcha",
                "regionName": "Brasil",
                "phase": "Live",
                "startDate": "2026-06-17T18:00:00Z",
                "participants": [
                    {"label": "Monsoon", "id": "10", "side": 1},
                    {"label": "SERC", "id": "20", "side": 2},
                ],
            }
        ],
        "markets": [],
        "selections": [],
        "scoreboards": [
            {
                "eventId": "f-LIVE",
                "scorePerParticipant": {"10": 2, "20": 1},
                "currentPhase": {"id": 2, "label": "2da mitad"},
                "matchClock": {"minutes": 64, "seconds": 0},
                "statistics": {
                    "10": {"redCards": {"value": 0}, "yellowCards": {"value": 3}},
                    "20": {"redCards": {"value": 1}, "yellowCards": {"value": 1}},
                },
            }
        ],
    }


def _tree() -> dict:
    return {
        "data": {
            "items": {
                "indexBySlug": {
                    "futbol/alemania/alemania-bundesliga": ["1", "14", "15"],
                },
                "categories": {
                    "1": {
                        "label": "Fútbol",
                        "regions": {
                            "0": {"label": "Partidos Top", "competitions": {}},  # skip
                            "14": {
                                "label": "Alemania",
                                "trackingLabel": "germany",
                                "competitions": {
                                    "0": {"label": "Todos Alemania", "slug": "futbol/alemania"},  # aggregate: skip
                                    "15": {
                                        "label": "Alemania Bundesliga",
                                        "slug": "futbol/alemania/alemania-bundesliga",
                                        "events": {
                                            "f-1": {
                                                "label": "Bayern - Dortmund",
                                                "eventType": "Fixture",
                                                "phase": "Prematch",
                                                "startDate": "2026-08-22T18:30:00Z",
                                            },
                                            "f-2": {
                                                "label": "Campeón 2026-2027",
                                                "eventType": "Outright",
                                                "phase": "Prematch",
                                            },
                                            "f-3": {
                                                "label": "Leipzig - Stuttgart",
                                                "eventType": "Fixture",
                                                "phase": "Live",
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    }
                },
            }
        }
    }


class BetssonParserTests(unittest.TestCase):
    def test_build_competition_maps_markets(self) -> None:
        extraction = build_competition_extraction(
            competition_id="30899", table_payload=_events_table(), source_url="betsson:competition:30899"
        )
        self.assertEqual(extraction.platform, "betsson_http")
        self.assertEqual(extraction.competition_name, "Mundial · Copa del Mundo")
        self.assertEqual(len(extraction.events), 1)  # outright skipped

        event = extraction.events[0]
        self.assertEqual(event.home, "Inglaterra")
        self.assertEqual(event.away, "Croacia")
        self.assertEqual(event.odds_1x2.home, 1.25)
        self.assertEqual(event.odds_1x2.draw, 5.4)
        self.assertEqual(event.odds_1x2.away, 9.3)
        self.assertTrue(event.scheduled_at.startswith("2026-06-17"))

        gl = event.markets_payload["goal_line"]["selections"]
        # nearest to 2.5 first; 1st-half totals (1HTG) excluded
        self.assertEqual(gl[0], {"selection": "Over", "line": "2.5", "odds": 1.92})
        self.assertEqual(gl[1], {"selection": "Under", "line": "2.5", "odds": 1.9})
        self.assertIn({"selection": "Over", "line": "3", "odds": 2.6}, gl)
        self.assertNotIn("1.5", {s["line"] for s in gl})

        btts = event.markets_payload["both_teams_to_score"]["selections"]
        self.assertEqual(btts, [{"selection": "Sí", "odds": 1.6}, {"selection": "No", "odds": 2.05}])

        # European 3-way handicap rides the asian_handicap slot (home/away legs +
        # signed line; draw kept separately). lineValue "1 - 0" -> home +1.
        ah = event.markets_payload["asian_handicap"]
        self.assertEqual(ah["market_name"], "Hándicap Europeo")
        self.assertEqual(
            ah["selections"],
            [
                {"selection": "Inglaterra", "line": "+1", "odds": 1.5},
                {"selection": "Croacia", "line": "-1", "odds": 6.5},
            ],
        )
        self.assertEqual(ah["draw"], [{"selection": "Empate", "line": "-1", "odds": 4.0}])

    def test_empty_table_is_empty(self) -> None:
        extraction = build_competition_extraction(
            competition_id="424242",
            table_payload={"events": [], "markets": [], "selections": []},
            source_url="betsson:competition:424242",
        )
        self.assertTrue(extraction.is_empty)


class BetssonLiveTests(unittest.TestCase):
    def test_live_events_map_score_and_cards(self) -> None:
        live = live_events_from_table(_live_table())
        self.assertEqual(len(live), 1)
        ev = live[0]
        self.assertEqual((ev.home, ev.away), ("Monsoon", "SERC"))
        self.assertEqual((ev.home_score, ev.away_score), (2, 1))
        self.assertEqual(ev.minute, "2da mitad 64'")
        self.assertEqual((ev.home_yellow_cards, ev.away_yellow_cards), (3, 1))
        self.assertEqual((ev.home_red_cards, ev.away_red_cards), (0, 1))
        self.assertEqual(ev.competition_name, "Brasil Recopa Gaúcha")  # country already in name
        self.assertEqual(ev.source_url, "betsson:competition:23487")


class BetssonDiscoveryTests(unittest.TestCase):
    def test_build_league_options_by_country(self) -> None:
        options = discovery_module.build_league_options_from_tree(
            _tree(),
            platform="betsson_http",
            platform_display_name="Betsson",
            category_id="1",
            country_name="alemania",
        )
        self.assertEqual(len(options), 1)
        opt = options[0]
        self.assertEqual(opt.league_name, "Alemania Bundesliga")
        self.assertEqual(opt.country_name, "Alemania")
        self.assertEqual(opt.source_url, "betsson:competition:15")
        self.assertEqual(opt.games_count, 3)

    def test_discovery_by_english_country(self) -> None:
        options = discovery_module.build_league_options_from_tree(
            _tree(),
            platform="betsson_http",
            platform_display_name="Betsson",
            category_id="1",
            country_name="germany",
        )
        self.assertEqual([o.league_name for o in options], ["Alemania Bundesliga"])

    def test_unknown_country_empty(self) -> None:
        options = discovery_module.build_league_options_from_tree(
            _tree(),
            platform="betsson_http",
            platform_display_name="Betsson",
            category_id="1",
            country_name="Narnia",
        )
        self.assertEqual(options, [])

    def test_prematch_listing_from_tree(self) -> None:
        events = prematch_events_from_tree(_tree(), category_id="1")
        # Only the prematch Fixture: outright + Live are dropped.
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual((ev.home, ev.away), ("Bayern", "Dortmund"))
        self.assertEqual(ev.competition_name, "Alemania Bundesliga")  # country in name
        self.assertEqual(ev.country_name, "Alemania")
        self.assertEqual(ev.source_url, "betsson:competition:15")
        self.assertTrue(ev.scheduled_at.startswith("2026-08-22"))

    def test_resolve_competition_id_from_slug(self) -> None:
        self.assertEqual(
            discovery_module.resolve_competition_id_from_slug(
                _tree(), "futbol/alemania/alemania-bundesliga"
            ),
            "15",
        )
        self.assertIsNone(discovery_module.resolve_competition_id_from_slug(_tree(), "futbol/desconocido"))


class BetssonUrlTests(unittest.TestCase):
    def test_can_handle_url(self) -> None:
        self.assertTrue(BetssonHttpExtractor.can_handle_url("betsson:competition:30899"))
        self.assertTrue(BetssonHttpExtractor.can_handle_url("https://cba.betsson.bet.ar/apuestas-deportivas/futbol"))
        self.assertFalse(BetssonHttpExtractor.can_handle_url("https://caba.betwarrior.bet.ar/x"))

    def test_competition_id_from_scheme(self) -> None:
        ex = BetssonHttpExtractor()
        cid = asyncio.run(ex._competition_id_from_url("betsson:competition:30899", client=None))
        self.assertEqual(cid, "30899")

    def test_build_competition_url(self) -> None:
        ex = BetssonHttpExtractor()
        self.assertEqual(ex.build_competition_url(competition_external_id="30899"), "betsson:competition:30899")

    def test_headers_contain_brand(self) -> None:
        settings = BetssonHttpSettings(brand_id="brand-x", market_code="ag")
        headers = settings.headers
        self.assertEqual(headers["brandid"], "brand-x")
        self.assertEqual(headers["marketcode"], "ag")
        self.assertIn("sessiontoken", headers)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from extractors.mrpunter_http import discovery as discovery_module
from extractors.mrpunter_http.client import extract_tokens_from_html
from extractors.mrpunter_http.extractor import MrPunterHttpExtractor, _league_id_from_url
from extractors.mrpunter_http.parser import build_competition_extraction, live_events_from_initial


def _pad(event: list, upto: int = 32) -> list:
    while len(event) < upto:
        event.append(None)
    return event


def _ml0_market() -> list:
    return [
        "m1", "Resultado del Partido", "Resultado del Partido", ["ML0", "Resultado del Partido", 1, 1],
        "ev1", "lg1", "1",
        [
            ["oD", {"ES": "Empate"}, {"ES": "Empate"}, False, 3.15],
            ["oH", {"ES": "Deportes Tolima"}, {"ES": "Deportes Tolima"}, False, 2.38],
            ["oA", {"ES": "Independiente del Valle"}, {"ES": "Independiente del Valle"}, False, 2.87],
        ],
    ]


def _ou200_market() -> list:
    return [
        "m2", "Total de Goles Más/Menos", "Total de Goles Más/Menos", ["OU200", "Total de Goles Más/Menos", 3, 1],
        "ev1", "lg1", "1",
        [
            ["t1", {"ES": "Más de 1.5"}, {"ES": "Más de"}, True, 1.26],
            ["t2", {"ES": "Menos de 1.5"}, {"ES": "Menos de"}, True, 3.22],
            ["t3", {"ES": "Más de 2.5"}, {"ES": "Más de"}, True, 1.99],
            ["t4", {"ES": "Menos de 2.5"}, {"ES": "Menos de"}, True, 1.68],
            ["t5", {"ES": "Más de 0.5"}, {"ES": "Más de"}, True, 0],  # closed line -> skipped
        ],
    ]


def _gameodds_event() -> list:
    ev = [
        "848241275974262784", "805808858558951424", "Copa Libertadores", "1", "Fútbol",
        "277", "SAM", "América del Sur",
        [["16262", {"ES": "Deportes Tolima"}, "Home"], ["217888", {"ES": "Independiente del Valle"}, "Away"]],
        214, "Deportes Tolima vs Independiente del Valle", "2026-08-12T13:00:00.000Z",
        ["", "", None, {}], False, False, {"ClockRunning": False}, False, [], "639",
        [_ml0_market(), _ou200_market()],  # index 19 = markets
    ]
    ev = _pad(ev, 32)
    ev[31] = "133"
    return ev


def _live_payload() -> dict:
    soccer = [
        "900", "lg9", "Brasileirao", "1", "Fútbol", "30", "BR", "Brasil",
        [["c1", {"ES": "Flamengo"}, "Home"], ["c2", {"ES": "Palmeiras"}, "Away"]],
        10, "Flamengo vs Palmeiras", "2026-06-01T20:00:00Z",
        ["2", "1", None, {}], True, False, {"ClockRunning": True, "Minute": 34}, False, [], "",
    ]
    soccer = _pad(soccer, 32)
    virtual = [
        "901", "lgV", "V-Liga", "234", "V-Fútbol", "275", "VR", "V-Fútbol",
        [["v1", {"ES": "Mónaco [V]"}, "Home"], ["v2", {"ES": "Barça [V]"}, "Away"]],
        10, "Mónaco [V] vs Barça [V]", "2026-06-01T06:00:00Z",
        ["0", "0", None, {}], True, False, {"ClockRunning": True}, False, [], "",
    ]
    virtual = _pad(virtual, 32)
    return {"sports": [{"sportId": "1", "numberOfEvents": 1}], "events": {"sport": "1", "data": [soccer, virtual]}}


class MrPunterParserTests(unittest.TestCase):
    def test_gameodds_maps_1x2_and_goal_line(self) -> None:
        extraction = build_competition_extraction(
            master_league_id="133",
            events=[_gameodds_event()],
            source_url="mrpunter:league:133",
            competition_name="Copa Libertadores",
            country_name="América del Sur",
        )
        self.assertEqual(extraction.platform, "mrpunter_http")
        self.assertEqual(extraction.competition_name, "América del Sur · Copa Libertadores")
        self.assertEqual(len(extraction.events), 1)
        e = extraction.events[0]
        self.assertEqual(e.home, "Deportes Tolima")
        self.assertEqual(e.away, "Independiente del Valle")
        self.assertEqual(e.odds_1x2.home, 2.38)
        self.assertEqual(e.odds_1x2.draw, 3.15)
        self.assertEqual(e.odds_1x2.away, 2.87)
        gl = e.markets_payload["goal_line"]["selections"]
        self.assertEqual(gl[0], {"selection": "Over", "line": "2.5", "odds": 1.99})
        self.assertEqual(gl[1], {"selection": "Under", "line": "2.5", "odds": 1.68})
        self.assertNotIn("0.5", [s["line"] for s in gl])  # closed 0-price line excluded
        self.assertTrue(e.scheduled_at.startswith("2026-08-12"))

    def test_live_maps_soccer_and_flags_virtual(self) -> None:
        live = live_events_from_initial(_live_payload(), sport_id="1")
        self.assertEqual(len(live), 2)
        real = [x for x in live if x.is_soccer]
        self.assertEqual(len(real), 1)
        e = real[0]
        self.assertEqual((e.home, e.away), ("Flamengo", "Palmeiras"))
        self.assertEqual((e.home_score, e.away_score), (2, 1))
        self.assertEqual(e.minute, "34'")  # Minute key -> minutes
        self.assertEqual(e.competition_name, "Brasileirao")

    def test_clock_minute_from_gametime_seconds(self) -> None:
        # FSB serves the clock in SECONDS (GameTime); show minutes, not "5690".
        from extractors.mrpunter_http.parser import _clock_minute

        self.assertEqual(_clock_minute({"GameTime": 2700}), "45'")
        self.assertEqual(_clock_minute({"GameTime": 5690}), "94'")
        self.assertEqual(_clock_minute({"Minute": 12}), "12'")  # already minutes
        self.assertIsNone(_clock_minute({}))

    def test_live_from_league_odds_dedupes_and_maps(self) -> None:
        from extractors.mrpunter_http.parser import live_events_from_league_odds

        soccer = _live_payload()["events"]["data"][0]  # Flamengo vs Palmeiras
        # Same event returned by two leagues' gameOdds must dedupe to one.
        live = live_events_from_league_odds(
            {"5579": [soccer], "9999": [soccer]}, sport_id="1"
        )
        self.assertEqual(len(live), 1)
        self.assertEqual((live[0].home, live[0].away), ("Flamengo", "Palmeiras"))
        self.assertTrue(live[0].is_soccer)


class MrPunterDiscoveryTests(unittest.TestCase):
    def _nav(self) -> list:
        return [
            {
                "_id": "1",
                "countries": [
                    {
                        "_id": "30", "RegionName": "Brasil",
                        "Leagues": [
                            {"MasterLeagueId": "133", "LeagueName": "Brasileirao", "fixtureEventsQuantity": 5},
                            {"MasterLeagueId": "200", "LeagueName": "Serie B", "fixtureEventsQuantity": 0, "eventsQuantity": 3},
                        ],
                    }
                ],
            },
            {"_id": "234", "countries": []},  # V-Fútbol ignored
        ]

    def test_build_league_options_by_country(self) -> None:
        opts = discovery_module.build_league_options(
            self._nav(), platform="mrpunter_http", platform_display_name="MrPunter",
            sport_id="1", country_name="brasil",
        )
        self.assertEqual(len(opts), 2)
        self.assertEqual(opts[0].league_name, "Brasileirao")
        self.assertEqual(opts[0].source_url, "mrpunter:league:133")
        self.assertEqual(opts[0].games_count, 5)

    def test_unknown_country_empty(self) -> None:
        self.assertEqual(
            discovery_module.build_league_options(
                self._nav(), platform="mrpunter_http", platform_display_name="MrPunter",
                sport_id="1", country_name="Narnia",
            ),
            [],
        )


class MrPunterMiscTests(unittest.TestCase):
    def test_league_id_from_url(self) -> None:
        self.assertEqual(_league_id_from_url("mrpunter:league:133"), "133")
        self.assertIsNone(_league_id_from_url("https://mrpunter.com/es/"))

    def test_can_handle_url(self) -> None:
        self.assertTrue(MrPunterHttpExtractor.can_handle_url("mrpunter:league:133"))
        self.assertTrue(MrPunterHttpExtractor.can_handle_url("https://mrpunter.com/es/sports"))
        self.assertFalse(MrPunterHttpExtractor.can_handle_url("https://m.bz.com/x"))

    def test_extract_tokens_from_html(self) -> None:
        import base64, json

        def jwt(payload: dict) -> str:
            body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
            return f"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.{body}.{'x' * 20}"

        auth = jwt({"customerType": "anon", "languageCode": "es"})
        sess = jwt({"customerId": -1, "expiredDate": 123, "iat": 1})
        html = f'<script>window.__INITIAL_STATE__={{"a":"{auth}","s":"{sess}"}}</script>'
        self.assertEqual(extract_tokens_from_html(html), (auth, sess))


if __name__ == "__main__":
    unittest.main()

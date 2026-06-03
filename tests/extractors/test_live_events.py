from __future__ import annotations

import unittest

from extractors.betovo_http.parser import live_events_from_livenow
from extractors.betwarrior_http.parser import live_events_from_open
from extractors.bz_http.parser import live_events_from_search
from extractors.solcasino_http.parser import live_events_from_snapshot
from extractors.xbet_http.parser import live_events_from_1x2_vzip, live_events_from_champ_zip


class XBetLiveTests(unittest.TestCase):
    def test_1x2_vzip_maps_inplay_and_filters_virtual_and_prematch(self) -> None:
        payload = {
            "Value": [
                {  # real, in-play
                    "I": 100, "O1": "Alto Zambeze", "O2": "Kalandula", "L": "Angola. Liga Bantu", "CN": "Angola",
                    "SC": {"FS": {"S1": 2, "S2": 3}, "I": "", "SLS": "76 minutos", "CP": 2, "RC1": 1, "RC2": 0},
                    "E": [{"T": 1, "C": 1.17}, {"T": 2, "C": 5.31}, {"T": 3, "C": 19.7}],
                },
                {  # prematch (in live feed but not kicked off) -> excluded
                    "I": 101, "O1": "A", "O2": "B", "L": "China. Liga", "CN": "China",
                    "SC": {"FS": {}, "I": "Apuestas prepartido", "SLS": "Comienza en 1 minutos"},
                    "E": [],
                },
                {  # virtual -> flagged is_soccer False
                    "I": 102, "O1": "X (sim)", "O2": "Y (sim)", "L": "Short Football 5x5", "CN": "Mundo",
                    "SC": {"FS": {"S1": 0, "S2": 0}, "I": "", "SLS": "3 minutos"},
                    "E": [],
                },
            ]
        }
        live = live_events_from_1x2_vzip(payload)
        self.assertEqual(len(live), 2)  # prematch excluded
        real = [e for e in live if e.is_soccer]
        self.assertEqual(len(real), 1)
        e = real[0]
        self.assertEqual((e.home, e.away), ("Alto Zambeze", "Kalandula"))
        self.assertEqual((e.home_score, e.away_score), (2, 3))
        self.assertEqual((e.home_red_cards, e.away_red_cards), (1, 0))
        self.assertEqual(e.minute, "76 minutos")
        self.assertEqual(e.odds_1x2.home, 1.17)
        self.assertEqual(e.odds_1x2.away, 19.7)

    def test_champ_zip_maps_live_events(self) -> None:
        payload = {
            "Success": True,
            "Value": {
                "LI": "1907776",
                "L": "Australia. NPL Northern NSW (F)",
                "CN": "Australia",
                "SI": "1",
                "G": [
                    {
                        "I": 105, "O1": "Maitland", "O2": "Broadmeadow",
                        "SC": {"FS": {"S1": 1, "S2": 2}, "I": "", "SLS": "45 minutos", "CP": 1},
                        "E": [{"T": 1, "C": 2.5}, {"T": 2, "C": 3.4}, {"T": 3, "C": 2.3}],
                    }
                ]
            }
        }
        live = live_events_from_champ_zip(payload)
        self.assertEqual(len(live), 1)
        e = live[0]
        self.assertEqual((e.home, e.away), ("Maitland", "Broadmeadow"))
        self.assertEqual(e.competition_name, "Australia. NPL Northern NSW (F)")
        self.assertEqual(e.country_name, "Australia")
        self.assertEqual((e.home_score, e.away_score), (1, 2))
        self.assertEqual(e.minute, "45 minutos")
        self.assertEqual(e.odds_1x2.home, 2.5)


class KambiLiveTests(unittest.TestCase):
    def test_open_maps_soccer_and_flags_esports(self) -> None:
        payload = {
            "liveEvents": [
                {
                    "event": {
                        "id": 1, "homeName": "Northern AFC", "awayName": "Coastal Spirit",
                        "group": "Premiership", "groupId": 50, "start": "2026-05-31T20:00:00Z",
                        "path": [
                            {"termKey": "football"},
                            {"termKey": "new_zealand", "name": "Nueva Zelanda"},
                            {"termKey": "premiership", "name": "Premiership"},
                        ],
                    },
                    "liveData": {"matchClock": {"minute": 40, "period": "1ª parte"}, "score": {"home": "1", "away": "1"}},
                },
                {
                    "event": {
                        "id": 2, "homeName": "Barça (x)", "awayName": "Madrid (y)", "group": "eBattle",
                        "path": [{"termKey": "football"}, {"termKey": "esports_football", "name": "eSports"}],
                    },
                    "liveData": {},
                },
            ]
        }
        live = live_events_from_open(payload)
        self.assertEqual(len(live), 2)
        real = [e for e in live if e.is_soccer]
        self.assertEqual(len(real), 1)
        e = real[0]
        self.assertEqual((e.home, e.away), ("Northern AFC", "Coastal Spirit"))
        self.assertEqual(e.country_name, "Nueva Zelanda")
        self.assertEqual(e.home_score, 1)
        self.assertIn("40'", e.minute)


class AltenarLiveTests(unittest.TestCase):
    def test_livenow_maps_score_and_country_iso(self) -> None:
        payload = {
            "champs": [{"id": 9, "name": "WPSL"}],
            "categories": [{"id": 5, "name": "USA", "iso": "USA"}, {"id": 6, "name": "GT League", "iso": ""}],
            "events": [
                {"id": 1, "name": "FC Tucson vs. Arizona Arsenal", "champId": 9, "catId": 5,
                 "score": [0, 1], "liveTime": "15'", "ls": "1st half", "startDate": "2026-05-31T20:00:00Z"},
                {"id": 2, "name": "Milan (a) vs. Napoli (b)", "champId": 9, "catId": 6,
                 "score": [0, 0], "liveTime": "Not started", "ls": "Not started"},
            ],
        }
        live = live_events_from_livenow(payload)
        real = [e for e in live if e.is_soccer]
        self.assertEqual(len(real), 1)
        e = real[0]
        self.assertEqual((e.home, e.away), ("FC Tucson", "Arizona Arsenal"))
        self.assertEqual(e.country_name, "USA")
        self.assertEqual((e.home_score, e.away_score), (0, 1))
        self.assertEqual(e.minute, "15'")


class BzLiveTests(unittest.TestCase):
    def test_search_maps_live_matches(self) -> None:
        data = [
            {
                "id": "sr:tournament:1", "name": "Primera", "categoryName": "Brasil",
                "matches": [
                    {"id": "sr:match:9", "homeName": "A", "awayName": "B", "matchStatusName": "2nd half",
                     "scheduledTime": 1780000000000,
                     "sportEventStatus": {"homeScore": 2, "awayScore": 1, "homeRedCards": 0, "awayRedCards": 1}},
                ],
            }
        ]
        live = live_events_from_search(data)
        self.assertEqual(len(live), 1)
        e = live[0]
        self.assertEqual((e.home, e.away), ("A", "B"))
        self.assertEqual(e.minute, "2nd half")
        self.assertEqual((e.home_score, e.away_score), (2, 1))
        self.assertEqual((e.home_red_cards, e.away_red_cards), (0, 1))
        self.assertEqual(e.source_url, "bz:tournament:1")


class BetbyLiveTests(unittest.TestCase):
    def test_snapshot_maps_inplay_only(self) -> None:
        snapshot = {
            "tournaments": {"100": {"name": "Chatham Cup", "category_id": "10"}},
            "categories": {"10": {"name": "New Zealand"}},
            "events": {
                "e1": {  # in-play (running clock)
                    "desc": {"type": "match", "sport": "1", "tournament": "100",
                             "competitors": [{"name": "Bay Olympic"}, {"name": "Birkenhead"}]},
                    "state": {"status": 1, "clock": {"match_time": "25:19"}},
                },
                "e2": {  # not started (no clock, status 0) -> excluded
                    "desc": {"type": "match", "sport": "1", "tournament": "100",
                             "competitors": [{"name": "X"}, {"name": "Y"}]},
                    "state": {"status": 0},
                },
            },
        }
        live = live_events_from_snapshot(snapshot, sport_id="1")
        self.assertEqual(len(live), 1)
        e = live[0]
        self.assertEqual((e.home, e.away), ("Bay Olympic", "Birkenhead"))
        self.assertEqual(e.country_name, "New Zealand")
        self.assertEqual(e.minute, "25:19")

    def test_snapshot_extracts_odds_and_scores(self) -> None:
        snapshot = {
            "tournaments": {"100": {"name": "Chatham Cup", "category_id": "10"}},
            "categories": {"10": {"name": "New Zealand"}},
            "events": {
                "e1": {
                    "desc": {"type": "match", "sport": "1", "tournament": "100",
                             "competitors": [{"name": "Bay Olympic"}, {"name": "Birkenhead"}]},
                    "state": {
                        "status": 1,
                        "clock": {"match_time": "25:19"},
                        "score": {"home": "2", "away": "1"}
                    },
                    "markets": {
                        "1": {"": {"1": {"k": "2.10"}, "2": {"k": "3.40"}, "3": {"k": "3.20"}}}
                    }
                }
            }
        }
        live = live_events_from_snapshot(snapshot, sport_id="1")
        self.assertEqual(len(live), 1)
        e = live[0]
        self.assertEqual((e.home, e.away), ("Bay Olympic", "Birkenhead"))
        self.assertEqual(e.home_score, 2)
        self.assertEqual(e.away_score, 1)
        self.assertEqual(e.odds_1x2.home, 2.10)
        self.assertEqual(e.odds_1x2.draw, 3.40)
        self.assertEqual(e.odds_1x2.away, 3.20)


if __name__ == "__main__":
    unittest.main()

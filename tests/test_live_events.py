from __future__ import annotations

import unittest

from extractors.betovo_http.parser import live_events_from_livenow
from extractors.betwarrior_http.parser import live_events_from_open
from extractors.bz_http.parser import live_events_from_search
from extractors.solcasino_http.parser import live_events_from_snapshot


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
                     "scheduledTime": 1780000000000, "sportEventStatus": {"homeScore": 2, "awayScore": 1}},
                ],
            }
        ]
        live = live_events_from_search(data)
        self.assertEqual(len(live), 1)
        e = live[0]
        self.assertEqual((e.home, e.away), ("A", "B"))
        self.assertEqual(e.minute, "2nd half")
        self.assertEqual((e.home_score, e.away_score), (2, 1))
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


if __name__ == "__main__":
    unittest.main()

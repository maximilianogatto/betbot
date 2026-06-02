from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from core.stats_models import MatchIdentityCandidate
from stats_providers.flashscore_http.parser import parse_day_fixtures, parse_statistics, parse_incidents
from stats_providers.flashscore_http.provider import FlashscoreHttpStatsProvider


def _rec(**fields: str) -> str:
    return "¬".join(f"{k}÷{v}" for k, v in fields.items())


# One league header + two matches (Flashscore ~/¬/÷ format).
DAY_FEED = "~".join(
    [
        _rec(SA="1"),
        _rec(ZA="ARGENTINA: Primera C", ZEE="L1", ZC="S1", ZB="1"),
        _rec(AA="m1", AD="1780000000", AE="Argentino de Quilmes", AF="Ituzaingo", AG="2", AH="1", AB="3"),
        _rec(AA="m2", AD="1780100000", AE="Liniers", AF="Cambaceres", AB="1"),
        _rec(ZA="ALEMANIA: Regionalliga", ZEE="L2", ZB="1"),
        _rec(AA="m3", AD="1780050000", AE="Croatia Berlin", AF="Makkabi Berlin", AG="0", AH="7", AB="3"),
    ]
)

STATS_FEED = "~".join(
    [_rec(SE="Partido"), _rec(SG="Posesión", SH="68%", SI="32%"), _rec(SG="Remates totales", SH="24", SI="12")]
)
SUMMARY_FEED = "~".join([_rec(AC="1er Tiempo"), _rec(IB="32'", IE="8", IF="Jugador X", IOX="1", IOY="0")])
META_FEED = _rec(DA="3", DE="2", DF="1")


class FakeFlashscoreClient:
    settings = SimpleNamespace(timezone_offset=-3, sport_id=1)

    def fetch_day_fixtures(self, *, day_offset: int = 0) -> str:
        return DAY_FEED if day_offset == 0 else ""

    def fetch_match_statistics(self, event_id: str) -> str:
        return STATS_FEED

    def fetch_match_summary(self, event_id: str) -> str:
        return SUMMARY_FEED

    def fetch_match_meta(self, event_id: str) -> str:
        return META_FEED


def _run(coro):
    return asyncio.run(coro)


class FlashscoreParserTests(unittest.TestCase):
    def test_parse_day_fixtures(self) -> None:
        leagues = parse_day_fixtures(DAY_FEED)
        self.assertEqual(len(leagues), 2)
        arg = leagues[0]
        self.assertEqual(arg["country"], "Argentina")
        self.assertEqual(arg["league_name"], "Primera C")
        self.assertEqual(arg["league_id"], "L1")
        self.assertEqual(len(arg["matches"]), 2)
        self.assertEqual(arg["matches"][0]["home"], "Argentino de Quilmes")
        self.assertEqual(arg["matches"][0]["status"], "finished")
        self.assertTrue(arg["matches"][0]["kickoff_utc"].startswith("20"))

    def test_parse_statistics_and_incidents(self) -> None:
        stats = parse_statistics(STATS_FEED)
        self.assertEqual(stats[0], {"name": "Posesión", "home": "68%", "away": "32%"})
        inc = parse_incidents(SUMMARY_FEED)
        self.assertEqual(inc[0]["minute"], "32'")
        self.assertEqual(inc[0]["player"], "Jugador X")


class FlashscoreProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = FlashscoreHttpStatsProvider(client=FakeFlashscoreClient(), day_offsets=(0,))

    def test_search_leagues_by_country(self) -> None:
        opts = _run(self.provider.search_leagues(country_name="Argentina"))
        self.assertEqual(len(opts), 1)
        self.assertEqual(opts[0].league_id, "L1")
        self.assertEqual(opts[0].league_name, "Primera C")
        self.assertEqual(opts[0].provider, "flashscore_http")

    def test_list_fixtures(self) -> None:
        fx = _run(self.provider.list_fixtures("L1"))
        self.assertEqual({f.home for f in fx}, {"Argentino de Quilmes", "Liniers"})

    def test_resolve_and_count(self) -> None:
        cand = MatchIdentityCandidate(home="Argentino Quilmes", away="Ituzaingó", scheduled_at=None)
        link = _run(self.provider.resolve_match(cand, league_id="L1"))
        self.assertIsNotNone(link)
        self.assertEqual(link.stats_match_id, "m1")
        self.assertGreaterEqual(link.confidence, 0.78)
        n = _run(self.provider.count_matching_events("L1", [cand]))
        self.assertEqual(n, 1)

    def test_build_match_report(self) -> None:
        rep = _run(self.provider.build_match_report("m1"))
        self.assertEqual(rep.provider, "flashscore_http")
        self.assertIn("Argentino de Quilmes vs Ituzaingo", rep.title)
        self.assertIn("Posesión: 68% | 32%", rep.markdown)
        self.assertIn("⚽ Gol", rep.markdown)
        self.assertIn("Marcador: 2-1", rep.markdown)


if __name__ == "__main__":
    unittest.main()

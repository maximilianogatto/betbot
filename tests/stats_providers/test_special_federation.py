from __future__ import annotations

import asyncio
import unittest

from bot.special_leagues import LeagueInfo, MatchRow
from core.stats_models import MatchIdentityCandidate
from stats_providers.special_federation.provider import SpecialLeagueStatsProvider


class _FakeAdapter:
    def __init__(self):
        self.closed = False

    def leagues(self):
        return [LeagueInfo(code="L1", name="Liga Uno"), LeagueInfo(code="L2", name="Liga Dos")]

    def fixtures(self, code):
        if code not in ("L1", "L2", "999"):
            return None, []
        rows = [
            MatchRow(match_id="m1", time_arg="14:00", date_arg="2026-06-12",
                     home="Varhaug", away="Viking 2", league_code=code),
            MatchRow(match_id="m2", time_arg="16:00", date_arg="2026-06-12",
                     home="Alta", away="Tromso 2", league_code=code),
        ]
        return f"Liga {code}", rows

    def match_report(self, match_id):
        return f"⚽ *Reporte {match_id}*\n📊 FORMA\n..."

    def close(self):
        self.closed = True


class _FakeProvider(SpecialLeagueStatsProvider):
    name = "fake_fed"
    display_name = "Fake Fed"
    country_label = "Faketania"
    country_aliases = ("faketania", "fakelandia")

    def _make_adapter(self):
        return _FakeAdapter()


class SpecialFederationProviderTests(unittest.TestCase):
    def setUp(self):
        self.p = _FakeProvider()

    def test_search_gated_by_country(self):
        self.assertEqual(asyncio.run(self.p.search_leagues(country_name="Brasil")), [])
        opts = asyncio.run(self.p.search_leagues(country_name="faketania"))
        self.assertEqual([(o.league_id, o.league_name) for o in opts],
                         [("L1", "Liga Uno"), ("L2", "Liga Dos")])

    def test_search_query_filter(self):
        opts = asyncio.run(self.p.search_leagues(country_name="Fakelandia", query="dos"))
        self.assertEqual([o.league_id for o in opts], ["L2"])

    def test_list_fixtures_maps_rows(self):
        fx = asyncio.run(self.p.list_fixtures("L1"))
        self.assertEqual([(f.home, f.away, f.match_id) for f in fx],
                         [("Varhaug", "Viking 2", "m1"), ("Alta", "Tromso 2", "m2")])
        self.assertTrue(fx[0].scheduled_at.startswith("2026-06-12T14:00"))

    def test_resolve_match_fuzzy(self):
        cand = MatchIdentityCandidate(home="Varhaug IL", away="Viking II",
                                      scheduled_at="2026-06-12T14:00:00-03:00")
        link = asyncio.run(self.p.resolve_match(cand, league_id="L1"))
        self.assertIsNotNone(link)
        self.assertEqual(link.stats_match_id, "m1")
        self.assertGreater(link.confidence, 0.72)

    def test_resolve_match_no_league_returns_none(self):
        cand = MatchIdentityCandidate(home="Varhaug", away="Viking 2", scheduled_at=None)
        self.assertIsNone(asyncio.run(self.p.resolve_match(cand, league_id=None)))

    def test_build_match_report_wraps_markdown(self):
        rep = asyncio.run(self.p.build_match_report("m1"))
        self.assertIn("Reporte m1", rep.markdown)
        self.assertEqual(rep.title, "Reporte m1")
        self.assertEqual(rep.provider, "fake_fed")

    def test_describe_league_known_and_unknown(self):
        known = asyncio.run(self.p.describe_league("L1"))
        self.assertEqual(known.league_name, "Liga Uno")
        unknown = asyncio.run(self.p.describe_league("999"))  # not in catalog -> via fixtures name
        self.assertEqual(unknown.league_id, "999")


class NorwayDirectLinkTests(unittest.TestCase):
    def test_reference_from_url_and_id(self):
        from stats_providers.special_federation import NorwayFederationStatsProvider

        p = NorwayFederationStatsProvider()
        self.assertEqual(
            p._reference_from_url("https://www.fotball.no/fotballdata/turnering/hjem/?fiksId=205689"),
            "205689",
        )
        self.assertEqual(p._reference_from_url("205689"), "205689")
        self.assertIsNone(p._reference_from_url("not-a-ref"))


if __name__ == "__main__":
    unittest.main()

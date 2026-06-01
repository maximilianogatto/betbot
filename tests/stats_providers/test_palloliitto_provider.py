import unittest
from stats_providers.palloliitto.provider import PalloliittoStatsProvider
from core.stats_models import MatchIdentityCandidate

class TestPalloliittoStatsProvider(unittest.TestCase):
    
    def setUp(self):
        self.provider = PalloliittoStatsProvider()
        
    def test_provider_metadata(self):
        self.assertEqual(self.provider.name, "palloliitto")
        self.assertIn("Finland", self.provider.display_name)
        self.assertTrue(self.provider.capabilities.supports_league_discovery)
        self.assertTrue(self.provider.capabilities.supports_fixture_discovery)
        self.assertTrue(self.provider.capabilities.supports_lineups)

    def test_search_leagues_empty_country(self):
        # Searching for non-Finland should return empty list
        options = self.provider.search_leagues(country_name="Argentina")
        if hasattr(options, "__await__"):
            # If the method was async
            import asyncio
            options = asyncio.run(options)
        self.assertEqual(options, [])

    def test_search_leagues_success(self):
        import asyncio
        options = self.provider.search_leagues(country_name="Finland", query="Veikkausliiga")
        if hasattr(options, "__await__"):
            options = asyncio.run(options)
        self.assertIsInstance(options, list)
        if options:
            first = options[0]
            self.assertEqual(first.provider, "palloliitto")
            self.assertIn("Veikkausliiga", first.league_name)
            self.assertEqual(first.league_id, "spljp26:VL")

    def test_list_fixtures_success(self):
        import asyncio
        fixtures = self.provider.list_fixtures("spljp26:VL")
        if hasattr(fixtures, "__await__"):
            fixtures = asyncio.run(fixtures)
        self.assertIsInstance(fixtures, list)
        if fixtures:
            first = fixtures[0]
            self.assertEqual(first.provider, "palloliitto")
            self.assertEqual(first.league_id, "spljp26:VL")
            self.assertIsNotNone(first.match_id)
            self.assertIsNotNone(first.home)
            self.assertIsNotNone(first.away)

    def test_resolve_match_direct_url(self):
        import asyncio
        candidate = MatchIdentityCandidate(
            home="FC Inter",
            away="VPS",
            scheduled_at="2026-04-04T17:00:00",
            stats_url="https://tulospalvelu.palloliitto.fi/match/4036852"
        )
        link = self.provider.resolve_match(candidate, league_id="spljp26:VL")
        if hasattr(link, "__await__"):
            link = asyncio.run(link)
        self.assertIsNotNone(link)
        self.assertEqual(link.stats_match_id, "4036852")
        self.assertEqual(link.confidence, 1.0)
        self.assertEqual(link.method, "direct_stats_url")

    def test_build_match_report_success(self):
        import asyncio
        report = self.provider.build_match_report("4036852")
        if hasattr(report, "__await__"):
            report = asyncio.run(report)
        self.assertIsNotNone(report)
        self.assertEqual(report.provider, "palloliitto")
        self.assertEqual(report.match_id, "4036852")
        self.assertIn("Estadio", report.markdown)
        self.assertIn("Fecha", report.markdown)

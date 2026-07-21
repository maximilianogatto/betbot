from __future__ import annotations

import asyncio
import importlib
import tempfile
import unittest
from pathlib import Path

from interfaces.telegram.renderers import group_events_by_physical_match, build_comparison_match_card_message
from core.extractor_base import Extractor, LeagueDiscoveryOption
import os
from core.models import PlatformDescriptor, ProviderCapabilities, CompetitionExtraction, EventSnapshot, CompetitionKey, ActiveEventUpsert, ActiveEventRecord
from core.registry import ExtractorRegistry
from monitors.tracking import TrackingService
from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema


class FakeExtractor(Extractor):
    name = "fake_platform"
    platform = "fake_platform"
    display_name = "Fake Platform"
    supports_league_discovery = True

    def __init__(self) -> None:
        self.leagues = [
            LeagueDiscoveryOption(
                platform="fake_platform",
                platform_display_name="Fake Platform",
                country_id="1",
                country_name="Australia",
                league_id="npl-vic",
                league_name="Australia. NPL Victoria",
                source_url="https://fake.platform/npl-vic",
            ),
            LeagueDiscoveryOption(
                platform="fake_platform",
                platform_display_name="Fake Platform",
                country_id="1",
                country_name="Australia",
                league_id="npl-vic-w",
                league_name="Australia. NPL Victoria (F)",
                source_url="https://fake.platform/npl-vic-w",
            ),
        ]

    def describe_platform(self) -> PlatformDescriptor:
        return PlatformDescriptor(
            key=self.platform,
            display_name=self.display_name,
            implemented=True,
            capabilities=ProviderCapabilities(supports_http=True),
        )

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        return "fake.platform" in url

    async def extract_league(self, url: str) -> CompetitionExtraction:
        # Determine competition ID from URL
        comp_id = "npl-vic" if "npl-vic" in url and "npl-vic-w" not in url else "npl-vic-w"
        comp_name = "Australia. NPL Victoria" if comp_id == "npl-vic" else "Australia. NPL Victoria (F)"
        return CompetitionExtraction(
            competition=CompetitionKey(platform=self.platform, competition_external_id=comp_id),
            competition_name=comp_name,
            source_url=url,
            events=[],
            is_empty=False,
            is_provisional_name=False,
            extracted_at="2026-06-05T12:00:00+00:00",
        )

    async def extract_match(self, url: str) -> EventSnapshot:
        raise NotImplementedError()

    async def search_leagues(
        self, *, country_name: str, query: str | None = None, limit: int = 80
    ) -> list[LeagueDiscoveryOption]:
        res = []
        for l in self.leagues:
            # Match country name
            if country_name and l.country_name.lower() != country_name.lower():
                continue
            # Match query (fuzzy / substring)
            if query:
                if query.lower() in l.league_name.lower():
                    res.append(l)
            else:
                res.append(l)
        return res[:limit]


def make_active_event_record(**kwargs) -> ActiveEventRecord:
    defaults = {
        "id": 1,
        "tracked_competition_id": 1,
        "platform": "bet365",
        "competition_external_id": "c1",
        "external_event_id": "e1",
        "home": "Home Team",
        "away": "Away Team",
        "scheduled_label_date": "07/06",
        "scheduled_label_time": "03:00",
        "scheduled_at": "2026-06-07T03:00:00+00:00",
        "event_url": "https://example.test",
        "odds_home": 1.5,
        "odds_draw": 3.5,
        "odds_away": 4.5,
        "markets_json": None,
        "raw_payload_json": None,
        "alerted": False,
        "is_active": True,
        "first_seen_at": "2026-06-05T00:00:00+00:00",
        "last_seen_at": "2026-06-05T00:00:00+00:00",
        "created_at": "2026-06-05T00:00:00+00:00",
        "updated_at": "2026-06-05T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return ActiveEventRecord(**defaults)


class UnifiedCompetitionsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp.name) / "unified_competitions.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.repository = SqliteStorage()

        self.registry = ExtractorRegistry()
        self.fake_extractor = FakeExtractor()
        self.registry.register(self.fake_extractor)
        self.service = TrackingService(
            extractor_registry=self.registry,
            repository=self.repository,
        )

    def tearDown(self) -> None:
        if self._prev_db is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db
        self.tmp.cleanup()

    def test_automatic_mapping_upon_confirm_pending_competition_request(self) -> None:
        chat_id = 42

        # 1. Track first league
        self.repository.create_pending_competition_request(
            chat_id,
            platform="platform_a",
            source_url="https://platform_a.test/npl-vic",
            competition_external_id="l1",
            competition_name="Australia. NPL Victoria",
            requires_empty_confirmation=False,
            needs_name_resolution=False,
        )
        tracked_1 = self.repository.confirm_pending_competition_request(chat_id)
        self.assertIsNotNone(tracked_1)

        # Verify unified competition is created
        self.assertIsNotNone(tracked_1.unified_competition_id)

        # 2. Track the SAME league on another platform (canonical-equal name).
        self.repository.create_pending_competition_request(
            chat_id,
            platform="platform_b",
            source_url="https://platform_b.test/npl-vic-b",
            competition_external_id="l2",
            competition_name="NPL Victoria, Australia",  # word shuffle -> same league
            requires_empty_confirmation=False,
            needs_name_resolution=False,
        )
        tracked_2 = self.repository.confirm_pending_competition_request(chat_id)
        self.assertIsNotNone(tracked_2)

        # Canonical-equal names share the same unified competition.
        self.assertEqual(tracked_1.unified_competition_id, tracked_2.unified_competition_id)

        # 2b. The WOMEN variant is a different league (gender is a discriminator):
        #     it must NOT auto-merge into the men/unmarked one.
        self.repository.create_pending_competition_request(
            chat_id,
            platform="platform_b",
            source_url="https://platform_b.test/npl-vic-femenil",
            competition_external_id="l2f",
            competition_name="Australia. NPL Victoria (F)",
            requires_empty_confirmation=False,
            needs_name_resolution=False,
        )
        tracked_2f = self.repository.confirm_pending_competition_request(chat_id)
        self.assertNotEqual(tracked_1.unified_competition_id, tracked_2f.unified_competition_id)

        # Verify that a completely different league gets a different unified_competition_id
        self.repository.create_pending_competition_request(
            chat_id,
            platform="platform_a",
            source_url="https://platform_a.test/premier-league",
            competition_external_id="l3",
            competition_name="England. Premier League",
            requires_empty_confirmation=False,
            needs_name_resolution=False,
        )
        tracked_3 = self.repository.confirm_pending_competition_request(chat_id)
        self.assertIsNotNone(tracked_3)
        self.assertNotEqual(tracked_1.unified_competition_id, tracked_3.unified_competition_id)

    def test_sharing_stats_links_dynamically(self) -> None:
        chat_id = 42
        self.repository.create_pending_competition_request(
            chat_id,
            platform="platform_a",
            source_url="https://platform_a.test/npl-vic",
            competition_external_id="l1",
            competition_name="Australia. NPL Victoria",
            requires_empty_confirmation=False,
            needs_name_resolution=False,
        )
        t1 = self.repository.confirm_pending_competition_request(chat_id)

        self.repository.create_pending_competition_request(
            chat_id,
            platform="platform_b",
            source_url="https://platform_b.test/npl-vic",
            competition_external_id="l2",
            competition_name="Australia. NPL Victoria",
            requires_empty_confirmation=False,
            needs_name_resolution=False,
        )
        t2 = self.repository.confirm_pending_competition_request(chat_id)

        # Add stats link to t1
        self.repository.upsert_stats_league_link(
            t1.id,
            stats_provider="sportradar_statshub",
            stats_league_id="888",
            stats_league_name="NPL Victoria",
            stats_country_name="Australia",
            confidence=0.99,
            payload={"test": "data"},
        )

        # List links for t2, which should include the link because they are unified
        links_for_t2 = self.repository.list_stats_league_links(t2.id)
        self.assertEqual(len(links_for_t2), 1)
        self.assertEqual(links_for_t2[0].stats_league_id, "888")

        # get_stats_league_link for t2 should also retrieve it
        link_for_t2 = self.repository.get_stats_league_link(t2.id)
        self.assertIsNotNone(link_for_t2)
        self.assertEqual(link_for_t2.stats_league_id, "888")

    def test_cross_platform_odds_grouping(self) -> None:
        dt_str = "2026-06-07T03:00:00+00:00"

        e1 = make_active_event_record(
            id=1,
            tracked_competition_id=10,
            platform="platform_a",
            external_event_id="e1",
            home="Canberra Olympic",
            away="Belconnen United",
            scheduled_label_date="07/06",
            scheduled_label_time="03:00",
            scheduled_at=dt_str,
            odds_home=1.5,
            odds_draw=4.0,
            odds_away=5.0,
            event_url="https://platform_a.test/e1",
        )

        e2 = make_active_event_record(
            id=2,
            tracked_competition_id=11,
            platform="platform_b",
            external_event_id="e2",
            home="Canberra Olympic",
            away="Belconnen Utd",
            scheduled_label_date="07/06",
            scheduled_label_time="03:00",
            scheduled_at=dt_str,
            odds_home=1.55,
            odds_draw=3.9,
            odds_away=5.2,
            event_url="https://platform_b.test/e2",
        )

        e3 = make_active_event_record(
            id=3,
            tracked_competition_id=10,
            platform="platform_a",
            external_event_id="e3",
            home="Melbourne Victory",
            away="Avondale",
            scheduled_label_date="07/06",
            scheduled_label_time="05:00",
            scheduled_at="2026-06-07T05:00:00+00:00",
            odds_home=2.0,
            odds_draw=3.4,
            odds_away=3.2,
            event_url="https://platform_a.test/e3",
        )

        groups = group_events_by_physical_match([e1, e2, e3])
        self.assertEqual(len(groups), 2)

        canberra_group = next(g for g in groups if g[0].home == "Canberra Olympic")
        self.assertEqual(len(canberra_group), 2)
        self.assertIn(e1, canberra_group)
        self.assertIn(e2, canberra_group)

        card = build_comparison_match_card_message(canberra_group)
        self.assertIn("Canberra Olympic vs Belconnen United", card)
        self.assertIn("1.50", card)
        self.assertIn("1.55", card)

    async def test_bulk_import_parsing_and_auto_tracking(self) -> None:
        chat_id = 99
        text = """Ligas:
📍 Australia. NPL Victoria (F)
• Australia. NPL Victoria
❌ Invalid line without dot
"""
        res = await self.service.bulk_track_leagues(chat_id, text)
        self.assertTrue(res.ok)
        self.assertIn("Resultado de Importación Masiva", res.message)
        self.assertIn("Vigilando en: Fake Platform", res.message)
        self.assertIn("Australia. NPL Victoria (F)", res.message)
        self.assertIn("Australia. NPL Victoria", res.message)

        tracked = self.repository.list_tracked_competitions()
        self.assertEqual(len(tracked), 2)


if __name__ == "__main__":
    unittest.main()

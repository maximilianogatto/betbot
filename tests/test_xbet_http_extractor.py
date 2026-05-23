from __future__ import annotations

import unittest
import importlib
from pathlib import Path
import tempfile

from core.models import CompetitionExtraction
from core.registry import ExtractorRegistry
from extractors import register_default_extractors
from extractors.xbet_http.client import build_champ_url, build_game_url
from extractors.xbet_http import XBetHttpExtractor, XBetHttpSettings
from monitors.tracking import TrackingService
from storage.tracking_repository import SqliteTrackingRepository

tracking_repository_module = importlib.import_module("storage.tracking_repository")


CHAMP_PAYLOAD = {
    "Id": 0,
    "Success": True,
    "Error": "",
    "ErrorCode": 0,
    "Value": {
        "SI": 1,
        "L": "Australia. ACT National Premier League",
        "LI": 2872359,
        "CN": "Australia",
        "G": [
            {
                "I": 722570772,
                "S": 1779510600,
                "O1": "Canberra Olympic",
                "O2": "Belconnen United",
                "O1I": 14361,
                "O2I": 1762,
                "N": 198798,
                "CI": 334482482,
                "CE": "Australia",
            }
        ],
    },
}

CHAMP_WITH_MARKETS_PAYLOAD = {
    **CHAMP_PAYLOAD,
    "Value": {
        **CHAMP_PAYLOAD["Value"],
        "G": [
            {
                **CHAMP_PAYLOAD["Value"]["G"][0],
                "E": [
                    {"T": 1, "G": 1, "C": 1.49},
                    {"T": 2, "G": 1, "C": 4.55},
                    {"T": 3, "G": 1, "C": 4.75},
                    {"T": 7, "G": 2, "P": -1.5, "C": 2.21},
                    {"T": 8, "G": 2, "P": 1.5, "C": 1.62},
                    {"T": 9, "G": 17, "P": 2.5, "C": 1.91},
                    {"T": 10, "G": 17, "P": 2.5, "C": 1.89},
                ],
            }
        ],
    },
}

FUTURE_CHAMP_WITH_MARKETS_PAYLOAD = {
    **CHAMP_WITH_MARKETS_PAYLOAD,
    "Value": {
        **CHAMP_WITH_MARKETS_PAYLOAD["Value"],
        "G": [
            {
                **CHAMP_WITH_MARKETS_PAYLOAD["Value"]["G"][0],
                "S": 4102444800,
            }
        ],
    },
}


class FakeXBetHttpClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.requested_urls: list[str] = []

    async def fetch_champ_zip(self, url: str) -> dict[str, object]:
        self.requested_urls.append(url)
        return self.payload


class XBetHttpExtractorTests(unittest.TestCase):
    def test_can_handle_spinbetter_get_champ_zip(self) -> None:
        url = "https://spinbetter.com/service-api/LineFeed/GetChampZip?champ=2872359&lng=es"
        self.assertTrue(XBetHttpExtractor.can_handle_url(url))

    def test_can_handle_requires_champ_id(self) -> None:
        url = "https://spinbetter.com/service-api/LineFeed/GetChampZip?lng=es"
        self.assertFalse(XBetHttpExtractor.can_handle_url(url))

    def test_can_handle_rejects_unsupported_host(self) -> None:
        url = "https://example.com/service-api/LineFeed/GetChampZip?champ=2872359&lng=es"
        self.assertFalse(XBetHttpExtractor.can_handle_url(url))

    def test_settings_validate_positive_values(self) -> None:
        with self.assertRaises(ValueError):
            XBetHttpSettings(timeout_seconds=0)

    def test_url_builders_normalize_hosts(self) -> None:
        self.assertEqual(
            build_champ_url(base_url="spinbetter.com", champ_id="2872359", language="es"),
            "https://spinbetter.com/service-api/LineFeed/GetChampZip?champ=2872359&lng=es",
        )
        self.assertEqual(
            build_game_url(base_url="spinbetter.com", event_id="722570772", language="es"),
            "https://spinbetter.com/service-api/LineFeed/GetGameZip?id=722570772&lng=es",
        )

    def test_default_registry_includes_1xbet_http(self) -> None:
        registry = ExtractorRegistry()
        register_default_extractors(registry)
        platforms = {platform.key for platform in registry.list_platforms()}
        self.assertIn("1xbet_http", platforms)


class XBetHttpExtractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_extract_league_maps_get_champ_zip_to_competition(self) -> None:
        client = FakeXBetHttpClient(CHAMP_PAYLOAD)
        extractor = XBetHttpExtractor(client=client)

        extraction = await extractor.extract_league(
            "https://spinbetter.com/service-api/LineFeed/GetChampZip?champ=2872359&lng=es"
        )

        self.assertIsInstance(extraction, CompetitionExtraction)
        self.assertEqual(extraction.platform, "1xbet_http")
        self.assertEqual(extraction.competition_external_id, "2872359")
        self.assertEqual(extraction.competition_name, "Australia. ACT National Premier League")
        self.assertEqual(len(extraction.events), 1)
        event = extraction.events[0]
        self.assertEqual(event.external_event_id, "722570772")
        self.assertEqual(event.home, "Canberra Olympic")
        self.assertEqual(event.away, "Belconnen United")
        self.assertEqual(event.scheduled_at, "2026-05-23T04:30:00+00:00")
        self.assertEqual(event.scheduled_label_date, "2026-05-23")
        self.assertEqual(event.scheduled_label_time, "04:30")
        self.assertEqual(event.odds_1x2.home, None)
        self.assertEqual(
            event.source_url,
            "https://spinbetter.com/service-api/LineFeed/GetGameZip?id=722570772&lng=es",
        )
        self.assertEqual(
            client.requested_urls,
            ["https://spinbetter.com/service-api/LineFeed/GetChampZip?champ=2872359&lng=es"],
        )

    async def test_extract_league_normalizes_markets_when_getchampzip_contains_odds(self) -> None:
        client = FakeXBetHttpClient(CHAMP_WITH_MARKETS_PAYLOAD)
        extractor = XBetHttpExtractor(client=client)

        extraction = await extractor.extract_league(
            "https://spinbetter.com/service-api/LineFeed/GetChampZip?champ=2872359&lng=es"
        )

        event = extraction.events[0]
        self.assertEqual(event.odds_1x2.home, 1.49)
        self.assertEqual(event.odds_1x2.draw, 4.55)
        self.assertEqual(event.odds_1x2.away, 4.75)
        assert event.markets_payload is not None
        self.assertEqual(
            event.markets_payload["1x2"],
            {"home": 1.49, "draw": 4.55, "away": 4.75},
        )
        self.assertEqual(
            event.markets_payload["asian_handicap"]["selections"],
            [
                {"selection": "Canberra Olympic", "line": "-1.5", "odds": 2.21},
                {"selection": "Belconnen United", "line": "+1.5", "odds": 1.62},
            ],
        )
        self.assertEqual(
            event.markets_payload["goal_line"]["selections"],
            [
                {"selection": "Over", "line": "2.5", "odds": 1.91},
                {"selection": "Under", "line": "2.5", "odds": 1.89},
            ],
        )

    async def test_tracking_service_persists_1xbet_events_in_existing_schema(self) -> None:
        old_db_path = tracking_repository_module.DB_FILE_PATH
        old_data_dir = tracking_repository_module.DATA_DIR

        with tempfile.TemporaryDirectory() as tmp_dir:
            tracking_repository_module.DATA_DIR = Path(tmp_dir)
            tracking_repository_module.DB_FILE_PATH = Path(tmp_dir) / "tracking.sqlite3"
            try:
                repository = SqliteTrackingRepository()
                registry = ExtractorRegistry()
                registry.register(XBetHttpExtractor(client=FakeXBetHttpClient(FUTURE_CHAMP_WITH_MARKETS_PAYLOAD)))
                service = TrackingService(
                    extractor_registry=registry,
                    repository=repository,
                )
                chat_id = 12345
                url = "https://spinbetter.com/service-api/LineFeed/GetChampZip?champ=2872359&lng=es"

                pending = await service.create_pending_track_from_url(chat_id, url)
                self.assertTrue(pending.ok)
                confirmed = await service.confirm_pending_track(chat_id)
                self.assertTrue(confirmed.ok)

                tracked = repository.list_tracked_competitions(chat_id)
                self.assertEqual(len(tracked), 1)
                self.assertEqual(tracked[0].tracked_league.platform, "1xbet_http")

                active_events = repository.get_active_events(
                    tracked[0].tracked_league.id,
                    only_future=True,
                )
                self.assertEqual(len(active_events), 1)
                event = active_events[0]
                self.assertEqual(event.home, "Canberra Olympic")
                self.assertEqual(event.away, "Belconnen United")
                self.assertEqual(event.odds_home, 1.49)
                self.assertEqual(event.odds_draw, 4.55)
                self.assertEqual(event.odds_away, 4.75)
                self.assertIn("asian_handicap", event.markets_json or "")
                self.assertIn("goal_line", event.markets_json or "")
            finally:
                tracking_repository_module.DB_FILE_PATH = old_db_path
                tracking_repository_module.DATA_DIR = old_data_dir


if __name__ == "__main__":
    unittest.main()

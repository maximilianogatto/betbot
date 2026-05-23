from __future__ import annotations

import unittest

from core.models import CompetitionExtraction
from extractors.xbet_http.client import build_champ_url, build_game_url
from extractors.xbet_http import XBetHttpExtractor, XBetHttpSettings


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


if __name__ == "__main__":
    unittest.main()

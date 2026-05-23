from __future__ import annotations

import unittest

from extractors.xbet_http import XBetHttpExtractor, XBetHttpSettings


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


if __name__ == "__main__":
    unittest.main()

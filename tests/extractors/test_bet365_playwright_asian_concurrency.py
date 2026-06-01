from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from extractors.bet365.client import Bet365HttpClient, Bet365ExtractorSettings


class MockPage:
    def __init__(self) -> None:
        self.evaluate = AsyncMock()
        self.goto = AsyncMock()
        self.wait_for_timeout = AsyncMock()
        self.wait_for_function = AsyncMock()


class MockContext:
    def __init__(self) -> None:
        self.cookies = AsyncMock(return_value=[{"name": "foo", "value": "bar"}])
        self.new_page = AsyncMock(return_value=MockPage())
        self.close = AsyncMock()


class MockBrowser:
    def __init__(self) -> None:
        self.new_context = AsyncMock(return_value=MockContext())
        self.close = AsyncMock()


class MockPlaywrightManager:
    def __init__(self) -> None:
        self.chromium = MagicMock()
        self.chromium.launch = AsyncMock(return_value=MockBrowser())


class MockResponse:
    def __init__(self, status_code: int, content: bytes) -> None:
        self.status_code = status_code
        self.content = content


def _league_matches(count: int) -> list[dict[str, object]]:
    return [
        {
            "fixture_id": str(1000 + index),
            "home": f"Home {index}",
            "away": f"Away {index}",
            "league": "Test League",
            "scheduled_label_date": "2026-05-13",
            "scheduled_label_time": "19:00",
            "scheduled_at": "2026-05-13T22:00:00+00:00",
            "event_url": f"https://www.bet365.bet.ar/#/AC/B1/C1/D8/E{1000 + index}/F3/I1/",
            "stats_url": None,
            "markets_payload": {
                "1x2": {
                    "home": 1.9,
                    "draw": 3.2,
                    "away": 4.1,
                }
            },
            "odds_home": 1.9,
            "odds_draw": 3.2,
            "odds_away": 4.1,
        }
        for index in range(count)
    ]


class Bet365PlaywrightAsianConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_event_captures_respect_max_parallel_event_pages(self) -> None:
        client = Bet365HttpClient(
            Bet365ExtractorSettings(
                max_parallel_event_pages=2,
            )
        )

        active_fetches = 0
        peak_fetches = 0
        lock = asyncio.Lock()

        # Mock page evaluations
        mock_page = MockPage()
        async def mock_evaluate(code: str, *args: object) -> object:
            if "Loader" in code and "xcft" in code:
                if args and isinstance(args[0], list):
                    # Batch coupon token evaluation
                    return [{"url": u, "term": "tok"} for u in args[0]]
                else:
                    # Single league token evaluation
                    return "league_token"
            elif "Guid" in code:
                return "guid_123"
            return None
        mock_page.evaluate = mock_evaluate

        mock_browser = MockBrowser()
        mock_context = MockContext()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        
        mock_pw = MockPlaywrightManager()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        async def fake_get(url: str, *args: object, **kwargs: object) -> MockResponse:
            nonlocal active_fetches, peak_fetches
            if "sports-configuration" in url or "markets" in url:
                return MockResponse(200, b"raw_league_data")
            
            # Coupon URL: check active fetches
            async with lock:
                active_fetches += 1
                peak_fetches = max(peak_fetches, active_fetches)
            await asyncio.sleep(0.02)
            async with lock:
                active_fetches -= 1
            return MockResponse(200, b"raw_coupon_data")

        @asynccontextmanager
        async def mock_playwright_ctx() -> object:
            yield mock_pw

        @asynccontextmanager
        async def mock_session_ctx(*args: object, **kwargs: object) -> object:
            session = MagicMock()
            session.cookies = MagicMock()
            session.get = fake_get
            yield session

        with (
            patch("playwright.async_api.async_playwright", return_value=mock_playwright_ctx()),
            patch("extractors.bet365.client.AsyncSession", side_effect=mock_session_ctx),
            patch(
                "extractors.bet365.client.parse_league_payload",
                return_value={
                    "league_name": "Test League",
                    "topic": "#AC#B1#",
                    "matches": _league_matches(5),
                },
            ),
            patch(
                "extractors.bet365.client.parse_asian_payload",
                return_value={
                    "event": {"league": "Test League"},
                    "markets_payload": {
                        "asian_handicap": {"market_id": "938", "selections": []},
                        "goal_line": {"market_id": "10143", "selections": []},
                    },
                },
            ),
        ):
            extraction = await client.fetch_league(
                "https://www.bet365.bet.ar/#/AC/B1/C1/D1002/E120757998/G40/"
            )

        self.assertEqual(len(extraction.matches), 5)
        # Verify that concurrency did not exceed the limit of 2, but reached 2
        self.assertEqual(peak_fetches, 2)


if __name__ == "__main__":
    unittest.main()

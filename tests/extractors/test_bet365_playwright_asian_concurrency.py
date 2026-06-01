from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from extractors.bet365.client import Bet365ExtractorSettings
from extractors.bet365.playwright_asian import Bet365PlaywrightAsianClient


class _NoopBrowserHandler:
    def __init__(self) -> None:
        self.request_restart = AsyncMock()

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


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
        client = Bet365PlaywrightAsianClient(
            Bet365ExtractorSettings(
                max_parallel_competitions=1,
                max_parallel_event_pages=2,
                capture_attempts=1,
                event_capture_attempts=1,
            ),
            browser_handler=_NoopBrowserHandler(),
        )

        active_event_captures = 0
        peak_event_captures = 0
        event_lock = asyncio.Lock()

        async def fake_capture(url, predicate, **kwargs):
            nonlocal active_event_captures, peak_event_captures
            if kwargs["capture_kind"] == "league":
                return "F|league", "https://example.test/league", []

            async with event_lock:
                active_event_captures += 1
                peak_event_captures = max(peak_event_captures, active_event_captures)
            await asyncio.sleep(0.02)
            async with event_lock:
                active_event_captures -= 1
            return "F|asian", f"https://example.test/{kwargs['capture_id']}", []

        with (
            patch(
                "extractors.bet365.playwright_asian.parse_league_payload",
                return_value={
                    "league_name": "Test League",
                    "topic": "#AC#B1#",
                    "matches": _league_matches(5),
                },
            ),
            patch(
                "extractors.bet365.playwright_asian.parse_asian_payload",
                return_value={
                    "event": {"league": "Test League"},
                    "markets_payload": {
                        "asian_handicap": {"market_id": "938", "selections": []},
                        "goal_line": {"market_id": "10143", "selections": []},
                    },
                },
            ),
            patch.object(client, "_capture_payload_with_retry", side_effect=fake_capture),
        ):
            extraction = await client.extract_league_with_asian_lines(
                "https://www.bet365.bet.ar/#/AC/B1/C1/D1002/E120757998/G40/"
            )

        self.assertEqual(len(extraction.matches), 5)
        self.assertGreaterEqual(peak_event_captures, 2)
        self.assertLessEqual(peak_event_captures, 2)

    async def test_league_captures_respect_max_parallel_competitions(self) -> None:
        client = Bet365PlaywrightAsianClient(
            Bet365ExtractorSettings(
                max_parallel_competitions=2,
                max_parallel_event_pages=1,
                capture_attempts=1,
                event_capture_attempts=1,
            ),
            browser_handler=_NoopBrowserHandler(),
        )

        active_league_captures = 0
        peak_league_captures = 0
        league_lock = asyncio.Lock()

        async def fake_capture(url, predicate, **kwargs):
            nonlocal active_league_captures, peak_league_captures
            if kwargs["capture_kind"] == "league":
                async with league_lock:
                    active_league_captures += 1
                    peak_league_captures = max(peak_league_captures, active_league_captures)
                await asyncio.sleep(0.02)
                async with league_lock:
                    active_league_captures -= 1
                return "F|league", f"https://example.test/{kwargs['capture_id']}", []

            return "F|asian", f"https://example.test/{kwargs['capture_id']}", []

        async def fake_event_extract(host, match):
            return {
                "error": None,
                "captured_url": f"https://example.test/{match['fixture_id']}",
                "debug": [],
                "event": {"league": "Test League"},
                "markets_payload": {},
                "asian_lines_unavailable": False,
                "duration_seconds": 0.01,
            }

        with (
            patch(
                "extractors.bet365.playwright_asian.parse_league_payload",
                return_value={
                    "league_name": "Test League",
                    "topic": "#AC#B1#",
                    "matches": _league_matches(1),
                },
            ),
            patch.object(client, "_capture_payload_with_retry", side_effect=fake_capture),
            patch.object(client, "_extract_event_asian_lines", side_effect=fake_event_extract),
        ):
            await asyncio.gather(
                client.extract_league_with_asian_lines(
                    "https://www.bet365.bet.ar/#/AC/B1/C1/D1002/E120757998/G40/"
                ),
                client.extract_league_with_asian_lines(
                    "https://www.bet365.bet.ar/#/AC/B1/C1/D1002/E123521148/G40/"
                ),
                client.extract_league_with_asian_lines(
                    "https://www.bet365.bet.ar/#/AC/B1/C1/D1002/E129621231/G40/"
                ),
            )

        self.assertGreaterEqual(peak_league_captures, 2)
        self.assertLessEqual(peak_league_captures, 2)


if __name__ == "__main__":
    unittest.main()

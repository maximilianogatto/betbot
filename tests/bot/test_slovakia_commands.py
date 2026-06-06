from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bot.handlers import (
    sk_leagues_command,
    sk_standings_command,
    sk_fixtures_command,
    sk_today_command,
    sk_match_command,
)

def _update():
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(message=message), message

class SkCommandTests(unittest.IsolatedAsyncioTestCase):
    def _patch_client(self, **methods):
        client = MagicMock()
        for name, value in methods.items():
            getattr(client, name).return_value = value
        client.close = MagicMock()
        return patch("stats_providers.slovakia_http.client.SlovakSportnetHTTPClient", return_value=client)

    async def test_leagues_lists_codes(self) -> None:
        update, message = _update()
        await sk_leagues_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("I. Liga Ženy", out)
        self.assertIn("`SK1A`", out)

    async def test_standings_renders_table(self) -> None:
        update, message = _update()
        part_data = {
            "resultsTable": {
                "results": [
                    {
                        "team": {"name": "Spartak Myjava"},
                        "stats": {
                            "matches": {"played": 25},
                            "points": 70,
                            "goals": {"given": 124, "received": 13}
                        }
                    }
                ]
            }
        }
        with self._patch_client(get_part=part_data):
            await sk_standings_command(update, SimpleNamespace(args=["SK1A"]))
        out = message.reply_text.await_args.args[0]
        self.assertIn("Posiciones: I. Liga Ženy - Play-off", out)
        self.assertIn("Spartak Myjava", out)

    async def test_fixtures_lists_matches_with_ids(self) -> None:
        update, message = _update()
        matches_data = {
            "matches": [
                {
                    "_id": "686114335a52cdc943092875",
                    "competitionPart": {"_id": "69a0455e2d75b679881fcbd4"},
                    "startDate": "2025-08-16T16:00:00.000Z",
                    "teams": [
                        {"name": "Tatran Presov", "additionalProperties": {"homeaway": "home"}},
                        {"name": "Zilina", "additionalProperties": {"homeaway": "away"}}
                    ],
                    "score": [2, 3]
                }
            ]
        }
        with self._patch_client(get_matches=matches_data):
            await sk_fixtures_command(update, SimpleNamespace(args=["SK1A"]))
        out = message.reply_text.await_args.args[0]
        self.assertIn("Tatran Presov", out)
        self.assertIn("686114335a52cdc943092875", out)

    async def test_today_filters_today_matches(self) -> None:
        from datetime import date
        today_str = date.today().isoformat()
        update, message = _update()
        # Matches today (using UTC T16:00:00.000Z which is translated to Argentina today)
        matches_data = {
            "matches": [
                {
                    "_id": "today_match_id",
                    "competitionPart": {"_id": "69a0455e2d75b679881fcbd4"},
                    "startDate": f"{today_str}T16:00:00.000Z",
                    "teams": [
                        {"name": "Presov Today", "additionalProperties": {"homeaway": "home"}},
                        {"name": "Zilina Today", "additionalProperties": {"homeaway": "away"}}
                    ],
                    "score": None
                }
            ]
        }
        with self._patch_client(get_matches=matches_data):
            await sk_today_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("Presov Today", out)
        self.assertIn("today_match_id", out)

    async def test_sk_match_returns_not_supported(self) -> None:
        update, message = _update()
        await sk_match_command(update, SimpleNamespace(args=["123456"]))
        out = message.reply_text.await_args.args[0]
        self.assertIn("no está disponible", out)

if __name__ == "__main__":
    unittest.main()

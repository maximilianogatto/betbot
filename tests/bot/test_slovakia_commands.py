from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from interfaces.telegram.handlers import (
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
        self.assertIn("I. liga ženy", out)
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
        self.assertIn("Posiciones: I. liga ženy - Play-off", out)
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

    async def test_sk_match_success(self) -> None:
        update, message = _update()
        match_detail = {
            "competitionId": "6849d25aeba10c40f7f8ff85",
            "competitionPart": {"_id": "part_123", "name": "I. liga ženy"},
            "startDate": "2026-06-11T16:00:00.000Z",
            "status": "ODOHRATY",
            "score": [3, 0],
            "teams": [
                {"_id": "team_home", "name": "TJ Družstevník Hlboké", "additionalProperties": {"homeaway": "home"}},
                {"_id": "team_away", "name": "FC Družstevník Rybky", "additionalProperties": {"homeaway": "away"}},
            ],
            "nominations": [
                {
                    "team": {"_id": "team_home"},
                    "athletes": [
                        {"name": "Michal Hrušecký", "shirtNo": 10, "position": "GK", "substitute": False},
                    ]
                },
                {
                    "team": {"_id": "team_away"},
                    "athletes": [
                        {"name": "Jaroslav Paszko", "shirtNo": 14, "position": "FW", "substitute": False},
                    ]
                }
            ],
            "protocol": {
                "events": [
                    {"eventType": "goal", "player": {"name": "Michal Hrušecký"}, "team": "team_home", "phase": "1HT", "eventTime": "10:00"},
                    {"eventType": "yellow_card", "player": {"name": "Jaroslav Paszko"}, "team": "team_away", "phase": "1HT", "eventTime": "34:00"},
                ]
            }
        }
        with self._patch_client(get_match_detail=match_detail, get_matches={"matches": []}):
            await sk_match_command(update, SimpleNamespace(args=["123456"]))
            
        self.assertGreaterEqual(message.reply_text.await_count, 2)
        out = message.reply_text.await_args.args[0]
        self.assertIn("TJ Družstevník Hlboké 3-0 FC Družstevník Rybky", out)
        self.assertIn("Michal Hrušecký", out)
        self.assertIn("10:00", out)

if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bot.handlers import (
    ro_leagues_command,
    ro_standings_command,
    ro_fixtures_command,
    ro_today_command,
    ro_match_command,
)

def _update():
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(message=message), message

class RoCommandTests(unittest.IsolatedAsyncioTestCase):
    def _patch_client(self, **methods):
        client = MagicMock()
        for name, value in methods.items():
            getattr(client, name).return_value = value
        client.close = MagicMock()
        return patch("stats_providers.romania_http.client.RomaniaFRFHTTPClient", return_value=client)

    async def test_leagues_lists_codes(self) -> None:
        update, message = _update()
        await ro_leagues_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("SuperLiga Feminină", out)
        self.assertIn("`RO1`", out)

    async def test_standings_renders_table(self) -> None:
        update, message = _update()
        data = {
            "responseData": {
                "rankings": [
                    ["4130", "18", "49", "82", "8", "16", "1", "1", "0"],
                ],
                "clubsRanking": [
                    {"clubId": 4130, "name": "ACS Kids Tampa"}
                ]
            }
        }
        filters = {
            "responseData": {
                "tours": [
                    {"tourRoundId": 43614, "seriesId": 3895, "seasonId": 20, "stageId": 94, "isCurrent": True}
                ]
            }
        }
        with self._patch_client(get_filters=filters, get_matches=data):
            await ro_standings_command(update, SimpleNamespace(args=["RO2S1"]))
        out = message.reply_text.await_args.args[0]
        self.assertIn("Posiciones: Liga 2 Feminin Seria 1", out)
        self.assertIn("ACS Kids Tampa", out)

    async def test_fixtures_lists_matches_with_ids(self) -> None:
        update, message = _update()
        filters = {
            "responseData": {
                "tours": [
                    {"tourRoundId": 43614, "seriesId": 3895, "seasonId": 20, "stageId": 94, "isCurrent": True}
                ]
            }
        }
        matches_data = {
            "responseData": {
                "matches": [
                    {
                        "list": [
                            {
                                "matchId": 123456,
                                "startDate": "2026-05-30T14:00:00",
                                "homeClub": {"name": "Kids Tampa"},
                                "awayClub": {"name": "Alexandria"},
                                "homeGoals": 0,
                                "awayGoals": 1,
                                "sysCompetitionMatchStatusId": 3
                            }
                        ]
                    }
                ]
            }
        }
        with self._patch_client(get_filters=filters, get_matches=matches_data):
            await ro_fixtures_command(update, SimpleNamespace(args=["RO2S1"]))
        out = message.reply_text.await_args.args[0]
        self.assertIn("Kids Tampa", out)
        self.assertIn("123456", out)

    async def test_today_filters_today_matches(self) -> None:
        from datetime import date
        today_str = date.today().isoformat()
        update, message = _update()
        filters = {
            "responseData": {
                "tours": [
                    {"tourRoundId": 43614, "seriesId": 3895, "seasonId": 20, "stageId": 94, "isCurrent": True}
                ]
            }
        }
        matches_data = {
            "responseData": {
                "matches": [
                    {
                        "list": [
                            {
                                "matchId": 99999,
                                "startDate": f"{today_str}T14:00:00",
                                "homeClub": {"name": "Tampa Today"},
                                "awayClub": {"name": "Alexandria Today"},
                                "homeGoals": None,
                                "awayGoals": None,
                                "sysCompetitionMatchStatusId": 1
                            }
                        ]
                    }
                ]
            }
        }
        with self._patch_client(get_filters=filters, get_matches=matches_data):
            await ro_today_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("Tampa Today", out)
        self.assertIn("99999", out)

    async def test_ro_match_success(self) -> None:
        update, message = _update()
        filters = {
            "responseData": {
                "tours": [
                    {"tourRoundId": 43614, "seriesId": 3895, "seasonId": 20, "stageId": 94, "isCurrent": True, "startDate": "2026-06-01"}
                ]
            }
        }
        matches_data = {
            "responseData": {
                "matches": [
                    {
                        "list": [
                            {
                                "matchId": 123456,
                                "startDate": "2026-05-30T14:00:00",
                                "homeClub": {"name": "Kids Tampa"},
                                "awayClub": {"name": "Alexandria"},
                                "homeGoals": 0,
                                "awayGoals": 1,
                                "sysCompetitionMatchStatusId": 3
                            }
                        ]
                    }
                ]
            }
        }
        with self._patch_client(get_filters=filters, get_matches=matches_data):
            await ro_match_command(update, SimpleNamespace(args=["123456"]))
            
        self.assertGreaterEqual(message.reply_text.await_count, 2)
        out = message.reply_text.await_args.args[0]
        self.assertIn("Kids Tampa 0-1 Alexandria", out)
        self.assertIn("FORMA", out)

if __name__ == "__main__":
    unittest.main()

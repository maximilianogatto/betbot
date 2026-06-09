from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bot.handlers import (
    _convert_swe_to_arg_datetime,
    _resolve_swe_league,
    swe_fixtures_command,
    swe_leagues_command,
    swe_standings_command,
    swe_today_command,
    swe_match_command,
)


def _update():
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(message=message), message


class SweHelperTests(unittest.TestCase):
    def test_resolve_league(self) -> None:
        self.assertEqual(_resolve_swe_league("al"), ("133348", "Allsvenskan", "Tier 1 · Varones"))
        self.assertEqual(_resolve_swe_league("DA")[0], "133440")
        self.assertIsNone(_resolve_swe_league("ZZ"))

    def test_convert_to_arg(self) -> None:
        # Sweden (CEST, UTC+2 in July) 19:00 -> Argentina (UTC-3) 14:00 same day.
        d, t = _convert_swe_to_arg_datetime("2026-07-03 19:00")
        self.assertEqual((d, t), ("2026-07-03", "14:00"))
        # Accepts ISO 'T' separator too.
        self.assertEqual(_convert_swe_to_arg_datetime("2026-06-03T19:30:00")[1], "14:30")
        self.assertEqual(_convert_swe_to_arg_datetime(None), ("N/A", "N/A"))


class SweCommandTests(unittest.IsolatedAsyncioTestCase):
    def _patch_client(self, **methods):
        client = MagicMock()
        for name, value in methods.items():
            getattr(client, name).return_value = value
        client.close = MagicMock()
        return patch("stats_providers.svenskfotboll_http.client.SvenskfotbollHTTPClient", return_value=client)

    async def test_leagues_lists_codes(self) -> None:
        update, message = _update()
        await swe_leagues_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("Allsvenskan", out)
        self.assertIn("`AL`", out)

    async def test_standings_renders_table(self) -> None:
        update, message = _update()
        data = {"title": "Allsvenskan 2026", "teams": [
            {"team": "IK Sirius FK", "played": 10, "points": 28, "goal_difference": 17},
        ]}
        with self._patch_client(get_standings=data):
            await swe_standings_command(update, SimpleNamespace(args=["AL"]))
        out = message.reply_text.await_args.args[0]
        self.assertIn("Posiciones: Allsvenskan", out)
        self.assertIn("IK Sirius FK", out)

    async def test_standings_invalid_code_shows_guide(self) -> None:
        update, message = _update()
        await swe_standings_command(update, SimpleNamespace(args=["ZZ"]))
        self.assertIn("No reconozco la liga", message.reply_text.await_args.args[0])

    async def test_fixtures_lists_matches_with_ids(self) -> None:
        update, message = _update()
        data = {"matches": [{"match_id": "6529914", "start_time_local": "2026-07-03 19:00", "home": "Sirius", "away": "Mjällby"}]}
        with self._patch_client(get_upcoming_matches=data):
            await swe_fixtures_command(update, SimpleNamespace(args=["AL"]))
        out = message.reply_text.await_args.args[0]
        self.assertIn("Sirius", out)
        self.assertIn("6529914", out)

    async def test_today_uses_arg_time(self) -> None:
        update, message = _update()
        today = [{"match_id": "1", "competition_name": "Allsvenskan 2026", "home": "A", "away": "B", "start_time_local": "2026-07-03T19:00:00"}]
        with self._patch_client(get_matches_today=today):
            await swe_today_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("Partidos de Hoy", out)
        self.assertIn("14:00", out)

    async def test_today_sorts_chronologically(self) -> None:
        update, message = _update()
        today = [
            {"match_id": "2", "competition_name": "Allsvenskan 2026", "home": "Home2", "away": "Away2", "start_time_local": "2026-07-03T21:00:00"},
            {"match_id": "1", "competition_name": "Allsvenskan 2026", "home": "Home1", "away": "Away1", "start_time_local": "2026-07-03T19:00:00"},
        ]
        with self._patch_client(get_matches_today=today):
            await swe_today_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("Partidos de Hoy", out)
        idx1 = out.index("Home1")
        idx2 = out.index("Home2")
        self.assertLess(idx1, idx2)

    async def test_swe_match_success(self) -> None:
        update, message = _update()
        game_info = {
            "home": "AIK",
            "away": "GAIS",
            "score": "2-1",
            "status": "In Play",
            "events": [
                {"minute": "12'", "type": "Goal", "player": "Player A"},
                {"minute": "45'", "type": "Yellow Card", "player": "Player B"},
            ]
        }
        with self._patch_client(get_live_game_info=game_info):
            await swe_match_command(update, SimpleNamespace(args=["6529915"]))
        
        # Note: _reply_text_chunks uses Message.reply_text to reply, so the mock assertions hold
        message.reply_text.assert_awaited_once()
        out = message.reply_text.await_args.args[0]
        self.assertIn("AIK vs GAIS", out)
        self.assertIn("Marcador: 2-1", out)
        self.assertIn("- 12' Goal Player A", out)


_CUP_TREE = {
    "seasonId": 0,
    "competitions": [
        {"category": "Svenska Cupen, herrar", "comps": [
            {"id": 127930, "name": "Svenska Cupen 2025/26, Slutspel"},
            {"id": 137810, "name": "Svenska Cupen 2026/27 omg. 1-2"},
        ]},
        {"category": "Svenska Cupen, damer", "comps": [
            {"id": 137816, "name": "Svenska Cupen 2026/27 omg. 1-3"},
        ]},
    ],
}


class SweCupTests(unittest.IsolatedAsyncioTestCase):
    def _patch_client(self, **methods):
        client = MagicMock()
        for name, value in methods.items():
            getattr(client, name).return_value = value
        client.close = MagicMock()
        return patch("stats_providers.svenskfotboll_http.client.SvenskfotbollHTTPClient", return_value=client)

    async def test_leagues_includes_cup(self) -> None:
        update, message = _update()
        with self._patch_client(get_competition_tree=_CUP_TREE):
            await swe_leagues_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("Svenska Cupen", out)
        self.assertIn("`SC`", out)
        self.assertIn("`SCD`", out)

    async def test_cup_resolves_latest_season_only(self) -> None:
        from bot.special_leagues import SwedenLeagues
        from bot.handlers import _SWE_LEAGUES
        client = MagicMock()
        client.get_competition_tree.return_value = _CUP_TREE
        s = SwedenLeagues(client, _SWE_LEAGUES)
        cups = s._resolve_cups()
        # 2026/27 wins over 2025/26: men's Slutspel id must be excluded.
        self.assertEqual(cups["SC"][1], ["137810"])
        self.assertEqual(cups["SCD"][1], ["137816"])

    async def test_cup_standings_shows_knockout_note(self) -> None:
        update, message = _update()
        with self._patch_client(get_competition_tree=_CUP_TREE, get_standings={"teams": []}):
            await swe_standings_command(update, SimpleNamespace(args=["SC"]))
        out = message.reply_text.await_args.args[0]
        self.assertIn("copa", out.lower())
        self.assertIn("/swe_fixtures SC", out)

    async def test_cup_today_maps_to_cup_code(self) -> None:
        update, message = _update()
        today = [{"match_id": "9", "competition_id": "137810",
                  "competition_name": "Svenska Cupen 2026/27 omg. 1-2",
                  "home": "Rappe", "away": "Hassleholm",
                  "start_time_local": "2026-06-09T19:00:00"}]
        with self._patch_client(get_competition_tree=_CUP_TREE, get_matches_today=today):
            await swe_today_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("Svenska Cupen", out)
        self.assertNotIn("202627", out)  # season must not leak into name/slug


if __name__ == "__main__":
    unittest.main()

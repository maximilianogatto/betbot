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
        self.assertIn("Ligas disponibles", message.reply_text.await_args.args[0])

    async def test_fixtures_lists_matches_with_ids(self) -> None:
        update, message = _update()
        data = {"matches": [{"match_id": "6529914", "start_time_local": "2026-07-03 19:00", "home": "Sirius", "away": "Mjällby"}]}
        with self._patch_client(get_upcoming_matches=data):
            await swe_fixtures_command(update, SimpleNamespace(args=["AL"]))
        out = message.reply_text.await_args.args[0]
        self.assertIn("Sirius", out)
        self.assertIn("/swe_match 6529914", out)

    async def test_today_uses_arg_time(self) -> None:
        update, message = _update()
        today = [{"match_id": "1", "competition_name": "Allsvenskan 2026", "home": "A", "away": "B", "start_time_local": "2026-07-03T19:00:00"}]
        with self._patch_client(get_matches_today=today):
            await swe_today_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("Partidos de hoy (Suecia)", out)
        self.assertIn("14:00", out)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from interfaces.telegram.handlers import (
    al_help_command,
    al_leagues_command,
    al_standings_command,
    al_fixtures_command,
    al_today_command,
    al_match_command,
)

def _update():
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(message=message), message

class AlCommandTests(unittest.IsolatedAsyncioTestCase):
    def _patch_client(self, **methods):
        client = MagicMock()
        for name, value in methods.items():
            getattr(client, name).return_value = value
        client.close = MagicMock()
        return patch("stats_providers.algeria_http.client.AlgeriaLNFFHTTPClient", return_value=client)

    async def test_help_command(self) -> None:
        update, message = _update()
        await al_help_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("Guía de Estadísticas de la Federación de Argelia", out)
        self.assertIn("`/al_leagues`", out)

    async def test_leagues_lists_codes(self) -> None:
        update, message = _update()
        await al_leagues_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("D1 Seniors Damas", out)
        self.assertIn("`DZ1`", out)

    async def test_standings_renders_table(self) -> None:
        update, message = _update()
        data = [
            {
                "division": "Division Nationale D1 2024-2025",
                "date_raw": "25-10-2024 10:00",
                "home": "CE Atlétic Sétif",
                "away": "FC Béjaia",
                "score_raw": "2 - 1",
                "match_url": "https://lnff.dz/joomsport_match/setif-vs-bejaia/"
            }
        ]
        with self._patch_client(get_matches=data):
            await al_standings_command(update, SimpleNamespace(args=["DZ1"]))
        out = message.reply_text.await_args.args[0]
        self.assertIn("Posiciones: D1 Seniors Damas (2024/2025)", out)
        self.assertIn("CE Atlétic Sétif", out)
        self.assertIn("FC Béjaia", out)

    async def test_fixtures_lists_matches_with_ids(self) -> None:
        update, message = _update()
        data = [
            {
                "division": "Division Nationale D1 2024-2025",
                "date_raw": "25-10-2024 10:00",
                "home": "CE Atlétic Sétif",
                "away": "AR GUELMA",
                "score_raw": "2 - 0",
                "match_url": "https://lnff.dz/joomsport_match/setif-vs-guelma/"
            }
        ]
        with self._patch_client(get_matches=data):
            await al_fixtures_command(update, SimpleNamespace(args=["DZ1"]))
        out = message.reply_text.await_args.args[0]
        self.assertIn("CE Atlétic Sétif", out)
        self.assertIn("setif-vs-guelma", out)

    async def test_today_filters_today_matches(self) -> None:
        from datetime import date
        # Convert today to DD-MM-YYYY format
        today_formatted = date.today().strftime("%d-%m-%Y")
        update, message = _update()
        data = [
            {
                "division": "Division Nationale D1 2024-2025",
                "date_raw": f"{today_formatted} 10:00",
                "home": "Sétif Today",
                "away": "Guelma Today",
                "score_raw": "vs",
                "match_url": "https://lnff.dz/joomsport_match/setif-vs-guelma-today/"
            }
        ]
        with self._patch_client(get_matches=data):
            await al_today_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("Sétif Today", out)
        self.assertIn("setif-vs-guelma-today", out)

    async def test_al_match_returns_details(self) -> None:
        update, message = _update()
        data = [
            {
                "division": "Division Nationale D1 2024-2025",
                "date_raw": "25-10-2024 10:00",
                "home": "CE Atlétic Sétif",
                "away": "FC Béjaia",
                "score_raw": "2 - 1",
                "match_url": "https://lnff.dz/joomsport_match/setif-vs-bejaia/"
            }
        ]
        with self._patch_client(get_matches=data):
            await al_match_command(update, SimpleNamespace(args=["setif-vs-bejaia"]))
        out = message.reply_text.await_args.args[0]
        self.assertIn("CE Atlétic Sétif", out)
        self.assertIn("FC Béjaia", out)
        self.assertIn("no está disponible", out)

if __name__ == "__main__":
    unittest.main()

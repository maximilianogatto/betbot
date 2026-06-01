from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot.handlers import (
    fin_help_command,
    fin_leagues_command,
    fin_standings_command,
    fin_fixtures_command,
    fin_today_command,
    fin_match_command,
)

class TestFinlandCommands(unittest.IsolatedAsyncioTestCase):
    
    async def test_fin_leagues_command_success(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=[])
        update = SimpleNamespace(message=message)

        # Mocking the api client ranking list
        mock_leagues = [
            {"sport": "Football", "name": "Veikkausliiga", "category_id": "VL", "gender": "Men", "tier": 1}
        ]
        
        with patch("stats_providers.palloliitto.api_client.PalloliittoAPI.get_league_ranking_list", return_value=mock_leagues):
            await fin_leagues_command(update, context)
            
        message.reply_text.assert_awaited_once()
        args = message.reply_text.await_args.args[0]
        self.assertIn("Jerarquía de Ligas Finlandesas", args)
        self.assertIn("Veikkausliiga", args)
        self.assertIn("VL", args)

    async def test_fin_standings_command_no_args_shows_guide(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=[])
        update = SimpleNamespace(message=message)

        await fin_standings_command(update, context)
        
        message.reply_text.assert_awaited_once()
        args = message.reply_text.await_args.args[0]
        self.assertIn("Código de liga ausente o inválido", args)
        self.assertIn("fin_standings", args)

    async def test_fin_standings_command_valid_league(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=["VL"])
        update = SimpleNamespace(message=message)

        mock_standings = [
            {"current_standing": 1, "team_name": "FC Inter", "matches_played": 11, "points": 24, "goals_diff": 9}
        ]
        
        with patch("stats_providers.palloliitto.api_client.PalloliittoAPI.get_standings", return_value=mock_standings):
            await fin_standings_command(update, context)
            
        self.assertEqual(message.reply_text.call_count, 2)
        self.assertEqual(message.reply_text.call_args_list[0][0][0], "📊 Cargando tabla de posiciones de la federación...")
        report = message.reply_text.call_args_list[1][0][0]
        self.assertIn("FC Inter", report)
        self.assertIn("24", report)

    async def test_fin_fixtures_command_no_args_shows_guide(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=[])
        update = SimpleNamespace(message=message)

        await fin_fixtures_command(update, context)
        
        message.reply_text.assert_awaited_once()
        args = message.reply_text.await_args.args[0]
        self.assertIn("Código de liga ausente o inválido", args)
        self.assertIn("fin_fixtures", args)

    async def test_fin_today_command_success(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=[])
        update = SimpleNamespace(message=message)

        mock_matches = [
            {"category_id": "VL", "category_name": "Veikkausliiga", "home_team_name": "HJK", "away_team_name": "SJK", "time": "18:00", "match_id": "4036853", "status": "Scheduled"}
        ]
        
        # We mock the date imported inside bot.handlers
        mock_date = Mock()
        mock_date.today.return_value.isoformat.return_value = "2026-06-01"
        
        with patch("bot.handlers.date", mock_date):
            with patch("stats_providers.palloliitto.api_client.PalloliittoAPI.get_matches_by_date", return_value=mock_matches):
                await fin_today_command(update, context)
            
        self.assertEqual(message.reply_text.call_count, 2)
        self.assertIn("Partidos de Hoy", message.reply_text.call_args_list[1][0][0])
        self.assertIn("HJK", message.reply_text.call_args_list[1][0][0])
        self.assertIn("4036853", message.reply_text.call_args_list[1][0][0])


    async def test_fin_match_command_no_args_shows_guide(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=[])
        update = SimpleNamespace(message=message)

        await fin_match_command(update, context)
        
        message.reply_text.assert_awaited_once()
        args = message.reply_text.await_args.args[0]
        self.assertIn("ID de partido ausente o inválido", args)
        self.assertIn("fin_match", args)

    async def test_fin_help_command_success(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=[])
        update = SimpleNamespace(message=message)

        await fin_help_command(update, context)

        message.reply_text.assert_awaited_once()
        args = message.reply_text.await_args.args[0]
        self.assertIn("Guía de Estadísticas de la Federación de Finlandia", args)
        self.assertIn("fin_leagues", args)
        self.assertIn("B-Team", args)



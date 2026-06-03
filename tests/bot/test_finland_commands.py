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
    async def test_fin_today_command_filters_futsal(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=[])
        update = SimpleNamespace(message=message)

        mock_matches = [
            {"category_id": "VL", "category_name": "Miesten Futsal-Liiga", "home_team_name": "HJK Futsal", "away_team_name": "SJK Futsal", "time": "18:00", "match_id": "4036853", "status": "Scheduled"},
            {"category_id": "VL", "category_name": "Veikkausliiga", "home_team_name": "HJK", "away_team_name": "SJK", "time": "19:00", "match_id": "4036854", "status": "Scheduled"},
        ]
        
        mock_date = Mock()
        mock_date.today.return_value.isoformat.return_value = "2026-06-01"
        
        with patch("bot.handlers.date", mock_date):
            with patch("stats_providers.palloliitto.api_client.PalloliittoAPI.get_matches_by_date", return_value=mock_matches):
                await fin_today_command(update, context)
            
        self.assertEqual(message.reply_text.call_count, 2)
        response = message.reply_text.call_args_list[1][0][0]
        self.assertIn("HJK vs SJK", response)
        self.assertNotIn("Futsal", response)

    async def test_fin_today_command_many_matches_shows_menu(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=[])
        update = SimpleNamespace(message=message)

        mock_matches = [
            {"category_id": "VL", "category_name": "Veikkausliiga", "home_team_name": f"Home {i}", "away_team_name": f"Away {i}", "time": "18:00", "match_id": f"id_{i}", "status": "Scheduled"}
            for i in range(6)
        ]
        
        mock_date = Mock()
        mock_date.today.return_value.isoformat.return_value = "2026-06-01"
        
        with patch("bot.handlers.date", mock_date):
            with patch("stats_providers.palloliitto.api_client.PalloliittoAPI.get_matches_by_date", return_value=mock_matches):
                await fin_today_command(update, context)
            
        self.assertEqual(message.reply_text.call_count, 2)
        response = message.reply_text.call_args_list[1][0][0]
        self.assertIn("Selecciona una liga para ver los partidos de hoy", response)
        self.assertIn("• `Veikkausliiga (Tier 1)` (6 part.) ➔ `/fin_today VL`", response)

    async def test_fin_today_command_with_league_argument(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=["VL"])
        update = SimpleNamespace(message=message)

        mock_matches = [
            {"category_id": "VL", "category_name": "Veikkausliiga", "home_team_name": "HJK", "away_team_name": "SJK", "time": "18:00", "match_id": "vl_1", "status": "Scheduled"},
            {"category_id": "M2", "category_name": "Kakkonen", "home_team_name": "TPV", "away_team_name": "Ilves II", "time": "18:00", "match_id": "m2_1", "status": "Scheduled"},
        ]
        
        mock_date = Mock()
        mock_date.today.return_value.isoformat.return_value = "2026-06-01"
        
        with patch("bot.handlers.date", mock_date):
            with patch("stats_providers.palloliitto.api_client.PalloliittoAPI.get_matches_by_date", return_value=mock_matches):
                await fin_today_command(update, context)
            
        self.assertEqual(message.reply_text.call_count, 2)
        response = message.reply_text.call_args_list[1][0][0]
        self.assertIn("Partidos de VL", response)
        self.assertIn("HJK vs SJK", response)
        self.assertNotIn("TPV vs Ilves II", response)


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

    def test_convert_fin_to_arg_datetime(self) -> None:
        from bot.handlers import _convert_fin_to_arg_datetime
        # Finland is UTC+3 in summer (June), Argentina is UTC-3. 6 hours difference.
        d, t = _convert_fin_to_arg_datetime("2026-06-03", "14:00:00")
        self.assertEqual(d, "2026-06-03")
        self.assertEqual(t, "08:00")
        
        # Test offset crossing midnight: 01:00 AM Finland is 19:00 PM previous day in Argentina
        d, t = _convert_fin_to_arg_datetime("2026-06-03", "01:00:00")
        self.assertEqual(d, "2026-06-02")
        self.assertEqual(t, "19:00")
        
        # Finland is UTC+2 in winter (December), Argentina is UTC-3. 5 hours difference.
        d, t = _convert_fin_to_arg_datetime("2026-12-15", "14:00:00")
        self.assertEqual(d, "2026-12-15")
        self.assertEqual(t, "09:00")




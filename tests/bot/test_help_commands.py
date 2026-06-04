from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers import (
    help_command,
    help_general_command,
    help_odds_command,
    help_live_command,
    help_stats_command,
    help_special_command,
)


class TestHelpCommands(unittest.IsolatedAsyncioTestCase):

    async def test_help_no_args_returns_menu(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=[])
        update = SimpleNamespace(message=message)

        await help_command(update, context)

        message.reply_text.assert_awaited_once()
        text = message.reply_text.await_args[0][0]
        self.assertIn("Menú de Ayuda de BetBot", text)
        self.assertIn("/help general", text)
        self.assertIn("/help_odds", text)

    async def test_help_with_general_arg_returns_general_help(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=["general"])
        update = SimpleNamespace(message=message)

        await help_command(update, context)

        message.reply_text.assert_awaited_once()
        text = message.reply_text.await_args[0][0]
        self.assertIn("Comandos Generales y de Configuración", text)
        self.assertIn("/start", text)

    async def test_help_with_odds_arg_returns_odds_help(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=["odds"])
        update = SimpleNamespace(message=message)

        await help_command(update, context)

        message.reply_text.assert_awaited_once()
        text = message.reply_text.await_args[0][0]
        self.assertIn("Comandos para Odds (Cuotas)", text)
        self.assertIn("/track_league", text)

    async def test_help_with_live_arg_returns_live_help(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=["live"])
        update = SimpleNamespace(message=message)

        await help_command(update, context)

        message.reply_text.assert_awaited_once()
        text = message.reply_text.await_args[0][0]
        self.assertIn("Live Commands (En vivo)", text)
        self.assertIn("/watch_live", text)

    async def test_help_with_stats_arg_returns_stats_help(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=["stats"])
        update = SimpleNamespace(message=message)

        await help_command(update, context)

        message.reply_text.assert_awaited_once()
        text = message.reply_text.await_args[0][0]
        self.assertIn("Stats y Estadísticas", text)
        self.assertIn("/link_stats", text)

    async def test_help_with_especial_arg_returns_special_help(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=["especial"])
        update = SimpleNamespace(message=message)

        await help_command(update, context)

        message.reply_text.assert_awaited_once()
        text = message.reply_text.await_args[0][0]
        self.assertIn("Stats de Federaciones", text)
        self.assertIn("/fin_help", text)

    async def test_direct_help_commands(self) -> None:
        commands = [
            (help_general_command, "Comandos Generales y de Configuración"),
            (help_odds_command, "Comandos para Odds (Cuotas)"),
            (help_live_command, "Live Commands (En vivo)"),
            (help_stats_command, "Stats y Estadísticas"),
            (help_special_command, "Stats de Federaciones"),
        ]

        for cmd, substring in commands:
            message = SimpleNamespace(reply_text=AsyncMock())
            context = SimpleNamespace(args=[])
            update = SimpleNamespace(message=message)

            await cmd(update, context)

            message.reply_text.assert_awaited_once()
            text = message.reply_text.await_args[0][0]
            self.assertIn(substring, text)

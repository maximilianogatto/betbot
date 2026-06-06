from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers import (
    help_command,
    help_matches_command,
    help_live_command,
    help_stats_command,
)


class TestHelpCommands(unittest.IsolatedAsyncioTestCase):

    async def test_help_no_args_returns_menu(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=[])
        update = SimpleNamespace(message=message)

        await help_command(update, context)

        message.reply_text.assert_awaited_once()
        text = message.reply_text.await_args[0][0]
        self.assertIn("Ayuda de BetBot - Comandos Generales y de Configuración", text)
        self.assertIn("/help_matches", text)
        self.assertIn("/help_live", text)
        self.assertIn("/help_stats", text)

    async def test_help_with_matches_arg_returns_matches_help(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        context = SimpleNamespace(args=["matches"])
        update = SimpleNamespace(message=message)

        await help_command(update, context)

        message.reply_text.assert_awaited_once()
        text = message.reply_text.await_args[0][0]
        self.assertIn("Comandos para Odds y Seguimiento de Partidos (Matches)", text)
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
        self.assertIn("Stats y Estadísticas (Estándar)", text)
        self.assertIn("/link_stats", text)
        self.assertIn("Ligas Especiales (Stats de Federaciones)", text)
        self.assertIn("[country]_help", text)

    async def test_direct_help_commands(self) -> None:
        commands = [
            (help_matches_command, "Comandos para Odds y Seguimiento de Partidos (Matches)"),
            (help_live_command, "Live Commands (En vivo)"),
            (help_stats_command, "Stats y Estadísticas (Estándar)"),
        ]

        for cmd, substring in commands:
            message = SimpleNamespace(reply_text=AsyncMock())
            context = SimpleNamespace(args=[])
            update = SimpleNamespace(message=message)

            await cmd(update, context)

            message.reply_text.assert_awaited_once()
            text = message.reply_text.await_args[0][0]
            self.assertIn(substring, text)

"""Cada comando registrado resuelve a un handler de verdad.

Los handlers se movieron entre módulos varias veces (E5) y los comandos por
federación son 37 alias que delegan en 5 genéricos. Si un alias queda apuntando
a un nombre que ya no existe, el bot igual arranca: el error recién aparece
cuando el usuario tipea ese comando.

Este test recorre lo que `register_handlers` registró de verdad y verifica que
cada comando tenga un callback invocable.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from telegram.ext import CommandHandler, ConversationHandler

from interfaces.telegram.handlers import register_handlers

# Comandos por federación: cada uno delega en el genérico correspondiente.
FEDERATION_PREFIXES = ("fin", "swe", "ro", "sk", "al", "no")
GENERIC_COMMANDS = ("standings", "fixtures", "match", "today", "stats_leagues")


def _registered_commands() -> dict[str, object]:
    """Mapea comando -> callback, tal como quedaron en la aplicación."""

    application = MagicMock()
    register_handlers(application)

    found: dict[str, object] = {}

    def _collect(handler) -> None:
        if isinstance(handler, CommandHandler):
            for command in handler.commands:
                found[command] = handler.callback
        elif isinstance(handler, ConversationHandler):
            for entry in handler.entry_points:
                _collect(entry)

    for call in application.add_handler.call_args_list:
        _collect(call.args[0])
    return found


class CommandRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.commands = _registered_commands()

    def test_every_registered_command_has_a_callable_handler(self) -> None:
        broken = [name for name, cb in self.commands.items() if not callable(cb)]
        self.assertEqual(broken, [], "comandos registrados sin handler invocable")
        self.assertGreater(len(self.commands), 50, "se registraron muchos menos comandos de los esperados")

    def test_the_generic_country_commands_are_registered(self) -> None:
        """Los genéricos son el destino al que consolidan las federaciones."""

        missing = [c for c in GENERIC_COMMANDS if c not in self.commands]
        self.assertEqual(missing, [], "faltan comandos genéricos por país")

    def test_every_federation_alias_still_resolves(self) -> None:
        """F6 consolidó a genéricos PERO los alias viejos tienen que seguir andando."""

        aliases = {
            name: cb
            for name, cb in self.commands.items()
            if name.split("_")[0] in FEDERATION_PREFIXES and "_" in name
        }
        self.assertGreater(len(aliases), 30, "esperaba ~37 alias por federación")

        broken = [name for name, cb in aliases.items() if not callable(cb)]
        self.assertEqual(broken, [], "alias de federación que dejaron de resolver")

    def test_echo_is_gone(self) -> None:
        """/echo era un resto de debug; F6 lo dio de baja."""

        self.assertNotIn("echo", self.commands)

    def test_resources_is_kept(self) -> None:
        """/resources se conserva a propósito: sirve para mirar el consumo del VPS."""

        self.assertIn("resources", self.commands)
        self.assertIn("status", self.commands)


if __name__ == "__main__":
    unittest.main()

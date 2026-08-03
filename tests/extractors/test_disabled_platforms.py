"""Apagar una plataforma a mano vía BOT_DISABLED_PLATFORMS.

Existe porque no alcanzaba con sacar una variable de entorno: los `*_is_configured()`
caen a una URL por defecto, así que la plataforma se registraba igual.
"""
from __future__ import annotations

from dataclasses import replace
import os
import unittest
from unittest.mock import patch

from bot.config import load_settings
from core.registry import ExtractorRegistry
from extractors import register_default_extractors


def _registered_names(disabled: tuple[str, ...]) -> set[str]:
    """Nombres de los extractores que quedan registrados con esa lista de apagados."""

    registry = ExtractorRegistry()
    settings = replace(load_settings(), disabled_platforms=disabled)
    register_default_extractors(registry, settings=settings)
    return {extractor.name for extractor in registry.list_registered()}


class DisabledPlatformsSettingTests(unittest.TestCase):
    def test_parses_a_comma_separated_list(self) -> None:
        with patch.dict(os.environ, {"BOT_DISABLED_PLATFORMS": "bz, Rainbet_HTTP ,"}):
            settings = load_settings()
        self.assertEqual(settings.disabled_platforms, ("bz", "rainbet_http"))

    def test_defaults_to_empty(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BOT_DISABLED_PLATFORMS", None)
            settings = load_settings()
        self.assertEqual(settings.disabled_platforms, ())


class DisabledPlatformsRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        # Un token cualquiera: load_settings() lo exige y no se usa acá.
        self._env = patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "x"})
        self._env.start()
        self.addCleanup(self._env.stop)

    def test_a_disabled_platform_is_not_registered(self) -> None:
        enabled = _registered_names(())
        self.assertIn("bz_http", enabled, "bz debería registrarse cuando no está apagado")

        after = _registered_names(("bz_http",))
        self.assertNotIn("bz_http", after)
        # Apagar una no puede arrastrar a las demás.
        self.assertEqual(enabled - after, {"bz_http"})

    def test_the_short_name_also_works(self) -> None:
        """En la variable de entorno tiene que valer `bz` igual que `bz_http`."""

        self.assertNotIn("bz_http", _registered_names(("bz",)))

    def test_unknown_names_are_ignored(self) -> None:
        """Un nombre mal escrito no puede apagar nada por accidente."""

        self.assertEqual(_registered_names(("no_existe",)), _registered_names(()))


if __name__ == "__main__":
    unittest.main()

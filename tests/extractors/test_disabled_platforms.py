"""Apagar una plataforma a mano vía BOT_DISABLED_PLATFORMS.

Existe porque no alcanzaba con sacar una variable de entorno: los `*_is_configured()`
caen a una URL por defecto, así que la plataforma se registraba igual.

Los tests construyen `Settings` a mano en vez de leer el `.env` del proyecto:
`load_settings()` exige ese archivo en disco, así que depender de él haría que
la suite pase donde hay un `.env` y falle en un checkout limpio.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from bot.config import Settings, load_settings
from core.registry import ExtractorRegistry
from extractors import register_default_extractors


def _registered_names(disabled: tuple[str, ...]) -> set[str]:
    """Nombres de los extractores que quedan registrados con esa lista de apagados."""

    registry = ExtractorRegistry()
    settings = Settings(telegram_bot_token="x", disabled_platforms=disabled)
    register_default_extractors(registry, settings=settings)
    return {extractor.name for extractor in registry.list_registered()}


class DisabledPlatformsSettingTests(unittest.TestCase):
    """El parseo de la variable de entorno."""

    def _load(self, raw: str | None) -> Settings:
        env = {"TELEGRAM_BOT_TOKEN": "x"}
        if raw is not None:
            env["BOT_DISABLED_PLATFORMS"] = raw
        with patch.dict(os.environ, env, clear=False):
            if raw is None:
                os.environ.pop("BOT_DISABLED_PLATFORMS", None)
            # load_settings() exige un .env en disco; acá sólo interesa el parseo.
            with patch("bot.config.load_dotenv", return_value=True):
                return load_settings()

    def test_parses_a_comma_separated_list(self) -> None:
        self.assertEqual(
            self._load("bz, Rainbet_HTTP ,").disabled_platforms,
            ("bz", "rainbet_http"),
        )

    def test_defaults_to_empty(self) -> None:
        self.assertEqual(self._load(None).disabled_platforms, ())


class DisabledPlatformsRegistrationTests(unittest.TestCase):
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

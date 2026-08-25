"""Cobertura del resolutor de provider que usa /sportradar_token.

El fallback al registry llamaba `stats_provider_registry.providers`, atributo
que no existe (la API es `list_registered()`). Como ningún test recorría esa
rama, el AttributeError sólo aparecía en producción: las dos formas del comando
—con .json adjunto y sin argumentos— pasan por acá, así que ambas morían en el
error handler genérico con "Ocurrió un error inesperado".
"""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from core.stats_provider_base import stats_provider_registry
from interfaces.telegram.handlers.system import _get_sportradar_provider


def _context(stats_service: object | None) -> SimpleNamespace:
    return SimpleNamespace(
        application=SimpleNamespace(bot_data={"stats_service": stats_service})
    )


class GetSportradarProviderTests(unittest.TestCase):
    def test_el_fallback_al_registry_no_explota(self) -> None:
        """Sin Sportradar en el stats_service, se recorre el registry y se devuelve None."""

        resultado = _get_sportradar_provider(
            _context(SimpleNamespace(_providers={}))
        )
        self.assertIsNone(resultado)

    def test_sin_stats_service_devuelve_none(self) -> None:
        self.assertIsNone(_get_sportradar_provider(_context(None)))

    def test_el_registry_expone_list_registered(self) -> None:
        """Guard del contrato que el fallback rompió."""

        self.assertTrue(hasattr(stats_provider_registry, "list_registered"))
        self.assertFalse(
            hasattr(stats_provider_registry, "providers"),
            "si el registry gana .providers, revisar el fallback de _get_sportradar_provider",
        )


if __name__ == "__main__":
    unittest.main()

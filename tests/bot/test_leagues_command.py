"""Cobertura de /leagues y /league, que ningún test ejercitaba.

El refactor PR2-E5-6 movió estas funciones a handlers/tracking.py sin traer el
import de `get_storage`, y como nadie las ejecutaba en los tests el
`NameError: name 'get_storage' is not defined` recién apareció en producción
cuando el usuario tocó /leagues. El guard de nombres cubre el AST; estos tests
cubren la ejecución real del handler.
"""
from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from interfaces.telegram.handlers.tracking import league_command, leagues_command


def _repository(unified: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(
        list_subscribed_unified_competitions=lambda chat_id: list(unified)
    )


def _update() -> SimpleNamespace:
    return SimpleNamespace(
        message=SimpleNamespace(reply_text=AsyncMock()),
        effective_chat=SimpleNamespace(id=123),
    )


class LeaguesCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_leagues_command_lista_las_ligas_suscriptas(self) -> None:
        unified = [
            {"id": 7, "name": "Kazakhstan First Division"},
            {"id": 3, "name": "Bhutan Premier League"},
        ]
        cards = {7: "carta-kaz", 3: "carta-bhu"}

        with patch(
            "interfaces.telegram.handlers.tracking.get_storage",
            return_value=_repository(unified),
        ), patch(
            "adapters.storage.get_storage",
            return_value=_repository(unified),
        ), patch(
            "bot.canonical_leagues.build_league_card",
            side_effect=lambda repo, uid: cards[uid],
        ), patch(
            "bot.canonical_leagues.render_leagues_list",
            side_effect=lambda cards_: "LISTA: " + " | ".join(cards_),
        ):
            update = _update()
            await leagues_command(update, SimpleNamespace())

        sent = update.message.reply_text.await_args.args[0]
        self.assertIn("carta-bhu", sent)
        self.assertIn("carta-kaz", sent)

    async def test_leagues_command_ordena_por_pais(self) -> None:
        """El orden es la fuente del índice N que usan /league y /link_league."""

        unified = [
            {"id": 7, "name": "Kazakhstan First Division"},
            {"id": 3, "name": "Bhutan Premier League"},
        ]
        seen: list[int] = []

        with patch(
            "interfaces.telegram.handlers.tracking.get_storage",
            return_value=_repository(unified),
        ), patch(
            "adapters.storage.get_storage",
            return_value=_repository(unified),
        ), patch(
            "bot.canonical_leagues.build_league_card",
            side_effect=lambda repo, uid: seen.append(uid) or f"c{uid}",
        ), patch(
            "bot.canonical_leagues.render_leagues_list",
            side_effect=lambda cards_: "\n".join(cards_),
        ):
            await leagues_command(_update(), SimpleNamespace())

        self.assertEqual(seen, [3, 7], "Bhutan debe ir antes que Kazakhstan")

    async def test_league_command_usa_el_indice_de_leagues(self) -> None:
        unified = [
            {"id": 7, "name": "Kazakhstan First Division"},
            {"id": 3, "name": "Bhutan Premier League"},
        ]

        with patch(
            "interfaces.telegram.handlers.tracking.get_storage",
            return_value=_repository(unified),
        ), patch(
            "adapters.storage.get_storage",
            return_value=_repository(unified),
        ), patch(
            "bot.canonical_leagues.build_league_card",
            side_effect=lambda repo, uid: f"carta-{uid}",
        ), patch(
            "bot.canonical_leagues.render_league_card",
            side_effect=lambda card: f"RENDER {card}",
        ):
            update = _update()
            # El índice 1 es Bhutan (id 3) por el orden por país.
            await league_command(update, SimpleNamespace(args=["1"]))

        self.assertIn("carta-3", update.message.reply_text.await_args.args[0])

    async def test_league_command_rechaza_indice_fuera_de_rango(self) -> None:
        with patch(
            "interfaces.telegram.handlers.tracking.get_storage",
            return_value=_repository([{"id": 7, "name": "Kazakhstan First Division"}]),
        ), patch(
            "adapters.storage.get_storage",
            return_value=_repository([{"id": 7, "name": "Kazakhstan First Division"}]),
        ):
            update = _update()
            await league_command(update, SimpleNamespace(args=["9"]))

        self.assertIn("fuera de rango", update.message.reply_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()

"""Orden y etiquetas de los selectores de ligas.

El riesgo real de este código no es estético: el botón lleva
``callback_data=f"{prefix}:{index}"``, y ese índice se resuelve contra la lista
guardada en ``user_data``. Si se ordenan las etiquetas pero no la lista, el
usuario ve "Argentina" y selecciona otra liga. Por eso los tests miran las dos
cosas juntas.
"""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from interfaces.telegram.handlers.common import (
    league_display_name,
    sort_leagues_by_country_and_name,
)


def _track(name: str) -> SimpleNamespace:
    """Un track por plataforma: el nombre va anidado, como en producción."""

    return SimpleNamespace(tracked_league=SimpleNamespace(competition_name=name))


class TrackSortingTests(unittest.TestCase):
    def test_ordena_tracks_por_pais_y_nombre(self) -> None:
        tracks = [
            _track("Sweden Allsvenskan"),
            _track("Argentina Primera Nacional"),
            _track("Argentina Copa Argentina"),
            _track("Denmark Superligaen"),
        ]
        ordenados = [
            t.tracked_league.competition_name
            for t in sort_leagues_by_country_and_name(tracks)
        ]
        self.assertEqual(
            ordenados,
            [
                "Argentina Copa Argentina",
                "Argentina Primera Nacional",
                "Denmark Superligaen",
                "Sweden Allsvenskan",
            ],
        )

    def test_el_indice_del_boton_sigue_apuntando_a_la_misma_liga(self) -> None:
        """El bug que este cambio evita: etiquetas ordenadas sobre lista sin ordenar."""

        tracks = [_track("Sweden Allsvenskan"), _track("Argentina Copa Argentina")]
        ordenados = sort_leagues_by_country_and_name(tracks)
        etiquetas = [league_display_name(t) for t in ordenados]

        # El usuario toca el primer botón -> índice 0 sobre la lista guardada.
        elegido = ordenados[0].tracked_league.competition_name
        self.assertIn("Argentina Copa Argentina", etiquetas[0])
        self.assertEqual(elegido, "Argentina Copa Argentina")

    def test_las_etiquetas_llevan_bandera(self) -> None:
        self.assertTrue(league_display_name(_track("Argentina Primera Nacional")).startswith("🇦🇷"))
        self.assertTrue(league_display_name(_track("Denmark Superligaen")).startswith("🇩🇰"))

    def test_liga_sin_pais_reconocible_no_rompe(self) -> None:
        etiqueta = league_display_name(_track("Copa Libertadores"))
        self.assertIn("Copa Libertadores", etiqueta)

    def test_ordena_objetos_con_label(self) -> None:
        """Las ligas explorables de /explore_stats exponen .label."""

        ligas = [
            SimpleNamespace(label="Sweden Allsvenskan"),
            SimpleNamespace(label="Argentina Primera Nacional"),
        ]
        self.assertEqual(
            [lg.label for lg in sort_leagues_by_country_and_name(ligas)],
            ["Argentina Primera Nacional", "Sweden Allsvenskan"],
        )


if __name__ == "__main__":
    unittest.main()

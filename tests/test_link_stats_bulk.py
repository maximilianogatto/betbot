"""Calibración del linkeo masivo de ligas contra el catálogo de stats.

Los umbrales no son arbitrarios: salieron de correr 7 ligas reales del bot
contra el catálogo real de Sportradar. Los dos casos que los fijan:

- "Peru · Liga Femenina" puntúa 0.667 contra la correcta y su segundo candidato
  queda en 0.000 → hay que aceptarla.
- "Sweden · Swedish Cup. Women" puntúa exactamente lo mismo, 0.667, pero
  empatada con el segundo → hay que rechazarla.

Juzgar por score absoluto los trata igual y falla en uno de los dos. Por eso
manda el margen. Si alguien sube ACCEPT_THRESHOLD "para estar más seguro",
estos tests muestran qué se rompe.
"""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from scripts.link_stats_bulk import (
    ACCEPT_THRESHOLD,
    MARGIN,
    _dedupe_catalog,
    _traits_compatible,
)


def _option(name: str, tournament: int, current: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        league_id=str(tournament),
        league_name=name,
        season_id="1",
        raw_payload={"unique_tournament_id": tournament, "is_current_season": current},
    )


class DedupeCatalogTests(unittest.TestCase):
    def test_descarta_lo_que_no_es_liga(self) -> None:
        """unique_tournament_id == 0 marca mercados, no competiciones."""

        catalogo = [_option("Dummy Goalscorer", 0), _option("Superligaen", 39)]
        self.assertEqual(
            [o.league_name for o in _dedupe_catalog(catalogo)], ["Superligaen"]
        )

    def test_prefiere_la_temporada_vigente(self) -> None:
        catalogo = [
            _option("Superligaen, Championship round", 39, current=False),
            _option("Superligaen", 39, current=True),
        ]
        vivos = _dedupe_catalog(catalogo)
        self.assertEqual(len(vivos), 1)
        self.assertEqual(vivos[0].league_name, "Superligaen")

    def test_colapsa_las_fases_del_mismo_torneo(self) -> None:
        """El proveedor repite la liga una vez por grupo; es un solo torneo."""

        catalogo = [
            _option("Primera Nacional, G1", 703),
            _option("Primera Nacional, G2", 703),
            _option("Primera B Nacional", 703),
        ]
        self.assertEqual(len(_dedupe_catalog(catalogo)), 1)


class TraitsTests(unittest.TestCase):
    def test_no_mezcla_generos(self) -> None:
        self.assertFalse(_traits_compatible("Primera Division", "Primera Division, Women"))

    def test_no_mezcla_categorias_de_edad(self) -> None:
        self.assertFalse(_traits_compatible("Primera Division", "Primera Division U20"))

    def test_acepta_cuando_coinciden(self) -> None:
        self.assertTrue(_traits_compatible("DBU Pokalen", "DBU Pokalen"))


class UmbralTests(unittest.TestCase):
    def test_acepta_score_bajo_con_margen_amplio(self) -> None:
        """El caso Perú: 0.667 contra un segundo en 0.000."""

        score, runner_up = 0.667, 0.000
        self.assertGreaterEqual(score, ACCEPT_THRESHOLD)
        self.assertGreaterEqual(score - runner_up, MARGIN)

    def test_rechaza_el_mismo_score_cuando_hay_empate(self) -> None:
        """El caso Suecia: mismo 0.667, pero el segundo también."""

        score, runner_up = 0.667, 0.667
        self.assertLess(score - runner_up, MARGIN)

    def test_rechaza_parecido_pobre(self) -> None:
        """El caso USA League Two: nada que se le parezca en el catálogo."""

        self.assertLess(0.444, ACCEPT_THRESHOLD)


if __name__ == "__main__":
    unittest.main()

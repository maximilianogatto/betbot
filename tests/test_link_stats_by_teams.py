"""Reglas del linkeo por equipos: las que evitan links equivocados (casos reales)."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from scripts.link_stats_by_teams import (
    _base_name, _category_compatible, _country_compatible, _country_of, _is_cup, _match_teams,
)


class LinkRulesTests(unittest.TestCase):
    def test_category_keeps_women_youth_reserves_and_cups_apart(self) -> None:
        self.assertTrue(_category_compatible("Norway · Toppserien, Women", "Toppserien (Damas)"))
        self.assertTrue(_category_compatible("Slovakia. Liga 1. Women", "I. liga ženy"))
        self.assertFalse(_category_compatible("USA · National Premier Soccer League",
                                              "National Women's Soccer League"))
        self.assertFalse(_category_compatible("Australia · U23 Victoria NPL", "Victoria NPL"))
        self.assertFalse(_category_compatible("Australia. NPL South Australia. Reserve League",
                                              "South Australia NPL"))
        self.assertFalse(_category_compatible("Austria · Bundesliga, Women", "OFB Cup, Women"))
        self.assertTrue(_category_compatible("Norway · NM Cup", "NM Cup"))

    def test_phases_of_one_league_are_the_same_league(self) -> None:
        self.assertEqual(_base_name("Mineiro, Women"), _base_name("Mineiro, Women, Final Stage"))
        self.assertEqual(_base_name("Liga Femenina, Women, Apertura"),
                         _base_name("Liga Femenina, Women, Clausura"))
        self.assertNotEqual(_base_name("Kolmonen, North Group"), _base_name("Kolmonen, Western, Group 2"))
        self.assertTrue(_is_cup("DBU Pokalen") and _is_cup("Slovensky Pohar") and not _is_cup("Esiliiga"))

    def test_countries_in_spanish_and_federation_names(self) -> None:
        self.assertEqual(_country_of("Bielorrusia - Liga Pershaya"), "belarus")
        self.assertEqual(_country_of("Croatian Cup"), "croatia")
        noruega = SimpleNamespace(country_name="Noruega")
        self.assertTrue(_country_compatible("norway", noruega))
        self.assertFalse(_country_compatible("sweden", noruega))
        self.assertTrue(_country_compatible(None, noruega))

    def test_team_matching(self) -> None:
        matched = _match_teams(["Bodo/Glimt [W]", "Aalesund", "Inexistente FC"],
                               {"Bodø/Glimt", "Aalesund", "Brann"})
        self.assertEqual([bot for bot, _ in matched], ["Bodo/Glimt [W]", "Aalesund"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from core.league_naming import normalize_league_name, same_league


class LeagueNamingTests(unittest.TestCase):
    def test_usl_word_vs_digit_and_country_alias(self) -> None:
        # The real failing case: these are the SAME league across books.
        self.assertTrue(same_league("USA. USL League Two", "Estados Unidos · USL League 2"))
        self.assertTrue(same_league("USL League Two", "USL League 2"))

    def test_victoria_premier_league_variants(self) -> None:
        self.assertTrue(same_league(
            "Australia · Australia - Liga Premier de Victoria 1 U23",
            "Australia · U23 Victoria Premier League 1",
        ))

    def test_roman_numerals(self) -> None:
        self.assertTrue(same_league("Serie A II", "Serie A 2"))
        self.assertEqual(normalize_league_name("Division III"), normalize_league_name("Division 3"))

    def test_gender_is_a_discriminator(self) -> None:
        self.assertFalse(same_league("Australia. NPL Northern NSW", "Australia. NPL Northern NSW (F)"))
        self.assertFalse(same_league("USL League 2", "USL League 2 Women"))

    def test_age_is_a_discriminator(self) -> None:
        self.assertFalse(same_league("Brasiliense U20", "Brasiliense U23"))
        # but sub-23 == u23
        self.assertTrue(same_league("Victoria sub-23 Premier League 1", "Victoria U23 Premier League 1"))

    def test_men_marker_dropped(self) -> None:
        # unmarked == explicitly men
        self.assertTrue(same_league("Ettan Norra", "Ettan Norra (Men)"))

    def test_empty_safe(self) -> None:
        self.assertEqual(normalize_league_name(None), "")
        self.assertFalse(same_league("", ""))
        self.assertFalse(same_league("Liga X", None))

    def test_order_insensitive(self) -> None:
        self.assertEqual(
            normalize_league_name("USA USL League Two"),
            normalize_league_name("USL League 2 USA"),
        )


if __name__ == "__main__":
    unittest.main()

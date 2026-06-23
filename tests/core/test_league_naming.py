from __future__ import annotations

import unittest

from core.league_naming import (
    extract_league_traits,
    league_slug,
    normalize_league_name,
    same_league,
)


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


class LeagueSlugTests(unittest.TestCase):
    def test_slug_preserves_order_and_discriminators(self) -> None:
        self.assertEqual(league_slug("USA. WPSL (F)"), "usa-wpsl-f")
        self.assertEqual(league_slug("Inglaterra · Premier League"), "inglaterra-premier-league")
        self.assertEqual(league_slug("Australia - NPL NSW Sub-20"), "australia-npl-nsw-sub-20")

    def test_slug_strips_accents_and_collapses(self) -> None:
        self.assertEqual(league_slug("SuperLiga Feminină"), "superliga-feminina")
        self.assertEqual(league_slug("  Liga --- X  "), "liga-x")

    def test_slug_empty_and_length(self) -> None:
        self.assertEqual(league_slug(None), "")
        self.assertEqual(league_slug(""), "")
        self.assertLessEqual(len(league_slug("x" * 200)), 60)


class LeagueTraitsTests(unittest.TestCase):
    def test_traits_full(self) -> None:
        traits = extract_league_traits("USA. WPSL (F)")
        self.assertEqual(traits, {"country": "usa", "gender": "F", "age_group": None})

    def test_traits_age_and_country_alias(self) -> None:
        traits = extract_league_traits("Inglaterra Premier League Sub-20")
        self.assertEqual(traits["country"], "england")
        self.assertEqual(traits["age_group"], "U20")

    def test_traits_unmarked_is_men(self) -> None:
        traits = extract_league_traits("Superettan")
        self.assertIsNone(traits["gender"])
        self.assertIsNone(traits["age_group"])


if __name__ == "__main__":
    unittest.main()


from core.league_naming import league_name_similarity, team_name_similarity

class FuzzySimilarityTests(unittest.TestCase):
    def test_league_name_similarity(self) -> None:
        self.assertGreater(league_name_similarity("Alemania Primera", "Germany Premier"), 0.8)
        self.assertGreater(league_name_similarity("Copa de Suecia", "Sweden Cup"), 0.8)
        self.assertEqual(league_name_similarity("", "Sweden Cup"), 0.0)

    def test_team_name_similarity(self) -> None:
        self.assertGreater(team_name_similarity("Fenix Femenino", "Fenix Women"), 0.8)
        self.assertGreater(team_name_similarity("Boca Juniors SC", "Boca Juniors"), 0.8)
        self.assertEqual(team_name_similarity("Boca Juniors", ""), 0.0)

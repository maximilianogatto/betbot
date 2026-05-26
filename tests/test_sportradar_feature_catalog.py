from __future__ import annotations

import unittest

from sandbox.sportradar_http.build_feature_catalog import render_feature_catalog


class SportradarFeatureCatalogTests(unittest.TestCase):
    def test_feature_catalog_documents_scales_and_attack_strength(self) -> None:
        catalog = render_feature_catalog()

        self.assertIn("Rates are normalized to `0..1`", catalog)
        self.assertIn("`attack_strength_home`", catalog)
        self.assertIn("not a probability", catalog)
        self.assertIn("`h2h_home_edge` ranges from `-1..1`", catalog)


if __name__ == "__main__":
    unittest.main()

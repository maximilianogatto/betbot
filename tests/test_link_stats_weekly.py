"""El vinculador semanal sube sólo lo que el vinculador agregó o cambió."""
from __future__ import annotations

import unittest

from scripts.link_stats_weekly import changed_links


def _row(comp: int, provider: str, league_id: str, name: str = "Liga") -> dict:
    return {"competition_id": comp, "provider": provider, "league_id": league_id, "league_name": name,
            "country_name": None, "confidence": 1.0, "payload_json": None,
            "created_at": "2026-09-24", "updated_at": "2026-09-24"}


class ChangedLinksTests(unittest.TestCase):
    def test_only_new_or_changed_links_are_pushed(self) -> None:
        before = {(1, "palloliitto"): _row(1, "palloliitto", "10"),
                  (2, "sportradar_statshub"): _row(2, "sportradar_statshub", "20")}
        after = dict(before)
        after[(2, "sportradar_statshub")] = _row(2, "sportradar_statshub", "21")   # corregido
        after[(3, "flashscore_http")] = _row(3, "flashscore_http", "30")           # nuevo
        after[(1, "palloliitto")] = {**before[(1, "palloliitto")], "updated_at": "2026-10-01"}  # igual

        pushed = changed_links(before, after)

        self.assertEqual(sorted((r["competition_id"], r["league_id"]) for r in pushed), [(2, "21"), (3, "30")])


if __name__ == "__main__":
    unittest.main()

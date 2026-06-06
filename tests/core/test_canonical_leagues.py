from __future__ import annotations

import unittest
from types import SimpleNamespace

from bot.canonical_leagues import build_league_card, render_league_card, render_leagues_list


def _comp(cid, platform, ext_id, name):
    return SimpleNamespace(id=cid, platform=platform, competition_external_id=ext_id, competition_name=name)


def _stat(provider, sid, name=""):
    return SimpleNamespace(stats_provider=provider, stats_league_id=sid, stats_league_name=name)


class FakeRepo:
    def __init__(self, meta, comps, stats_by_comp=None):
        self._meta = meta
        self._comps = comps
        self._stats = stats_by_comp or {}

    def get_canonical_league(self, cid):
        return self._meta if self._meta and cid == self._meta["id"] else None

    def list_competitions_for_canonical_league(self, cid):
        return self._comps

    def list_stats_league_links(self, comp_id):
        return self._stats.get(comp_id, [])


class BuildCardTests(unittest.TestCase):
    def test_tracking_flags_and_ids_in_order(self) -> None:
        repo = FakeRepo(
            {"id": 7, "name": "Brazil. Campeonato Brasiliense U20"},
            [
                _comp(1, "1xbet_http", "L1X", "Brasiliense U20"),
                _comp(2, "betovo_http", "LBET", "Brasiliense Sub20"),
            ],
        )
        card = build_league_card(repo, 7)
        assert card is not None
        self.assertEqual(card.name, "Brazil. Campeonato Brasiliense U20")
        by = {p.platform: p for p in card.platforms}
        self.assertTrue(by["1xbet_http"].tracking)
        self.assertEqual(by["1xbet_http"].league_id, "L1X")
        self.assertTrue(by["betovo_http"].tracking)
        self.assertFalse(by["solcasino_http"].tracking)
        self.assertFalse(by["bet365"].tracking)
        self.assertEqual(card.tracked_count, 2)
        # canonical order: 1xbet before betovo before the rest
        order = [p.platform for p in card.platforms]
        self.assertLess(order.index("1xbet_http"), order.index("betovo_http"))
        self.assertLess(order.index("betovo_http"), order.index("bet365"))

    def test_stats_dedup_across_platforms(self) -> None:
        repo = FakeRepo(
            {"id": 1, "name": "L"},
            [_comp(1, "1xbet_http", "a", "A"), _comp(2, "betovo_http", "b", "B")],
            {
                1: [_stat("sportradar", "999", "Liga X")],
                2: [_stat("sportradar", "999", "Liga X"), _stat("flashscore", "abc")],
            },
        )
        card = build_league_card(repo, 1)
        self.assertTrue(card.has_stats)
        keys = {(s.provider, s.stats_league_id) for s in card.stats}
        self.assertEqual(keys, {("sportradar", "999"), ("flashscore", "abc")})

    def test_missing_league(self) -> None:
        repo = FakeRepo({"id": 1, "name": "L"}, [])
        self.assertIsNone(build_league_card(repo, 999))


class RenderTests(unittest.TestCase):
    def test_render_card(self) -> None:
        repo = FakeRepo(
            {"id": 7, "name": "Brasiliense U20"},
            [_comp(1, "1xbet_http", "L1X", "Brasiliense U20")],
            {1: [_stat("sportradar", "999", "Liga X")]},
        )
        out = render_league_card(build_league_card(repo, 7))
        self.assertIn("Brasiliense U20", out)
        self.assertIn("✅", out)        # tracked platform
        self.assertIn("⚪️", out)       # untracked platform
        self.assertIn("L1X", out)
        self.assertIn("sportradar", out)

    def test_render_list_empty(self) -> None:
        self.assertIn("Todavía no hay", render_leagues_list([]))


if __name__ == "__main__":
    unittest.main()

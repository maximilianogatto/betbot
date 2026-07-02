from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from monitors.tracking import _is_refresh_due, _refresh_interval_seconds

NOW = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)


class RefreshIntervalTests(unittest.TestCase):
    def test_interval_by_proximity(self) -> None:
        self.assertEqual(_refresh_interval_seconds(NOW, None), 3600.0)
        # in-play (started 30 min ago) -> fast tier (default 20 s)
        self.assertEqual(_refresh_interval_seconds(NOW, NOW - timedelta(minutes=30)), 20.0)
        # 10 min to kickoff -> fast tier
        self.assertEqual(_refresh_interval_seconds(NOW, NOW + timedelta(minutes=10)), 20.0)
        # 2 h -> normal
        self.assertEqual(_refresh_interval_seconds(NOW, NOW + timedelta(hours=2)), 120.0)
        # 10 h -> slow
        self.assertEqual(_refresh_interval_seconds(NOW, NOW + timedelta(hours=10)), 600.0)
        # 3 days -> hourly
        self.assertEqual(_refresh_interval_seconds(NOW, NOW + timedelta(days=3)), 3600.0)

    def test_in_play_tier_is_configurable(self) -> None:
        # El tier caliente respeta el valor pasado (p.ej. modo conservador 45 s).
        self.assertEqual(
            _refresh_interval_seconds(NOW, NOW - timedelta(minutes=5), in_play_seconds=45.0),
            45.0,
        )
        # Los tiers lejanos no dependen del valor in-play.
        self.assertEqual(
            _refresh_interval_seconds(NOW, NOW + timedelta(hours=2), in_play_seconds=45.0),
            120.0,
        )


class IsRefreshDueTests(unittest.TestCase):
    def test_never_synced_is_due(self) -> None:
        self.assertTrue(_is_refresh_due(NOW, None, NOW + timedelta(hours=2)))

    def test_normal_tier_respects_interval(self) -> None:
        ko = NOW + timedelta(hours=2)  # 120 s tier
        self.assertTrue(_is_refresh_due(NOW, NOW - timedelta(seconds=130), ko))
        self.assertFalse(_is_refresh_due(NOW, NOW - timedelta(seconds=30), ko))

    def test_far_league_skips_most_cycles(self) -> None:
        ko = NOW + timedelta(days=3)  # 3600 s tier
        self.assertFalse(_is_refresh_due(NOW, NOW - timedelta(seconds=600), ko))
        self.assertTrue(_is_refresh_due(NOW, NOW - timedelta(seconds=3600), ko))

    def test_in_play_is_due_each_cycle(self) -> None:
        ko = NOW - timedelta(minutes=20)  # in-play, 20 s tier
        # Ya pasaron 25 s desde el último sync -> supera el tier de 20 s (con gracia).
        self.assertTrue(_is_refresh_due(NOW, NOW - timedelta(seconds=25), ko))
        # A los 40 s en vivo -> claramente due.
        self.assertTrue(_is_refresh_due(NOW, NOW - timedelta(seconds=40), ko))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

tracking_repository_module = importlib.import_module("storage.tracking_repository")


class UnifiedSubscriptionTests(unittest.TestCase):
    """Fase 2: la suscripción es por liga unificada (herencia entre plataformas)."""

    CHAT_A = 111
    CHAT_B = 222

    def setUp(self) -> None:
        self.old_db_path = tracking_repository_module.DB_FILE_PATH
        self.tmp = tempfile.TemporaryDirectory()
        tracking_repository_module.DB_FILE_PATH = Path(self.tmp.name) / "tracking.sqlite3"
        self.repo = tracking_repository_module.SqliteTrackingRepository()

    def tearDown(self) -> None:
        tracking_repository_module.DB_FILE_PATH = self.old_db_path
        self.tmp.cleanup()

    def _confirm_track(self, chat_id: int, platform: str, ext_id: str, name: str):
        """Run the real track flow: pending request -> confirm."""
        self.repo.create_pending_competition_request(
            chat_id,
            platform=platform,
            source_url=f"https://{platform}.example/{ext_id}",
            competition_external_id=ext_id,
            competition_name=name,
        )
        return self.repo.confirm_pending_competition_request(chat_id)

    def _subs(self, chat_id: int) -> set[tuple[str, str]]:
        with tracking_repository_module._connect() as c:
            rows = c.execute(
                """
                SELECT tc.platform, tc.competition_external_id
                FROM competition_subscriptions cs
                JOIN tracked_competitions tc ON tc.id = cs.tracked_competition_id
                WHERE cs.telegram_chat_id = ? AND cs.enabled = 1
                """,
                (chat_id,),
            ).fetchall()
        return {(r["platform"], r["competition_external_id"]) for r in rows}

    def test_tracking_second_platform_inherits_both_ways(self) -> None:
        # Chat A tracks the league on 1xbet.
        self._confirm_track(self.CHAT_A, "1xbet_http", "100", "Premier League")
        # Chat B tracks the SAME league (auto-merge by name) on betovo.
        self._confirm_track(self.CHAT_B, "betovo_http", "200", "Premier League")

        # Both chats end up subscribed to both platforms of the league.
        expected = {("1xbet_http", "100"), ("betovo_http", "200")}
        self.assertEqual(self._subs(self.CHAT_A), expected)
        self.assertEqual(self._subs(self.CHAT_B), expected)

    def test_auto_track_live_propagates(self) -> None:
        self._confirm_track(self.CHAT_A, "1xbet_http", "100", "Premier League")
        self.repo.auto_track_live_detected_league(
            self.CHAT_B, "bz_http", "300", "Premier League", "bz:league:300"
        )
        self.assertIn(("bz_http", "300"), self._subs(self.CHAT_A))
        self.assertIn(("1xbet_http", "100"), self._subs(self.CHAT_B))

    def test_manual_link_league_propagates(self) -> None:
        a = self._confirm_track(self.CHAT_A, "1xbet_http", "100", "Premier League")
        # Different name -> separate unified league; no inheritance yet.
        b = self._confirm_track(self.CHAT_B, "betovo_http", "200", "Liga Inglesa Total")
        self.assertEqual(self._subs(self.CHAT_A), {("1xbet_http", "100")})

        # /link_league merges B's competition into A's unified league.
        uid = a.tracked_competition.unified_competition_id
        self.repo.link_tracked_competition_to_unified(b.tracked_competition.id, uid)

        expected = {("1xbet_http", "100"), ("betovo_http", "200")}
        self.assertEqual(self._subs(self.CHAT_A), expected)
        self.assertEqual(self._subs(self.CHAT_B), expected)

    def test_remove_unified_subscription_untracks_all_platforms(self) -> None:
        a = self._confirm_track(self.CHAT_A, "1xbet_http", "100", "Premier League")
        self._confirm_track(self.CHAT_A, "betovo_http", "200", "Premier League")
        uid = a.tracked_competition.unified_competition_id

        results = self.repo.remove_unified_subscription(self.CHAT_A, uid)
        self.assertEqual(len(results), 2)
        self.assertEqual(self._subs(self.CHAT_A), set())
        # Orphaned platforms get disabled.
        self.assertTrue(all(r.competition_disabled for r in results))

    def test_remove_unified_subscription_keeps_other_chats(self) -> None:
        a = self._confirm_track(self.CHAT_A, "1xbet_http", "100", "Premier League")
        self._confirm_track(self.CHAT_B, "betovo_http", "200", "Premier League")
        uid = a.tracked_competition.unified_competition_id

        results = self.repo.remove_unified_subscription(self.CHAT_A, uid)
        self.assertEqual(self._subs(self.CHAT_A), set())
        # Chat B keeps its league subscription on every platform.
        self.assertEqual(self._subs(self.CHAT_B), {("1xbet_http", "100"), ("betovo_http", "200")})
        self.assertFalse(any(r.competition_disabled for r in results))


if __name__ == "__main__":
    unittest.main()

"""El watch detecta el entretiempo y el final, y archiva sin esperar a que venza.

Caso real (2026-09-24): Bnot Netanya 0-7 ASA Tel Aviv se vio terminar a las 15:22 y
se archivó recién a las 15:30, cuando venció el watch (kickoff + 2 h).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from core.models import LiveEventSnapshot
from services.live_watch import LiveWatchService

CHAT = 31


def _event(minute: str, home_score: int, away_score: int, *, event_id: str = "ev-1",
           platform: str = "betovo_http", home: str = "Bnot Netanya (W)",
           away: str = "AS Tel Aviv University (W)") -> LiveEventSnapshot:
    return LiveEventSnapshot(platform=platform, external_event_id=event_id, home=home, away=away,
                             competition_name="Israel Women", minute=minute,
                             home_score=home_score, away_score=away_score)


class LiveWatchFinishTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp_dir.name) / "finish.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.repository = SqliteStorage()
        self.service = LiveWatchService(repository=self.repository)
        self.feed: list[LiveEventSnapshot] = []
        self.service.extractor_registry = SimpleNamespace(list_registered=lambda: [SimpleNamespace(
            name="betovo_http", supports_live_detection=True, supports_prematch_listing=False,
            list_live_events=AsyncMock(side_effect=lambda: list(self.feed)),
            list_prematch_events=AsyncMock(return_value=[]))])
        self.entry = self.repository.add_live_watch(
            CHAT, home="Bnot Netanya", away="ASA Tel Aviv (Visitantes +4/5)", league_hint="Israel (F)",
            kickoff_at=(datetime.now(timezone.utc) - timedelta(minutes=90)).isoformat())
        self.repository.mark_live_watch_fired(self.entry.id, platform="betovo_http", event_id="ev-1",
                                              minute="10'")

    def tearDown(self) -> None:
        if self._prev_db is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db
        self.tmp_dir.cleanup()

    def _set_state(self, platform: str = "betovo_http", **state) -> None:
        base = {"event_id": "ev-1", "home": "Bnot Netanya (W)", "away": "AS Tel Aviv University (W)",
                "observed_at": datetime.now(timezone.utc).isoformat()}
        self.repository.update_live_watch_platform_state(self.entry.id, platform, {**base, **state})

    def _state(self, platform: str = "betovo_http") -> dict:
        [entry] = [w for w in self.repository.list_live_watches(CHAT) if w.id == self.entry.id]
        return entry.live_state[platform]

    def _watching(self) -> bool:
        return any(w.id == self.entry.id for w in self.repository.list_live_watches(CHAT))

    # ----- entretiempo -----

    async def test_halftime_from_the_book_label(self) -> None:
        self._set_state(minute="44'", home_score=0, away_score=3)
        self.feed = [_event("HT", 0, 3)]
        await self.service.poll_once()
        state = self._state()
        self.assertEqual((state["ht_home_score"], state["ht_away_score"]), (0, 3))
        self.assertTrue(self.service.consume_settlement_trigger())
        self.assertFalse(self.service.consume_settlement_trigger())  # una sola vez

    async def test_halftime_from_the_jump_to_the_second_half(self) -> None:
        self._set_state(minute="45+2'", home_score=0, away_score=3)
        self.feed = [_event("46'", 0, 3)]
        await self.service.poll_once()
        self.assertEqual(self._state()["ht_away_score"], 3)

        # Y queda fijo aunque el marcador siga cambiando.
        self.feed = [_event("70'", 0, 5)]
        await self.service.poll_once()
        self.assertEqual((self._state()["ht_home_score"], self._state()["ht_away_score"]), (0, 3))

    async def test_no_halftime_without_seeing_the_end_of_the_first_half(self) -> None:
        self._set_state(minute="30'", home_score=0, away_score=1)
        self.feed = [_event("55'", 0, 3)]
        await self.service.poll_once()
        self.assertNotIn("ht_home_score", self._state())

    # ----- final -----

    async def test_a_final_label_archives_at_once_with_halftime(self) -> None:
        self._set_state(minute="89'", home_score=0, away_score=6, ht_home_score=0, ht_away_score=3)
        self.feed = [_event("FT", 0, 7)]
        await self.service.poll_once()

        self.assertFalse(self._watching())
        [result] = self.repository.list_match_results()
        self.assertEqual((result.status, result.final_home_score, result.final_away_score),
                         ("FINISHED", 0, 7))
        self.assertEqual((result.ht_home_score, result.ht_away_score), (0, 3))
        self.assertTrue(self.service.consume_settlement_trigger())

    async def test_gone_from_an_answering_book_after_88_is_finished(self) -> None:
        missing = (datetime.now(timezone.utc) - timedelta(minutes=7)).isoformat()
        self._set_state(minute="90'", home_score=0, away_score=7, missing_since=missing)
        # La casa responde (otro partido en vivo), pero ya no lista éste.
        self.feed = [_event("20'", 1, 0, event_id="otro", home="Maccabi Haifa", away="Hapoel Beer Sheva")]
        await self.service.poll_once()

        self.assertFalse(self._watching())
        [result] = self.repository.list_match_results()
        self.assertEqual((result.status, result.final_away_score), ("FINISHED", 7))

    async def test_a_short_gap_only_marks_it_missing(self) -> None:
        self._set_state(minute="90'", home_score=0, away_score=7)
        self.feed = [_event("20'", 1, 0, event_id="otro", home="Maccabi Haifa", away="Hapoel Beer Sheva")]
        await self.service.poll_once()

        self.assertTrue(self._watching())
        self.assertIn("missing_since", self._state())
        self.assertEqual(self.repository.list_match_results(), [])

    async def test_a_silent_book_says_nothing(self) -> None:
        """Si la casa no devolvió nada (caída), que no esté el partido no significa que terminó."""
        self._set_state(minute="90'", home_score=0, away_score=7)
        self.feed = []
        await self.service.poll_once()
        self.assertTrue(self._watching())
        self.assertNotIn("missing_since", self._state())

    async def test_another_book_still_in_play_blocks_the_finish(self) -> None:
        missing = (datetime.now(timezone.utc) - timedelta(minutes=7)).isoformat()
        self._set_state(minute="89'", home_score=0, away_score=7, missing_since=missing)
        self.repository.mark_live_watch_fired(self.entry.id, platform="mystake_http", event_id="m-1",
                                              minute="70'")
        self._set_state("mystake_http", event_id="m-1", minute="70'", home_score=0, away_score=5)
        self.feed = [_event("20'", 1, 0, event_id="otro", home="Maccabi Haifa", away="Hapoel Beer Sheva")]
        await self.service.poll_once()
        self.assertTrue(self._watching())


class HalftimeCaptureTests(unittest.TestCase):
    def test_first_half_stoppage_time_is_not_the_second_half(self) -> None:
        from datetime import datetime, timedelta, timezone

        from services.live_watch import _with_halftime

        now = datetime(2026, 9, 24, 19, 17, tzinfo=timezone.utc)
        previous = {"home_score": 0, "away_score": 1, "minute": "45'"}
        current = {"home_score": 0, "away_score": 1, "minute": "46'"}

        in_stoppage = _with_halftime(previous, current, kickoff=now - timedelta(minutes=47), now=now)
        self.assertNotIn("ht_home_score", in_stoppage)
        second_half = _with_halftime(previous, current, kickoff=now - timedelta(minutes=62), now=now)
        self.assertEqual((second_half["ht_home_score"], second_half["ht_away_score"]), (0, 1))
        self.assertIn("ht_home_score", _with_halftime(previous, current))  # sin horario: como antes

    def test_the_official_halftime_wins_over_a_book(self) -> None:
        from services.live_watch import halftime_states

        states = {"betovo_http": {"ht_home_score": 1, "ht_away_score": 1},
                  "_alerts": {}, "statshub": {"ht_home_score": 0, "ht_away_score": 1, "official": True}}
        self.assertEqual([name for name, _ in halftime_states(states)], ["statshub", "betovo_http"])


if __name__ == "__main__":
    unittest.main()

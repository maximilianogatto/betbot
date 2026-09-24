"""El live-watch con fuentes oficiales (federación, Statshub): entretiempo y final
aunque ninguna casa muestre el partido en vivo."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from core.stats_models import MatchStatus
from services.live_watch import LiveWatchService

CHAT = 44


class _FakeSource:
    def __init__(self, name: str, matches: list[MatchStatus]) -> None:
        self.name = name
        self.matches = matches
        self.days: list[date] = []

    def day_for(self, when: datetime) -> date:
        return when.astimezone(timezone.utc).date()

    async def matches_on(self, day: date) -> list[MatchStatus]:
        self.days.append(day)
        return list(self.matches)


def _status(source: str, phase: str, *, home="San Marino", away="Kosovo", score=(0, 3),
            halftime=None, minute=None, competition="U21 EURO, Qualification, Group A",
            kickoff: str | None = None) -> MatchStatus:
    return MatchStatus(source=source, match_id=f"{source}-1", home=home, away=away,
                       scheduled_at=kickoff, competition_name=competition, phase=phase,
                       home_score=score[0], away_score=score[1],
                       ht_home_score=halftime[0] if halftime else None,
                       ht_away_score=halftime[1] if halftime else None, minute=minute)


class LiveWatchOfficialStatusTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp_dir.name) / "official.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.repository = SqliteStorage()
        self.kickoff = (datetime.now(timezone.utc) - timedelta(minutes=50)).isoformat()
        self.entry = self.repository.add_live_watch(
            CHAT, home="San Marino U21", away="Kosovo U21", kickoff_at=self.kickoff)

    def tearDown(self) -> None:
        if self._prev_db is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db
        self.tmp_dir.cleanup()

    def _service(self, *sources) -> LiveWatchService:
        service = LiveWatchService(repository=self.repository, status_sources=sources)
        service.extractor_registry = SimpleNamespace(list_registered=lambda: [])  # ninguna casa
        return service

    def _state(self, platform: str) -> dict:
        [entry] = self.repository.list_live_watches(CHAT)
        return entry.live_state[platform]

    async def test_official_halftime_then_final_close_the_match(self) -> None:
        source = _FakeSource("statshub", [_status("statshub", "halftime", score=(0, 3), halftime=(0, 3),
                                                  minute="HT", kickoff=self.kickoff)])
        service = self._service(source)

        await service.poll_once()
        state = self._state("statshub")
        self.assertEqual((state["ht_home_score"], state["ht_away_score"], state["phase"]), (0, 3, "halftime"))
        self.assertTrue(service.consume_settlement_trigger())

        source.matches = [_status("statshub", "ended", score=(0, 5), halftime=(0, 3), minute="FT",
                                  kickoff=self.kickoff)]
        await service.poll_once()
        self.assertEqual(self.repository.list_live_watches(CHAT), [])  # cerrado sin esperar el vencimiento
        [result] = self.repository.list_match_results()
        self.assertEqual((result.status, result.platform, result.final_away_score, result.ht_away_score),
                         ("FINISHED", "statshub", 5, 3))
        self.assertTrue(service.consume_settlement_trigger())

    async def test_a_senior_match_of_the_same_teams_is_not_the_u21(self) -> None:
        source = _FakeSource("statshub", [_status("statshub", "ended", minute="FT", kickoff=self.kickoff,
                                                  competition="UEFA Nations League, League D")])
        await self._service(source).poll_once()
        [entry] = self.repository.list_live_watches(CHAT)
        self.assertNotIn("statshub", entry.live_state)

    async def test_the_federation_comes_first(self) -> None:
        federation = _FakeSource("palloliitto", [_status("palloliitto", "live", minute="67'",
                                                         kickoff=self.kickoff)])
        statshub = _FakeSource("statshub", [_status("statshub", "live", minute="2T en juego",
                                                    kickoff=self.kickoff)])
        await self._service(federation, statshub).poll_once()
        [entry] = self.repository.list_live_watches(CHAT)
        self.assertIn("palloliitto", entry.live_state)
        self.assertNotIn("statshub", entry.live_state)
        self.assertEqual(statshub.days, [])  # ni la consultó: ya estaba resuelto

    async def test_a_watch_without_kickoff_learns_it(self) -> None:
        self.repository.remove_live_watch(CHAT, self.entry.id)
        entry = self.repository.add_live_watch(CHAT, home="San Marino U21", away="Kosovo U21")
        later = (datetime.now(timezone.utc) + timedelta(hours=5)).replace(microsecond=0).isoformat()
        await self._service(_FakeSource("statshub", [_status("statshub", "scheduled", score=(None, None),
                                                             kickoff=later)])).poll_once()
        [entry] = self.repository.list_live_watches(CHAT)
        self.assertEqual(entry.kickoff_at, later)
        self.assertNotIn("statshub", entry.live_state)  # sin empezar: no hay estado que guardar

    async def test_a_matched_but_still_running_match_is_not_closed(self) -> None:
        source = _FakeSource("statshub", [_status("statshub", "live", minute="2T en juego",
                                                  kickoff=self.kickoff)])
        await self._service(source).poll_once()
        self.assertEqual(len(self.repository.list_live_watches(CHAT)), 1)
        self.assertEqual(self.repository.list_match_results(), [])


if __name__ == "__main__":
    unittest.main()

"""Lo que el bot hace solo con el libro: vigilar el partido de /bet y avisar al liquidar."""
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
from bot.jobs.tasks import _orchestrated_ledger_settlement
from core.betting import parse_bet_text
from core.models import MatchResult
from interfaces.telegram.handlers.bets import _watch_unlinked
from services.ledger import LedgerService
from services.live_watch import LiveWatchService

CHAT = 1804
BET = "San Marino u21 vs Kosovo u21 Kosovou21 -3.5 FT @1.62 12usd pre melbet #franko"


class LedgerAutomationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp_dir.name) / "automation.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.storage = SqliteStorage()
        self.ledger = LedgerService(self.storage)

    def tearDown(self) -> None:
        if self._prev_db is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db
        self.tmp_dir.cleanup()

    def _add_unlinked(self):
        parsed = parse_bet_text(BET)
        parsed.bet.chat_id = CHAT
        return self.ledger.add_bet(parsed.bet).bet

    def test_bet_on_an_untracked_match_opens_a_watch_once(self) -> None:
        bet = self._add_unlinked()
        context = SimpleNamespace(application=SimpleNamespace(
            bot_data={"live_watch_service": LiveWatchService(repository=self.storage)}))

        self.assertTrue(_watch_unlinked(context, bet))
        [watch] = self.storage.list_live_watches(CHAT)
        self.assertEqual((watch.home, watch.away), ("San Marino u21", "Kosovo u21"))
        self.assertFalse(_watch_unlinked(context, bet))  # otra apuesta al mismo partido

    async def test_the_job_settles_and_tells_the_chat(self) -> None:
        bet = self._add_unlinked()
        self.storage.record_match_result(MatchResult(
            platform="betovo_http", external_event_id="ev-u21", home="San Marino U21",
            away="Kosovo U21", status="FINISHED", source="live_watch",
            recorded_at=(datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
            final_home_score=0, final_away_score=5))
        send_message = AsyncMock()
        application = SimpleNamespace(bot_data={"ledger_service": self.ledger},
                                      bot=SimpleNamespace(send_message=send_message))

        await _orchestrated_ledger_settlement(application)

        send_message.assert_awaited_once()
        kwargs = send_message.await_args.kwargs
        self.assertEqual(kwargs["chat_id"], CHAT)
        self.assertIn("Apuesta liquidada", kwargs["text"])
        self.assertIn(f"#{bet.id}", kwargs["text"])
        self.assertEqual(self.storage.get_bet(bet.id).status, "won")


if __name__ == "__main__":
    unittest.main()

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


class LedgerReportJobTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self._prev = {key: os.environ.get(key) for key in ("BETBOT_DB_PATH", "LEDGER_REPORT_HOUR")}
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp_dir.name) / "reports.sqlite3")
        os.environ["LEDGER_REPORT_HOUR"] = "0"  # que el diario ya "toque" a cualquier hora
        with open_connection() as conn:
            initialize_schema(conn)
        self.storage = SqliteStorage()
        self.ledger = LedgerService(self.storage)

    def tearDown(self) -> None:
        for key, value in self._prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp_dir.cleanup()

    async def test_the_daily_report_goes_once_and_only_with_activity(self) -> None:
        from bot.jobs.tasks import _due_reports, _orchestrated_ledger_reports
        from services.ledger import report_window
        from services.timezones import resolve_chat_timezone

        send_message = AsyncMock()
        application = SimpleNamespace(bot_data={"ledger_service": self.ledger},
                                      bot=SimpleNamespace(send_message=send_message))
        bet = self.ledger.add_bet(parse_bet_text(BET).bet)  # sin chat: no recibe reportes
        self.assertIsNone(bet.bet.chat_id)
        parsed = parse_bet_text(BET)
        parsed.bet.chat_id = CHAT
        bet = self.ledger.add_bet(parsed.bet).bet
        self.ledger.settle_manual(bet.id, "won")
        since, _, _ = report_window("ayer", now=datetime.now(timezone.utc),
                                    tz=resolve_chat_timezone(CHAT))
        with open_connection() as conn:  # liquidada "ayer" en el huso del chat
            conn.execute("UPDATE bets SET settled_at = ?, placed_at = ? WHERE id = ?",
                         ((since + timedelta(hours=12)).isoformat(),
                          (since + timedelta(hours=11)).isoformat(), bet.id))

        await _orchestrated_ledger_reports(application)
        await _orchestrated_ledger_reports(application)  # la marca evita el duplicado

        send_message.assert_awaited_once()
        kwargs = send_message.await_args.kwargs
        self.assertEqual(kwargs["chat_id"], CHAT)
        self.assertIn("Reporte diario", kwargs["text"])
        self.assertIn("+7.44 USD", kwargs["text"])

        monday_10 = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
        self.assertEqual([period for period, _ in _due_reports(monday_10)], ["yesterday", "last_week"])
        first_of_month = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
        self.assertIn(("last_month", "monthly:2026-09"), _due_reports(first_of_month))


class FxRateJobTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self._prev = {key: os.environ.get(key) for key in ("BETBOT_DB_PATH", "LEDGER_ARS_RATE_KIND")}
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp_dir.name) / "fx.sqlite3")
        os.environ.pop("LEDGER_ARS_RATE_KIND", None)
        with open_connection() as conn:
            initialize_schema(conn)
        self.ledger = LedgerService(SqliteStorage())

    def tearDown(self) -> None:
        for key, value in self._prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp_dir.cleanup()

    async def test_the_job_stores_the_digital_dollar_and_quotes_ars_bets(self) -> None:
        from unittest.mock import patch

        from adapters.fx.dolarhoy import DollarQuote
        from bot.jobs import tasks

        bet = self.ledger.add_bet(parse_bet_text("Equipo -1 @1.9 16.031,30 ars 20bet").bet).bet
        quotes = {"blue": DollarQuote("blue", "Dólar blue", 1540, 1560),
                  "digital": DollarQuote("digital", "Dólar Digital (USDC)", 1599.38, 1606.88)}
        application = SimpleNamespace(bot_data={"ledger_service": self.ledger})
        with patch("adapters.fx.dolarhoy.fetch_quotes", AsyncMock(return_value=quotes)):
            await tasks._orchestrated_fx_rate(application)

        info = self.ledger.fx_rate("ARS")
        self.assertEqual((info["ars_per_usd"], info["kind"], info["buy"]), (1603.13, "digital", 1599.38))
        self.assertAlmostEqual(self.ledger.repository.get_bet(bet.id).stake_usd, 10.0, places=3)

    async def test_a_failing_source_keeps_the_last_rate(self) -> None:
        from unittest.mock import patch

        from bot.jobs import tasks

        self.ledger.set_fx_rate("ARS", 1550.0)
        application = SimpleNamespace(bot_data={"ledger_service": self.ledger})
        with patch("adapters.fx.dolarhoy.fetch_quotes", AsyncMock(side_effect=httpx_error())):
            await tasks._orchestrated_fx_rate(application)
        self.assertEqual(self.ledger.fx_rate("ARS")["ars_per_usd"], 1550.0)


def httpx_error() -> Exception:
    import httpx

    return httpx.ConnectError("dolarhoy caído")


class LiveWatchTriggersSettlementTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_finished_match_or_a_halftime_settles_at_once(self) -> None:
        from unittest.mock import patch

        from bot.jobs import tasks

        service = LiveWatchService(repository=SimpleNamespace())
        service.poll_once = AsyncMock(return_value=[])
        application = SimpleNamespace(bot_data={tasks.LIVE_WATCH_SERVICE_KEY: service})
        with patch.object(tasks, "_orchestrated_ledger_settlement", AsyncMock()) as settle:
            await tasks._orchestrated_live_watch(application)
            settle.assert_not_awaited()
            service._settlement_triggers = 1  # el watch archivó un resultado
            await tasks._orchestrated_live_watch(application)
            settle.assert_awaited_once_with(application)


if __name__ == "__main__":
    unittest.main()

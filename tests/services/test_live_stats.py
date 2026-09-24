"""Panel de stats en vivo: 1xBet (lo que muestra Melbet) + los extras de Statshub."""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from core.live_stats import merge_live_stats
from extractors.xbet_http.live_stats import build_live_game_url, parse_game_stats
from interfaces.telegram.renderers.live_stats import build_live_stats_message
from services.live_stats import LiveStatsService
from stats_providers.sportradar_http.live_stats import parse_match_details

# GetGameZip de San Marino U21 - Kosovo U21 en el entretiempo (recortado).
XBET_GAME = {"Value": {
    "O1": "San Marino U21", "O2": "Kosovo U21", "L": "UEFA European U21 Championship Qualification",
    "SC": {"FS": {"S2": 1}, "CP": 2, "CPS": "Half-time", "TS": 2700,
           "PS": [{"Key": 1, "Value": {"S2": 1, "NF": "1st half"}}, {"Key": 2, "Value": {"NF": "2nd half"}}],
           "ST": [{"Key": 0, "Value": [
               {"ID": 45, "S1": "35", "S2": "37", "N": "Attacks"},
               {"ID": 58, "S1": "21", "S2": "46", "N": "Dangerous attacks"},
               {"ID": 29, "S1": "35", "S2": "65", "N": "Possession %"},
               {"ID": 59, "S1": "1", "S2": "3", "N": "Shots on target"},
               {"ID": 70, "S1": "1", "S2": "4", "N": "Corner"},
               {"ID": 26, "S1": "0", "S2": "1", "N": "Yellow cards"}]}]}}}
STATSHUB_DETAILS = {"doc": [{"data": {
    "teams": {"home": "San Marino", "away": "Kosovo"},
    "values": {"129": {"name": "Fouls", "value": {"home": 9, "away": 9}},
               "123": {"name": "Offsides", "value": {"home": 0, "away": 2}},
               "1126": {"name": "Attack", "value": {"home": 30, "away": 25}},
               "124": {"name": "Corner kicks", "value": {"home": 1, "away": 4}}}}}]}


class ParserTests(unittest.TestCase):
    def test_the_xbet_panel(self) -> None:
        snapshot = parse_game_stats(XBET_GAME)

        self.assertEqual(snapshot.stats["possession"], (35, 65))
        self.assertEqual(snapshot.stats["dangerous_attacks"], (21, 46))
        self.assertEqual((snapshot.home_score, snapshot.away_score, snapshot.ht_score), (0, 1, (0, 1)))
        self.assertEqual((snapshot.period, snapshot.minute), ("Entretiempo", "45'"))
        self.assertIsNone(parse_game_stats({"Value": {}}))  # el partido ya no está en LiveFeed
        self.assertEqual(
            build_live_game_url(base_url="https://spinbetter.com/service-api/LineFeed", event_id="7", language="en"),
            "https://spinbetter.com/service-api/LiveFeed/GetGameZip?id=7&lng=en")

    def test_statshub_details(self) -> None:
        snapshot = parse_match_details(STATSHUB_DETAILS)

        self.assertEqual(snapshot.stats["fouls"], (9, 9))
        self.assertEqual(snapshot.stats["offsides"], (0, 2))
        self.assertIsNone(parse_match_details({"doc": []}))

    def test_merge_prefers_the_book_and_adds_the_extras(self) -> None:
        view = merge_live_stats([parse_game_stats(XBET_GAME), parse_match_details(STATSHUB_DETAILS)])

        rows = {row.key: row for row in view.rows}
        self.assertEqual((rows["attacks"].home, rows["attacks"].source), (35, "1xbet"))
        self.assertEqual((rows["fouls"].home, rows["fouls"].source), (9, "statshub"))
        self.assertEqual(view.sources, ("1xbet", "statshub"))
        self.assertEqual([row.key for row in view.rows][:3], ["attacks", "dangerous_attacks", "possession"])

        text = build_live_stats_message(view, updated_at=datetime(2026, 9, 24, 21, 18))
        self.assertIn("San Marino U21 0-1 Kosovo U21", text)
        self.assertIn(" 35%  Posesión           65%", text)
        self.assertIn("Entretiempo · 45' · 1T 0-1", text)
        self.assertIn("Fuente: 1xBet + Statshub (faltas, offsides)", text)


def _entry(**live_state) -> SimpleNamespace:
    return SimpleNamespace(id=1580, chat_id=1804, home="San Marino u21", away="Kosovo u21",
                           live_state=live_state)


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_both_sources_once_per_refresh_window(self) -> None:
        xbet = SimpleNamespace(settings=SimpleNamespace(base_url="https://x/service-api/LineFeed", language="en"),
                               fetch_game_zip=AsyncMock(return_value=XBET_GAME))
        service = LiveStatsService(xbet_client=xbet, statshub_provider=object())
        entry = _entry(**{"1xbet_http": {"event_id": "755743183"}, "statshub": {"event_id": "58208351"}})
        statshub = AsyncMock(return_value=parse_match_details(STATSHUB_DETAILS))

        with patch("stats_providers.sportradar_http.live_stats.fetch_match_stats", statshub):
            view = await service.for_entry(entry)
            await service.for_entry(entry)  # dentro del caché: no se vuelve a pedir

        self.assertEqual(view.sources, ("1xbet", "statshub"))
        xbet.fetch_game_zip.assert_awaited_once_with("https://x/service-api/LiveFeed/GetGameZip?id=755743183&lng=en")
        statshub.assert_awaited_once()

    async def test_a_failing_book_leaves_statshub_with_the_watch_score(self) -> None:
        xbet = SimpleNamespace(settings=SimpleNamespace(base_url="https://x/service-api/LineFeed", language="en"),
                               fetch_game_zip=AsyncMock(side_effect=RuntimeError("PoolTimeout")))
        service = LiveStatsService(xbet_client=xbet, statshub_provider=object())
        entry = _entry(**{
            "1xbet_http": {"event_id": "1", "home_score": 0, "away_score": 0},
            "statshub": {"event_id": "2", "official": True, "home_score": 0, "away_score": 1, "minute": "2T"}})

        with patch("stats_providers.sportradar_http.live_stats.fetch_match_stats",
                   AsyncMock(return_value=parse_match_details(STATSHUB_DETAILS))):
            view = await service.for_entry(entry)

        self.assertEqual(view.sources, ("statshub",))
        self.assertEqual((view.home_score, view.away_score, view.minute), (0, 1, "2T"))

    async def test_no_source_no_panel(self) -> None:
        self.assertIsNone(await LiveStatsService().for_entry(_entry(betovo_http={"event_id": "9"})))


class TelegramTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        from adapters.storage import SqliteStorage
        from adapters.storage.connection import open_connection
        from adapters.storage.schema import initialize_schema
        from services.live_watch import LiveWatchService

        self.tmp_dir = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp_dir.name) / "stats.sqlite3")
        with open_connection() as conn:
            initialize_schema(conn)
        self.storage = SqliteStorage()
        self.watch = LiveWatchService(repository=self.storage)
        self.watch.add_fixture_lines(1804, ["San Marino u21 - Kosovo u21"])
        [self.entry] = self.storage.list_live_watches(1804)
        self.storage.update_live_watch_platform_state(self.entry.id, "1xbet_http", {"event_id": "755743183"})
        xbet = SimpleNamespace(settings=SimpleNamespace(base_url="https://x/service-api/LineFeed", language="en"),
                               fetch_game_zip=AsyncMock(return_value=XBET_GAME))
        self.context = SimpleNamespace(application=SimpleNamespace(bot_data={
            "live_watch_service": self.watch, "live_stats_service": LiveStatsService(xbet_client=xbet)}))

    def tearDown(self) -> None:
        if self._prev_db is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db
        self.tmp_dir.cleanup()

    def _update(self, data: str):
        message = SimpleNamespace(chat=SimpleNamespace(id=1804), reply_text=AsyncMock())
        query = SimpleNamespace(data=data, message=message, answer=AsyncMock(), edit_message_text=AsyncMock())
        return SimpleNamespace(callback_query=query), query

    async def test_the_alert_button_sends_the_panel_and_refresh_edits_it(self) -> None:
        from interfaces.telegram.handlers.live_watch import live_stats_callback

        update, query = self._update(f"lstats:{self.entry.id}")
        await live_stats_callback(update, self.context)
        text = query.message.reply_text.await_args.args[0]
        self.assertIn("Posesión", text)
        [[button]] = query.message.reply_text.await_args.kwargs["reply_markup"].inline_keyboard
        self.assertEqual(button.callback_data, f"lstatsr:{self.entry.id}")

        update, query = self._update(f"lstatsr:{self.entry.id}")
        await live_stats_callback(update, self.context)
        query.edit_message_text.assert_awaited_once()
        query.message.reply_text.assert_not_awaited()

    async def test_a_removed_watch_just_answers(self) -> None:
        from interfaces.telegram.handlers.live_watch import live_stats_callback

        update, query = self._update("lstats:999999")
        await live_stats_callback(update, self.context)
        query.answer.assert_awaited_once_with("Ese partido ya no está en vigilancia.")


if __name__ == "__main__":
    unittest.main()

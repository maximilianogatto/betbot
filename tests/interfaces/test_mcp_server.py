"""Servidor MCP: las tools contra una base real y el servidor completo por stdio."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

HAS_MCP = importlib.util.find_spec("mcp") is not None
REPO_ROOT = Path(__file__).resolve().parents[2]
CHAT = 1804
BET = "San Marino u21 vs Kosovo u21 Kosovou21 -3.5 FT @1.62 12usd pre melbet #franko"


@unittest.skipUnless(HAS_MCP, "falta el paquete mcp")
class McpToolsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        from adapters.storage.connection import open_connection
        from adapters.storage.schema import initialize_schema
        import interfaces.mcp.server as mcp_server

        self.tmp_dir = tempfile.TemporaryDirectory()
        self._prev_env = {key: os.environ.get(key) for key in ("BETBOT_DB_PATH", "BETBOT_MCP_CHAT_ID")}
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp_dir.name) / "mcp.sqlite3")
        os.environ["BETBOT_MCP_CHAT_ID"] = str(CHAT)
        with open_connection() as conn:
            initialize_schema(conn)
        self.mcp = mcp_server
        mcp_server.runtime = mcp_server._Runtime()  # sin services cacheados de otro test
        self.storage = mcp_server.runtime.storage

    def tearDown(self) -> None:
        for key, value in self._prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp_dir.cleanup()

    def _track(self, chat_id: int = CHAT) -> int:
        from core.models import ActiveEventUpsert

        self.storage.create_pending_competition_request(
            chat_id=chat_id, platform="betovo_http", source_url="betovo:champ:77",
            competition_external_id="77", competition_name="European U21 Championship, Qualification",
            requires_empty_confirmation=False, needs_name_resolution=False)
        competition = self.storage.confirm_pending_competition_request(chat_id)
        self.storage.upsert_active_events(competition.id, [ActiveEventUpsert(
            external_event_id="bo-1", home="San Marino U21", away="Kosovo U21",
            scheduled_label_date=None, scheduled_label_time=None,
            scheduled_at=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
            odds_home=21.0, odds_draw=9.0, odds_away=1.12,
            markets_payload={"asian_handicap": {"selections": [
                {"selection": "San Marino U21", "line": "+3.5", "odds": 2.05},
                {"selection": "Kosovo U21", "line": "-3.5", "odds": 1.75}]}})])
        return competition.id

    # ----- lectura -----

    def test_schema_and_read_only_query(self) -> None:
        tables = self.mcp.schema()["tables"]
        self.assertIn("bets", tables)
        self.assertIn("ticket_id", [column["name"] for column in tables["bets"]["columns"]])

        result = self.mcp.query("SELECT ? AS a, ? AS b", [1, "x"])
        self.assertEqual((result["columns"], result["rows"]), (["a", "b"], [[1, "x"]]))
        with self.assertRaises(ValueError):
            self.mcp.query("INSERT INTO ledger_settings (key, value) VALUES ('x', 1)")
        with self.assertRaises(ValueError):
            self.mcp.query("DELETE FROM bets")

    def test_query_caps_rows(self) -> None:
        result = self.mcp.query("WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n"
                                " WHERE i < 50) SELECT i FROM n", limit=10)
        self.assertEqual((result["row_count"], result["truncated"]), (10, True))

    def test_events_with_markets_for_the_default_chat(self) -> None:
        competition_id = self._track()
        [event] = self.mcp.events(with_markets=True)["events"]
        self.assertEqual((event["competition_id"], event["home"]), (competition_id, "San Marino U21"))
        sides = {(m["market_type"], m["side"], m["line"]) for m in event["markets"]}
        self.assertIn(("asian_handicap", "away", -3.5), sides)
        self.assertEqual(self.mcp.events(team="boca")["events"], [])
        [league] = self.mcp.leagues()["leagues"]
        self.assertEqual((league["id"], league["active_events"]), (competition_id, 1))

    def test_odds_history_is_flattened(self) -> None:
        from core.models import OddsSnapshot

        self.storage.archive_snapshots([OddsSnapshot(
            platform="betovo_http", external_event_id="bo-1", captured_at="2026-09-24T10:00:00+00:00",
            payload_hash="h1", home="San Marino U21", away="Kosovo U21",
            odds_home=21.0, odds_draw=9.0, odds_away=1.12,
            markets_json=json.dumps({"1x2": {"home": 21.0, "draw": 9.0, "away": 1.12}}))])
        [snapshot] = self.mcp.odds_history("betovo_http", "bo-1")["snapshots"]
        self.assertIn({"market_type": "1x2", "side": "away", "odds": 1.12},
                      [{k: m[k] for k in ("market_type", "side", "odds")} for m in snapshot["markets"]])

    async def test_live_stats_of_a_watched_match(self) -> None:
        from unittest.mock import AsyncMock
        from types import SimpleNamespace

        from services.live_stats import LiveStatsService
        from tests.services.test_live_stats import XBET_GAME

        self.mcp.bet_add(text=BET)
        [watch] = self.mcp.watches()["watches"]
        self.storage.update_live_watch_platform_state(watch["id"], "1xbet_http", {"event_id": "755743183"})
        xbet = SimpleNamespace(settings=SimpleNamespace(base_url="https://x/service-api/LineFeed", language="en"),
                               fetch_game_zip=AsyncMock(return_value=XBET_GAME))
        self.mcp.runtime._live_stats = LiveStatsService(xbet_client=xbet)

        panel = await self.mcp.live_stats(watch["id"])

        self.assertEqual((panel["home_score"], panel["away_score"], panel["period"]), (0, 1, "Entretiempo"))
        self.assertIn({"stat": "possession", "label": "Posesión", "home": 35, "away": 65, "source": "1xbet"},
                      panel["rows"])
        with self.assertRaises(LookupError):
            await self.mcp.live_stats(999999)

    # ----- escritura -----

    def test_bet_add_watches_an_untracked_match_and_skips_duplicate_tickets(self) -> None:
        added = self.mcp.bet_add(text=BET, ticket_id="87753678021",
                                 placed_at="2026-09-23T14:57:00+00:00")
        bet = added["bet"]
        self.assertEqual((bet["source"], bet["chat_id"], bet["ticket_id"]), ("mcp", CHAT, "87753678021"))
        self.assertEqual((bet["legs"][0]["side"], bet["legs"][0]["line"]), ("away", -3.5))
        self.assertEqual([(w["home"], w["away"]) for w in added["watched"]],
                         [("San Marino u21", "Kosovo u21")])
        self.assertTrue(self.mcp.bet_add(text=BET, ticket_id="87753678021")["duplicate"])
        self.assertEqual(len(self.mcp.bets()["bets"]), 1)
        self.assertEqual(len(self.mcp.watches()["watches"]), 1)

    def test_bet_builder_with_structured_legs(self) -> None:
        legs = [{"match_label": "San Marino u21 vs Kosovo u21", "market_type": "team_total",
                 "side": "under", "odds": 0.0, "line": 0.5, "team": "San Marino u21"},
                {"match_label": "San Marino u21 vs Kosovo u21", "market_type": "goal_line",
                 "side": "over", "odds": 0.0, "line": 3.5}]
        bet = self.mcp.bet_add(legs=legs, stake=10, odds_total=1.797, bookmaker="Solcasino",
                               tags=["#franko"], watch=False)["bet"]
        self.assertEqual((bet["odds_total"], bet["bookmaker"], bet["tags"]), (1.797, "solcasino", "franko"))
        self.assertEqual([leg["market_type"] for leg in bet["legs"]], ["team_total_home", "goal_line"])
        with self.assertRaises(ValueError):
            self.mcp.bet_add(text=BET, legs=legs)

    def test_settle_void_and_pnl(self) -> None:
        won = self.mcp.bet_add(text=BET, watch=False)["bet"]
        lost = self.mcp.bet_add(text=BET.replace("melbet", "linebet").replace("12usd", "10usd"),
                                watch=False)["bet"]
        voided = self.mcp.bet_add(text=BET.replace("12usd", "5usd"), watch=False)["bet"]
        self.assertEqual(self.mcp.bet_settle(won["id"], "won")["status"], "won")
        self.mcp.bet_settle(lost["id"], "lost")
        self.assertEqual(self.mcp.bet_void(voided["id"])["status"], "void")

        by_book = {g["bookmaker"]: g for g in self.mcp.pnl("bookmaker")["groups"]}
        self.assertAlmostEqual(by_book["melbet"]["profit_usd"], 7.44)
        self.assertAlmostEqual(by_book["linebet"]["profit_usd"], -10.0)
        [franko] = self.mcp.pnl("tag")["groups"]
        self.assertEqual((franko["tag"], franko["bets"]), ("franko", 2))
        self.assertEqual(self.mcp.exposure()["open_bets"], 0)
        self.assertEqual([b["id"] for b in self.mcp.bets(status="settled")["bets"]], [lost["id"], won["id"]])

    def test_fx_tool(self) -> None:
        self.assertEqual(self.mcp.fx(), {"ARS": None})
        self.mcp.runtime.ledger.set_fx_rate("ARS", 1603.13, kind="digital")
        rate = self.mcp.fx()["ARS"]
        self.assertEqual((rate["ars_per_usd"], rate["kind"], rate["fresh"]), (1603.13, "digital", True))

    def test_report_tool(self) -> None:
        won = self.mcp.bet_add(text=BET, watch=False)["bet"]
        self.mcp.bet_settle(won["id"], "won")
        report = self.mcp.report("day")
        self.assertEqual((report["settled"]["bets"], report["settled"]["profit_usd"]), (1, 7.44))
        self.assertEqual(report["chat_id"], CHAT)
        with self.assertRaises(ValueError):
            self.mcp.report("trimestre")

    def test_watch_add_remove_and_limits(self) -> None:
        from zoneinfo import ZoneInfo

        # Una hora en el futuro: un horario fijo ("20:30") pasa a estar vencido según
        # a qué hora corra el test, y un partido terminado no se vigila.
        kickoff = (datetime.now(ZoneInfo("Europe/Madrid")) + timedelta(hours=1)).replace(second=0, microsecond=0)
        [added] = self.mcp.watch_add([f"{kickoff:%H:%M} UEFA U21 | San Marino U21 - Kosovo U21"],
                                     timezone_name="Europe/Madrid")["added"]
        self.assertTrue(added["kickoff_at"].endswith(f"{kickoff.astimezone(timezone.utc):%H:%M}:00+00:00"))
        self.assertTrue(self.mcp.watch_remove(added["id"])["removed"])
        self.assertEqual(self.mcp.watches()["watches"], [])

        self.assertEqual(self.mcp.limit_set("max_stake_per_bet_usd", 50)["limits"]["max_stake_per_bet_usd"], 50)
        with self.assertRaises(ValueError):
            self.mcp.limit_set("max_stake", 50)

    def test_default_chat_is_the_one_with_most_leagues(self) -> None:
        os.environ.pop("BETBOT_MCP_CHAT_ID")
        self._track(chat_id=77)
        self.assertEqual(self.mcp.runtime.chat_id(None), 77)
        self.assertEqual(self.mcp.runtime.chat_id(5), 5)


@unittest.skipUnless(HAS_MCP, "falta el paquete mcp")
class McpStdioTests(unittest.IsolatedAsyncioTestCase):
    """El servidor de verdad, lanzado como lo lanza el cliente (python -m interfaces.mcp)."""

    async def test_initialize_list_and_call_over_stdio(self) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        from adapters.storage.connection import open_connection
        from adapters.storage.schema import initialize_schema

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "stdio.sqlite3")
            previous = os.environ.get("BETBOT_DB_PATH")
            os.environ["BETBOT_DB_PATH"] = db_path
            try:
                with open_connection() as conn:
                    initialize_schema(conn)
            finally:
                if previous is None:
                    os.environ.pop("BETBOT_DB_PATH", None)
                else:
                    os.environ["BETBOT_DB_PATH"] = previous
            params = StdioServerParameters(
                command=sys.executable, args=["-m", "interfaces.mcp"], cwd=str(REPO_ROOT),
                env={**os.environ, "BETBOT_DB_PATH": db_path, "BETBOT_MCP_CHAT_ID": str(CHAT)})
            with open(os.devnull, "w") as errlog:
                async with stdio_client(params, errlog=errlog) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        names = {tool.name for tool in (await session.list_tools()).tools}
                        self.assertTrue({"query", "bet_add", "pnl", "watch_add"} <= names)
                        result = await session.call_tool("query", {"sql": "SELECT count(*) AS n FROM bets"})
                        self.assertFalse(result.is_error)
                        payload = result.structured_content or json.loads(result.content[0].text)
                        self.assertEqual(payload["rows"], [[0]])
                        # El motivo del error le llega al cliente (no un "Error executing tool").
                        failed = await session.call_tool("query", {"sql": "DELETE FROM bets"})
                        self.assertTrue(failed.is_error)
                        self.assertIn("readonly", failed.content[0].text)
                        failed = await session.call_tool("bet_add", {"text": "Boca @1.9 10usd"})
                        self.assertTrue(failed.is_error)
                        self.assertIn("no reconozco el mercado", failed.content[0].text)


if __name__ == "__main__":
    unittest.main()

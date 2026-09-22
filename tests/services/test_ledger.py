"""El libro de apuestas de punta a punta, con el caso real que lo motivó.

Darwin Olympic W 8-0 Palmerston Rovers W (4-0 al descanso), con los tickets que
el usuario cargó a mano: el sistema tiene que liquidarlos igual que él.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from adapters.storage import SqliteStorage
from adapters.storage.connection import open_connection
from adapters.storage.schema import initialize_schema
from core.betting import parse_bet_text
from core.models import MatchResult, OddsSnapshot
from services.ledger import LedgerService, label_similarity, score_at_minute

KICKOFF = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
GOALS = [{"minute": m, "team": "home"} for m in (9, 18, 24, 31, 49, 58, 85, 90)]


class LabelTests(unittest.TestCase):
    def test_one_team_resolves_the_side(self) -> None:
        score, side = label_similarity("Darwin", "Darwin Olympic W", "Palmerston Rovers W")
        self.assertGreater(score, 0.7)
        self.assertEqual(side, "home")
        _, side = label_similarity("Palmerston", "Darwin Olympic W", "Palmerston Rovers W")
        self.assertEqual(side, "away")

    def test_both_teams_need_to_match(self) -> None:
        score, side = label_similarity("Darwin vs Palmerston", "Darwin Olympic W",
                                       "Palmerston Rovers W")
        self.assertGreater(score, 0.7)
        self.assertIsNone(side)
        self.assertEqual(label_similarity("Boca vs River", "Darwin Olympic W",
                                          "Palmerston Rovers W")[0], 0.0)

    def test_score_at_minute_from_archived_goal_minutes(self) -> None:
        result = MatchResult(home="a", away="b", status="FINISHED", source="test",
                             recorded_at="x", goal_minutes_json=json.dumps(GOALS))
        self.assertEqual(score_at_minute(result, 13), (1, 0))   # sólo el del 9'
        self.assertEqual(score_at_minute(result, 31), (3, 0))   # el del 31' todavía no
        self.assertEqual(score_at_minute(result, 95), (8, 0))


class LedgerFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self._prev_db = os.environ.get("BETBOT_DB_PATH")
        os.environ["BETBOT_DB_PATH"] = str(Path(self.tmp_dir.name) / "ledger.sqlite3")
        os.environ.pop("LEDGER_ARS_PER_USD", None)
        with open_connection() as conn:
            initialize_schema(conn)
        self.storage = SqliteStorage()
        self.now = KICKOFF + timedelta(hours=3)
        self.ledger = LedgerService(self.storage, clock=lambda: self.now)
        self.storage.record_match_result(MatchResult(
            platform="1xbet_http", external_event_id="ev-darwin",
            home="Darwin Olympic W", away="Palmerston Rovers W",
            competition_name="NT Women's Premier League", status="FINISHED",
            kickoff_at=KICKOFF.isoformat(), source="live_watch",
            recorded_at=KICKOFF.isoformat(),
            final_home_score=8, final_away_score=0, ht_home_score=4, ht_away_score=0,
            goal_minutes_json=json.dumps(GOALS)))
        # Serie de cuotas: el local se desploma antes del partido.
        self.storage.archive_snapshots([
            OddsSnapshot(platform="1xbet_http", external_event_id="ev-darwin",
                         captured_at=(KICKOFF - timedelta(hours=3)).isoformat(),
                         payload_hash="h1", home="Darwin Olympic W", away="Palmerston Rovers W",
                         odds_home=1.40, odds_draw=8.0, odds_away=15.0,
                         markets_json=json.dumps({"1x2": {"home": 1.40, "draw": 8.0, "away": 15.0}})),
            OddsSnapshot(platform="1xbet_http", external_event_id="ev-darwin",
                         captured_at=(KICKOFF - timedelta(minutes=5)).isoformat(),
                         payload_hash="h2", home="Darwin Olympic W", away="Palmerston Rovers W",
                         odds_home=1.08, odds_draw=11.0, odds_away=21.0,
                         markets_json=json.dumps({"1x2": {"home": 1.08, "draw": 11.0, "away": 21.0}})),
        ])

    def tearDown(self) -> None:
        if self._prev_db is None:
            os.environ.pop("BETBOT_DB_PATH", None)
        else:
            os.environ["BETBOT_DB_PATH"] = self._prev_db
        self.tmp_dir.cleanup()

    def _add(self, text: str, **kwargs):
        parsed = parse_bet_text(text, now=self.now, **kwargs)
        return self.ledger.add_bet(parsed.bet)

    def test_links_the_match_and_rebuilds_the_score_of_that_minute(self) -> None:
        result = self._add("Darwin -2.5 HT @1.605 10usd min 13 megapari")
        leg = result.bet.legs[0]
        self.assertEqual((leg.platform, leg.external_event_id), ("1xbet_http", "ev-darwin"))
        self.assertEqual(leg.side, "home")
        # Al 13' había un gol (9'): sale de los minutos archivados.
        self.assertEqual((leg.placed_home_score, leg.placed_away_score), (1, 0))
        self.assertEqual(leg.handicap_from, "full")  # rusas: marcador completo

    def test_settles_the_real_darwin_tickets(self) -> None:
        wins = ["Darwin -2.5 HT @1.56 10usd min 13 megapari",
                "Darwin vs Palmerston over 2.5 HT @1.616 10usd min 13 megapari",
                "Darwin -5.5 @1.632 10usd min 31 megapari"]
        losses = ["Darwin vs Palmerston over 4.5 HT @1.832 10usd min 31 megapari",
                  "Darwin -4.5 HT @1.83 10usd min 31 megapari"]
        bets = [self._add(text).bet for text in wins + losses]
        # Se liquidan solas al cargarlas, porque el resultado ya está archivado.
        self.assertEqual([bet.status for bet in bets], ["won"] * 3 + ["lost"] * 2)
        self.assertEqual([round(bet.profit, 3) for bet in bets],
                         [5.6, 6.16, 6.32, -10.0, -10.0])

    def test_settlement_when_the_match_finishes_later(self) -> None:
        # Partido todavía sin resultado archivado: la apuesta queda abierta.
        with open_connection() as conn:
            conn.execute("UPDATE match_results SET final_home_score = NULL, status = 'LIVE'")
        bet = self._add("Darwin -2.5 HT @1.56 10usd min 13 megapari").bet
        self.assertEqual(bet.status, "open")

        with open_connection() as conn:
            conn.execute("UPDATE match_results SET final_home_score = 8, final_away_score = 0,"
                         " status = 'FINISHED'")
        self.assertEqual(self.ledger.settle_event(
            platform="1xbet_http", external_event_id="ev-darwin"), 1)
        self.assertEqual(self.storage.get_bet(bet.id).status, "won")

    def test_a_suspended_match_is_never_settled_automatically(self) -> None:
        with open_connection() as conn:
            conn.execute("UPDATE match_results SET status = 'SUSPENDED'")
        bet = self._add("Darwin -2.5 HT @1.56 10usd min 13 megapari").bet
        self.assertEqual(bet.status, "open")
        settled = self.ledger.settle_manual(bet.id, "void", note="suspendido")
        self.assertEqual(settled.status, "void")

    def test_prematch_clv_against_the_closing_we_observed(self) -> None:
        bet = self._add("Darwin gana @1.40 10usd pre megapari").bet
        leg = self.storage.get_bet(bet.id).legs[0]
        # Pre-match sin hora: no se inventa qué se veía en ese momento...
        self.assertIsNone(leg.observed_odds)
        # ...pero el cierre observado y el CLV sí son datos reales.
        self.assertEqual(leg.closing_odds, 1.08)
        self.assertAlmostEqual(leg.clv, 1.40 / 1.08 - 1, places=3)

    def test_live_bet_uses_the_odds_of_that_minute(self) -> None:
        self.storage.archive_snapshots([OddsSnapshot(
            platform="1xbet_http", external_event_id="ev-darwin",
            captured_at=(KICKOFF + timedelta(minutes=13)).isoformat(), payload_hash="h3",
            home="Darwin Olympic W", away="Palmerston Rovers W",
            markets_json=json.dumps({"asian_handicap": {"selections": [
                {"selection": "Darwin Olympic W", "line": "-2.5", "odds": 1.66},
                {"selection": "Palmerston Rovers W", "line": "+2.5", "odds": 2.10}]}}))])
        # Handicap de partido completo, que es el que se archivó arriba.
        bet = self._add("Darwin -2.5 @1.605 10usd min 13 megapari").bet
        leg = self.storage.get_bet(bet.id).legs[0]
        # El minuto ubica el instante (kickoff + 13'): ahí veíamos 1.66.
        self.assertEqual(leg.observed_odds, 1.66)

    def test_a_first_half_bet_is_not_matched_against_the_full_time_market(self) -> None:
        self.storage.archive_snapshots([OddsSnapshot(
            platform="1xbet_http", external_event_id="ev-darwin",
            captured_at=(KICKOFF + timedelta(minutes=13)).isoformat(), payload_hash="h4",
            home="Darwin Olympic W", away="Palmerston Rovers W",
            markets_json=json.dumps({"asian_handicap": {"selections": [
                {"selection": "Darwin Olympic W", "line": "-2.5", "odds": 1.66},
                {"selection": "Palmerston Rovers W", "line": "+2.5", "odds": 2.10}]}}))])
        # La apuesta es al primer tiempo y sólo hay archivado el de partido
        # completo: se deja vacío en vez de usar el precio equivocado.
        bet = self._add("Darwin -2.5 HT @1.605 10usd min 13 megapari").bet
        self.assertIsNone(self.storage.get_bet(bet.id).legs[0].observed_odds)

    def test_unlinked_bet_stays_open_and_settles_by_hand(self) -> None:
        result = self._add("Equipo Inexistente -1 @1.9 10usd")
        self.assertTrue(any("no coincide" in w for w in result.warnings))
        self.assertEqual(result.bet.status, "open")
        self.assertAlmostEqual(self.ledger.settle_manual(result.bet.id, "won").profit, 9.0)

    def test_limits_warn_but_never_block(self) -> None:
        self.ledger.set_limit("max_exposure_per_match_usd", 15)
        with open_connection() as conn:  # partido sin resultado: quedan abiertas
            conn.execute("UPDATE match_results SET final_home_score = NULL, status = 'LIVE'")
        self._add("Darwin -2.5 HT @1.56 10usd min 13 megapari")
        second = self._add("Darwin -4.5 HT @1.83 10usd min 31 megapari")
        self.assertTrue(any("límite por partido" in w for w in second.warnings))
        self.assertEqual(self.ledger.exposure()["open_bets"], 2)

    def test_ars_without_exchange_rate_warns_and_stays_out_of_usd_totals(self) -> None:
        result = self._add("Darwin -2.5 HT @1.56 15.000 ars min 13 megapari")
        self.assertTrue(any("tipo de cambio" in w for w in result.warnings))
        self.assertIsNone(result.bet.stake_usd)

    def test_paper_tip_does_not_touch_exposure_or_limits(self) -> None:
        self.ledger.set_limit("max_exposure_per_match_usd", 5)
        tip = self._add("Darwin vs Palmerston descanso-final G1/G1 @1.40 #grupo_x", paper=True)
        self.assertEqual(tip.warnings, [])
        self.assertEqual((tip.bet.mode, tip.bet.currency, tip.bet.status), ("paper", "U", "won"))
        self.assertAlmostEqual(tip.bet.profit, 0.40)
        self.assertEqual(self.ledger.exposure()["open_bets"], 0)


if __name__ == "__main__":
    unittest.main()

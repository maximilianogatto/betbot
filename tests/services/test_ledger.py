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
from core.betting.parse import ParseError
from core.models import ActiveEventUpsert, MatchResult, OddsSnapshot
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


class ParseTests(unittest.TestCase):
    """Cómo se escriben de verdad en el grupo (VPS, 2026-09-24)."""

    REAL = "San Marino u21 vs Kosovo u21 Kosovou21 -3.5 FT @1.62 12usd pre melbet #franko"

    def test_match_plus_team_is_the_team_bet(self) -> None:
        leg = parse_bet_text(self.REAL).bet.legs[0]
        self.assertEqual((leg.market_type, leg.side, leg.line), ("asian_handicap", "team", -3.5))
        self.assertEqual(leg.match_label, "San Marino u21 vs Kosovo u21")
        self.assertEqual(leg.team, "Kosovou21")
        self.assertEqual(leg.market_period, "FT")

    def test_age_category_is_not_an_under_or_over(self) -> None:
        leg = parse_bet_text("Chile u20 vs Peru u20 over 2.5 @1.9 10usd").bet.legs[0]
        self.assertEqual((leg.market_type, leg.side, leg.line), ("goal_line", "over", 2.5))
        self.assertEqual(leg.match_label, "Chile u20 vs Peru u20")
        leg = parse_bet_text("Kosovo u21 -3.5 @1.62 10usd").bet.legs[0]
        self.assertEqual((leg.market_type, leg.line, leg.team), ("asian_handicap", -3.5, "Kosovo u21"))

    def test_short_under_and_over_still_work(self) -> None:
        for text, side, line in (("Boca vs River u2.5 @1.8 10usd", "under", 2.5),
                                 ("Boca vs River o3 @1.8 10usd", "over", 3.0)):
            leg = parse_bet_text(text).bet.legs[0]
            self.assertEqual((leg.market_type, leg.side, leg.line), ("goal_line", side, line))

    def test_category_tokens_stay_with_the_away_team(self) -> None:
        leg = parse_bet_text("San Marino u21 vs Kosovo u21 San Marino +3.5 @2.1 10usd").bet.legs[0]
        self.assertEqual((leg.match_label, leg.team), ("San Marino u21 vs Kosovo u21", "San Marino"))

    def test_a_separator_or_an_exact_repeat_marks_the_team(self) -> None:
        for text in ("Bnot Netanya vs ASA Tel Aviv - Asa tel aviv -2.5 FT @1.79 14usd min 14 con 0-1",
                     "Bnot Netanya vs ASA Tel Aviv Asa tel aviv -2.5 FT @1.79 14usd min 14 con 0-1"):
            leg = parse_bet_text(text).bet.legs[0]
            self.assertEqual((leg.match_label, leg.team), ("Bnot Netanya vs ASA Tel Aviv", "Asa tel aviv"))
            self.assertEqual((leg.line, leg.placed_minute, leg.placed_score), (-2.5, 14, (0, 1)))

    def test_a_match_without_the_team_still_asks_for_it(self) -> None:
        for text in ("Darwin vs Palmerston -2.5 @1.6 10usd", "Darwin vs Palmerston Rovers W -2.5 @1.6 10usd"):
            with self.assertRaises(ParseError):
                parse_bet_text(text)


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

    def test_links_an_active_match_of_the_chat(self) -> None:
        """Partido todavía sin resultado: se busca entre los vigentes del chat.

        El repositorio los devuelve como filas (dict); antes el ledger les pedía
        `.home` y la apuesta no se registraba.
        """
        chat_id = 4242
        self.storage.create_pending_competition_request(
            chat_id=chat_id, platform="1xbet_http",
            source_url="https://spinbetter.com/service-api/LineFeed/GetChampZip?champ=1&lng=en",
            competition_external_id="1", competition_name="UEFA U21 Qualifiers",
            requires_empty_confirmation=False, needs_name_resolution=False)
        competition = self.storage.confirm_pending_competition_request(chat_id)
        kickoff = self.now + timedelta(hours=4)
        self.storage.upsert_active_events(competition.id, [ActiveEventUpsert(
            external_event_id="ev-smr-kos", home="San Marino U21", away="Kosovo U21",
            scheduled_label_date=None, scheduled_label_time=None,
            scheduled_at=kickoff.isoformat(), odds_home=21.0, odds_draw=9.0, odds_away=1.12)])

        parsed = parse_bet_text(ParseTests.REAL, now=self.now)
        parsed.bet.chat_id = chat_id
        result = self.ledger.add_bet(parsed.bet)

        leg = result.bet.legs[0]
        self.assertEqual((leg.platform, leg.external_event_id), ("1xbet_http", "ev-smr-kos"))
        self.assertEqual((leg.side, leg.line), ("away", -3.5))
        self.assertEqual((leg.home, leg.away), ("San Marino U21", "Kosovo U21"))
        self.assertEqual(leg.competition_name, "UEFA U21 Qualifiers")
        self.assertEqual(result.bet.status, "open")
        self.assertFalse(any("no coincide" in w for w in result.warnings))

    def test_unlinked_match_plus_team_keeps_the_pick(self) -> None:
        """Partido que el bot no trackea: el equipo apostado sale del texto."""
        from interfaces.telegram.renderers.bets import leg_line

        result = self._add(ParseTests.REAL)
        leg = self.storage.get_bet(result.bet.id).legs[0]
        self.assertTrue(any("no coincide" in w for w in result.warnings))
        self.assertIsNone(leg.external_event_id)
        self.assertEqual((leg.side, leg.line), ("away", -3.5))
        self.assertEqual((leg.home, leg.away), ("San Marino u21", "Kosovo u21"))
        text = leg_line(leg)
        self.assertIn("Kosovo u21 -3.5", text)
        self.assertIn("(sin enlazar)", text)

    # ----- enlace tardío y liquidación del job -----

    def _u21_result(self, *, home="San Marino U21", away="Kosovo U21", platform="betovo_http",
                    event_id="ev-u21", score=(0, 5), kickoff=None) -> None:
        self.storage.record_match_result(MatchResult(
            platform=platform, external_event_id=event_id, home=home, away=away,
            status="FINISHED", source="live_watch", kickoff_at=kickoff,
            recorded_at=(self.now + timedelta(hours=10)).isoformat(),
            final_home_score=score[0], final_away_score=score[1]))

    def test_an_unlinked_bet_links_late_and_settles_when_the_result_arrives(self) -> None:
        from interfaces.telegram.renderers.bets import render_settled

        bet = self._add(ParseTests.REAL).bet
        self.assertEqual(self.ledger.run_settlement(), [])  # todavía no hay resultado
        self._u21_result()  # el watch lo archiva con el id de la casa donde lo vio

        [settled] = self.ledger.run_settlement()
        self.assertEqual((settled.id, settled.status), (bet.id, "won"))
        leg = settled.legs[0]
        self.assertEqual((leg.platform, leg.external_event_id), ("betovo_http", "ev-u21"))
        self.assertAlmostEqual(settled.profit, 12 * 0.62, places=4)
        self.assertIn("Apuesta liquidada", render_settled(settled))
        self.assertEqual(self.ledger.run_settlement(), [])  # una sola vez

    def test_late_linking_never_crosses_categories(self) -> None:
        bet = self._add(ParseTests.REAL).bet
        self._u21_result(home="San Marino", away="Kosovo", event_id="ev-senior")  # mayores
        self.assertEqual(self.ledger.run_settlement(), [])
        leg = self.storage.get_bet(bet.id).legs[0]
        self.assertIsNone(leg.external_event_id)

    def test_a_linked_bet_settles_with_the_result_seen_on_another_book(self) -> None:
        chat_id = 4343
        self.storage.create_pending_competition_request(
            chat_id=chat_id, platform="solcasino_http", source_url="solcasino:tournament:9",
            competition_external_id="9", competition_name="U21 European Championship, Qualification",
            requires_empty_confirmation=False, needs_name_resolution=False)
        competition = self.storage.confirm_pending_competition_request(chat_id)
        kickoff = (self.now + timedelta(hours=4)).isoformat()
        self.storage.upsert_active_events(competition.id, [ActiveEventUpsert(
            external_event_id="sol-1", home="San Marino", away="Kosovo",
            scheduled_label_date=None, scheduled_label_time=None, scheduled_at=kickoff,
            odds_home=21.0, odds_draw=9.0, odds_away=1.12)])
        parsed = parse_bet_text("San Marino u21 vs Kosovo u21 over 3.5 @1.9 10usd solcasino",
                                now=self.now)
        parsed.bet.chat_id = chat_id
        bet = self.ledger.add_bet(parsed.bet).bet
        self.assertEqual(bet.legs[0].external_event_id, "sol-1")

        self._u21_result(kickoff=kickoff, score=(0, 4))  # archivado desde betovo, otro id
        [settled] = self.ledger.run_settlement()
        self.assertEqual((settled.id, settled.status), (bet.id, "won"))

    def test_an_unlinked_bet_links_to_a_league_tracked_afterwards(self) -> None:
        chat_id = 4444
        parsed = parse_bet_text(ParseTests.REAL, now=self.now)
        parsed.bet.chat_id = chat_id
        bet = self.ledger.add_bet(parsed.bet).bet
        self.assertIsNone(bet.legs[0].external_event_id)

        self.storage.create_pending_competition_request(
            chat_id=chat_id, platform="betovo_http", source_url="betovo:champ:77",
            competition_external_id="77", competition_name="European U21 Championship, Qualification",
            requires_empty_confirmation=False, needs_name_resolution=False)
        competition = self.storage.confirm_pending_competition_request(chat_id)
        kickoff = (self.now + timedelta(hours=6)).isoformat()
        self.storage.upsert_active_events(competition.id, [
            # Misma liga sub-21 en otra casa que no pone la categoría en los equipos.
            ActiveEventUpsert(external_event_id="bo-0", home="San Marino", away="Kosovo",
                              scheduled_label_date=None, scheduled_label_time=None,
                              scheduled_at=kickoff, odds_home=21.0, odds_draw=9.0, odds_away=1.12),
            ActiveEventUpsert(external_event_id="bo-1", home="San Marino U21", away="Kosovo U21",
                              scheduled_label_date=None, scheduled_label_time=None,
                              scheduled_at=kickoff, odds_home=21.0, odds_draw=9.0, odds_away=1.12)])

        self.assertEqual(self.ledger.run_settlement(), [])  # enlazada, todavía sin jugar
        leg = self.storage.get_bet(bet.id).legs[0]
        self.assertEqual((leg.platform, leg.external_event_id, leg.side), ("betovo_http", "bo-1", "away"))

    def test_late_link_prefers_the_event_of_the_bet_own_book(self) -> None:
        """Cuota observada y CLV tienen sentido contra la casa donde se apostó."""
        chat_id = 4545
        parsed = parse_bet_text(ParseTests.REAL.replace("melbet", "solcasino"), now=self.now)
        parsed.bet.chat_id = chat_id
        bet = self.ledger.add_bet(parsed.bet).bet
        kickoff = (self.now + timedelta(hours=6)).isoformat()
        for platform, event_id, home, away in (("betovo_http", "bo-1", "San Marino U21", "Kosovo U21"),
                                               ("solcasino_http", "sol-1", "San Marino", "Kosovo")):
            self.storage.create_pending_competition_request(
                chat_id=chat_id, platform=platform, source_url=f"{platform}:u21",
                competition_external_id=f"{platform}-u21",
                competition_name="U21 European Championship, Qualification",
                requires_empty_confirmation=False, needs_name_resolution=False)
            competition = self.storage.confirm_pending_competition_request(chat_id)
            self.storage.upsert_active_events(competition.id, [ActiveEventUpsert(
                external_event_id=event_id, home=home, away=away, scheduled_label_date=None,
                scheduled_label_time=None, scheduled_at=kickoff,
                odds_home=21.0, odds_draw=9.0, odds_away=1.12)])

        self.ledger.run_settlement()
        leg = self.storage.get_bet(bet.id).legs[0]
        self.assertEqual((leg.platform, leg.external_event_id), ("solcasino_http", "sol-1"))

    def test_bet_builder_legs_have_no_odds_of_their_own(self) -> None:
        from core.betting.models import BetInput, LegInput
        from interfaces.telegram.renderers.bets import render_bet

        legs = [LegInput(match_label="San Marino u21 vs Kosovo u21", market_type="team_total",
                         side="under", odds=0.0, line=0.5, team="San Marino u21",
                         placed_phase="prematch"),
                LegInput(match_label="San Marino u21 vs Kosovo u21", market_type="goal_line",
                         side="over", odds=0.0, line=3.5, placed_phase="prematch")]
        bet = self.ledger.add_bet(BetInput(legs=legs, stake=10, currency="USD", odds_total=1.797,
                                           bookmaker="solcasino")).bet
        self.assertEqual([leg.market_type for leg in bet.legs], ["team_total_home", "goal_line"])
        self.assertNotIn("@0", render_bet(bet))
        self._u21_result(score=(0, 5))
        [settled] = self.ledger.run_settlement()
        self.assertEqual(settled.status, "won")
        self.assertAlmostEqual(settled.profit, 7.97, places=2)  # paga la cuota del ticket

    def _watch_live(self, chat_id: int) -> None:
        """Watch de la planilla que ya vio el partido en vivo en dos casas."""
        entry = self.storage.add_live_watch(
            chat_id, home="Bnot Netanya", away="ASA Tel Aviv (Visitantes +4/5)",
            league_hint="Israel (F)", kickoff_at=(self.now - timedelta(minutes=15)).isoformat())
        for platform, event_id, home, away, score in (
                ("solcasino_http", "sol-9", "Bnot Netanya FC", "ASA Tel Aviv", None),
                ("betovo_http", "bo-9", "Bnot Netanya (W)", "AS Tel Aviv University (W)", 0)):
            self.storage.update_live_watch_platform_state(entry.id, platform, {
                "event_id": event_id, "home": home, "away": away, "home_score": score,
                "away_score": None if score is None else 1, "minute": "14'"})

    def test_a_live_bet_links_to_the_match_the_watch_is_following(self) -> None:
        chat_id = 4646
        self._watch_live(chat_id)
        parsed = parse_bet_text("Bnot Netanya vs ASA Tel Aviv - Asa tel aviv -2.5 FT @1.79 14usd"
                                " min 14 con 0-1 melbet #excel", now=self.now)
        parsed.bet.chat_id = chat_id
        result = self.ledger.add_bet(parsed.bet)

        leg = result.bet.legs[0]
        self.assertEqual((leg.platform, leg.external_event_id), ("solcasino_http", "sol-9"))
        self.assertEqual((leg.side, leg.line), ("away", -2.5))
        self.assertEqual(leg.competition_name, "Israel (F)")
        self.assertFalse(any("no coincide" in w for w in result.warnings))

    def test_a_bet_linked_to_one_book_settles_with_the_result_archived_from_another(self) -> None:
        """Solcasino da "ASA Tel Aviv" y el resultado lo archiva betovo ("AS Tel Aviv
        University"): por nombre no se reconocen, por los ids que agrupa el watch sí."""
        from services.live_watch import LiveWatchService

        chat_id = 4848
        self._watch_live(chat_id)
        parsed = parse_bet_text("Bnot Netanya vs ASA Tel Aviv - Asa tel aviv -2.5 FT @1.79 14usd"
                                " min 14 con 0-1 melbet", now=self.now)
        parsed.bet.chat_id = chat_id
        bet = self.ledger.add_bet(parsed.bet).bet
        self.assertEqual(bet.legs[0].platform, "solcasino_http")

        [entry] = self.storage.list_live_watches(chat_id)
        self.storage.update_live_watch_platform_state(entry.id, "betovo_http", {
            "event_id": "bo-9", "home": "Bnot Netanya (W)", "away": "AS Tel Aviv University (W)",
            "home_score": 0, "away_score": 4, "minute": "90+3'",
            "observed_at": datetime.now(timezone.utc).isoformat()})
        LiveWatchService(repository=self.storage).purge_expired()  # vence y archiva desde betovo

        [settled] = self.ledger.run_settlement()
        self.assertEqual((settled.id, settled.status), (bet.id, "won"))

    def test_a_first_half_bet_settles_at_halftime_while_the_match_goes_on(self) -> None:
        chat_id = 4949
        self._watch_live(chat_id)
        [entry] = self.storage.list_live_watches(chat_id)
        self.storage.update_live_watch_platform_state(entry.id, "betovo_http", {
            "event_id": "bo-9", "home": "Bnot Netanya (W)", "away": "AS Tel Aviv University (W)",
            "home_score": 0, "away_score": 3, "ht_home_score": 0, "ht_away_score": 3, "minute": "HT"})
        parsed = parse_bet_text("Bnot Netanya vs ASA Tel Aviv - Asa tel aviv -1.5 HT @1.9 10usd"
                                " min 14 con 0-1 melbet", now=self.now)
        parsed.bet.chat_id = chat_id
        ht_bet = self.ledger.add_bet(parsed.bet).bet
        parsed = parse_bet_text("Bnot Netanya vs ASA Tel Aviv - Asa tel aviv -2.5 @1.8 10usd"
                                " min 14 con 0-1 melbet", now=self.now)
        parsed.bet.chat_id = chat_id
        ft_bet = self.ledger.add_bet(parsed.bet).bet

        [settled] = self.ledger.run_settlement()  # sólo la del 1er tiempo: el partido sigue
        self.assertEqual((settled.id, settled.status), (ht_bet.id, "won"))
        self.assertEqual(self.storage.get_bet(ft_bet.id).status, "open")

    def test_both_halves_and_second_half_markets(self) -> None:
        from core.betting.settlement import settle_leg

        def outcome(market_type, period, side, line, *, final=(3, 0), halftime=(1, 0)):
            result = settle_leg(market_type=market_type, market_period=period, side=side, line=line,
                                odds=1.62, final=final, halftime=halftime)
            return result.status if result else None

        # Ambas mitades más de 1.5: 1er tiempo 1 gol -> "no" gana.
        self.assertEqual(outcome("both_halves_over", "FT", "no", 1.5), "won")
        self.assertEqual(outcome("both_halves_over", "FT", "yes", 1.5), "lost")
        self.assertEqual(outcome("both_halves_over", "FT", "yes", 1.5, final=(3, 2), halftime=(1, 1)), "won")
        self.assertIsNone(outcome("both_halves_over", "FT", "no", 1.5, halftime=None))  # a mano
        # 2º tiempo: 3-0 con 1-0 al descanso -> 2-0 en el 2º.
        self.assertEqual(outcome("goal_line", "2H", "over", 1.5), "won")
        self.assertEqual(outcome("asian_handicap", "2H", "away", 1.5), "lost")

    def test_an_unlinked_bet_links_late_to_a_watched_match(self) -> None:
        chat_id = 4747
        parsed = parse_bet_text("Bnot Netanya vs ASA Tel Aviv - Asa tel aviv -2.5 @1.79 14usd min 14"
                                " con 0-1 melbet", now=self.now)
        parsed.bet.chat_id = chat_id
        bet = self.ledger.add_bet(parsed.bet).bet
        self.assertIsNone(bet.legs[0].external_event_id)

        self._watch_live(chat_id)  # el partido se sumó a /watching después
        self.ledger.run_settlement()
        leg = self.storage.get_bet(bet.id).legs[0]
        self.assertEqual((leg.external_event_id, leg.side), ("sol-9", "away"))

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

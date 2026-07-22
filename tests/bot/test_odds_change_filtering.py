import dataclasses
import json
import unittest
from unittest.mock import MagicMock

from services.change_detection import evaluate_subscription_odds_change, find_main_line_selections
from core.models import ActiveEventRecord, CompetitionSubscription, EventBaseline, TrackedCompetition


class OddsChangeFilteringTests(unittest.TestCase):
    def test_find_main_line_selections_picks_most_balanced_line(self) -> None:
        selections = [
            {"selection": "Home", "line": "-3", "odds": 5.85},
            {"selection": "Away", "line": "+3", "odds": 1.10},
            {"selection": "Home", "line": "-1.5", "odds": 2.14},
            {"selection": "Away", "line": "+1.5", "odds": 1.68},
            {"selection": "Home", "line": "-0.5", "odds": 3.42},
            {"selection": "Away", "line": "+0.5", "odds": 1.30},
        ]
        
        main_sels = find_main_line_selections(selections, is_handicap=True)
        self.assertEqual(len(main_sels), 2)
        lines = {sel["line"] for sel in main_sels}
        self.assertEqual(lines, {"-1.5", "+1.5"})

    def test_odds_change_ignores_alternative_lines(self) -> None:
        repository = MagicMock()
        
        subscription = CompetitionSubscription(
            telegram_chat_id=123,
            tracked_competition_id=1,
            notify_new_events=True,
            notify_odds_changes=True,
            change_percent_threshold=10.0,
            enabled=True,
            created_at="...",
            updated_at="..."
        )
        
        tracked_league = TrackedCompetition(
            id=1,
            platform="1xbet_http",
            source_url="http://example.com",
            competition_external_id="123",
            competition_name="Test League",
            metadata_json=None,
            needs_name_resolution=False,
            enabled=True,
            last_synced_at=None,
            consecutive_unavailable_refreshes=0,
            last_unavailable_refresh_at=None,
            last_unavailable_reason=None,
            last_unavailable_notification_at=None,
            created_at="...",
            updated_at="..."
        )
        
        baseline_markets = {
            "1x2": {"home": 2.0, "draw": 3.0, "away": 3.0},
            "asian_handicap": {
                "selections": [
                    {"selection": "Home", "line": "-0.5", "odds": 1.95},
                    {"selection": "Away", "line": "+0.5", "odds": 1.95},
                    {"selection": "Home", "line": "-1.5", "odds": 3.0},
                    {"selection": "Away", "line": "+1.5", "odds": 1.40}
                ]
            }
        }
        
        baseline = EventBaseline(
            telegram_chat_id=123,
            active_event_id=1,
            tracked_competition_id=1,
            external_event_id="match_1",
            baseline_home=2.0,
            baseline_draw=3.0,
            baseline_away=3.0,
            baseline_markets_json=json.dumps(baseline_markets),
            baseline_set_at="...",
            updated_at="..."
        )
        repository.get_event_baseline.return_value = baseline
        
        current_markets = {
            "1x2": {"home": 2.0, "draw": 3.0, "away": 3.0},
            "asian_handicap": {
                "selections": [
                    {"selection": "Home", "line": "-0.5", "odds": 1.95},
                    {"selection": "Away", "line": "+0.5", "odds": 1.95},
                    {"selection": "Home", "line": "-1.5", "odds": 5.0},
                    {"selection": "Away", "line": "+1.5", "odds": 1.15}
                ]
            }
        }
        
        match = ActiveEventRecord(
            id=1,
            tracked_competition_id=1,
            platform="1xbet_http",
            competition_external_id="123",
            external_event_id="match_1",
            home="Home",
            away="Away",
            scheduled_label_date="2026-06-03",
            scheduled_label_time="12:00",
            scheduled_at="2026-06-03T15:00:00+00:00",
            event_url="...",
            odds_home=2.0,
            odds_draw=3.0,
            odds_away=3.0,
            markets_json=json.dumps(current_markets),
            raw_payload_json=None,
            alerted=False,
            is_active=True,
            first_seen_at="...",
            last_seen_at="...",
            created_at="...",
            updated_at="..."
        )
        
        alert = evaluate_subscription_odds_change(
            repository,
            subscription,
            tracked_league,
            match,
            confirmation_refreshes=1
        )
        
        self.assertIsNone(alert)
        
        current_markets_main_changed = {
            "1x2": {"home": 2.0, "draw": 3.0, "away": 3.0},
            "asian_handicap": {
                "selections": [
                    {"selection": "Home", "line": "-0.5", "odds": 2.50},
                    {"selection": "Away", "line": "+0.5", "odds": 1.10},
                    {"selection": "Home", "line": "-1.5", "odds": 3.0},
                    {"selection": "Away", "line": "+1.5", "odds": 1.40}
                ]
            }
        }
        match_main_changed = dataclasses.replace(
            match,
            markets_json=json.dumps(current_markets_main_changed)
        )

        # 1.95 -> 1.10 = caída del 43.6% en la línea principal: alerta de posible bug.
        alert2 = evaluate_subscription_odds_change(
            repository,
            subscription,
            tracked_league,
            match_main_changed,
            confirmation_refreshes=1,
            fast_path_percent=40.0,
        )

        self.assertIsNotNone(alert2)
        self.assertGreaterEqual(alert2.max_percent_change, 40.0)
        for detail in alert2.change_details:
            self.assertIn(detail.line, ("-0.5", "+0.5"))
            self.assertNotIn(detail.line, ("-1.5", "+1.5"))
            self.assertLess(detail.after, detail.before)


class OddsChangeFastPathTests(unittest.TestCase):
    """Fast-path: un salto grande (tipo gol) alerta en el 1er refresh sin esperar
    la confirmación de 2 ciclos; los movimientos normales siguen esperando."""

    def _evaluate(self, *, home_after: float, confirmation_refreshes: int, fast_path_percent):
        repository = MagicMock()
        subscription = CompetitionSubscription(
            telegram_chat_id=123, tracked_competition_id=1,
            notify_new_events=True, notify_odds_changes=True,
            change_percent_threshold=10.0, enabled=True,
            created_at="...", updated_at="...",
        )
        tracked_league = TrackedCompetition(
            id=1, platform="1xbet_http", source_url="http://x",
            competition_external_id="123", competition_name="Test League",
            metadata_json=None, needs_name_resolution=False, enabled=True,
            last_synced_at=None, consecutive_unavailable_refreshes=0,
            last_unavailable_refresh_at=None, last_unavailable_reason=None,
            last_unavailable_notification_at=None, created_at="...", updated_at="...",
        )
        baseline_markets = {"1x2": {"home": 2.0, "draw": 3.0, "away": 3.0}}
        baseline = EventBaseline(
            telegram_chat_id=123, active_event_id=1, tracked_competition_id=1,
            external_event_id="match_1", baseline_home=2.0, baseline_draw=3.0,
            baseline_away=3.0, baseline_markets_json=json.dumps(baseline_markets),
            baseline_set_at="...", updated_at="...",
        )
        repository.get_event_baseline.return_value = baseline
        current_markets = {"1x2": {"home": home_after, "draw": 3.0, "away": 3.0}}
        match = ActiveEventRecord(
            id=1, tracked_competition_id=1, platform="1xbet_http",
            competition_external_id="123", external_event_id="match_1",
            home="Home", away="Away", scheduled_label_date="2026-06-03",
            scheduled_label_time="12:00", scheduled_at="2026-06-03T15:00:00+00:00",
            event_url="...", odds_home=home_after, odds_draw=3.0, odds_away=3.0,
            markets_json=json.dumps(current_markets), raw_payload_json=None,
            alerted=False, is_active=True, first_seen_at="...", last_seen_at="...",
            created_at="...", updated_at="...",
        )
        return evaluate_subscription_odds_change(
            repository, subscription, tracked_league, match,
            confirmation_refreshes=confirmation_refreshes,
            fast_path_percent=fast_path_percent,
        )

    def test_big_drop_alerts_on_first_sighting_with_fast_path(self) -> None:
        # 2.0 -> 1.0 = -50%, por encima del umbral fast-path (40%): posible bug.
        alert = self._evaluate(home_after=1.0, confirmation_refreshes=2, fast_path_percent=40.0)
        self.assertIsNotNone(alert)
        self.assertGreaterEqual(alert.max_percent_change, 40.0)
        self.assertEqual(alert.alert_kind, "bug_drop")

    def test_big_drop_still_waits_without_fast_path(self) -> None:
        # Sin fast-path, la misma caída espera la 2da confirmación (1er sighting -> None).
        alert = self._evaluate(home_after=1.0, confirmation_refreshes=2, fast_path_percent=None)
        self.assertIsNone(alert)

    def test_small_move_below_threshold_still_waits(self) -> None:
        # 2.0 -> 2.4 = +20%, debajo del fast-path (40%): sigue esperando confirmación.
        alert = self._evaluate(home_after=2.4, confirmation_refreshes=2, fast_path_percent=40.0)
        self.assertIsNone(alert)

    def test_big_rise_never_alerts(self) -> None:
        # 2.0 -> 4.0 = +100%: las subas son ruido, ni con fast-path ni confirmadas.
        alert = self._evaluate(home_after=4.0, confirmation_refreshes=1, fast_path_percent=40.0)
        self.assertIsNone(alert)


class SustainedDropPolicyTests(unittest.TestCase):
    """Política anti-ruido: solo alertan caídas sostenidas o caídas bruscas (bug).

    Un reprice único (aunque supere el umbral del chat) y cualquier suba se
    absorben en silencio.
    """

    def setUp(self) -> None:
        self.repository = MagicMock()
        self.subscription = CompetitionSubscription(
            telegram_chat_id=123, tracked_competition_id=1,
            notify_new_events=True, notify_odds_changes=True,
            change_percent_threshold=10.0, enabled=True,
            created_at="...", updated_at="...",
        )
        self.tracked_league = TrackedCompetition(
            id=1, platform="1xbet_http", source_url="http://x",
            competition_external_id="123", competition_name="Test League",
            metadata_json=None, needs_name_resolution=False, enabled=True,
            last_synced_at=None, consecutive_unavailable_refreshes=0,
            last_unavailable_refresh_at=None, last_unavailable_reason=None,
            last_unavailable_notification_at=None, created_at="...", updated_at="...",
        )
        self.baseline_odds = {"home": 1.34, "draw": 5.50, "away": 6.13}
        self.baseline = self._build_baseline(json.dumps({"1x2": self.baseline_odds}))
        self.repository.get_event_baseline.return_value = self.baseline

    def _build_baseline(self, markets_json: str | None) -> EventBaseline:
        return EventBaseline(
            telegram_chat_id=123, active_event_id=1, tracked_competition_id=1,
            external_event_id="match_1",
            baseline_home=self.baseline_odds["home"],
            baseline_draw=self.baseline_odds["draw"],
            baseline_away=self.baseline_odds["away"],
            baseline_markets_json=markets_json,
            baseline_set_at="...", updated_at="...",
        )

    def _build_match(self, *, home: float, draw: float, away: float) -> ActiveEventRecord:
        markets = {"1x2": {"home": home, "draw": draw, "away": away}}
        return ActiveEventRecord(
            id=1, tracked_competition_id=1, platform="1xbet_http",
            competition_external_id="123", external_event_id="match_1",
            home="Blackbird", away="Komeetat", scheduled_label_date="2026-07-22",
            scheduled_label_time="18:00", scheduled_at="2026-07-22T15:00:00+00:00",
            event_url="...", odds_home=home, odds_draw=draw, odds_away=away,
            markets_json=json.dumps(markets), raw_payload_json=None,
            alerted=False, is_active=True, first_seen_at="...", last_seen_at="...",
            created_at="...", updated_at="...",
        )

    def _evaluate(self, match: ActiveEventRecord):
        return evaluate_subscription_odds_change(
            self.repository, self.subscription, self.tracked_league, match,
            confirmation_refreshes=1,
            fast_path_percent=40.0,
        )

    def _advance_baseline_from_last_upsert(self) -> None:
        """Simula la persistencia: el próximo get_event_baseline devuelve el meta guardado."""
        call = self.repository.upsert_event_baseline.call_args
        self.repository.get_event_baseline.return_value = self._build_baseline(
            call.kwargs["baseline_markets_json"]
        )

    def test_single_reprice_drop_does_not_alert(self) -> None:
        # El caso reportado como ruido: 2 cae 6.13 -> 4.38 (-28.5%) en un solo paso.
        alert = self._evaluate(self._build_match(home=1.50, draw=5.10, away=4.38))
        self.assertIsNone(alert)

    def test_sustained_drop_alerts_with_cumulative_percent(self) -> None:
        # Paso 1: 6.13 -> 5.50 (-10.3%). Primera caída: todavía no alerta.
        alert = self._evaluate(self._build_match(home=1.34, draw=5.50, away=5.50))
        self.assertIsNone(alert)
        self._advance_baseline_from_last_upsert()

        # Paso 2: 5.50 -> 4.90. Segunda caída consecutiva: alerta con el acumulado.
        alert = self._evaluate(self._build_match(home=1.34, draw=5.50, away=4.90))
        self.assertIsNotNone(alert)
        self.assertEqual(alert.alert_kind, "sustained_drop")
        self.assertAlmostEqual(alert.max_percent_change, (6.13 - 4.90) / 6.13 * 100, places=1)
        detail = alert.change_details[0]
        self.assertEqual(detail.selection, "2")
        self.assertAlmostEqual(detail.before, 6.13)
        self.assertAlmostEqual(detail.after, 4.90)

    def test_rebound_resets_streak(self) -> None:
        # Cae, rebota y vuelve a caer: el rebote mata la racha, así que la
        # caída posterior vuelve a contar como primera y no alerta.
        alert = self._evaluate(self._build_match(home=1.34, draw=5.50, away=5.50))
        self.assertIsNone(alert)
        self._advance_baseline_from_last_upsert()

        alert = self._evaluate(self._build_match(home=1.34, draw=5.50, away=6.00))
        self.assertIsNone(alert)
        self._advance_baseline_from_last_upsert()

        alert = self._evaluate(self._build_match(home=1.34, draw=5.50, away=5.40))
        self.assertIsNone(alert)


if __name__ == "__main__":
    unittest.main()

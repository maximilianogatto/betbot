import dataclasses
import json
import unittest
from unittest.mock import MagicMock

from monitors.change_detection import evaluate_subscription_odds_change, find_main_line_selections
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
                    {"selection": "Away", "line": "+0.5", "odds": 1.60},
                    {"selection": "Home", "line": "-1.5", "odds": 3.0},
                    {"selection": "Away", "line": "+1.5", "odds": 1.40}
                ]
            }
        }
        match_main_changed = dataclasses.replace(
            match,
            markets_json=json.dumps(current_markets_main_changed)
        )
        
        alert2 = evaluate_subscription_odds_change(
            repository,
            subscription,
            tracked_league,
            match_main_changed,
            confirmation_refreshes=1
        )
        
        self.assertIsNotNone(alert2)
        self.assertGreaterEqual(alert2.max_percent_change, 10.0)
        for detail in alert2.change_details:
            self.assertIn(detail.line, ("-0.5", "+0.5"))
            self.assertNotIn(detail.line, ("-1.5", "+1.5"))


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

    def test_big_move_alerts_on_first_sighting_with_fast_path(self) -> None:
        # 2.0 -> 4.0 = +100%, por encima del umbral fast-path (40%).
        alert = self._evaluate(home_after=4.0, confirmation_refreshes=2, fast_path_percent=40.0)
        self.assertIsNotNone(alert)
        self.assertGreaterEqual(alert.max_percent_change, 40.0)

    def test_big_move_still_waits_without_fast_path(self) -> None:
        # Sin fast-path, el mismo salto espera la 2da confirmación (1er sighting -> None).
        alert = self._evaluate(home_after=4.0, confirmation_refreshes=2, fast_path_percent=None)
        self.assertIsNone(alert)

    def test_small_move_below_threshold_still_waits(self) -> None:
        # 2.0 -> 2.4 = +20%, debajo del fast-path (40%): sigue esperando confirmación.
        alert = self._evaluate(home_after=2.4, confirmation_refreshes=2, fast_path_percent=40.0)
        self.assertIsNone(alert)


if __name__ == "__main__":
    unittest.main()

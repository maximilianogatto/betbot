"""El camino nuevo: decidir en services, publicar al bus, confirmar si llegó.

Espeja la red de `test_notifications_behaviour.py` sobre la separación nueva. Lo
que no se puede perder es que el `commit` (marcar enviado / mover baseline)
ocurre SÓLO si la entrega salió bien.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from core.event_bus import EventBus
from core.events import MatchRemindersEvent, NewMatchesEvent, OddsChangedEvent
from core.listener import EventListener
from core.models import (
    ActiveEventRecord,
    CompetitionSubscription,
    EventBaseline,
    SubscriptionOddsAlert,
    TrackedCompetition,
)
from services.models import CompetitionRefreshResult, OddsChange
from services.notifications import NotificationService, dispatch_refresh_notifications


def _league() -> TrackedCompetition:
    return TrackedCompetition(
        id=1, platform="betovo_http", source_url="http://x",
        competition_external_id="c1", competition_name="Liga Test",
        metadata_json=None, needs_name_resolution=False, enabled=True,
        last_synced_at=None, consecutive_unavailable_refreshes=0,
        last_unavailable_refresh_at=None, last_unavailable_reason=None,
        last_unavailable_notification_at=None, created_at="t", updated_at="t",
    )


def _match(fixture_id: str = "m1", **overrides) -> ActiveEventRecord:
    payload = dict(
        id=1, tracked_competition_id=1, platform="betovo_http",
        competition_external_id="c1", external_event_id=fixture_id,
        home="Local", away="Visita",
        scheduled_label_date="2026-08-10", scheduled_label_time="12:00",
        scheduled_at="2026-08-10T15:00:00+00:00", event_url="http://e",
        odds_home=2.0, odds_draw=3.0, odds_away=3.5,
        markets_json=json.dumps({"1x2": {"home": 2.0, "draw": 3.0, "away": 3.5}}),
        raw_payload_json=None, alerted=False, is_active=True,
        first_seen_at="t", last_seen_at="t", created_at="t", updated_at="t",
    )
    payload.update(overrides)
    return ActiveEventRecord(**payload)


def _subscription(**overrides) -> CompetitionSubscription:
    payload = dict(
        telegram_chat_id=123, tracked_competition_id=1,
        notify_new_events=True, notify_odds_changes=True,
        change_percent_threshold=10.0, enabled=True,
        created_at="t", updated_at="t",
    )
    payload.update(overrides)
    return CompetitionSubscription(**payload)


def _result(**overrides) -> CompetitionRefreshResult:
    payload = dict(
        tracked_league=_league(), active_matches=[], new_matches=[],
        odds_changes=[], reminder_matches=[],
        removed_missing_count=0, removed_past_count=0,
    )
    payload.update(overrides)
    return CompetitionRefreshResult(**payload)


def _alert(match: ActiveEventRecord) -> SubscriptionOddsAlert:
    baseline = EventBaseline(
        telegram_chat_id=123, active_event_id=1, tracked_competition_id=1,
        external_event_id=match.external_event_id,
        baseline_home=2.0, baseline_draw=3.0, baseline_away=3.5,
        baseline_markets_json=match.markets_json,
        baseline_set_at="t", updated_at="t",
    )
    return SubscriptionOddsAlert(
        match=match, baseline=baseline, max_percent_change=100.0,
        change_details=(), changed_market_types=("1x2",),
    )


class _Collector(EventListener):
    def __init__(self) -> None:
        self.seen: list[object] = []

    async def handle(self, event: object) -> None:
        self.seen.append(event)


class _Failing(EventListener):
    async def handle(self, event: object) -> None:
        raise RuntimeError("telegram caído")


class DecisionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.repo = MagicMock()
        self.repo.get_subscriptions_for_competition.return_value = [_subscription()]
        self.repo.has_sent_alert.return_value = False
        self.service = NotificationService(self.repo)

    async def test_new_matches_produce_one_event_for_the_subscriber(self) -> None:
        decisions = await self.service.decide_for_refresh_result(
            _result(new_matches=[_match("m1"), _match("m2")])
        )

        self.assertEqual(len(decisions), 1)
        self.assertIsInstance(decisions[0].event, NewMatchesEvent)
        self.assertEqual(decisions[0].event.chat_id, 123)
        self.assertEqual(decisions[0].mark_sent_fixture_ids, ("m1", "m2"))

    async def test_deciding_writes_nothing(self) -> None:
        """Decidir es sólo leer: nada se marca hasta que el aviso llegue."""

        await self.service.decide_for_refresh_result(_result(new_matches=[_match()]))

        self.repo.mark_sent_alerts.assert_not_called()
        self.repo.upsert_event_baseline.assert_not_called()
        self.repo.mark_events_alerted.assert_not_called()

    async def test_an_already_sent_match_produces_no_decision(self) -> None:
        self.repo.has_sent_alert.return_value = True

        decisions = await self.service.decide_for_refresh_result(
            _result(new_matches=[_match()])
        )

        self.assertEqual(decisions, [])

    async def test_a_subscriber_with_new_matches_off_gets_no_decision(self) -> None:
        self.repo.get_subscriptions_for_competition.return_value = [
            _subscription(notify_new_events=False)
        ]

        decisions = await self.service.decide_for_refresh_result(
            _result(new_matches=[_match()])
        )

        self.assertEqual(decisions, [])

    async def test_without_subscribers_nothing_is_decided_or_read(self) -> None:
        self.repo.get_subscriptions_for_competition.return_value = []

        decisions = await self.service.decide_for_refresh_result(
            _result(new_matches=[_match()])
        )

        self.assertEqual(decisions, [])
        self.repo.initialize_event_baselines.assert_not_called()

    async def test_odds_changes_carry_the_evaluated_alerts(self) -> None:
        change = OddsChange(before=_match(), after=_match(odds_home=4.0))

        with patch(
            "services.notifications.evaluate_subscription_odds_change",
            return_value=_alert(change.after),
        ):
            decisions = await self.service.decide_for_refresh_result(
                _result(odds_changes=[change])
            )

        self.assertEqual(len(decisions), 1)
        self.assertIsInstance(decisions[0].event, OddsChangedEvent)
        self.assertEqual(len(decisions[0].event.alerts), 1)

    async def test_a_change_that_is_not_alert_worthy_produces_no_decision(self) -> None:
        change = OddsChange(before=_match(), after=_match(odds_home=2.05))

        with patch(
            "services.notifications.evaluate_subscription_odds_change",
            return_value=None,
        ):
            decisions = await self.service.decide_for_refresh_result(
                _result(odds_changes=[change])
            )

        self.assertEqual(decisions, [])

    async def test_a_subscriber_with_odds_off_gets_no_decision(self) -> None:
        self.repo.get_subscriptions_for_competition.return_value = [
            _subscription(notify_odds_changes=False)
        ]
        change = OddsChange(before=_match(), after=_match(odds_home=4.0))

        with patch(
            "services.notifications.evaluate_subscription_odds_change",
            return_value=_alert(change.after),
        ):
            decisions = await self.service.decide_for_refresh_result(
                _result(odds_changes=[change])
            )

        self.assertEqual(decisions, [])


class DeliveryAndCommitTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.repo = MagicMock()
        self.repo.get_subscriptions_for_competition.return_value = [_subscription()]
        self.repo.has_sent_alert.return_value = False
        self.service = NotificationService(self.repo)
        self.bus = EventBus()

    def _summary(self, result) -> SimpleNamespace:
        return SimpleNamespace(league_results=[result])

    async def test_a_delivered_alert_is_marked_as_sent(self) -> None:
        listener = _Collector()
        self.bus.subscribe(NewMatchesEvent, listener.handle)

        delivered = await dispatch_refresh_notifications(
            self.service, self._summary(_result(new_matches=[_match()])), self.bus
        )

        self.assertEqual(delivered, 1)
        self.assertEqual(len(listener.seen), 1)
        self.repo.mark_sent_alerts.assert_called_once()

    async def test_a_failed_delivery_is_not_marked_so_it_retries(self) -> None:
        """La garantía de entrega al menos una vez, en el camino nuevo."""

        self.bus.subscribe(NewMatchesEvent, _Failing().handle)

        with self.assertLogs("core.event_bus", level="ERROR"):
            delivered = await dispatch_refresh_notifications(
                self.service, self._summary(_result(new_matches=[_match()])), self.bus
            )

        self.assertEqual(delivered, 0)
        self.repo.mark_sent_alerts.assert_not_called()

    async def test_without_any_listener_nothing_is_marked(self) -> None:
        """Si nadie está suscrito el aviso no llegó: no se puede dar por enviado."""

        delivered = await dispatch_refresh_notifications(
            self.service, self._summary(_result(new_matches=[_match()])), self.bus
        )

        self.assertEqual(delivered, 0)
        self.repo.mark_sent_alerts.assert_not_called()

    async def test_a_delivered_odds_alert_moves_the_baseline(self) -> None:
        self.bus.subscribe(OddsChangedEvent, _Collector().handle)
        change = OddsChange(before=_match(), after=_match(odds_home=4.0))

        with patch(
            "services.notifications.evaluate_subscription_odds_change",
            return_value=_alert(change.after),
        ):
            await dispatch_refresh_notifications(
                self.service, self._summary(_result(odds_changes=[change])), self.bus
            )

        self.repo.upsert_event_baseline.assert_called_once()

    async def test_reminders_are_marked_after_delivery(self) -> None:
        self.bus.subscribe(MatchRemindersEvent, _Collector().handle)

        await dispatch_refresh_notifications(
            self.service, self._summary(_result(reminder_matches=[_match()])), self.bus
        )

        self.repo.mark_events_alerted.assert_called_once()

    async def test_one_broken_league_does_not_stop_the_others(self) -> None:
        self.bus.subscribe(NewMatchesEvent, _Collector().handle)
        good = _result(new_matches=[_match()])
        summary = SimpleNamespace(league_results=[good, good])

        original = self.service.decide_for_refresh_result
        calls = {"n": 0}

        async def _flaky(result):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("liga rota")
            return await original(result)

        self.service.decide_for_refresh_result = _flaky

        with self.assertLogs("services.notifications", level="ERROR"):
            delivered = await dispatch_refresh_notifications(self.service, summary, self.bus)

        self.assertEqual(delivered, 1)


if __name__ == "__main__":
    unittest.main()

"""Caracterización de la ruta de notificaciones de tracking.

Fija el comportamiento observable ANTES de moverlo al EventBus: qué se manda,
qué se marca en la base y —lo más importante— en qué orden. La regla que no se
puede perder es "mandar y recién después marcar": si se marcara primero, un
envío fallido dejaría el aviso como enviado y el usuario nunca se enteraría.

Esta ruta ya tuvo una caída silenciosa de 9 días en producción; el refactor va
contra estos tests.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.models import (
    ActiveEventRecord,
    CompetitionSubscription,
    EventBaseline,
    TrackedCompetition,
)
from interfaces.telegram.notifications import notify_for_refresh_result
from services.models import CompetitionRefreshResult, OddsChange, SubscriptionOddsAlert


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


class NewMatchNotificationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bot = SimpleNamespace(send_message=AsyncMock())
        self.repo = MagicMock()
        self.repo.get_subscriptions_for_competition.return_value = [_subscription()]
        self.repo.has_sent_alert.return_value = False

    async def test_sends_new_match_and_only_then_marks_it_as_sent(self) -> None:
        """El marcado va DESPUÉS del envío: si falla el envío, se reintenta."""

        order: list[str] = []
        self.bot.send_message = AsyncMock(side_effect=lambda **kw: order.append("send"))
        self.repo.mark_sent_alerts.side_effect = lambda *a, **k: order.append("mark")

        await notify_for_refresh_result(self.bot, _result(new_matches=[_match()]), self.repo)

        self.assertEqual(order, ["send", "mark"])
        self.repo.mark_sent_alerts.assert_called_once()
        marked_ids = self.repo.mark_sent_alerts.call_args.args[2]
        self.assertEqual(marked_ids, ["m1"])

    async def test_an_already_sent_match_is_not_sent_again(self) -> None:
        self.repo.has_sent_alert.return_value = True

        await notify_for_refresh_result(self.bot, _result(new_matches=[_match()]), self.repo)

        self.bot.send_message.assert_not_awaited()
        self.repo.mark_sent_alerts.assert_not_called()

    async def test_several_new_matches_go_in_a_single_grouped_message(self) -> None:
        matches = [_match("m1"), _match("m2"), _match("m3")]

        await notify_for_refresh_result(self.bot, _result(new_matches=matches), self.repo)

        self.assertEqual(self.bot.send_message.await_count, 1)
        self.assertEqual(self.repo.mark_sent_alerts.call_args.args[2], ["m1", "m2", "m3"])

    async def test_a_subscriber_who_disabled_new_matches_gets_nothing(self) -> None:
        self.repo.get_subscriptions_for_competition.return_value = [
            _subscription(notify_new_events=False)
        ]

        await notify_for_refresh_result(self.bot, _result(new_matches=[_match()]), self.repo)

        self.bot.send_message.assert_not_awaited()

    async def test_without_subscribers_nothing_is_sent_or_read(self) -> None:
        self.repo.get_subscriptions_for_competition.return_value = []

        await notify_for_refresh_result(self.bot, _result(new_matches=[_match()]), self.repo)

        self.bot.send_message.assert_not_awaited()
        self.repo.initialize_event_baselines.assert_not_called()


class OddsChangeNotificationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bot = SimpleNamespace(send_message=AsyncMock())
        self.repo = MagicMock()
        self.repo.get_subscriptions_for_competition.return_value = [_subscription()]
        self.repo.has_sent_alert.return_value = False

    async def test_an_alert_is_sent_and_the_baseline_moves_to_the_new_price(self) -> None:
        change = OddsChange(before=_match(), after=_match(odds_home=4.0))
        with patch(
            "interfaces.telegram.notifications.evaluate_subscription_odds_change",
            return_value=_alert(change.after),
        ):
            await notify_for_refresh_result(self.bot, _result(odds_changes=[change]), self.repo)

        self.bot.send_message.assert_awaited()
        # Sin mover el baseline, el mismo movimiento volvería a alertar en cada ciclo.
        self.repo.upsert_event_baseline.assert_called_once()

    async def test_when_the_change_is_not_alert_worthy_nothing_is_sent(self) -> None:
        change = OddsChange(before=_match(), after=_match(odds_home=2.05))

        with patch(
            "interfaces.telegram.notifications.evaluate_subscription_odds_change",
            return_value=None,
        ):
            await notify_for_refresh_result(self.bot, _result(odds_changes=[change]), self.repo)

        self.bot.send_message.assert_not_awaited()
        self.repo.upsert_event_baseline.assert_not_called()

    async def test_a_subscriber_who_disabled_odds_gets_nothing(self) -> None:
        self.repo.get_subscriptions_for_competition.return_value = [
            _subscription(notify_odds_changes=False)
        ]
        change = OddsChange(before=_match(), after=_match(odds_home=4.0))
        with patch(
            "interfaces.telegram.notifications.evaluate_subscription_odds_change",
            return_value=_alert(change.after),
        ):
            await notify_for_refresh_result(self.bot, _result(odds_changes=[change]), self.repo)

        self.bot.send_message.assert_not_awaited()


class ReminderAndTimezoneTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bot = SimpleNamespace(send_message=AsyncMock())
        self.repo = MagicMock()
        self.repo.get_subscriptions_for_competition.return_value = [_subscription()]
        self.repo.has_sent_alert.return_value = False

    async def test_reminders_are_sent_and_marked(self) -> None:
        await notify_for_refresh_result(
            self.bot, _result(reminder_matches=[_match()]), self.repo
        )

        self.bot.send_message.assert_awaited()
        self.repo.mark_events_alerted.assert_called_once()

    async def test_the_display_timezone_does_not_leak_after_the_dispatch(self) -> None:
        """Cada suscriptor se renderiza en SU zona; al terminar se limpia.

        Si quedara seteada, el siguiente trabajo de esta task mostraría horarios
        en la zona del último suscriptor.
        """

        with patch("interfaces.telegram.notifications.set_display_timezone") as tz_mock:
            await notify_for_refresh_result(
                self.bot, _result(new_matches=[_match()]), self.repo
            )

        self.assertIsNone(tz_mock.call_args_list[-1].args[0])


if __name__ == "__main__":
    unittest.main()

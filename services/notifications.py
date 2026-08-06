"""Decide a quién avisarle y de qué, sin saber que Telegram existe.

Separa dos cosas que estaban pegadas en `interfaces/telegram/notifications.py`:

* **decidir** (acá): a qué chats les corresponde un aviso, evaluando baselines,
  confirmaciones y deduplicación. Es lógica de dominio y necesita el repositorio.
* **redactar y mandar**: del listener de la interfaz.

Entre las dos va el EventBus, y el orden importa: se decide, se publica, y
**recién si la entrega salió bien** se persiste (`commit`). Marcar antes de
mandar rompería la garantía de entrega al menos una vez — un envío fallido
quedaría registrado como enviado y el usuario nunca se enteraría.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
from typing import Any

from core.events import MatchRemindersEvent, NewMatchesEvent, OddsChangedEvent
from core.models import ActiveEventRecord, SubscriptionOddsAlert
from services.change_detection import evaluate_subscription_odds_change
from services.models import CompetitionRefreshResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotificationDecision:
    """Un aviso resuelto: qué publicar y qué persistir si la entrega sale bien.

    Lo que hay que grabar se guarda como datos y no como callback, para que la
    decisión siga siendo inspeccionable y testeable sin ejecutarla.
    """

    event: Any
    mark_sent_fixture_ids: tuple[str, ...] = ()
    baseline_updates: tuple[SubscriptionOddsAlert, ...] = ()
    mark_reminders_fixture_ids: tuple[str, ...] = ()


class NotificationService:
    """Traduce el resultado de un refresh en avisos por chat."""

    def __init__(
        self,
        repository: Any,
        *,
        odds_change_confirmation_refreshes: int = 1,
        odds_flap_window_minutes: int = 15,
        odds_flap_epsilon: float = 0.05,
        odds_fast_path_percent: float = 15.0,
    ) -> None:
        self.repository = repository
        self._confirmation_refreshes = odds_change_confirmation_refreshes
        self._flap_window_minutes = odds_flap_window_minutes
        self._flap_epsilon = odds_flap_epsilon
        self._fast_path_percent = odds_fast_path_percent

    async def decide_for_refresh_result(
        self, result: CompetitionRefreshResult
    ) -> list[NotificationDecision]:
        """Resuelve todos los avisos que dispara el refresh de una liga.

        Sólo lee: no marca ni mueve baselines. Eso es de `commit`.
        """

        subscriptions = await asyncio.to_thread(
            self.repository.get_subscriptions_for_competition,
            result.tracked_league.id,
            only_enabled=True,
        )
        if not subscriptions:
            return []

        decisions: list[NotificationDecision] = []
        for subscription in subscriptions:
            chat_id = subscription.telegram_chat_id
            await asyncio.to_thread(
                self.repository.initialize_event_baselines,
                chat_id,
                result.tracked_league.id,
                result.active_matches,
            )

            if subscription.notify_new_matches:
                decision = await self._decide_new_matches(result, chat_id)
                if decision is not None:
                    decisions.append(decision)

            odds_decision = await self._decide_odds_changes(result, subscription)
            if odds_decision is not None:
                decisions.append(odds_decision)

            if result.reminder_matches:
                decisions.append(
                    NotificationDecision(
                        event=MatchRemindersEvent(
                            chat_id=chat_id,
                            tracked_league=result.tracked_league,
                            matches=tuple(result.reminder_matches),
                        ),
                        mark_reminders_fixture_ids=tuple(
                            m.fixture_id for m in result.reminder_matches
                        ),
                    )
                )

        return decisions

    async def _decide_new_matches(
        self, result: CompetitionRefreshResult, chat_id: int
    ) -> NotificationDecision | None:
        if not result.new_matches:
            return None

        def _unsent() -> list[ActiveEventRecord]:
            return [
                match
                for match in result.new_matches
                if not self.repository.has_sent_alert(
                    chat_id, result.tracked_league.id, match.fixture_id, "new_event"
                )
            ]

        unsent = await asyncio.to_thread(_unsent)
        if not unsent:
            return None

        return NotificationDecision(
            event=NewMatchesEvent(
                chat_id=chat_id,
                tracked_league=result.tracked_league,
                matches=tuple(unsent),
            ),
            mark_sent_fixture_ids=tuple(m.fixture_id for m in unsent),
        )

    async def _decide_odds_changes(
        self, result: CompetitionRefreshResult, subscription: Any
    ) -> NotificationDecision | None:
        if not result.odds_changes or not subscription.notify_odds_changes:
            return None

        alerts: list[SubscriptionOddsAlert] = []
        for change in result.odds_changes:
            alert = await asyncio.to_thread(
                evaluate_subscription_odds_change,
                self.repository,
                subscription,
                result.tracked_league,
                change.after,
                confirmation_refreshes=self._confirmation_refreshes,
                flap_window_minutes=self._flap_window_minutes,
                flap_epsilon=self._flap_epsilon,
                fast_path_percent=self._fast_path_percent,
            )
            if alert is not None:
                alerts.append(alert)

        if not alerts:
            return None

        return NotificationDecision(
            event=OddsChangedEvent(
                chat_id=subscription.telegram_chat_id,
                tracked_league=result.tracked_league,
                alerts=tuple(alerts),
            ),
            baseline_updates=tuple(alerts),
        )

    async def commit(self, decision: NotificationDecision) -> None:
        """Persiste lo que una entrega exitosa confirma.

        Se llama SÓLO después de que el aviso llegó. Si el envío falló no se
        marca nada, y el próximo ciclo lo reintenta.
        """

        event = decision.event
        league_id = event.tracked_league.id
        chat_id = event.chat_id

        if decision.mark_sent_fixture_ids:
            await asyncio.to_thread(
                self.repository.mark_sent_alerts,
                chat_id,
                league_id,
                list(decision.mark_sent_fixture_ids),
                "new_event",
            )

        if decision.baseline_updates:
            await asyncio.to_thread(
                self._move_baselines, chat_id, league_id, decision.baseline_updates
            )

        if decision.mark_reminders_fixture_ids:
            await asyncio.to_thread(
                self.repository.mark_events_alerted,
                league_id,
                list(decision.mark_reminders_fixture_ids),
            )

    def _move_baselines(
        self, chat_id: int, league_id: int, alerts: tuple[SubscriptionOddsAlert, ...]
    ) -> None:
        """Mueve el baseline al precio que se acaba de avisar.

        Sin esto, el mismo movimiento volvería a superar el umbral en cada ciclo
        y el chat recibiría el mismo aviso para siempre.
        """

        for alert in alerts:
            self.repository.upsert_event_baseline(
                chat_id,
                league_id,
                alert.match.fixture_id,
                baseline_home=alert.match.odds_home,
                baseline_draw=alert.match.odds_draw,
                baseline_away=alert.match.odds_away,
                baseline_markets_json=(
                    alert.match.markets_json
                    if alert.confirmed_baseline_markets_payload is None
                    else json.dumps(
                        alert.confirmed_baseline_markets_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                ),
            )
            self.repository.resolve_small_change_with_current_baseline(
                chat_id, league_id, alert.match.fixture_id
            )


async def dispatch_refresh_notifications(
    service: NotificationService,
    summary: Any,
    bus: Any,
) -> int:
    """Decide → publica → confirma, para todas las ligas de un refresh.

    Devuelve cuántos avisos se entregaron. Un aviso que no llegó a ningún
    listener NO se confirma: queda pendiente y el próximo ciclo lo reintenta.
    """

    delivered_total = 0
    for result in summary.league_results:
        try:
            decisions = await service.decide_for_refresh_result(result)
        except Exception:
            # Una liga que falla no puede tumbar los avisos de las demás.
            logger.exception(
                "No pude resolver los avisos de la liga id=%s",
                getattr(result.tracked_league, "id", "?"),
            )
            continue

        for decision in decisions:
            delivery = await bus.publish(decision.event)
            if delivery.delivered:
                await service.commit(decision)
                delivered_total += 1
            else:
                logger.warning(
                    "Aviso %s para el chat %s no se entregó (fallos=%s); no se marca y se reintenta.",
                    type(decision.event).__name__,
                    decision.event.chat_id,
                    delivery.failed,
                )
    return delivered_total

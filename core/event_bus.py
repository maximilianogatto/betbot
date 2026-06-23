"""Asynchronous in-memory event bus to decouple the Core from Telegram and CLI."""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine, Type

logger = logging.getLogger(__name__)

class EventBus:
    """Publish-subscribe event bus for dispatching domain events asynchronously."""

    def __init__(self) -> None:
        self._listeners: dict[Type[Any], list[Callable[[Any], Coroutine[Any, Any, None]]]] = {}

    def subscribe(
        self,
        event_type: Type[Any],
        callback: Callable[[Any], Coroutine[Any, Any, None]],
    ) -> None:
        """Subscribe a listener callback to a specific event type."""
        self._listeners.setdefault(event_type, []).append(callback)
        logger.debug("Subscribed %s to event %s", callback.__name__, event_type.__name__)

    def unsubscribe(
        self,
        event_type: Type[Any],
        callback: Callable[[Any], Coroutine[Any, Any, None]],
    ) -> None:
        """Unsubscribe a listener callback from a specific event type."""
        if event_type in self._listeners:
            self._listeners[event_type] = [
                cb for cb in self._listeners[event_type] if cb != callback
            ]
            logger.debug("Unsubscribed %s from event %s", callback.__name__, event_type.__name__)

    async def publish(self, event: Any) -> None:
        """Publish an event asynchronously to all subscribed listeners."""
        event_type = type(event)
        listeners = self._listeners.get(event_type, [])
        if not listeners:
            logger.debug("No listeners registered for event %s", event_type.__name__)
            return

        logger.debug("Publishing event %s to %d listeners", event_type.__name__, len(listeners))
        for callback in listeners:
            try:
                await callback(event)
            except Exception as e:
                logger.error(
                    "Error executing callback %s for event %s: %s",
                    getattr(callback, "__name__", "anonymous"),
                    event_type.__name__,
                    e,
                    exc_info=True,
                )

# Global shared instance of the EventBus
event_bus = EventBus()

__all__ = ["EventBus", "event_bus"]

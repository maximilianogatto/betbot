from __future__ import annotations

from typing import Protocol, Any

class EventListener(Protocol):
    """Port defining a subscriber to the core EventBus."""

    async def on_event(self, event: Any) -> None:
        """Handle a dispatched domain event reactively (e.g. format and push notification)."""
        ...

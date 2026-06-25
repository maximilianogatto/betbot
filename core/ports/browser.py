from __future__ import annotations

from typing import Protocol, Any, AsyncIterator

class BrowserPort(Protocol):
    """Port defining a persistent browser runtime with limited page concurrency."""

    def acquire_page(self) -> AsyncIterator[Any]:
        """Async context manager to acquire a page from the browser runtime pool."""
        ...

    def request_restart(self, reason: str) -> None:
        """Mark the browser as needing a restart (e.g. on RAM pressure or Akamai blocking)."""
        ...

    @property
    def active_pages(self) -> int:
        """The number of currently leased web pages."""
        ...

    async def start(self) -> None:
        """Initialize the browser context and launch processes."""
        ...

    async def stop(self) -> None:
        """Close all pages and terminate browser processes cleanly."""
        ...

from __future__ import annotations

from typing import Protocol

class ChatSettingsPort(Protocol):
    """Port defining chat preferences storage operations."""

    def get_chat_timezone(self, chat_id: int) -> str | None:
        """Retrieve the configured IANA timezone string for a chat."""
        ...

    def set_chat_timezone(self, chat_id: int, timezone_name: str) -> None:
        """Update or create the IANA timezone configuration for a chat."""
        ...

    def clear_chat_timezone(self, chat_id: int) -> None:
        """Remove the configured timezone, reverting to default."""
        ...

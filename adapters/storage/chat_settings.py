from __future__ import annotations

from datetime import datetime, timezone

from core.ports.chat_settings import ChatSettingsPort
from adapters.storage.connection import open_connection


class SQLiteChatSettingsAdapter(ChatSettingsPort):
    """Adapter implementing ChatSettingsPort using SQLite (chat_settings table)."""

    def get_chat_timezone(self, chat_id: int) -> str | None:
        with open_connection() as conn:
            row = conn.execute(
                "SELECT timezone FROM chat_settings WHERE chat_id = ?",
                (int(chat_id),),
            ).fetchone()
        if row is None:
            return None
        tz = row["timezone"]
        return tz.strip() if isinstance(tz, str) and tz.strip() else None

    def set_chat_timezone(self, chat_id: int, timezone_name: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            conn.execute(
                """
                INSERT INTO chat_settings (chat_id, timezone, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    timezone = excluded.timezone,
                    updated_at = excluded.updated_at
                """,
                (int(chat_id), timezone_name.strip(), now_iso),
            )

    def clear_chat_timezone(self, chat_id: int) -> None:
        # Keep the row but null the timezone → reverting to default. Forward-safe
        # if chat_settings gains more columns later. No-op if the chat has no row.
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            conn.execute(
                "UPDATE chat_settings SET timezone = NULL, updated_at = ? WHERE chat_id = ?",
                (now_iso, int(chat_id)),
            )

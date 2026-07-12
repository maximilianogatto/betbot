"""Per-chat display timezone resolution.

The bot shows kickoff times, alerts and live messages in a *display* timezone.
Historically this was hardcoded to Argentina; now each Telegram chat can pick its
own zone (default Argentina). To avoid threading a ``tz`` argument through the
dozen formatting helpers in :mod:`bot.alerts` (and friends), the active display
timezone is kept in a :class:`~contextvars.ContextVar`. Command handlers and the
broadcast loops set it for the recipient chat right before building a message;
the formatters read it via :func:`current_display_timezone`.

Setting it inside a synchronous message-building block is safe even under
asyncio: each Telegram update is processed in its own context, and the broadcast
loops set/reset the value with :func:`use_timezone` around the build.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from functools import lru_cache
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Fallback default when nothing is configured (env or per-chat).
DEFAULT_TIMEZONE_NAME = "America/Argentina/Buenos_Aires"

# A few friendly suggestions surfaced by the /timezone command.
COMMON_TIMEZONES = (
    "America/Argentina/Buenos_Aires",
    "America/Montevideo",
    "America/Sao_Paulo",
    "America/Santiago",
    "America/Bogota",
    "America/Mexico_City",
    "Europe/Madrid",
    "UTC",
)


def _env_default_name() -> str:
    """Default zone name from env (BOT_DEFAULT_TIMEZONE), else Argentina."""

    return (os.getenv("BOT_DEFAULT_TIMEZONE") or "").strip() or DEFAULT_TIMEZONE_NAME


@lru_cache(maxsize=256)
def _load_zoneinfo(name: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError, KeyError):
        return None


def get_zoneinfo(name: str | None) -> ZoneInfo | None:
    """Return a validated ZoneInfo for ``name`` or ``None`` if invalid/empty."""

    if not name:
        return None
    return _load_zoneinfo(name.strip())


def default_timezone() -> ZoneInfo:
    """The configured default display timezone (env override, else Argentina)."""

    return get_zoneinfo(_env_default_name()) or _load_zoneinfo("UTC")  # type: ignore[return-value]


_display_tz: ContextVar[ZoneInfo | None] = ContextVar("betbot_display_tz", default=None)


def current_display_timezone() -> ZoneInfo:
    """The timezone the current message should be rendered in."""

    return _display_tz.get() or default_timezone()


def set_display_timezone(tz: ZoneInfo | None) -> None:
    """Set the active display timezone for the current context (no reset)."""

    _display_tz.set(tz)


@contextmanager
def use_timezone(tz: ZoneInfo | None):
    """Temporarily set the active display timezone, restoring it on exit."""

    token = _display_tz.set(tz)
    try:
        yield
    finally:
        _display_tz.reset(token)


def resolve_chat_timezone(chat_id: int | None) -> ZoneInfo:
    """Resolve a chat's saved timezone, falling back to the default."""

    if chat_id is None:
        return default_timezone()
    try:
        from adapters.storage import get_storage
        tracking_repository = get_storage()

        name = tracking_repository.get_chat_timezone(chat_id)
    except Exception:
        name = None
    return get_zoneinfo(name) or default_timezone()


def tz_offset_label(tz: ZoneInfo, when: datetime | None = None) -> str:
    """Short offset label for display, e.g. ``UTC-03`` or ``UTC+05:30``."""

    when = when or datetime.now(tz=tz)
    if when.tzinfo is None:
        when = when.replace(tzinfo=tz)
    offset = when.astimezone(tz).utcoffset()
    if offset is None:
        return "UTC"
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    hours, minutes = divmod(total // 60, 60)
    label = f"UTC{sign}{hours:02d}"
    if minutes:
        label += f":{minutes:02d}"
    return label

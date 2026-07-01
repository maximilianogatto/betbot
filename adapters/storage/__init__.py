"""Storage adapters package + `SqliteStorage` facade.

`SqliteStorage` compone los adapters SQLite por agregado en un único objeto que
implementa TODOS los ports de storage. Es el reemplazo drop-in del legacy
`SqliteTrackingRepository` en el composition root (PR2-E2-S9).

Los adapters son *stateless* (sin `__init__`, abren la conexión por método), así
que la composición por herencia múltiple no tiene conflicto de estado: el MRO
reúne todos los métodos (cada adapter aporta los de su agregado, sin solapes).
"""
from __future__ import annotations

from adapters.storage.competitions import SQLiteCompetitionsAdapter
from adapters.storage.events import SQLiteEventsAdapter
from adapters.storage.subscriptions import SQLiteSubscriptionsAdapter
from adapters.storage.baselines import SQLiteBaselinesAdapter
from adapters.storage.stats_links import SQLiteStatsLinksAdapter
from adapters.storage.live_watch import SQLiteLiveWatchAdapter
from adapters.storage.maintenance import SQLiteMaintenanceAdapter
from adapters.storage.chat_settings import SQLiteChatSettingsAdapter


class SqliteStorage(
    SQLiteCompetitionsAdapter,
    SQLiteEventsAdapter,
    SQLiteSubscriptionsAdapter,
    SQLiteBaselinesAdapter,
    SQLiteStatsLinksAdapter,
    SQLiteLiveWatchAdapter,
    SQLiteMaintenanceAdapter,
    SQLiteChatSettingsAdapter,
):
    """Facade: un objeto que implementa todos los ports de storage."""

    pass


__all__ = [
    "SqliteStorage",
    "SQLiteCompetitionsAdapter",
    "SQLiteEventsAdapter",
    "SQLiteSubscriptionsAdapter",
    "SQLiteBaselinesAdapter",
    "SQLiteStatsLinksAdapter",
    "SQLiteLiveWatchAdapter",
    "SQLiteMaintenanceAdapter",
    "SQLiteChatSettingsAdapter",
]

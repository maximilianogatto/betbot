"""Storage adapters package + `SqliteStorage` facade.

`SqliteStorage` compone los adapters SQLite por agregado en un único objeto que
implementa TODOS los ports de storage. Es el reemplazo drop-in del repositorio
SQLite monolítico legacy en el composition root (PR2-E2-S9).

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
# El archivo de cuotas NO integra el facade: es una DB separada (retención
# infinita, fuera del alcance de prune/VACUUM). Se re-exporta para conveniencia.
from adapters.storage.odds_archive import SQLiteOddsArchiveAdapter, OddsArchiveSnapshot


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


_storage: SqliteStorage | None = None


def get_storage() -> SqliteStorage:
    """Devuelve el facade de storage del proceso (singleton lazy).

    Bridge para migrar los consumidores legacy (que usaban el global
    singleton de storage legacy) al storage greenfield sin
    cambiar firmas función por función. El facade es stateless (abre conexión por
    método), así que un singleton por proceso alcanza.
    """

    global _storage
    if _storage is None:
        _storage = SqliteStorage()
    return _storage


__all__ = [
    "SqliteStorage",
    "get_storage",
    "SQLiteCompetitionsAdapter",
    "SQLiteEventsAdapter",
    "SQLiteSubscriptionsAdapter",
    "SQLiteBaselinesAdapter",
    "SQLiteStatsLinksAdapter",
    "SQLiteLiveWatchAdapter",
    "SQLiteMaintenanceAdapter",
    "SQLiteChatSettingsAdapter",
    "SQLiteOddsArchiveAdapter",
    "OddsArchiveSnapshot",
]

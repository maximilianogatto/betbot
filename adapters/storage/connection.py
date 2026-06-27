"""SQLite connection primitives for the PR2 storage adapters.

The aggregate repositories should obtain connections through this module so
SQLite pragmas, path resolution, and transaction behavior stay consistent.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "tracking.sqlite3"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_BUSY_TIMEOUT_MS = 30_000


def resolve_database_path(path: str | os.PathLike[str] | None = None) -> Path:
    """Resolve a database path relative to the project root.

    Args:
        path: Explicit database path. When omitted, `BETBOT_DB_PATH` is used;
            if the env var is also empty, `data/tracking.sqlite3` is returned.

    Returns:
        Absolute path to the SQLite database file. The path is not created here.
    """

    raw_path = str(path or os.environ.get("BETBOT_DB_PATH", "")).strip()
    if not raw_path:
        return DEFAULT_DB_PATH
    if raw_path == ":memory:":
        return Path(raw_path)

    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def configure_connection(
    connection: sqlite3.Connection,
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> sqlite3.Connection:
    """Apply standard SQLite settings to one connection.

    Args:
        connection: Open SQLite connection.
        busy_timeout_ms: Milliseconds SQLite should wait before raising
            `database is locked`.

    Returns:
        The same connection, configured for adapter use.
    """

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    return connection


def open_connection(
    path: str | os.PathLike[str] | None = None,
    *,
    initialize: bool = True,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> sqlite3.Connection:
    """Open a configured SQLite connection.

    Args:
        path: Optional database path. Relative paths resolve from project root.
        initialize: When true, create the PR2 greenfield schema immediately.
        timeout: SQLite connection timeout in seconds.

    Returns:
        A configured `sqlite3.Connection` with `sqlite3.Row` row factory.
    """

    db_path = resolve_database_path(path)
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path, timeout=timeout)
    configure_connection(connection)

    if initialize:
        from adapters.storage.schema import initialize_schema

        initialize_schema(connection)
        connection.commit()

    return connection


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a block inside a commit/rollback boundary.

    Args:
        connection: Open SQLite connection.

    Yields:
        The same connection, so callers can execute SQL within the transaction.

    Raises:
        Any exception raised inside the block after rolling back.
    """

    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()

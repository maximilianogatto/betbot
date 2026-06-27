import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from .schema import initialize_schema

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

def resolve_database_path() -> Path:
    """Return the resolved database file path based on environmental variables or defaults."""
    db_path_env = os.environ.get("BETBOT_DB_PATH", "").strip()
    if db_path_env:
        path = Path(db_path_env)
        return path if path.is_absolute() else (PROJECT_ROOT / path)
    return DATA_DIR / "tracking.sqlite3"

def create_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create and configure a new SQLite connection with greenfield default settings."""
    if db_path is None:
        db_path = resolve_database_path()
    elif isinstance(db_path, str) and db_path == ":memory:":
        # Special case for in-memory database
        conn = sqlite3.connect(":memory:", timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        initialize_schema(conn)
        return conn
    else:
        db_path = Path(db_path)

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    
    # Configure WAL mode and performance pragmas
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    
    initialize_schema(conn)
    
    return conn

@contextmanager
def open_connection(db_path: Path | str | None = None):
    """Context manager for SQLite connections with automatic commit/rollback and cleanup."""
    conn = create_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@contextmanager
def transaction(connection: sqlite3.Connection):
    """Context manager for explicit transaction block."""
    with connection:
        yield connection

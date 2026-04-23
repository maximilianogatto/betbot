"""SQLite persistence for the incremental Bet365 integration.

This module introduces a small database-backed state layer dedicated to the
Bet365 workflow. It is purposely isolated from the existing bot flow so we
can validate the integration incrementally and safely.

What this module stores:
    - known league definitions mirrored from the static Bet365 catalog
    - currently active or upcoming matches for one `(platform, league_key)`
    - notification subscription preferences per Telegram chat

What this module explicitly does not store yet:
    - historical snapshots of every scrape
    - Telegram messages or delivery logs
    - scheduled jobs
    - odds history over time

That design keeps the first database step focused on *current state*. The next
integration step can connect the Playwright scraper to this module and then
compare fresh scrape results against the stored rows to detect new matches or
odds changes.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3

from services.bet365_leagues import Bet365LeagueConfig, get_league_config, list_known_leagues

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_FILE_PATH = DATA_DIR / "bet365_state.sqlite3"


@dataclass(frozen=True)
class ActiveMatchUpsert:
    """Represent one scraped match before it is persisted.

    Attributes:
        fixture_id (str): Stable fixture identifier produced by the scraper.
        home (str): Home team name.
        away (str): Away team name.
        odds_home (float | None): Current home-win odds when available.
        odds_draw (float | None): Current draw odds when available.
        odds_away (float | None): Current away-win odds when available.

    Notes:
        This is the minimal payload expected from the future Bet365 scraper.
        Platform and league information are not stored here because they are
        already provided separately to `upsert_active_matches()`.
    """

    fixture_id: str
    home: str
    away: str
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None


@dataclass(frozen=True)
class ActiveMatchRecord:
    """Represent one currently stored Bet365 match row.

    Attributes:
        platform (str): Betting platform identifier.
        league_key (str): Internal league identifier.
        fixture_id (str): Stable fixture identifier for deduplication.
        home (str): Home team name.
        away (str): Away team name.
        odds_home (float | None): Stored home-win odds.
        odds_draw (float | None): Stored draw odds.
        odds_away (float | None): Stored away-win odds.
        last_seen_at (str): UTC timestamp marking the latest scrape where the
            fixture was seen.
        created_at (str): UTC timestamp when the row was first inserted.
        updated_at (str): UTC timestamp when the row was last updated.

    Notes:
        These rows model the *current* state of the market feed, not a full
        historical time series.
    """

    platform: str
    league_key: str
    fixture_id: str
    home: str
    away: str
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None
    last_seen_at: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class NotificationSubscription:
    """Represent one Telegram notification preference row.

    Attributes:
        telegram_chat_id (int): Telegram chat that owns the subscription.
        platform (str): Betting platform identifier.
        league_key (str): Internal league identifier the chat is subscribed to.
        notify_new_matches (bool): Whether new fixtures should trigger alerts.
        notify_odds_changes (bool): Whether odds updates should trigger
            alerts once that stage is implemented.
        enabled (bool): Whether the subscription is currently active.
        created_at (str): UTC timestamp when the row was first inserted.
        updated_at (str): UTC timestamp when the row was last updated.

    Notes:
        This table is intentionally small but future-proof. It gives the next
        Telegram integration step a clear place to store user preferences
        without forcing a full migration of the existing bot data model.
    """

    telegram_chat_id: int
    platform: str
    league_key: str
    notify_new_matches: bool
    notify_odds_changes: bool
    enabled: bool
    created_at: str
    updated_at: str


def sync_known_leagues(platform: str | None = None) -> int:
    """Register static Bet365 catalog entries in the SQLite database.

    Args:
        platform (str | None): Optional platform filter. When omitted, every
            known catalog entry is mirrored into the database.

    Returns:
        int: Number of catalog entries processed during the synchronization.

    Side Effects:
        Creates the SQLite database if needed and upserts rows in the
        `known_leagues` table.

    Notes:
        This is the bridge between the code-based league catalog and the
        database. It exists so the next scraper step can keep using a stable
        code catalog while still having those leagues registered in SQLite.
    """

    league_configs = list_known_leagues(platform=platform)

    with _connect() as connection:
        for config in league_configs:
            _upsert_known_league_row(connection, config)

    logger.info("Synced %s known Bet365 leagues into SQLite state.", len(league_configs))
    return len(league_configs)


def upsert_active_matches(
    platform: str,
    league_key: str,
    matches: Sequence[ActiveMatchUpsert],
) -> int:
    """Insert or update the current active matches for one league.

    Args:
        platform (str): Betting platform identifier, for example `"bet365"`.
        league_key (str): Internal league identifier, for example
            `"la_liga"`.
        matches (Sequence[ActiveMatchUpsert]): Current scraped fixtures for the
            specified league.

    Returns:
        int: Number of match payloads processed.

    Side Effects:
        Upserts rows in the `active_matches` table and refreshes the
        `last_seen_at` / `updated_at` timestamps.

    Raises:
        ValueError: If the platform or league key does not exist in the static
            catalog, or if one of the match payloads is incomplete.

    Notes:
        This function models *current state only*. It does not keep a
        historical snapshot per scrape. The intended next-step flow is:

        1. scraper loads fresh matches
        2. caller compares against `get_active_matches()`
        3. caller upserts the latest rows here
        4. caller removes stale rows with `remove_missing_matches()`
    """

    normalized_platform, normalized_league_key = _normalize_scope(platform, league_key)
    now_iso = _utc_now_iso()

    with _connect() as connection:
        _ensure_known_league_registered(connection, normalized_platform, normalized_league_key)

        payload = []
        for match in matches:
            fixture_id = match.fixture_id.strip()
            home = match.home.strip()
            away = match.away.strip()

            if not fixture_id or not home or not away:
                raise ValueError("Each active Bet365 match must include fixture_id, home, and away.")

            payload.append(
                (
                    normalized_platform,
                    normalized_league_key,
                    fixture_id,
                    home,
                    away,
                    _coerce_optional_float(match.odds_home),
                    _coerce_optional_float(match.odds_draw),
                    _coerce_optional_float(match.odds_away),
                    now_iso,
                    now_iso,
                    now_iso,
                )
            )

        if not payload:
            logger.info(
                "No active matches were provided for platform=%s league_key=%s.",
                normalized_platform,
                normalized_league_key,
            )
            return 0

        connection.executemany(
            """
            INSERT INTO active_matches (
                platform,
                league_key,
                fixture_id,
                home,
                away,
                odds_home,
                odds_draw,
                odds_away,
                last_seen_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(platform, league_key, fixture_id) DO UPDATE SET
                home = excluded.home,
                away = excluded.away,
                odds_home = excluded.odds_home,
                odds_draw = excluded.odds_draw,
                odds_away = excluded.odds_away,
                last_seen_at = excluded.last_seen_at,
                updated_at = excluded.updated_at
            """,
            payload,
        )

    logger.info(
        "Upserted %s active Bet365 matches for platform=%s league_key=%s.",
        len(payload),
        normalized_platform,
        normalized_league_key,
    )
    return len(payload)


def remove_missing_matches(
    platform: str,
    league_key: str,
    current_fixture_ids: Iterable[str],
) -> int:
    """Delete matches that no longer appear in the latest scrape.

    Args:
        platform (str): Betting platform identifier.
        league_key (str): Internal league identifier.
        current_fixture_ids (Iterable[str]): Fixture identifiers present in the
            most recent scrape result for the given league.

    Returns:
        int: Number of rows deleted from the `active_matches` table.

    Side Effects:
        Removes stale rows from SQLite so the database stays aligned with the
        latest known current state.

    Raises:
        ValueError: If the `(platform, league_key)` pair is unknown.

    Notes:
        This function is the complement of `upsert_active_matches()`. Together
        they let the next scraper integration keep the database synchronized
        without storing historical snapshots.
    """

    normalized_platform, normalized_league_key = _normalize_scope(platform, league_key)
    normalized_fixture_ids = sorted(
        {fixture_id.strip() for fixture_id in current_fixture_ids if fixture_id and fixture_id.strip()}
    )

    with _connect() as connection:
        _ensure_known_league_registered(connection, normalized_platform, normalized_league_key)

        if not normalized_fixture_ids:
            cursor = connection.execute(
                """
                DELETE FROM active_matches
                WHERE platform = ? AND league_key = ?
                """,
                (normalized_platform, normalized_league_key),
            )
            deleted_rows = cursor.rowcount
        else:
            placeholders = ", ".join("?" for _ in normalized_fixture_ids)
            cursor = connection.execute(
                f"""
                DELETE FROM active_matches
                WHERE platform = ?
                  AND league_key = ?
                  AND fixture_id NOT IN ({placeholders})
                """,
                (normalized_platform, normalized_league_key, *normalized_fixture_ids),
            )
            deleted_rows = cursor.rowcount

    logger.info(
        "Removed %s stale Bet365 matches for platform=%s league_key=%s.",
        deleted_rows,
        normalized_platform,
        normalized_league_key,
    )
    return deleted_rows


def get_active_matches(platform: str, league_key: str) -> list[ActiveMatchRecord]:
    """Load the currently stored matches for one league.

    Args:
        platform (str): Betting platform identifier.
        league_key (str): Internal league identifier.

    Returns:
        list[ActiveMatchRecord]: Current active matches stored for the given
        league, ordered by teams and fixture identifier.

    Raises:
        ValueError: If the `(platform, league_key)` pair is unknown.

    Notes:
        This read API is the main comparison point for the next scraper step.
        The scraper can load the current database state, compare it with fresh
        scraped data, and decide which fixtures are new or changed.
    """

    normalized_platform, normalized_league_key = _normalize_scope(platform, league_key)

    with _connect() as connection:
        _validate_known_league(normalized_platform, normalized_league_key)
        rows = connection.execute(
            """
            SELECT
                platform,
                league_key,
                fixture_id,
                home,
                away,
                odds_home,
                odds_draw,
                odds_away,
                last_seen_at,
                created_at,
                updated_at
            FROM active_matches
            WHERE platform = ? AND league_key = ?
            ORDER BY home, away, fixture_id
            """,
            (normalized_platform, normalized_league_key),
        ).fetchall()

    return [_row_to_active_match_record(row) for row in rows]


def save_or_update_subscription(
    telegram_chat_id: int,
    platform: str,
    league_key: str,
    notify_new_matches: bool = True,
    notify_odds_changes: bool = False,
    enabled: bool = True,
) -> NotificationSubscription:
    """Create or update one Telegram notification subscription row.

    Args:
        telegram_chat_id (int): Telegram chat that owns the subscription.
        platform (str): Betting platform identifier.
        league_key (str): Internal league identifier.
        notify_new_matches (bool): Whether the chat wants alerts when new
            matches appear in the active state.
        notify_odds_changes (bool): Whether the chat wants alerts when odds
            change in the future odds-monitoring stage.
        enabled (bool): Whether the subscription is active.

    Returns:
        NotificationSubscription: The stored subscription row after the
        upsert operation.

    Side Effects:
        Upserts one row in the `league_subscriptions` table.

    Raises:
        ValueError: If the `(platform, league_key)` pair is unknown.

    Notes:
        This function does not send Telegram messages. It only prepares the
        persistence contract that a future command layer and notification
        layer can use.
    """

    normalized_platform, normalized_league_key = _normalize_scope(platform, league_key)
    now_iso = _utc_now_iso()

    with _connect() as connection:
        _ensure_known_league_registered(connection, normalized_platform, normalized_league_key)
        connection.execute(
            """
            INSERT INTO league_subscriptions (
                telegram_chat_id,
                platform,
                league_key,
                notify_new_matches,
                notify_odds_changes,
                enabled,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_chat_id, platform, league_key) DO UPDATE SET
                notify_new_matches = excluded.notify_new_matches,
                notify_odds_changes = excluded.notify_odds_changes,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (
                telegram_chat_id,
                normalized_platform,
                normalized_league_key,
                int(notify_new_matches),
                int(notify_odds_changes),
                int(enabled),
                now_iso,
                now_iso,
            ),
        )

        row = connection.execute(
            """
            SELECT
                telegram_chat_id,
                platform,
                league_key,
                notify_new_matches,
                notify_odds_changes,
                enabled,
                created_at,
                updated_at
            FROM league_subscriptions
            WHERE telegram_chat_id = ? AND platform = ? AND league_key = ?
            """,
            (telegram_chat_id, normalized_platform, normalized_league_key),
        ).fetchone()

    if row is None:
        raise RuntimeError("Subscription upsert succeeded but no row could be reloaded.")

    return _row_to_notification_subscription(row)


def get_subscriptions_for_league(
    platform: str,
    league_key: str,
    include_disabled: bool = False,
) -> list[NotificationSubscription]:
    """Load subscription preferences for one league.

    Args:
        platform (str): Betting platform identifier.
        league_key (str): Internal league identifier.
        include_disabled (bool): Whether disabled subscriptions should also be
            returned. By default only active subscriptions are loaded.

    Returns:
        list[NotificationSubscription]: Stored subscription rows for the
        specified league.

    Raises:
        ValueError: If the `(platform, league_key)` pair is unknown.

    Notes:
        The future Telegram notification step can call this function after
        detecting new matches or odds changes to decide which chats should
        receive a message.
    """

    normalized_platform, normalized_league_key = _normalize_scope(platform, league_key)

    query = """
        SELECT
            telegram_chat_id,
            platform,
            league_key,
            notify_new_matches,
            notify_odds_changes,
            enabled,
            created_at,
            updated_at
        FROM league_subscriptions
        WHERE platform = ? AND league_key = ?
    """
    params: tuple[object, ...] = (normalized_platform, normalized_league_key)

    if not include_disabled:
        query += " AND enabled = 1"

    query += " ORDER BY telegram_chat_id"

    with _connect() as connection:
        _validate_known_league(normalized_platform, normalized_league_key)
        rows = connection.execute(query, params).fetchall()

    return [_row_to_notification_subscription(row) for row in rows]


def _connect() -> sqlite3.Connection:
    """Open a SQLite connection and lazily create the schema.

    Returns:
        sqlite3.Connection: Ready-to-use connection with row access by column
        name.

    Side Effects:
        Creates the data directory, the SQLite file, and the required schema
        the first time it is called.
    """

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_FILE_PATH)
    connection.row_factory = sqlite3.Row

    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    """Create the minimal Bet365 state schema if it does not exist yet.

    Args:
        connection (sqlite3.Connection): Open SQLite connection.

    Returns:
        None: The function mutates the database schema in place.
    """

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS known_leagues (
            platform TEXT NOT NULL,
            country TEXT NOT NULL,
            league_key TEXT NOT NULL,
            league_name TEXT NOT NULL,
            url TEXT NOT NULL,
            enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (platform, league_key)
        );

        CREATE TABLE IF NOT EXISTS active_matches (
            platform TEXT NOT NULL,
            league_key TEXT NOT NULL,
            fixture_id TEXT NOT NULL,
            home TEXT NOT NULL,
            away TEXT NOT NULL,
            odds_home REAL,
            odds_draw REAL,
            odds_away REAL,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (platform, league_key, fixture_id)
        );

        CREATE TABLE IF NOT EXISTS league_subscriptions (
            telegram_chat_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            league_key TEXT NOT NULL,
            notify_new_matches INTEGER NOT NULL CHECK (notify_new_matches IN (0, 1)),
            notify_odds_changes INTEGER NOT NULL CHECK (notify_odds_changes IN (0, 1)),
            enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (telegram_chat_id, platform, league_key)
        );

        CREATE INDEX IF NOT EXISTS idx_active_matches_scope
            ON active_matches (platform, league_key, last_seen_at);

        CREATE INDEX IF NOT EXISTS idx_league_subscriptions_scope
            ON league_subscriptions (platform, league_key, enabled);
        """
    )


def _ensure_known_league_registered(
    connection: sqlite3.Connection,
    platform: str,
    league_key: str,
) -> None:
    """Validate a league against the static catalog and mirror it in SQLite.

    Args:
        connection (sqlite3.Connection): Open SQLite connection.
        platform (str): Normalized platform identifier.
        league_key (str): Normalized league key.

    Returns:
        None: The function upserts the matching known league row.

    Raises:
        ValueError: If the static catalog does not know the requested league.
    """

    config = _validate_known_league(platform, league_key)
    _upsert_known_league_row(connection, config)


def _upsert_known_league_row(
    connection: sqlite3.Connection,
    config: Bet365LeagueConfig,
) -> None:
    """Insert or update one known league row in SQLite.

    Args:
        connection (sqlite3.Connection): Open SQLite connection.
        config (Bet365LeagueConfig): Static catalog entry to mirror.

    Returns:
        None: The function writes the row into `known_leagues`.
    """

    now_iso = _utc_now_iso()

    connection.execute(
        """
        INSERT INTO known_leagues (
            platform,
            country,
            league_key,
            league_name,
            url,
            enabled,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(platform, league_key) DO UPDATE SET
            country = excluded.country,
            league_name = excluded.league_name,
            url = excluded.url,
            enabled = excluded.enabled,
            updated_at = excluded.updated_at
        """,
        (
            config.platform,
            config.country,
            config.league_key,
            config.league_name,
            config.url,
            int(config.enabled),
            now_iso,
            now_iso,
        ),
    )


def _validate_known_league(platform: str, league_key: str) -> Bet365LeagueConfig:
    """Return a validated catalog entry for a requested league scope.

    Args:
        platform (str): Normalized platform identifier.
        league_key (str): Normalized league key.

    Returns:
        Bet365LeagueConfig: Matching static catalog entry.

    Raises:
        ValueError: If the league is unknown to the current Bet365 catalog.
    """

    config = get_league_config(platform=platform, league_key=league_key)

    if config is None:
        raise ValueError(
            f"Unknown Bet365 league configuration for platform={platform!r}, league_key={league_key!r}."
        )

    return config


def _normalize_scope(platform: str, league_key: str) -> tuple[str, str]:
    """Normalize platform and league identifiers before DB access.

    Args:
        platform (str): Raw platform identifier.
        league_key (str): Raw league identifier.

    Returns:
        tuple[str, str]: Normalized `(platform, league_key)` pair.

    Raises:
        ValueError: If either identifier is empty after normalization.
    """

    normalized_platform = platform.strip().lower()
    normalized_league_key = league_key.strip().lower()

    if not normalized_platform:
        raise ValueError("platform must not be empty.")

    if not normalized_league_key:
        raise ValueError("league_key must not be empty.")

    return normalized_platform, normalized_league_key


def _coerce_optional_float(value: float | None) -> float | None:
    """Normalize optional numeric odds values before persistence.

    Args:
        value (float | None): Raw odds value provided by the caller.

    Returns:
        float | None: Normalized floating-point value or `None`.
    """

    if value is None:
        return None

    return float(value)


def _row_to_active_match_record(row: sqlite3.Row) -> ActiveMatchRecord:
    """Convert one SQLite row into an `ActiveMatchRecord`.

    Args:
        row (sqlite3.Row): Raw database row from `active_matches`.

    Returns:
        ActiveMatchRecord: Typed current-state match record.
    """

    return ActiveMatchRecord(
        platform=str(row["platform"]),
        league_key=str(row["league_key"]),
        fixture_id=str(row["fixture_id"]),
        home=str(row["home"]),
        away=str(row["away"]),
        odds_home=_coerce_optional_float(row["odds_home"]),
        odds_draw=_coerce_optional_float(row["odds_draw"]),
        odds_away=_coerce_optional_float(row["odds_away"]),
        last_seen_at=str(row["last_seen_at"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _row_to_notification_subscription(row: sqlite3.Row) -> NotificationSubscription:
    """Convert one SQLite row into a `NotificationSubscription`.

    Args:
        row (sqlite3.Row): Raw database row from `league_subscriptions`.

    Returns:
        NotificationSubscription: Typed subscription preference record.
    """

    return NotificationSubscription(
        telegram_chat_id=int(row["telegram_chat_id"]),
        platform=str(row["platform"]),
        league_key=str(row["league_key"]),
        notify_new_matches=bool(row["notify_new_matches"]),
        notify_odds_changes=bool(row["notify_odds_changes"]),
        enabled=bool(row["enabled"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format.

    Returns:
        str: Current UTC time serialized as an ISO-formatted string.
    """

    return datetime.now(timezone.utc).isoformat()

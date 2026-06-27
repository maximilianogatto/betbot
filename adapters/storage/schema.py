"""SQLite greenfield schema for the PR2 storage adapters.

This module owns only schema creation and schema introspection. It does not
implement repository behavior; aggregate-specific adapters will use these
tables through their own modules (`competitions.py`, `events.py`, etc.).

Schema goals:
- persist current state only, not historical odds snapshots;
- keep tables compact and relational, with JSON reserved for small metadata;
- expose stable table names for future adapters instead of mirroring the
  legacy `storage/tracking_repository.py` layout.
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

EXPECTED_TABLES: tuple[str, ...] = (
    "competitions",
    "pending_competition_requests",
    "unified_competitions",
    "chat_subscriptions",
    "events",
    "baselines",
    "small_changes",
    "sent_alerts",
    "stats_league_links",
    "stats_match_links",
    "stats_league_subscriptions",
    "stats_payload_cache",
    "live_watch",
    "live_watch_settings",
    "peak_digest_subscriptions",
    "chat_settings",
)

FORBIDDEN_LEGACY_TABLES: tuple[str, ...] = (
    "active_events",
    "event_odds_snapshots",
)


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create the clean current-state schema if it does not exist.

    Args:
        connection: Open SQLite connection. The caller is responsible for
            enabling connection-level pragmas such as foreign keys.

    Returns:
        None. The function is idempotent and commits through the caller's
        connection context.
    """

    connection.executescript(
        """
        PRAGMA user_version = 1;

        CREATE TABLE IF NOT EXISTS unified_competitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            country TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(normalized_name, country)
        );

        CREATE TABLE IF NOT EXISTS competitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            external_id TEXT NOT NULL,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            source_url TEXT,
            country TEXT,
            unified_competition_id INTEGER,
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
            needs_name_resolution INTEGER NOT NULL DEFAULT 0 CHECK(needs_name_resolution IN (0, 1)),
            metadata_json TEXT,
            last_refreshed_at TEXT,
            unavailable_count INTEGER NOT NULL DEFAULT 0,
            last_unavailable_at TEXT,
            last_unavailable_reason TEXT,
            last_unavailable_notified_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(platform, external_id),
            FOREIGN KEY(unified_competition_id) REFERENCES unified_competitions(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_competitions_active
        ON competitions(active, platform, normalized_name);

        CREATE INDEX IF NOT EXISTS idx_competitions_unified
        ON competitions(unified_competition_id);

        CREATE TABLE IF NOT EXISTS pending_competition_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            source_url TEXT NOT NULL,
            competition_external_id TEXT NOT NULL,
            competition_name TEXT NOT NULL,
            requires_empty_confirmation INTEGER NOT NULL DEFAULT 0 CHECK(requires_empty_confirmation IN (0, 1)),
            needs_name_resolution INTEGER NOT NULL DEFAULT 0 CHECK(needs_name_resolution IN (0, 1)),
            payload_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_competition_requests_chat
        ON pending_competition_requests(chat_id);

        CREATE TABLE IF NOT EXISTS chat_subscriptions (
            chat_id INTEGER NOT NULL,
            competition_id INTEGER NOT NULL,
            notify_new_matches INTEGER NOT NULL DEFAULT 1 CHECK(notify_new_matches IN (0, 1)),
            notify_odds_changes INTEGER NOT NULL DEFAULT 1 CHECK(notify_odds_changes IN (0, 1)),
            change_threshold_percent REAL NOT NULL DEFAULT 20.0,
            reminders_enabled INTEGER NOT NULL DEFAULT 0 CHECK(reminders_enabled IN (0, 1)),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(chat_id, competition_id),
            FOREIGN KEY(competition_id) REFERENCES competitions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_chat_subscriptions_competition
        ON chat_subscriptions(competition_id, enabled);

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competition_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            competition_external_id TEXT NOT NULL,
            external_event_id TEXT NOT NULL,
            home TEXT NOT NULL,
            away TEXT NOT NULL,
            scheduled_at TEXT,
            scheduled_label_date TEXT,
            scheduled_label_time TEXT,
            status TEXT NOT NULL DEFAULT 'PREMATCH',
            event_url TEXT,
            stats_url TEXT,
            odds_home REAL,
            odds_draw REAL,
            odds_away REAL,
            markets_json TEXT,
            alerted INTEGER NOT NULL DEFAULT 0 CHECK(alerted IN (0, 1)),
            reminder_enabled INTEGER NOT NULL DEFAULT 0 CHECK(reminder_enabled IN (0, 1)),
            reminder_sent_at TEXT,
            missing_seen_count INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(platform, external_event_id),
            FOREIGN KEY(competition_id) REFERENCES competitions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_events_competition_active
        ON events(competition_id, active, scheduled_at);

        CREATE INDEX IF NOT EXISTS idx_events_kickoff
        ON events(active, scheduled_at);

        CREATE TABLE IF NOT EXISTS baselines (
            chat_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            competition_id INTEGER NOT NULL,
            odds_home REAL,
            odds_draw REAL,
            odds_away REAL,
            markets_json TEXT,
            baseline_set_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(chat_id, event_id),
            FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
            FOREIGN KEY(competition_id) REFERENCES competitions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_baselines_event
        ON baselines(event_id);

        CREATE TABLE IF NOT EXISTS small_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            competition_id INTEGER NOT NULL,
            previous_odds_home REAL,
            previous_odds_draw REAL,
            previous_odds_away REAL,
            current_odds_home REAL,
            current_odds_draw REAL,
            current_odds_away REAL,
            max_change_percent REAL NOT NULL,
            payload_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            confirmed_at TEXT,
            dismissed_at TEXT,
            UNIQUE(chat_id, event_id),
            FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
            FOREIGN KEY(competition_id) REFERENCES competitions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_small_changes_chat_status
        ON small_changes(chat_id, status, updated_at);

        CREATE INDEX IF NOT EXISTS idx_small_changes_event
        ON small_changes(event_id);

        CREATE TABLE IF NOT EXISTS sent_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            alert_type TEXT NOT NULL,
            sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chat_id, event_id, alert_type),
            FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_sent_alerts_event
        ON sent_alerts(event_id);

        CREATE TABLE IF NOT EXISTS stats_league_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competition_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            stats_league_id TEXT NOT NULL,
            stats_league_name TEXT NOT NULL,
            stats_country_name TEXT,
            confidence REAL NOT NULL DEFAULT 1.0,
            payload_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(competition_id, provider),
            FOREIGN KEY(competition_id) REFERENCES competitions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_stats_league_links_provider
        ON stats_league_links(provider, stats_league_id);

        CREATE TABLE IF NOT EXISTS stats_match_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            stats_match_id TEXT NOT NULL,
            stats_url TEXT,
            confidence REAL NOT NULL DEFAULT 0.0,
            method TEXT NOT NULL DEFAULT 'manual',
            payload_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(event_id, provider),
            FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_stats_match_links_provider
        ON stats_match_links(provider, stats_match_id);

        CREATE INDEX IF NOT EXISTS idx_stats_match_links_event
        ON stats_match_links(event_id);

        CREATE TABLE IF NOT EXISTS stats_league_subscriptions (
            chat_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            stats_league_id TEXT NOT NULL,
            stats_league_name TEXT NOT NULL,
            stats_country_name TEXT,
            source_url TEXT,
            payload_json TEXT,
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(chat_id, provider, stats_league_id)
        );

        CREATE INDEX IF NOT EXISTS idx_stats_league_subscriptions_provider
        ON stats_league_subscriptions(provider, stats_league_id, enabled);

        CREATE TABLE IF NOT EXISTS stats_payload_cache (
            cache_key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_stats_payload_cache_expires
        ON stats_payload_cache(expires_at);

        CREATE TABLE IF NOT EXISTS live_watch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            chat_local_id INTEGER,
            home TEXT NOT NULL,
            away TEXT NOT NULL,
            league_hint TEXT,
            note TEXT,
            kickoff_at TEXT,
            status TEXT NOT NULL DEFAULT 'watching',
            matched_platform TEXT,
            matched_event_id TEXT,
            matched_minute TEXT,
            prematch_seen_at TEXT,
            prematch_platform TEXT,
            fired_at TEXT,
            fired_platforms TEXT,
            prematch_fired_platforms TEXT,
            countdown_fired_at TEXT,
            live_state_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chat_id, chat_local_id)
        );

        CREATE INDEX IF NOT EXISTS idx_live_watch_chat_status
        ON live_watch(chat_id, status);

        CREATE INDEX IF NOT EXISTS idx_live_watch_active_kickoff
        ON live_watch(status, kickoff_at);

        CREATE TABLE IF NOT EXISTS live_watch_settings (
            chat_id INTEGER PRIMARY KEY,
            alert_goals INTEGER NOT NULL DEFAULT 1 CHECK(alert_goals IN (0, 1)),
            alert_red_cards INTEGER NOT NULL DEFAULT 1 CHECK(alert_red_cards IN (0, 1)),
            alert_yellow_cards INTEGER NOT NULL DEFAULT 0 CHECK(alert_yellow_cards IN (0, 1)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS peak_digest_subscriptions (
            chat_id INTEGER PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chat_settings (
            chat_id INTEGER PRIMARY KEY,
            timezone TEXT,
            language TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def get_schema_version(connection: sqlite3.Connection) -> int:
    """Return the SQLite user_version for this database."""

    row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row is not None else 0


def list_tables(connection: sqlite3.Connection) -> set[str]:
    """Return user-defined table names in the current database."""

    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return {str(row[0]) for row in rows}

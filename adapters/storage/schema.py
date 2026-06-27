import sqlite3

EXPECTED_TABLES = [
    "pending_track_requests",
    "unified_competitions",
    "competitions",
    "chat_subscriptions",
    "events",
    "event_reminders",
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
]

FORBIDDEN_LEGACY_TABLES = [
    "active_events",
    "tracked_competitions",
    "competition_subscriptions",
    "event_odds_snapshots",
    "event_payloads_debug",
    "dirty_chats",
    "chat_subscriptions_bitmap",
    "user_event_baselines",
]

def get_schema_version(connection: sqlite3.Connection) -> int:
    """Return the current user schema version from the database."""
    return connection.execute("PRAGMA user_version").fetchone()[0]

def list_tables(connection: sqlite3.Connection) -> list[str]:
    """List all table names present in the database."""
    cursor = connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [row["name"] for row in cursor.fetchall()]

def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create all SQLite tables and indexes for the greenfield current-state schema."""
    connection.executescript(
        """
        -- 1. Pending track requests
        CREATE TABLE IF NOT EXISTS pending_track_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL UNIQUE,
            platform TEXT NOT NULL,
            source_url TEXT NOT NULL,
            competition_external_id TEXT NOT NULL,
            competition_name TEXT NOT NULL,
            requires_empty_confirmation INTEGER NOT NULL DEFAULT 0,
            needs_name_resolution INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT
        );

        -- 2. Canonical Unified Competitions
        CREATE TABLE IF NOT EXISTS unified_competitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            public_id TEXT UNIQUE,
            display_name TEXT,
            country TEXT,
            gender TEXT,
            age_group TEXT,
            odds_providers_mask INTEGER NOT NULL DEFAULT 0,
            stats_providers_mask INTEGER NOT NULL DEFAULT 0,
            odds_external_ids TEXT,
            odds_source_urls TEXT,
            stats_external_ids TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unified_competitions_public_id
        ON unified_competitions(public_id) WHERE public_id IS NOT NULL;

        -- 3. Competitions (Tracked competitions)
        CREATE TABLE IF NOT EXISTS competitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            external_id TEXT NOT NULL,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            source_url TEXT NOT NULL DEFAULT '',
            metadata_json TEXT,
            needs_name_resolution INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_refreshed_at TEXT,
            consecutive_unavailable_refreshes INTEGER NOT NULL DEFAULT 0,
            last_unavailable_refresh_at TEXT,
            last_unavailable_reason TEXT,
            last_unavailable_notification_at TEXT,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            unified_competition_id INTEGER,
            reminders_enabled INTEGER NOT NULL DEFAULT 0,
            UNIQUE(platform, external_id),
            FOREIGN KEY(unified_competition_id) REFERENCES unified_competitions(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_competitions_unified
        ON competitions(unified_competition_id);

        -- 4. Chat subscriptions to competitions
        CREATE TABLE IF NOT EXISTS chat_subscriptions (
            chat_id INTEGER NOT NULL,
            competition_id INTEGER NOT NULL,
            notify_new_events INTEGER NOT NULL DEFAULT 1,
            notify_odds_changes INTEGER NOT NULL DEFAULT 1,
            change_threshold_percent REAL NOT NULL DEFAULT 20.0,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (chat_id, competition_id),
            FOREIGN KEY(competition_id) REFERENCES competitions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_chat_subscriptions_tracked
        ON chat_subscriptions(competition_id);

        -- 5. Active Events
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competition_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            competition_external_id TEXT NOT NULL,
            external_event_id TEXT NOT NULL,
            home TEXT NOT NULL,
            away TEXT NOT NULL,
            scheduled_label_date TEXT,
            scheduled_label_time TEXT,
            scheduled_at TEXT,
            event_url TEXT,
            odds_home REAL,
            odds_draw REAL,
            odds_away REAL,
            markets_json TEXT,
            raw_payload_json TEXT,
            reminder_sent_at TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            reminder_enabled INTEGER NOT NULL DEFAULT 0,
            first_seen_at TEXT NOT NULL DEFAULT '',
            last_seen_at TEXT NOT NULL DEFAULT '',
            UNIQUE(platform, external_event_id),
            FOREIGN KEY(competition_id) REFERENCES competitions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_events_competition
        ON events(competition_id, is_active, scheduled_at);

        -- 6. Event Kickoff Reminders (per chat/event)
        CREATE TABLE IF NOT EXISTS event_reminders (
            chat_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            PRIMARY KEY (chat_id, event_id),
            FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
        );

        -- 7. Odds Baselines for notification thresholding
        CREATE TABLE IF NOT EXISTS baselines (
            chat_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            competition_id INTEGER NOT NULL,
            baseline_odds_home REAL,
            baseline_odds_draw REAL,
            baseline_odds_away REAL,
            baseline_markets_json TEXT,
            baseline_set_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (chat_id, event_id),
            FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
            FOREIGN KEY(competition_id) REFERENCES competitions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_baselines_event
        ON baselines(event_id);

        -- 8. Small Odds Changes pending confirmation
        CREATE TABLE IF NOT EXISTS small_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            active_event_id INTEGER NOT NULL,
            previous_odds_home REAL,
            previous_odds_draw REAL,
            previous_odds_away REAL,
            current_odds_home REAL,
            current_odds_draw REAL,
            current_odds_away REAL,
            max_change_percent REAL NOT NULL,
            payload_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            confirmed_at TEXT,
            dismissed_at TEXT,
            UNIQUE(chat_id, active_event_id),
            FOREIGN KEY(active_event_id) REFERENCES events(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_small_changes_event
        ON small_changes(active_event_id);
        CREATE INDEX IF NOT EXISTS idx_small_changes_chat_status
        ON small_changes(chat_id, status, updated_at);

        -- 9. Sent alerts deduplication
        CREATE TABLE IF NOT EXISTS sent_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            alert_type TEXT NOT NULL,
            sent_at TEXT NOT NULL DEFAULT '',
            UNIQUE(chat_id, event_id, alert_type),
            FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_sent_alerts_event
        ON sent_alerts(event_id);

        -- 10. Stats League Mapping Links
        CREATE TABLE IF NOT EXISTS stats_league_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competition_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            stats_league_id TEXT NOT NULL,
            stats_league_name TEXT NOT NULL,
            stats_country_name TEXT,
            confidence REAL NOT NULL DEFAULT 1.0,
            payload_json TEXT,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            unified_competition_id INTEGER,
            UNIQUE(competition_id, provider),
            FOREIGN KEY(competition_id) REFERENCES competitions(id) ON DELETE CASCADE,
            FOREIGN KEY(unified_competition_id) REFERENCES unified_competitions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_stats_league_links_unified
        ON stats_league_links(unified_competition_id);

        -- 11. Stats Match Mapping Links
        CREATE TABLE IF NOT EXISTS stats_match_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            stats_match_id TEXT NOT NULL,
            stats_url TEXT,
            confidence REAL NOT NULL DEFAULT 1.0,
            method TEXT NOT NULL DEFAULT '',
            payload_json TEXT,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            UNIQUE(event_id, provider),
            FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_stats_match_links_event
        ON stats_match_links(event_id);

        -- 12. Stats League Subscriptions
        CREATE TABLE IF NOT EXISTS stats_league_subscriptions (
            telegram_chat_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            stats_league_id TEXT NOT NULL,
            stats_league_name TEXT NOT NULL,
            stats_country_name TEXT,
            source_url TEXT,
            payload_json TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (telegram_chat_id, provider, stats_league_id)
        );

        -- 13. Cache for Stats Payloads
        CREATE TABLE IF NOT EXISTS stats_payload_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cache_key TEXT NOT NULL UNIQUE,
            payload_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_stats_payload_cache_expires
        ON stats_payload_cache(expires_at);

        -- 14. Live Watch Fixtures list
        CREATE TABLE IF NOT EXISTS live_watch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            home TEXT NOT NULL,
            away TEXT NOT NULL,
            league_hint TEXT,
            note TEXT,
            status TEXT NOT NULL DEFAULT 'watching',
            matched_platform TEXT,
            matched_event_id TEXT,
            matched_minute TEXT,
            created_at TEXT NOT NULL,
            fired_at TEXT,
            kickoff_at TEXT,
            prematch_seen_at TEXT,
            prematch_platform TEXT,
            fired_platforms TEXT,
            prematch_fired_platforms TEXT,
            countdown_fired_at TEXT,
            chat_local_id INTEGER,
            live_state_json TEXT,
            status_flags INTEGER NOT NULL DEFAULT 1,
            fired_odds_mask INTEGER NOT NULL DEFAULT 0,
            fired_stats_mask INTEGER NOT NULL DEFAULT 0
        );

        -- 15. Live Watch Settings (goals, cards, etc. per chat)
        CREATE TABLE IF NOT EXISTS live_watch_settings (
            chat_id INTEGER PRIMARY KEY,
            alert_goals INTEGER NOT NULL DEFAULT 1,
            alert_red_cards INTEGER NOT NULL DEFAULT 1,
            alert_yellow_cards INTEGER NOT NULL DEFAULT 0
        );

        -- 16. Peak Digest Subscriptions
        CREATE TABLE IF NOT EXISTS peak_digest_subscriptions (
            chat_id INTEGER PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- 17. General Chat Settings
        CREATE TABLE IF NOT EXISTS chat_settings (
            chat_id INTEGER PRIMARY KEY,
            change_threshold_percent REAL NOT NULL DEFAULT 20.0,
            language TEXT NOT NULL DEFAULT 'es',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    # Set the user version to 1
    connection.execute("PRAGMA user_version = 1")

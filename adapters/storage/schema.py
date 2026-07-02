import sqlite3

EXPECTED_TABLES = [
    "unified_competitions",
    "competitions",
    "unified_merge_exceptions",
    "subscriptions",
    "events",
    "baselines",
    "small_changes",
    "sent_alerts",
    "stats_league_links",
    "stats_match_links",
    "stats_league_subscriptions",
    "stats_payload_cache",
    "live_watch_entries",
    "live_watch_settings",
    "peak_digest_subscriptions",
    "chat_settings",
    "pending_track_requests",
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
    "chat_subscriptions",
    "live_watch",
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
        -- Registro canónico de ligas (cross-plataforma)
        CREATE TABLE IF NOT EXISTS unified_competitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            display_name TEXT,
            country TEXT, gender TEXT, age_group TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unified_competitions_public_id
        ON unified_competitions(public_id) WHERE public_id IS NOT NULL;

        -- Ligas trackeadas por plataforma
        CREATE TABLE IF NOT EXISTS competitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            external_id TEXT NOT NULL,
            name TEXT NOT NULL,
            source_url TEXT NOT NULL,
            metadata_json TEXT,
            unified_competition_id INTEGER REFERENCES unified_competitions(id) ON DELETE SET NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            reminders_enabled INTEGER NOT NULL DEFAULT 0,
            last_refreshed_at TEXT,
            consecutive_unavailable_refreshes INTEGER NOT NULL DEFAULT 0,
            last_unavailable_at TEXT, last_unavailable_reason TEXT, last_unavailable_notified_at TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(platform, external_id)
        );
        CREATE INDEX IF NOT EXISTS idx_competitions_unified ON competitions(unified_competition_id);

        -- Excepciones de auto-merge (blocklist por par plataforma+external_id, orden
        -- canónico a<=b). La escribe /unlink_league (un par por miembro que quedaba);
        -- el learner la lee para no re-fusionar ligas separadas a mano.
        CREATE TABLE IF NOT EXISTS unified_merge_exceptions (
            platform_a TEXT NOT NULL, external_id_a TEXT NOT NULL,
            platform_b TEXT NOT NULL, external_id_b TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (platform_a, external_id_a, platform_b, external_id_b)
        );

        -- Suscripción chat ↔ liga (booleanos en columnas, no bitmask)
        CREATE TABLE IF NOT EXISTS subscriptions (
            chat_id INTEGER NOT NULL,
            competition_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
            notify_new_events INTEGER NOT NULL DEFAULT 1,
            notify_odds_changes INTEGER NOT NULL DEFAULT 1,
            change_threshold_percent REAL NOT NULL DEFAULT 20.0,
            reminders_enabled INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, competition_id)
        );
        CREATE INDEX IF NOT EXISTS idx_subscriptions_competition ON subscriptions(competition_id);

        -- Estado actual de partidos + odds (current-state, sin historial)
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competition_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
            platform TEXT NOT NULL,
            external_event_id TEXT NOT NULL,
            home TEXT NOT NULL, away TEXT NOT NULL,
            scheduled_at TEXT,
            scheduled_label_date TEXT, scheduled_label_time TEXT,
            event_url TEXT, stats_url TEXT,
            odds_home REAL, odds_draw REAL, odds_away REAL,
            markets_json TEXT,
            status TEXT NOT NULL DEFAULT 'PREMATCH',   -- PREMATCH | LIVE | FINISHED
            is_active INTEGER NOT NULL DEFAULT 1,
            missing_seen_count INTEGER NOT NULL DEFAULT 0,
            reminder_enabled INTEGER NOT NULL DEFAULT 0,
            reminder_sent_at TEXT,
            first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(platform, external_event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_events_competition ON events(competition_id, is_active, scheduled_at);

        -- Recordatorios de partidos específicos por chat
        CREATE TABLE IF NOT EXISTS chat_event_reminders (
            chat_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            enabled INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (chat_id, event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_chat_event_reminders_event ON chat_event_reminders(event_id);

        -- Baselines por chat (índice en el FK desde el día 1)
        CREATE TABLE IF NOT EXISTS baselines (
            chat_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            odds_home REAL, odds_draw REAL, odds_away REAL,
            markets_json TEXT,
            set_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_baselines_event ON baselines(event_id);

        CREATE TABLE IF NOT EXISTS small_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            prev_home REAL, prev_draw REAL, prev_away REAL,
            cur_home REAL, cur_draw REAL, cur_away REAL,
            max_change_percent REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',     -- pending | confirmed | dismissed
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(chat_id, event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_small_changes_event ON small_changes(event_id);
        CREATE INDEX IF NOT EXISTS idx_small_changes_chat_status ON small_changes(chat_id, status, updated_at);

        CREATE TABLE IF NOT EXISTS sent_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            alert_type TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            UNIQUE(chat_id, event_id, alert_type)
        );
        CREATE INDEX IF NOT EXISTS idx_sent_alerts_event ON sent_alerts(event_id);
        CREATE INDEX IF NOT EXISTS idx_sent_alerts_sent_at ON sent_alerts(sent_at);   -- para el prune >30d

        -- Vínculos liga/partido ↔ proveedor de stats
        CREATE TABLE IF NOT EXISTS stats_league_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competition_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            league_id TEXT NOT NULL, league_name TEXT NOT NULL, country_name TEXT,
            confidence REAL NOT NULL DEFAULT 1.0,
            payload_json TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(competition_id, provider)
        );
        CREATE INDEX IF NOT EXISTS idx_stats_league_links_provider ON stats_league_links(provider, league_id);

        CREATE TABLE IF NOT EXISTS stats_match_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            match_id TEXT NOT NULL, url TEXT,
            confidence REAL NOT NULL DEFAULT 0.0, method TEXT NOT NULL,
            payload_json TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(event_id, provider)
        );
        CREATE INDEX IF NOT EXISTS idx_stats_match_links_event ON stats_match_links(event_id);
        CREATE INDEX IF NOT EXISTS idx_stats_match_links_provider ON stats_match_links(provider, match_id);

        CREATE TABLE IF NOT EXISTS stats_league_subscriptions (
            chat_id INTEGER NOT NULL,
            provider TEXT NOT NULL, league_id TEXT NOT NULL,
            league_name TEXT NOT NULL, country_name TEXT, source_url TEXT,
            payload_json TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, provider, league_id)
        );

        -- Cache de payloads de stats (cap FIFO 200 + TTL → MaintenancePort)
        CREATE TABLE IF NOT EXISTS stats_payload_cache (
            cache_key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL, expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_stats_payload_cache_expires ON stats_payload_cache(expires_at);

        -- Live watch (vigilancia in-play, independiente de cuotas)
        CREATE TABLE IF NOT EXISTS live_watch_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            chat_local_id INTEGER,
            home TEXT NOT NULL, away TEXT NOT NULL,
            league_hint TEXT, note TEXT,
            status TEXT NOT NULL DEFAULT 'watching',   -- watching | fired | cancelled
            matched_platform TEXT, matched_event_id TEXT, matched_minute TEXT,
            kickoff_at TEXT,
            prematch_seen_at TEXT, prematch_platform TEXT,
            fired_platforms TEXT,                       -- comma-separated
            prematch_fired_platforms TEXT,              -- comma-separated
            countdown_fired_at TEXT,
            live_state_json TEXT,                       -- JSON dictionary by platform
            status_flags INTEGER NOT NULL DEFAULT 1,
            fired_odds_mask INTEGER NOT NULL DEFAULT 0,
            fired_stats_mask INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, fired_at TEXT,
            UNIQUE(chat_id, chat_local_id)
        );
        CREATE INDEX IF NOT EXISTS idx_live_watch_chat_status ON live_watch_entries(chat_id, status);


        CREATE TABLE IF NOT EXISTS live_watch_settings (
            chat_id INTEGER PRIMARY KEY,
            alert_goals INTEGER NOT NULL DEFAULT 1,
            alert_red_cards INTEGER NOT NULL DEFAULT 1,
            alert_yellow_cards INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS peak_digest_subscriptions (
            chat_id INTEGER PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chat_settings (
            chat_id INTEGER PRIMARY KEY,
            timezone TEXT,
            updated_at TEXT NOT NULL
        );

        -- Pending track requests (flujo /track)
        CREATE TABLE IF NOT EXISTS pending_track_requests (
            chat_id INTEGER PRIMARY KEY,
            platform TEXT NOT NULL, source_url TEXT NOT NULL,
            external_id TEXT NOT NULL, name TEXT NOT NULL,
            requires_empty_confirmation INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT,
            created_at TEXT NOT NULL, expires_at TEXT
        );
        """
    )
    # Set the user version to 5
    connection.execute("PRAGMA user_version = 5")

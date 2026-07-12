# Esquema greenfield — PR2-F3 (`adapters/storage/schema.py`)

> Esquema **current-state limpio** que destraba PR2-E2. Se crea de cero en DB vacía (sin migración, sin `active_events`, sin `event_odds_snapshots`, sin bitmask de settings).
> Grounded en las columnas reales del repo legacy (post-PR1) + las decisiones tomadas. Cada tabla mapea a un port de `PORTS_SPEC.md`.
> `connection.py` aplica los PRAGMAs: `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`.

## Decisiones reflejadas
- **Nombres limpios:** `active_events`→`events`, `tracked_competitions`→`competitions`, `competition_subscriptions`→`subscriptions`, `user_event_baselines`→`baselines`.
- **Sin `raw_payload_json`** por defecto. Si se necesita debug, va en tabla aparte `event_payloads_debug` (opcional, TTL corto) — no se crea salvo `DEBUG_PAYLOADS=1`.
- **Lifecycle como texto** (`status`: `PREMATCH`/`LIVE`/`FINISHED`), no bitmask — queryable.
- **Settings booleanos = columnas INTEGER** independientes (no bitmask) — medido: el bitmask ahorra ~0.3 KB y rompe `WHERE`/índices.
- **Índices en TODOS los FK a `event_id`** (incorpora el fix de PR1-T5 desde el día 1).
- Cap FIFO de `stats_payload_cache` (200 filas) y prune/vacuum: lógica de `MaintenancePort`, no del schema.

## DDL

```sql
-- Registro canónico de ligas (cross-plataforma)
CREATE TABLE IF NOT EXISTS unified_competitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    display_name TEXT,
    country TEXT, gender TEXT, age_group TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

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
    last_refreshed_at TEXT,
    consecutive_unavailable_refreshes INTEGER NOT NULL DEFAULT 0,
    last_unavailable_at TEXT, last_unavailable_reason TEXT, last_unavailable_notified_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(platform, external_id)
);
CREATE INDEX IF NOT EXISTS idx_competitions_unified ON competitions(unified_competition_id);

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
    reminder_sent_at TEXT,
    first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(platform, external_event_id)
);
CREATE INDEX IF NOT EXISTS idx_events_competition ON events(competition_id, is_active, scheduled_at);

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
    home TEXT NOT NULL, away TEXT NOT NULL,
    league_hint TEXT, note TEXT,
    status TEXT NOT NULL DEFAULT 'watching',   -- watching | fired | cancelled
    matched_platform TEXT, matched_event_id TEXT, matched_minute TEXT,
    created_at TEXT NOT NULL, fired_at TEXT, fired_platforms TEXT
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
```

## Mapeo tabla → port (para los adapters S1-S8)
| Tabla(s) | Port | Sub-tarea |
| :--- | :--- | :--- |
| competitions, unified_competitions, pending_track_requests | CompetitionsPort | S1 |
| events | EventsPort | S2 |
| subscriptions, stats_league_subscriptions, peak_digest_subscriptions | SubscriptionsPort | S3 |
| baselines, small_changes, sent_alerts | BaselinesPort | S4 |
| stats_league_links, stats_match_links | StatsLinksPort | S5 |
| live_watch_entries, live_watch_settings | LiveWatchPort | S6 |
| stats_payload_cache + prune/vacuum | MaintenancePort | S7 |
| chat_settings | ChatSettingsPort | S2/S3 |

## Nota de paridad
Antes de borrar `tracking_repository.py` (S8), verificar que cada método consumido (los 81 de `PORTS_SPEC`) tenga equivalente en el adapter nuevo. Tests de los servicios = la red de paridad.

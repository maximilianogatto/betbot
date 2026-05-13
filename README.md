# BetBot: Bet365 League Tracking for Telegram

This project is now focused on one practical workflow:

1. track Bet365 leagues from Telegram by URL
2. confirm the league manually
3. keep one global scraped state per league
4. fan out notifications to subscribed Telegram chats

The design stays intentionally simple:

- one real platform for now: Bet365
- one tracking flow: `/track_url` -> `/confirm_track`
- one global store for current fixtures and odds
- one subscription layer per Telegram chat

## Current commands

- `/start`: welcome message
- `/help`: command list
- `/guide`: quick usage guide
- `/ping`: replies with `pong`
- `/status`: reports that the bot is online
- `/stats`: shows simple runtime resource metrics
- `/echo <text>`: echoes back the provided text
- `/track_url <url>`: extract a Bet365 league and store it as pending
- `/confirm_track`: confirm the latest pending league for the current chat
- `/list_tracks`: list tracked leagues for the current chat
- `/refresh_tracks`: refresh the tracked leagues for the current chat
- `/matches`: browse stored active matches by numeric selection
- `/untrack`: stop tracking one league by numeric selection
- `/odds_on`: enable odds-change notifications for one league by numeric selection
- `/odds_off`: disable odds-change notifications for one league by numeric selection
- `/set_change_percent <n>`: set the minimum percent change required to trigger an odds alert
- `/check_little_changes`: list pending small odds changes for the current chat
- `/confirm_change <n>`: confirm one pending little change and move the baseline forward
- `/confirm_all_little_changes`: confirm every pending little change
- `/cancel`: cancel the current interactive selection

## Main flow

### 1. Track a league by URL

```text
/track_url https://www.bet365.es/#/AC/B1/C1/D1002/E120757998/G40/
```

The bot validates the URL, opens the Bet365 page with Playwright, reads the
internal page state, and extracts:

- `league_name`
- `platform=bet365`
- `topic`

The league is not activated yet. The bot asks for confirmation.

### 2. Confirm the league

```text
/confirm_track
```

After confirmation:

- the league is stored globally
- the current chat gets a subscription row
- the league appears in `/list_tracks`
- the bot stores an initial silent snapshot of current matches so the first
  monitor cycle does not mark every existing fixture as "new"

### 3. Monitor the league

The bot runs a periodic monitor loop in the background.

Each cycle:

1. loads globally active leagues
2. scrapes each league once
3. updates the current global state for its fixtures
4. detects new matches using `fixture_id`
5. detects odds changes by comparing `odds_home`, `odds_draw`, and `odds_away`
6. removes fixtures that disappeared or already passed
7. sends Telegram notifications to subscribed chats according to each chat's flags

## Persistence model

The key design rule is:

- subscriptions are per chat
- scraped league state is global

That avoids duplicating the same Bet365 fixtures and odds when several chats
track the same league.

### Pending track requests

Stored in `pending_track_requests`:

- `telegram_chat_id`
- `platform`
- `url`
- `topic`
- `league_name`
- `payload_json`
- `created_at`
- `expires_at`

### Globally tracked leagues

Stored in `tracked_leagues`:

- `id`
- `platform`
- `url`
- `topic`
- `league_name`
- `enabled`
- `last_scraped_at`
- `created_at`
- `updated_at`

### Chat subscriptions

Stored in `tracked_league_subscriptions`:

- `telegram_chat_id`
- `tracked_league_id`
- `enabled`
- `notify_new_matches`
- `notify_odds_changes`
- `change_percent_threshold`
- `created_at`
- `updated_at`

### Active global fixtures

Stored in `active_matches`:

- `tracked_league_id`
- `fixture_id`
- `home`
- `away`
- `kickoff_label_date`
- `kickoff_label_time`
- `kickoff_at`
- `odds_home`
- `odds_draw`
- `odds_away`
- `last_seen_at`
- `created_at`
- `updated_at`

### Per-chat baselines

Stored in `subscription_match_baselines`:

- `telegram_chat_id`
- `tracked_league_id`
- `fixture_id`
- `baseline_home`
- `baseline_draw`
- `baseline_away`
- `updated_at`

Each chat compares odds changes against its own baseline instead of against the
previous global scrape. That avoids duplicating the global match state while
still allowing different sensitivity levels per chat.

### Little changes

Stored in `little_changes`:

- `telegram_chat_id`
- `tracked_league_id`
- `fixture_id`
- `baseline_home`, `baseline_draw`, `baseline_away`
- `current_home`, `current_draw`, `current_away`
- `max_percent_change`
- `status`

If the change stays below the configured threshold, the bot does not send an
automatic odds alert. Instead, it updates the pending `little_change` for that
chat so it can be reviewed later with `/check_little_changes`.

## Notifications

### New match

When a new `fixture_id` appears, the bot sends a notification to chats where:

- the subscription is enabled
- `notify_new_matches = true`

### Odds change

When `odds_home`, `odds_draw`, or `odds_away` changes, the bot compares the
current odds against the per-chat baseline and calculates:

`abs(current - baseline) / baseline * 100`

using the maximum valid variation across `1`, `X`, and `2`.

If the change is large enough, the bot sends a notification to chats where:

- the subscription is enabled
- `notify_odds_changes = true`
- `max_percent_change >= change_percent_threshold`

After sending the alert, the chat baseline is updated automatically to the
current odds so the same move is not reported over and over again.

If the change is smaller than the threshold:

- the global odds still update normally
- the chat baseline stays unchanged
- the change is stored as a pending `little_change`

## Match browsing

Use:

```text
/matches
```

The bot asks:

1. which tracked league you want to inspect
2. which match you want to see

You reply using numbers, for example:

```text
1
2
```

Then the bot returns either:

- all matches from that league
- or one selected match

Each match message includes:

- league
- kickoff
- home vs away
- odds `1 / X / 2`

## Quick guide

1. `/track_url <url>`
2. `/confirm_track`
3. `/list_tracks`
4. `/matches`
5. `/odds_on`
6. `/set_change_percent 20`
7. `/check_little_changes`
8. `/confirm_change <n>` or `/confirm_all_little_changes`

## Untracking

Use:

```text
/untrack
```

The bot shows your tracked leagues with numbers. After selecting one:

- your chat subscription is removed
- if no enabled subscriptions remain for that league, its stored active fixtures are cleaned
- orphaned global league rows are automatically purged by the SQLite sanitation step

This keeps the global state lean without duplicating or accumulating stale data.

## Environment variables

Copy the example file first:

```bash
cp .env.example .env
```

Current variables:

```env
TELEGRAM_BOT_TOKEN=123456789:replace_with_your_real_token
LOG_LEVEL=INFO
TRACKING_REFRESH_INTERVAL_SECONDS=120
TRACKING_MAX_PARALLEL_REFRESHES=3
EXTRACTOR_MAX_PARALLEL_COMPETITIONS=3
EXTRACTOR_MAX_PARALLEL_PAGES=3
EXTRACTOR_MAX_PARALLEL_EVENT_PAGES=3
EXTRACTOR_PAGE_REUSE_ENABLED=false
EXTRACTOR_PAGE_LOAD_TIMEOUT_MS=60000
EXTRACTOR_POST_LOAD_WAIT_MS=4000
TRACKING_DEFAULT_CHANGE_THRESHOLD_PERCENT=20.0
TRACKING_DEFAULT_NOTIFY_ODDS_CHANGES=true
TRACKING_REMOVE_MISSING_AFTER_CYCLES=3
```

### What they mean

- `TELEGRAM_BOT_TOKEN`: required BotFather token
- `LOG_LEVEL`: console logging verbosity
- `TRACKING_REFRESH_INTERVAL_SECONDS`: interval of the background tracking monitor loop
- `TRACKING_MAX_PARALLEL_REFRESHES`: legacy alias for competition refresh parallelism
- `EXTRACTOR_MAX_PARALLEL_COMPETITIONS`: max number of competitions refreshed in parallel per cycle
- `EXTRACTOR_MAX_PARALLEL_PAGES`: global max number of Playwright pages processed in parallel
- `EXTRACTOR_MAX_PARALLEL_EVENT_PAGES`: per-league max number of concurrent event captures
- `EXTRACTOR_PAGE_REUSE_ENABLED`: reuses Playwright pages between captures when possible
- `EXTRACTOR_PAGE_LOAD_TIMEOUT_MS`: page load and runtime wait timeout
- `EXTRACTOR_POST_LOAD_WAIT_MS`: extra wait after runtime readiness before extraction
- `TRACKING_DEFAULT_CHANGE_THRESHOLD_PERCENT`: default threshold persisted for new chat subscriptions
- `TRACKING_DEFAULT_NOTIFY_ODDS_CHANGES`: default odds-change notification flag for new chat subscriptions
- `TRACKING_REMOVE_MISSING_AFTER_CYCLES`: how many refresh cycles an event can stay missing before removal
- `ENABLE_MONITORING`: enables periodic resource monitoring in background
- `MONITOR_INTERVAL_SECONDS`: interval of the resource monitor loop
- `MONITOR_LOG_TO_FILE`: when `true`, also writes monitor blocks to `monitor.log`
- `MONITOR_CHROMIUM_RAM_ALERT_MB`: warning threshold for total Chromium RAM

Legacy compatibility:

- `BET365_REFRESH_INTERVAL_SECONDS`
- `BET365_MAX_PARALLEL_PAGES`
- `BET365_PAGE_LOAD_TIMEOUT_MS`
- `BET365_POST_LOAD_WAIT_MS`

Those legacy names are still accepted by the loader, but the internal app configuration now uses the generic `TRACKING_*` and `EXTRACTOR_*` names.

## Resource monitoring

The project can also monitor runtime resources without changing the bot flow.

When enabled, the background monitor logs:

- RAM used by the bot process
- CPU used by the bot process
- total system RAM usage
- number of Chromium processes
- total RAM used by Chromium
- SQLite database size

Enable it in `.env`:

```env
ENABLE_MONITORING=true
MONITOR_INTERVAL_SECONDS=60
MONITOR_LOG_TO_FILE=false
MONITOR_CHROMIUM_RAM_ALERT_MB=800
```

When active, the bot prints blocks like:

```text
[MONITOR]
RAM bot: 180.4 MB
CPU bot: 6.2 %
RAM sistema: 54.8 % (8421.3 MB)
Chromium: 4 procesos (512.6 MB)
DB: 1.3 MB
```

If system RAM goes above 90% or Chromium RAM goes above the configured
threshold, the bot logs a warning.

You can also request the same metrics from Telegram with:

```text
/stats
```

## Install and run

Before starting, you need:

- Python 3.11 or newer
- internet access to download Python packages and Playwright Chromium

### Linux and macOS

From the project root:

```bash
chmod +x install.sh run.sh
./install.sh
```

Then edit `.env` and run:

```bash
./run.sh
```

### Windows

From PowerShell in the project root:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Then edit `.env` and run:

```powershell
.\run.ps1
```

### What the install scripts do

- create `betbot/` if you are not already inside a virtual environment
- upgrade `pip`
- install `requirements.txt`
- install Playwright Chromium
- create `.env` from `.env.example` if it does not exist

Note for Linux:
if Chromium fails because of missing system libraries, run:

```bash
python -m playwright install chromium
python -m playwright install --with-deps chromium
```

### What the run scripts do

- activate the virtual environment
- verify that `.env` exists
- verify that `TELEGRAM_BOT_TOKEN` is not empty or left as the example value
- start the bot with `python main.py`

### Compatibility scripts

The older setup entrypoints still exist and now delegate to the new installers:

- `setup.sh` -> `install.sh`
- `setup.ps1` -> `install.ps1`

## Run the bot

If you prefer to run manually after installation:

```bash
python main.py
```

## Project structure

```text
.
├── bot
│   ├── alerts.py
│   ├── application.py
│   ├── config.py
│   ├── error_handler.py
│   ├── handlers.py
│   └── jobs.py
├── core
│   ├── extractor_base.py
│   ├── models.py
│   └── registry.py
├── data
├── extractors
│   ├── __init__.py
│   └── bet365
│       ├── __init__.py
│       ├── client.py
│       └── extractor.py
├── monitors
│   └── tracking.py
├── sandbox
├── storage
│   └── tracking_repository.py
├── .env.example
├── install.ps1
├── install.sh
├── main.py
├── monitoring.py
├── README.md
├── requirements.txt
├── run.ps1
├── run.sh
├── setup.ps1
└── setup.sh
```

## Why this is ready to grow

The current architecture already separates:

- Telegram handlers
- Bet365 extraction
- persistent subscription state
- global league/fixture state
- periodic monitoring

That means future steps can extend the system without redesigning the core:

- richer date parsing from Bet365
- better match formatting
- extra commands for subscription management
- more precise odds-change rules
- support for other platforms later, if you decide to add them

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
- `/ping`: replies with `pong`
- `/status`: reports that the bot is online
- `/echo <text>`: echoes back the provided text
- `/track_url <url>`: extract a Bet365 league and store it as pending
- `/confirm_track`: confirm the latest pending league for the current chat
- `/list_tracks`: list tracked leagues for the current chat
- `/refresh_tracks`: refresh the tracked leagues for the current chat
- `/matches`: browse stored active matches by numeric selection
- `/untrack`: stop tracking one league by numeric selection
- `/odds_on`: enable odds-change notifications for one league by numeric selection
- `/odds_off`: disable odds-change notifications for one league by numeric selection
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

## Notifications

### New match

When a new `fixture_id` appears, the bot sends a notification to chats where:

- the subscription is enabled
- `notify_new_matches = true`

### Odds change

When `odds_home`, `odds_draw`, or `odds_away` changes, the bot sends a
notification to chats where:

- the subscription is enabled
- `notify_odds_changes = true`

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

## Untracking

Use:

```text
/untrack
```

The bot shows your tracked leagues with numbers. After selecting one:

- your chat subscription is removed
- if no enabled subscriptions remain for that league, the global league is disabled
- the stored active fixtures for that league are also cleaned

This keeps the global state lean without forcing a hard delete of the league row.

## Environment variables

Copy the example file first:

```bash
cp .env.example .env
```

Current variables:

```env
TELEGRAM_BOT_TOKEN=123456789:replace_with_your_real_token
LOG_LEVEL=INFO
BET365_REFRESH_INTERVAL_SECONDS=120
BET365_MAX_PARALLEL_PAGES=3
BET365_PAGE_LOAD_TIMEOUT_MS=60000
BET365_POST_LOAD_WAIT_MS=4000
```

### What they mean

- `TELEGRAM_BOT_TOKEN`: required BotFather token
- `LOG_LEVEL`: console logging verbosity
- `BET365_REFRESH_INTERVAL_SECONDS`: interval of the background Bet365 monitor loop
- `BET365_MAX_PARALLEL_PAGES`: max number of Bet365 pages processed in parallel
- `BET365_PAGE_LOAD_TIMEOUT_MS`: page load and runtime wait timeout
- `BET365_POST_LOAD_WAIT_MS`: extra wait after runtime readiness before extraction

## Install dependencies

With the virtual environment activated:

```bash
pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
```

## Run the bot

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
├── data
├── monitors
│   └── bet365_tracking.py
├── sandbox
├── services
│   └── bet365_extractor.py
├── storage
│   └── bet365_tracking.py
├── .env.example
├── main.py
├── README.md
└── requirements.txt
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

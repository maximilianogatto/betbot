# BetBot: Telegram Bot for Tracking Leagues and Building Weekly Watchlists

Base project for learning Python, Telegram bots, and modular monitoring
architecture.

The project now supports two clear stages:

1. tracking leagues from Telegram
2. building a weekly watchlist of imbalanced fixtures from those leagues

At this stage the project still does **not** use scraping, bookmaker logic,
or real pre-match odds. The current goal is to establish a clean foundation
before adding those pieces.

## Technologies

- Python 3.11+
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [python-dotenv](https://github.com/theskumar/python-dotenv)

## Current features

- `/start`: welcome message
- `/help`: command list
- `/ping`: replies with `pong`
- `/status`: reports that the bot is online
- `/echo <text>`: echoes back the provided text
- `/track <type> <value>`: stores a target for the current chat
- `/list_tracks`: lists saved targets for the current chat
- `/untrack <type> <value>`: removes a saved target
- `/build_watchlist`: manually builds the weekly watchlist
- `/list_watchlist`: lists the currently saved watchlist entries
- unknown command fallback: points the user to `/help`

## What the new watchlist stage does

The weekly watchlist flow works like this:

1. you track leagues with `/track league <league_code>`
2. the bot loads upcoming fixtures for the next 7 days
3. the bot loads league standings for those tracked leagues
4. the system calculates an `imbalance_score` per fixture
5. strongly uneven fixtures are stored in a watchlist
6. that saved watchlist becomes the future input for an odds provider

This separation is intentional:

- watchlist stage: "which matches look one-sided on paper?"
- odds stage: "is that match listed pre-match and are the odds interesting?"

## Project structure

```text
.
├── alerts
│   ├── __init__.py
│   └── telegram_alerts.py
├── bot
│   ├── __init__.py
│   ├── alerts.py
│   ├── application.py
│   ├── config.py
│   ├── error_handler.py
│   ├── handlers.py
│   └── jobs.py
├── data
│   └── .gitkeep
├── jobs
│   ├── __init__.py
│   └── scheduler.py
├── monitors
│   ├── __init__.py
│   ├── imbalance.py
│   ├── rules.py
│   ├── tracker.py
│   └── watchlist_builder.py
├── sandbox
│   ├── .env.example
│   ├── bet365_probe.py
│   ├── README.md
│   └── vendor
│       └── .gitkeep
├── services
│   ├── __init__.py
│   ├── football_data_provider.py
│   ├── odds_provider.py
│   └── sports_api.py
├── storage
│   ├── __init__.py
│   ├── tracks.py
│   └── watchlist.py
├── .env.example
├── .gitignore
├── main.py
├── README.md
└── requirements.txt
```

## Environment variables

Copy the example file first:

```bash
cp .env.example .env
```

Current variables:

```env
TELEGRAM_BOT_TOKEN=123456789:replace_with_your_real_token
LOG_LEVEL=INFO
FOOTBALL_DATA_PROVIDER=mock
FOOTBALL_DATA_API_KEY=
WATCHLIST_DAYS_AHEAD=7
WATCHLIST_IMBALANCE_THRESHOLD=60
```

### What they mean

- `TELEGRAM_BOT_TOKEN`: required BotFather token
- `LOG_LEVEL`: console logging verbosity
- `FOOTBALL_DATA_PROVIDER`: current source of fixtures and standings
  - today: `mock`
  - future: a real API-backed provider
- `FOOTBALL_DATA_API_KEY`: reserved for future API integrations
- `WATCHLIST_DAYS_AHEAD`: fixture window used by `/build_watchlist`
- `WATCHLIST_IMBALANCE_THRESHOLD`: minimum score required to save a fixture in
  the watchlist

## How to create the bot with BotFather

1. Open Telegram and search for `@BotFather`.
2. Start the chat with `/start`.
3. Run `/newbot`.
4. Choose a display name.
5. Choose a unique username ending in `bot`.
6. Copy the token returned by BotFather.
7. Put that token in your local `.env`.

## How to create and activate a virtual environment on macOS/zsh

From the project folder:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

If `python3.11` is unavailable:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Install dependencies

With the virtual environment activated:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Run the bot

```bash
python main.py
```

If everything is configured correctly, the bot will start polling Telegram and
logging to the console.

## Track leagues from Telegram

Track one league:

```text
/track league premier_league
```

Track another one:

```text
/track league la_liga
```

List tracked targets:

```text
/list_tracks
```

Remove one:

```text
/untrack league la_liga
```

## Build the weekly watchlist manually

Once at least one league is tracked, run:

```text
/build_watchlist
```

The bot will:

1. read tracked league codes from local storage
2. ask the configured football-data provider for fixtures in the next 7 days
3. ask the same provider for standings
4. calculate an `imbalance_score`
5. save the selected fixtures in the local watchlist

## List the saved watchlist

```text
/list_watchlist
```

Each saved watchlist entry includes:

- league code and league name
- home team
- away team
- kickoff datetime
- `imbalance_score`
- simple reasons that explain why the fixture was selected
- `odds_seen`
- `alert_sent`

## How `imbalance_score` works

The current score is a simple composite based on standings only:

- difference in table position
- difference in points
- difference in goal difference

That makes the current system intentionally conservative and easy to reason
about. It is not trying to predict odds; it is only trying to flag fixtures
that already look uneven from basic league performance data.

## Current provider behavior

The current implementation uses `services/football_data_provider.py` with a
`MockFootballDataProvider`.

That means:

- no external API is required
- `/build_watchlist` is fully testable locally
- the architecture is already prepared for a future real provider

Unknown tracked leagues are simply skipped during watchlist construction and
reported back in the build summary.

## Local persistence

### Tracked targets

Stored in:

```text
data/tracks.json
```

Shape:

```json
{
  "chats": [
    {
      "chat_id": 123,
      "targets": [
        {
          "type": "league",
          "key": "premier_league"
        }
      ]
    }
  ]
}
```

### Weekly watchlists

Stored in:

```text
data/watchlists.json
```

Shape:

```json
{
  "chats": [
    {
      "chat_id": 123,
      "generated_at": "2026-04-12T12:00:00+00:00",
      "matches": [
        {
          "fixture_id": "epl-001",
          "league_code": "premier_league",
          "league_name": "Premier League",
          "home_team": "Arsenal",
          "away_team": "Ipswich",
          "kickoff_at": "2026-04-14T18:00:00+00:00",
          "imbalance_score": 82.5,
          "reasons": [
            "Arsenal is 17 places above Ipswich in the table."
          ],
          "odds_seen": false,
          "alert_sent": false
        }
      ]
    }
  ]
}
```

## Main architectural responsibilities

- `bot/`: Telegram-specific interface
- `storage/`: local persistence
- `services/`: data sources and provider interfaces
- `monitors/`: analysis logic and watchlist construction
- `sandbox/`: isolated playground for external Bet365 experiments

## Why the watchlist is separate from odds

This is one of the most important design decisions in the project.

The weekly watchlist is intentionally built **before** checking odds.

Why:

- it keeps the first signal independent from bookmakers
- it makes the project testable without scraping or betting APIs
- it lets you validate the analysis stage first
- it makes later odds integration cleaner and easier to replace

Future odds flow:

1. build watchlist from fixtures + standings
2. query a separate odds provider for those saved fixtures
3. mark `odds_seen=True` when a fixture appears pre-match
4. evaluate odds-specific alert rules
5. send Telegram alerts and mark `alert_sent=True`

## Sandbox for Bet365 GitHub experiments

The folder `sandbox/` is purposely isolated from the main bot.

Use it to:

- clone external Bet365-related GitHub wrappers under `sandbox/vendor/`
- run local experiments without polluting the main architecture
- inspect raw API or wrapper responses
- design the future `services/odds_provider.py` interface

Basic flow:

1. copy `sandbox/.env.example` to `sandbox/.env`
2. adjust the base URL, path, and headers
3. run:

```bash
python sandbox/bet365_probe.py
```

This probe is not part of the production bot. It is only a safe playground for
research and validation.

## Placeholder modules already prepared for the next stages

- `bot/alerts.py`: watchlist-alert interface without odds
- `bot/jobs.py`: placeholder weekly watchlist job
- `services/odds_provider.py`: future pre-match odds interface
- `jobs/scheduler.py`: generic async orchestration pattern for future monitors

## Suggested roadmap from here

### Stage 1: done now

- track leagues from Telegram
- build a weekly watchlist of uneven fixtures
- persist everything locally

### Stage 2

- implement a real football-data provider
- improve league coverage
- enrich fixture metadata if needed

### Stage 3

- implement `services/odds_provider.py`
- check whether saved watchlist fixtures appear pre-match
- update `odds_seen`

### Stage 4

- add rule-based alerting on top of odds availability
- send Telegram alerts only when your criteria are met
- update `alert_sent`

### Stage 5

- replace manual `/build_watchlist` with a scheduled weekly job
- combine weekly watchlist building with periodic odds checks

The important part is that the project is now structured to grow into that
pipeline without mixing everything in the Telegram handlers.

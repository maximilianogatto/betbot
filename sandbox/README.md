# Sandbox for External Bet365 Experiments

This folder is intentionally isolated from the main bot flow.

Use it to test third-party Bet365-related wrappers, GitHub repos, or local
HTTP services without coupling unstable experiments to the production bot
architecture.

## Goal of the sandbox

The core project currently stops at:

1. tracking leagues
2. building a weekly watchlist of imbalanced fixtures
3. saving those fixtures locally

The sandbox exists for the *next* step: trying odds-oriented integrations
before deciding how a future `services/odds_provider.py` should look.

## Suggested workflow

1. Copy `.env.example` to `.env`.
2. Clone or copy a GitHub repo into `sandbox/vendor/`.
3. If the repo exposes an HTTP API locally, point `BET365_PROBE_BASE_URL`
   and `BET365_PROBE_PATH` to that service.
4. Run `python sandbox/bet365_probe.py` from the project root.
5. Inspect the raw JSON response and only after that decide how to map it into
   the future odds-provider interface.

## Why this folder is separate

- GitHub Bet365 wrappers are often experimental and unstable.
- Their response format may differ a lot from one repo to another.
- The main bot should stay clean and focused on track -> fixtures -> watchlist.

## Important design rule

Do not make the Telegram bot depend directly on sandbox code.

When you find a source you trust, the clean migration path is:

1. keep the raw experiment in `sandbox/`
2. design a stable adapter under `services/odds_provider.py`
3. connect that adapter later to watchlist enrichment jobs
4. only then integrate Telegram alerts based on real odds

## Example future roadmap

- `services/watchlist_builder.py`: creates candidate fixtures from standings
- `storage/watchlist.py`: saves those candidates
- `services/odds_provider.py`: checks if the fixture exists pre-match
- `bot/alerts.py`: sends Telegram alerts when odds and rules match

That way, the watchlist remains your "what looks interesting?" stage, and the
odds provider becomes your "is this actually listed and worth notifying?" stage.

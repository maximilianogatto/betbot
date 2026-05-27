# Sportradar HTTP Sandbox

Research-only sandbox for building a production-oriented Statshub/Sportradar
HTTP replay layer.

This folder must stay isolated from `core/`, `bot/`, `extractors/`,
`storage/`, and the production DB until the interface is stable.

## Phase 1: Session Bootstrap

Goal:

1. Open a minimal browser bootstrap page.
2. Capture the signed `T` token, cookies, and replay headers.
3. Produce a reusable HTTP session context.
4. Compare headed vs headless behavior.

The intended architecture is:

```text
browser bootstrap -> signed token/cookies/headers -> HTTP replay client
```

## Current Status

Phase 1 is implemented in `session_manager.py`.
Phase 2 is implemented in `http_client.py`.
Phase 3 endpoint wrappers live in `endpoints/`.
Phase 4 league snapshots/features live in `run_league_pipeline.py`.
Phase 5 match snapshots/features live in `run_match_pipeline.py`.
Tournament navigation lives in `run_tournament_navigation.py`.
The stable bot-ready match intelligence schema lives in `match_intelligence.py`.

## Run Phase 1 Bootstrap

Compare headless vs headed:

```bash
./betbot/bin/python sandbox/sportradar_http/bootstrap_session.py \
  --compare \
  --seconds 4 \
  --out-dir sandbox/sportradar_http/reports/session_bootstrap
```

Run only headed when headless is blocked:

```bash
./betbot/bin/python sandbox/sportradar_http/bootstrap_session.py \
  --headed \
  --seconds 4 \
  --out-dir sandbox/sportradar_http/reports/session_bootstrap_headed
```

Outputs:

- `session_state_headless.json`
- `session_state_headed.json`
- `session_bootstrap_report.md`

## Programmatic Use

```python
from sandbox.sportradar_http.session_manager import BootstrapConfig, SportradarSessionManager
from sandbox.sportradar_http.http_client import SportradarHTTPClient

manager = SportradarSessionManager(BootstrapConfig(headed=True))
state = manager.refresh_session()

client = SportradarHTTPClient(session_state=state, session_manager=manager)
payload = client.get_gismo("match_markets/61624678")
```

The returned HTTP client is configured with:

- `origin: https://statshub.sportradar.com`
- `referer: https://statshub.sportradar.com/`
- captured cookies
- captured user-agent/language hints when available

## Limitations

- This phase does not implement endpoint wrappers yet.
- This phase does not generate or crack signed tokens.
- Headless bootstrap can be blocked with 403 depending on environment.
- If the token expires, `refresh_session()` must run browser bootstrap again.

## HTTP Client Behavior

`SportradarHTTPClient` does pure HTTP replay and does not import Playwright.
It can refresh only through a provided `SportradarSessionManager`.

It detects:

- blocked JSON payloads
- expired token/signature payloads
- empty payloads
- invalid JSON
- HTTP errors

It tracks:

- request count
- success/block/expired counts
- retry count
- refresh count
- endpoint timing summaries

## Endpoint Wrappers

Use wrappers instead of raw URLs:

```python
from sandbox.sportradar_http.endpoints.odds import get_match_markets
from sandbox.sportradar_http.endpoints.standings import get_season_tables

markets = get_match_markets(client, match_id=61624678)
table = get_season_tables(client, season_id=130805)
```

The generated endpoint map is:

```bash
./betbot/bin/python sandbox/sportradar_http/build_endpoint_catalog.py
```

Output:

- `sandbox/sportradar_http/reports/endpoint_catalog_v2.md`

## Real HTTP Replay Examples

Run the end-to-end Phase 2/3 smoke test:

```bash
./betbot/bin/python sandbox/sportradar_http/run_http_client_examples.py --seconds 4
```

This uses browser only for refresh/bootstrap when required, then performs pure
HTTP replay for:

- fixtures
- fixture market references / odds-server candidate
- match markets
- standings
- form table
- team last matches
- team streaks

Outputs:

- `sandbox/sportradar_http/examples/http_client/success_examples.json`
- `sandbox/sportradar_http/examples/http_client/blocked_example.json`
- `sandbox/sportradar_http/examples/http_client/refresh_example.json`
- `sandbox/sportradar_http/examples/http_client/http_replay_snapshot.json`
- `sandbox/sportradar_http/reports/http_client_report.md`

## Tournament Navigation

Resolve a Statshub tournament URL id into the concrete current season and list
fixtures:

```bash
./betbot/bin/python sandbox/sportradar_http/run_tournament_navigation.py \
  --sport-id 1 \
  --tournament-id 18340 \
  --out-dir sandbox/sportradar_http/examples/tournament_18340
```

Outputs:

- `tournament_navigation.json`
- `tournament_fixtures.json`
- `tournament_navigation_report.md`

Validated example:

- `tournament_id=18340` maps to `Australia / South Australia NPL, Women`
- URL-facing id matched as `unique_tournament_id`
- current `season_id=138964`
- fixtures returned by `stats_season_fixtures2`

This is the stable navigation bridge for:

```text
sport -> tournaments -> season fixtures -> match_id -> match intelligence
```

To inspect a selected fixture, pass its `match_id` to `run_match_pipeline.py`.

It does not render Telegram. It produces compact JSON that a future BetBot
provider can consume.

## League Pipeline

Run a compact league collection using browser only for session bootstrap and
HTTP replay for the actual data:

```bash
./betbot/bin/python sandbox/sportradar_http/run_league_pipeline.py \
  --sport-id 1 \
  --tournament-id 8 \
  --season-id 130805 \
  --out-dir sandbox/sportradar_http/examples/league_laliga
```

Outputs:

- `league_snapshot.json`
- `league_features.json`
- `league_report.md`

The snapshot keeps normalized data and raw references separate. It intentionally
does not embed full raw payload dumps.

Current league pipeline endpoints:

- `stats_season_leaguesummary`
- `stats_season_teams2`
- `stats_season_fixtures2`
- `stats_season_tables`
- `stats_formtable`
- `stats_season_venues`
- `stats_season_injuries`
- `stats_season_topgoals`
- `stats_season_topcards`
- `stats_season_topassists`
- sampled `stats_season_teamscoringconceding`
- sampled `stats_team_streaks`

Feature values are explicitly documented in `league_features.json` and
`league_report.md`. For example, Statshub league outcome fields such as
`home_wins`, `draws`, and `away_wins` were observed as percentages, so the
normalizer stores them as rates in the `0..1` range.

## Match Pipeline

Build a compact match snapshot, feature document, and Markdown report:

```bash
./betbot/bin/python sandbox/sportradar_http/run_match_pipeline.py \
  --match-id 61624678 \
  --out-dir sandbox/sportradar_http/examples/match_61624678
```

Outputs:

- `match_snapshot.json`
- `match_features.json`
- `match_intelligence.json`
- `match_report.md`
- `match_intelligence_report.md`

Current match pipeline endpoints:

- `match_info_statshub`
- `stats_match_get`
- `match_markets`
- `match_details`
- `stats_match_tableslice`
- `stats_match_head2head`
- `match_timeline`
- `match_timelinedelta`
- `stats_match_situation`
- `stats_team_lastx`
- `stats_team_nextx`
- `stats_team_streaks`
- `stats_season_teamscoringconceding`
- `stats_season_topgoals`
- `stats_season_topcards`
- `stats_season_topassists`
- `stats_season_injuries`
- `stats_team_versus`
- `stats_h2h_versus`

The report explicitly distinguishes:

- `has_odds_endpoint`: `match_markets` responded.
- `has_priced_odds`: the response contained usable 1X2, handicap, or totals markets.

This matters because ended matches can have full stats and live history while
returning an empty `match_markets` payload.

`match_intelligence.json` is the compact interface intended for future BetBot
presentation. It keeps Telegram rendering out of the data layer and exposes:

- teams, competition, kickoff, status, and score
- form ratings with dated last matches
- H2H edge with dated historical matches
- table context
- strength indexes
- injuries
- goal context
- top players
- traceability evidence
- a compact `report_summary`

Historical evidence in H2H and traceability always includes dates because stale
results should not be weighted the same as recent matches.

## Bot-Ready Adapter

The research-only adapter lives in `bot_ready/` and exposes stable methods that
can later be wired into BetBot behind a production provider interface:

```python
from sandbox.sportradar_http.bot_ready import (
    BotReadyLeagueRequest,
    BotReadyMatchRequest,
    SportradarBotReadyProvider,
)

provider = SportradarBotReadyProvider()
match_package = provider.get_match_report(BotReadyMatchRequest(match_id=61624678))
league_package = provider.get_league_snapshot(BotReadyLeagueRequest(sport_id=1, tournament_id=8, season_id=130805))
live_state = provider.get_live_match_state(BotReadyMatchRequest(match_id=61624678))
```

These methods still live in sandbox and intentionally do not import `bot/`,
`core/`, `extractors/`, `storage/`, or the production DB.

## Feature Catalog

Generate the feature catalog:

```bash
./betbot/bin/python sandbox/sportradar_http/build_feature_catalog.py
```

Output:

- `sandbox/sportradar_http/reports/feature_catalog.md`

The catalog documents formulas, scales, directionality, and which values are
raw football units versus normalized rates.

## Live Probe

Run a controlled live/delta polling probe:

```bash
./betbot/bin/python sandbox/sportradar_http/run_live_probe.py \
  --match-id 61624678 \
  --polls 2 \
  --interval 1 \
  --out-dir sandbox/sportradar_http/examples/live_probe_61624678
```

Outputs:

- `live_probe.ndjson`
- `live_probe_summary.json`
- `live_probe_report.md`

The probe stores compact live state documents per poll. It is meant to compare
`match_timeline`, `match_timelinedelta`, and `stats_match_situation` behavior
without keeping a browser open.

## Viability Report

Current provider viability notes are in:

- `sandbox/sportradar_http/reports/provider_viability.md`

Summary: this is already viable as a stats/report provider with browser
bootstrap plus HTTP replay. Odds endpoints are reachable, but active prematch or
live priced-market validation is still required before using it as an odds
provider.

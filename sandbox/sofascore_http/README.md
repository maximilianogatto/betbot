# SofaScore HTTP Stats Provider Research

This sandbox investigates SofaScore as a future BetBot stats provider without
touching production code. The result is intentionally split into two paths:

1. Playwright is an offline discovery tool for observing API traffic.
2. `curl_cffi` is the runtime candidate for HTTP-only discovery and snapshots.

The current tests show that the provider path does not require a persistent
browser, browser cookies, or a bootstrap token. Plain `httpx` requests received
`403 Forbidden` from the current network even when browser headers and cookies
were replayed. The same public API URLs returned JSON through `curl_cffi`.

## Files

| File | Purpose |
| --- | --- |
| `capture_traffic.py` | Opens one SofaScore page briefly with Playwright and records only useful `/api/` JSON responses. |
| `probe_http.py` | Replays captured URLs with `httpx` variants and `curl_cffi` to compare transport viability. |
| `client.py` | HTTP-only research client with defensive wrappers for discovery, fixtures, live state, stats and odds. |
| `normalizers.py` | Pure compact normalizers for leagues, fixtures, odds, incidents and match snapshots. |
| `build_match_snapshot.py` | Builds one compact HTTP-only match snapshot from a SofaScore event ID. |
| `probe_provider.py` | Runs an HTTP-only end-to-end feasibility probe: countries, leagues, fixtures, live events and one optional match. |
| `bot_ready/provider.py` | Implements BetBot's real `StatsProvider` interface without registering SofaScore in production. |
| `reporting.py` | Renders compact provider-level Markdown from one normalized snapshot. |
| `validate_bot_ready.py` | Validates country -> league -> fixtures -> standings -> report through the future bot contract. |

## Requirements

Use the BetBot virtual environment. Playwright is needed only for manual
discovery captures. Runtime probes use `curl_cffi`.

```bash
../BetBot/betbot/bin/python -c "import playwright, curl_cffi"
```

## Discovery Capture

Capture the homepage endpoint inventory:

```bash
../BetBot/betbot/bin/python sandbox/sofascore_http/capture_traffic.py \
  "https://www.sofascore.com/es-la" \
  --seconds 8 \
  --out-dir sandbox/sofascore_http/captures/home
```

Capture a match page:

```bash
../BetBot/betbot/bin/python sandbox/sofascore_http/capture_traffic.py \
  "https://www.sofascore.com/es-la/football/match/zed-fc-al-masry/kwrstnZc#id:16200011" \
  --seconds 8 \
  --out-dir sandbox/sofascore_http/captures/live_match
```

The capture runs headless by default. Use `--headed` only when investigating a
browser-only failure. Raw captures are ignored by Git because they can include
cookies and large response bodies.

Capture outputs:

- `responses.ndjson`
- `endpoints_index.json`
- `endpoint_report.md`
- `capture_metadata.json`
- `storage_state.json`

## HTTP Replay Comparison

```bash
../BetBot/betbot/bin/python sandbox/sofascore_http/probe_http.py \
  sandbox/sofascore_http/captures/live_match
```

This writes:

- `http_probe_results.json`
- `http_probe_report.md`

## HTTP-only Provider Probe

Run country/league discovery, fixture discovery, live discovery and an optional
match snapshot without Playwright:

```bash
../BetBot/betbot/bin/python sandbox/sofascore_http/probe_provider.py \
  --date 2026-06-01 \
  --category-id 34 \
  --event-id 16200011 \
  --out-dir sandbox/sofascore_http/examples/http_only_probe
```

Build only a compact event snapshot:

```bash
../BetBot/betbot/bin/python sandbox/sofascore_http/build_match_snapshot.py \
  16200011 \
  --out sandbox/sofascore_http/captures/live_16200011/match_snapshot.json
```

## Bot-ready Contract Validation

The adapter stays under `sandbox/`, but already implements the production
`StatsProvider` interface. It uses current-season `next/0` and `last/0` pages
instead of expensive date-by-date or full-season scans.

```bash
../BetBot/betbot/bin/python sandbox/sofascore_http/validate_bot_ready.py \
  --country Australia \
  --query "Northern NSW" \
  --league-id 1638 \
  --event-id 16200011 \
  --out-dir sandbox/sofascore_http/examples/bot_ready_validation
```

This writes:

- `bot_ready_validation.json`
- `bot_ready_validation.md`

The adapter adds:

- one reusable `curl_cffi.Session`;
- an in-memory TTL cache;
- serialized requests with a conservative rate limit;
- optional compatibility with BetBot's existing payload-cache protocol;
- tolerant team-name and kickoff matching;
- standings normalization and compact reports.

## Useful Endpoint Families

Discovery and fixtures:

- `sport/football/categories/all`
- `category/<id>/unique-tournaments`
- `unique-tournament/<id>/seasons`
- `unique-tournament/<id>/season/<id>/events/last/<page>`
- `unique-tournament/<id>/season/<id>/events/next/<page>`
- `unique-tournament/<id>/season/<id>/standings/total`
- `sport/football/scheduled-events/<date>`
- `sport/football/events/live`

Match state and stats:

- `event/<id>`
- `event/<id>/statistics`
- `event/<id>/incidents`
- `event/<id>/lineups`
- `event/<id>/h2h`
- `event/<id>/win-probability`
- `event/<id>/odds/1/all`

The APIs are unofficial. A production adapter must use conservative polling,
caching, rate limiting and a circuit breaker. Endpoint schemas and access
behavior may change without notice.

## Current Recommendation

Do not integrate this sandbox directly into Telegram handlers. The next step is
to move the validated adapter into `stats_providers/sofascore_http`, add
`curl_cffi` to production requirements and register the provider behind an
environment flag, keeping:

- league discovery independent from odds collectors;
- SofaScore event IDs as provider-specific external IDs;
- compact normalized snapshots at the provider boundary;
- Playwright completely outside the runtime path.

See `reports/http_feasibility.md` for the evidence summary.

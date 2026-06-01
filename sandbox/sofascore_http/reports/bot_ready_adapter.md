# SofaScore Bot-ready Adapter

## Scope

Validated on June 1, 2026 without Playwright after the initial endpoint
discovery. The adapter remains isolated under `sandbox/sofascore_http/bot_ready`
and is not registered in BetBot production.

## Stable Flow

```text
country
  -> sport/football/categories/all
  -> category/<id>/unique-tournaments
  -> unique-tournament/<id>/seasons
  -> unique-tournament/<id>/season/<season>/events/next/0
  -> unique-tournament/<id>/season/<season>/events/last/0
  -> fixture identity matching
  -> event/<id> compact snapshot
  -> provider-level Markdown report
```

## Runtime Characteristics

- Transport: `curl_cffi`
- Persistent browser: not required
- Browser bootstrap: not required
- HTTP session reuse: enabled
- Request serialization: enabled
- Default minimum interval between HTTP requests: `0.15s`
- Default in-memory TTL cache: `30s`
- Optional BetBot payload-cache compatibility: implemented

## Real Validation

The committed example validates:

- Country: `Australia`
- League query: `Northern NSW`
- Unique tournament ID: `1638`
- Match report event ID: `16200011`

Observed HTTP-only output:

- 5 league options matching the query;
- 60 deduplicated recent/upcoming fixtures;
- 1 standings table;
- compact match report with score, stats, H2H, incidents and available odds.

## Production Promotion Checklist

1. Move the adapter into `stats_providers/sofascore_http`.
2. Add `curl_cffi` to `requirements.txt`.
3. Register the provider behind an environment flag.
4. Reuse the existing SQLite stats payload cache.
5. Add provider URL detection in `StatsService` only if direct SofaScore URLs
   should auto-link.
6. Keep Playwright discovery scripts in the sandbox.

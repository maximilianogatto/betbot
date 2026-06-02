# FootyStats HTTP Provider

Production-facing adapter for FootyStats behind BetBot's generic
`StatsProvider` contract.

## Current scope

The default adapter intentionally uses a narrow public HTTP fallback:

- country and league discovery from the public homepage
- league standings from server-rendered HTML
- league fixtures from embedded `mh_matchData`
- public H2H URL generation per fixture
- lightweight live score lookup through `ajax_livescore.php`

It does not use Playwright, synthetic browser headers or DOM automation.
Normalized snapshots are cached through BetBot's shared SQLite payload cache;
raw HTML is not persisted.

## Licensed API

The HTTP client accepts `FOOTYSTATS_API_KEY` for the documented
`api.football-data-api.com` surface. Rich official API normalization is kept as
an incremental next step because public fallback and licensed endpoints have
different stability contracts.

## Configuration

```env
FOOTYSTATS_ENABLED=true
# FOOTYSTATS_API_KEY=
```

The daily cache is shared with the generic stats job:

```env
STATS_PREFETCH_ENABLED=true
STATS_PREFETCH_INTERVAL_SECONDS=86400
STATS_PREFETCH_TTL_SECONDS=90000
```

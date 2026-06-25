# FootyStats HTTP Provider

Production-facing adapter for FootyStats behind BetBot's generic
`StatsProvider` contract.

## Current scope

The default adapter exposes a narrow public surface:

- country and league discovery from the public homepage
- league standings from server-rendered HTML
- league fixtures from embedded `mh_matchData`
- public H2H URL generation per fixture
- lightweight live score lookup through `ajax_livescore.php`

Normalized snapshots are cached through BetBot's shared SQLite payload cache;
raw HTML is not persisted.

## Cloudflare challenge

As of mid-2026 footystats.org serves every public **HTML** page behind a
Cloudflare Managed Challenge (`cf-mitigated: challenge` + Turnstile). Plain
httpx, `curl_cffi` TLS impersonation and headless Playwright are all answered
with HTTP 403. The adapter therefore fetches HTML pages through a headed,
challenge-clearing browser (`cloudflare_browser.CloudflareBrowserFetcher`,
built on `patchright` + real Chrome): the first navigation solves the
interactive Turnstile, and a single warm, persistent context reuses the
`cf_clearance` cookie for fast subsequent loads. The compact `ajax_livescore.php`
feed and the licensed API are **not** challenged and stay on plain httpx.

Requirements: `pip install patchright` and a real Chrome install
(`patchright install chromium` provides a fallback). The browser is launched
lazily on the first HTML fetch, so startup is unaffected.

```env
# Headed Chrome is required to pass the challenge; headless is detected (403).
FOOTYSTATS_BROWSER_HEADLESS=false
FOOTYSTATS_BROWSER_CHANNEL=chrome        # falls back to bundled chromium
# FOOTYSTATS_BROWSER_PROFILE=<dir>       # default: stats_providers/footystats_http/.chrome_profile
```

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

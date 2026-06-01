# SofaScore HTTP Provider Feasibility

## Scope

Tested on June 1, 2026 against `https://www.sofascore.com/es-la` and a live
football match page. Playwright was used only to observe browser API traffic.
All provider probes after discovery were executed without a browser.

## Transport Result

| Client mode | Result | Notes |
| --- | --- | --- |
| `httpx` bare | Blocked | Useful API requests returned `403 Forbidden`. |
| `httpx` with browser-like headers | Blocked | `User-Agent`, `Referer`, language and accept headers did not change the result. |
| `httpx` with captured browser headers | Blocked | Replaying `x-requested-with` and captured request headers still returned `403`. |
| `httpx` with captured headers and Playwright cookies | Blocked | Browser cookies did not change the result. |
| `curl_cffi` bare | Usable | Core public endpoints returned JSON without cookies or a bootstrap token. |

The relevant difference is the HTTP client transport fingerprint, not an
application-level token captured from Playwright.

## Real HTTP-only Probe

The committed probe sample in `examples/http_only_probe` used:

- category ID `34` for Australia;
- event ID `16200011` for `Al-Masry vs ZED FC`;
- `curl_cffi` only;
- no browser bootstrap.

Observed results:

- 296 football categories;
- 68 Australian football tournaments;
- 200 scheduled football events for the tested date;
- 27 live football events at capture time;
- match metadata, score, clock, incidents, lineups, H2H, win probability,
  statistics and live 1X2 odds for the selected event.

## Useful Data

League discovery can support a future `/link_stats` flow through:

`sport/football/categories/all -> category/<id>/unique-tournaments`

Prematch and live fixture discovery can use:

- `sport/football/scheduled-events/<date>`
- `sport/football/events/live`
- season event pages under `unique-tournament/<id>/season/<id>/events/...`

Match intelligence can use:

- `event/<id>` for metadata, status, score and clock;
- `event/<id>/statistics` for possession, corners, cards and shots when covered;
- `event/<id>/incidents` for dated timeline evidence;
- `event/<id>/lineups`;
- `event/<id>/h2h`;
- `event/<id>/win-probability`;
- `event/<id>/odds/1/all`.

## Limits

- This is an unofficial API and can change without notice.
- Some endpoints legitimately return `404` when a market or optional coverage
  document is absent.
- Odds are provider-specific and should remain optional in a stats provider.
- Runtime polling needs rate limiting, caching and backoff before production
  integration.

## Recommendation

SofaScore is viable as an HTTP-only stats provider candidate. Keep Playwright
as an offline discovery tool only. A future production adapter should depend on
the small `curl_cffi` HTTP surface, normalize external IDs at its boundary and
avoid coupling SofaScore schemas to Telegram handlers or tracking storage.

# SofaScore HTTP-only Provider Probe

- Generated at: `2026-06-01T15:57:36.372849+00:00`
- Transport: `curl_cffi_http_only`
- Browser required after discovery: `False`
- Date: `2026-06-01`
- Category ID: `34`

## Discovery

- Football categories: `296`
- Tournaments in selected category: `68`
- Scheduled events on date: `200`
- Live football events: `27`

## Useful HTTP endpoints

- `sport/football/categories/all`: country/category discovery.
- `category/<id>/unique-tournaments`: league discovery.
- `unique-tournament/<id>/seasons`: season discovery.
- `sport/football/scheduled-events/<date>`: prematch fixture discovery.
- `sport/football/events/live`: live fixture discovery.
- `event/<id>`: event metadata, status, score and clock.
- `event/<id>/statistics`: match statistics when covered.
- `event/<id>/incidents`: goals, cards, substitutions and period markers.
- `event/<id>/lineups`: lineups when covered.
- `event/<id>/h2h`: compact H2H counters.
- `event/<id>/win-probability`: SofaScore probability model when covered.
- `event/<id>/odds/1/all`: provider-specific odds, including live 1X2.

## Match sample

- Match: `Al-Masry vs ZED FC`
- SofaScore event ID: `16200011`
- Status: `inprogress` / `2nd half`
- Score: `1-0`
- Coverage: `{"has_event": true, "has_h2h": true, "has_incidents": true, "has_lineups": true, "has_odds": true, "has_statistics": true, "has_win_probability": true}`

## Conclusion

SofaScore is viable as an HTTP-only stats-provider candidate when requests use `curl_cffi`. Plain `httpx` replay returned `403` for every tested URL, while `curl_cffi` returned JSON without browser cookies or a bootstrap token. Keep Playwright only as an offline endpoint-discovery tool.

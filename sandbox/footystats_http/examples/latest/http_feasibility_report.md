# FootyStats HTTP Feasibility

Generated at `2026-06-01T21:41:05.774076+00:00`.

## Result

FootyStats can be queried without a browser. It exposes three distinct contracts:

1. Public server-rendered HTML pages with league discovery and rich stats.
2. Public AJAX helpers, including a browserless live-score JSON feed.
3. An official key-authenticated JSON API intended for stable integrations.

## Public HTML

- Discovered league links from homepage: `1676`.
- Australian league links: `75`.
- Embedded league match records: `132`.
- Match page IDs: `{'match_id': '8535299', 'competition_id': '15434'}`.
- Live match panel present in sampled page: `True`.

## Public AJAX

- Current live-score records: `3`.
- AJAX endpoints referenced by frontend script: `24`.

## Official JSON API

- Demo request success: `True`.
- Demo league matches returned: `380`.
- Sample odds fields: `68`.

## Recommendation

Use the official JSON API as the production candidate if a licensed key is available. Use public HTML and AJAX only as an isolated research/fallback path because their markup and undocumented endpoint contracts can change without notice.

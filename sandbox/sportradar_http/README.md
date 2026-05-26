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

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


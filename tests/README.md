# Tests

Organized into packages by area:

- `tests/bot/` — Telegram handlers, jobs, alerts.
- `tests/core/` — generic services (tracking, stats service, live-watch).
- `tests/extractors/` — one module per sportsbook extractor (+ live parsing).
- `tests/stats_providers/` — stats providers (Sportradar under `sportradar/`).

## Running

Always run from the repo root with the repo as the top-level dir, so the test
packages import as `tests.<area>.*` and don't shadow the real `bot`/`core`/
`extractors` packages:

```bash
./run_tests.sh                                   # full suite
./run_tests.sh tests.extractors.test_mrpunter_http   # one module
```

Equivalent: `python -m unittest discover -t . -s tests`.

⚠️ Do **not** use `python -m unittest discover -s tests` (without `-t .`): that
puts `tests/` on `sys.path`, so `tests/bot` shadows the real `bot` package and
discovery fails with import errors.

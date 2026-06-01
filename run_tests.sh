#!/usr/bin/env bash
# Run the test suite.
#
# Tests live in packages under tests/ (tests/bot, tests/core, tests/extractors,
# tests/stats_providers). They must be discovered with the repo root as the
# top-level dir (-t .) so the test packages import as `tests.bot.*` and do NOT
# shadow the real `bot`/`core`/`extractors` packages.
#
# Usage:  ./run_tests.sh                 # full suite
#         ./run_tests.sh tests.extractors.test_mrpunter_http   # one module
set -euo pipefail
cd "$(dirname "$0")"
PY="./betbot/bin/python"
[ -x "$PY" ] || PY="python3"
if [ "$#" -gt 0 ]; then
  exec "$PY" -m unittest "$@"
fi
exec "$PY" -m unittest discover -t . -s tests "$@"

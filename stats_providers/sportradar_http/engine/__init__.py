"""Research-only Statshub/Sportradar HTTP client sandbox."""
"""Research-only Sportradar/Statshub HTTP replay provider.

This package contains the isolated investigation layer for Bet365 Statshub data.
It deliberately lives under `sandbox/` and does not import production BetBot
modules. The intended data flow is:

1. `session_manager` does a minimal browser bootstrap and captures a signed `T`
   token plus replay headers/cookies.
2. `http_client` reuses that state to call `/gismo/` endpoints through pure HTTP.
3. `endpoints/*` maps named business calls to concrete gismo paths.
4. `normalizers` convert raw gismo JSON into compact, stable Python dicts.
5. `features_engine`, `match_intelligence`, and pipeline scripts build bot-ready
   snapshots, features, reports, and future Telegram-ready summaries.

Nothing in this package should mutate production storage or rely on Telegram.
"""

# FootyStats HTTP Research Report

Generated from live probes on June 1, 2026.

## Scope

This sandbox evaluates FootyStats as a future BetBot stats provider without
changing production code. The investigation separates three contracts:

| Contract | Example | Result | Intended role |
| --- | --- | --- | --- |
| Public HTML | `https://footystats.org/australia/northern-nsw-npl` | Reusable with minimal HTTP | Discovery and research fallback |
| Public AJAX | `https://footystats.org/ajax_livescore.php` | Reusable JSON with minimal HTTP | Lightweight live-score research |
| Official API | `https://api.football-data-api.com/league-matches?key=example&league_id=2012` | Reusable structured JSON; licensed key required for real usage | Preferred production candidate |

## Replay Matrix

The public homepage, league page and sampled match page were tested with the
same replay variants.

| Transport | Headers | Observed result |
| --- | --- | --- |
| `httpx` | Minimal defaults | `200` |
| `httpx` | Synthetic browser-like headers | `403` Cloudflare block |
| `httpx` | Headers copied from Playwright | `403` Cloudflare block |
| `curl_cffi` Chrome impersonation | Minimal defaults | `200` |
| `curl_cffi` Chrome impersonation | Synthetic browser-like headers | `403` Cloudflare block |
| Playwright headless | Browser navigation | `403` Cloudflare challenge |
| Playwright headed | Browser navigation | `403` Cloudflare challenge |

The correct public-web strategy is deliberately simple: use ordinary HTTP
requests with minimal headers. `curl_cffi` remains useful as a diagnostic
comparison, but is not required by the current public HTML or AJAX flow.

## Available Data

The public homepage exposed `1676` deduplicated league links, including `75`
Australian leagues. The sampled Northern NSW NPL page embeds league tables,
aggregates and a JavaScript match-history array. The sampled match page exposed
form, H2H and odds content; while the match was live it also exposed score,
minute, shots, shots on target, corners, possession, attacks and dangerous
attacks.

`ajax_livescore.php` returned a compact JSON feed with match ID, score and
minute. Frontend JavaScript referenced additional AJAX helpers such as
`ajax_matches.php`, `ajax_h2h_neo.php`, `ajax_hover_modal_team.php` and
`ajax_livescore_h2h.php`. These are undocumented and require narrower,
endpoint-specific research before any production dependency.

The documented official API is structurally stronger. Its public demo
`league-matches` response included fixtures, match statistics and numerous
odds fields. Documentation also advertises league lists, today's matches,
league stats, teams, players, referees, recent form, individual match details,
H2H, odds comparison and tables.

## Recommendation

Use the official JSON API as the FootyStats production adapter if a licensed
key is acceptable. Its contract is the only stable basis for a maintainable
stats provider.

Keep public HTML parsing and public AJAX calls isolated in research/fallback
code. They are useful for validating coverage and for a low-cost live-score
observer, but their markup and undocumented routes can change without notice.
Do not add Playwright to the FootyStats runtime path.


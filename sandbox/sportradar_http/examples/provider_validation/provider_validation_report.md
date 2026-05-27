# Sportradar Provider Validation Report

## Summary

- Targets: `5`
- Resolved tournaments: `5`
- Targets with fixtures: `5`
- Targets with priced odds: `0`
- Targets with H2H: `5`
- Targets with live endpoint response: `5`
- Targets with dated H2H evidence: `5`
- Failed targets: `0`

## Matrix

| Target | Category | Resolved | Fixtures | Selected match | Odds priced | Odds source | H2H dates | Traceability dates | Live events | Warnings |
|---|---|---:|---:|---|---:|---|---:|---:|---:|---|
| LaLiga (8) | top | yes | 383 | Girona vs Vallecano (61623434) | no | unified_sport_matches_markets | yes | yes | 164 | no_priced_odds, fixture_markets_error |
| A-League (136) | top | yes | 169 | Adelaide vs Sydney FC (63684367) | no | unified_sport_matches_markets | yes | yes | 144 | no_priced_odds, fixture_markets_error |
| A-League Women (1894) | women | yes | 127 | Western Sydney Wanderers vs Perth (63684953) | no | unified_sport_matches_markets | yes | yes | 117 | no_priced_odds, fixture_markets_error |
| Capital NPL 1 (1260) | minor | yes | 114 | Brindabella Blues FC vs Canberra Ol. (69194940) | no | unified_sport_matches_markets | yes | yes | 0 | no_priced_odds |
| South Australia NPL Women (18340) | women | yes | 92 | Campbelltown City SC vs Salisbury Inter (68049818) | no | unified_sport_matches_markets | yes | yes | 0 | no_priced_odds |

## Details

### LaLiga (`8`)

- Category: `top`
- Tournament: `Spain / LaLiga`
- Season id: `130805`
- Fixture count: `383`
- Selected fixture: `Girona vs Vallecano`
- Match id: `61623434`
- Kickoff UTC: `2025-08-15T17:00:00+00:00`
- Package: `sandbox/sportradar_http/examples/provider_validation/packages/8_laliga.json`
- Error: `None`

### A-League (`136`)

- Category: `top`
- Tournament: `Australia / A-League`
- Season id: `134825`
- Fixture count: `169`
- Selected fixture: `Adelaide vs Sydney FC`
- Match id: `63684367`
- Kickoff UTC: `2025-10-17T08:00:00+00:00`
- Package: `sandbox/sportradar_http/examples/provider_validation/packages/136_a_league.json`
- Error: `None`

### A-League Women (`1894`)

- Category: `women`
- Tournament: `Australia / A-League, Women`
- Season id: `135135`
- Fixture count: `127`
- Selected fixture: `Western Sydney Wanderers vs Perth`
- Match id: `63684953`
- Kickoff UTC: `2025-10-31T08:00:00+00:00`
- Package: `sandbox/sportradar_http/examples/provider_validation/packages/1894_a_league_women.json`
- Error: `None`

### Capital NPL 1 (`1260`)

- Category: `minor`
- Tournament: `Australia / Capital NPL 1`
- Season id: `140108`
- Fixture count: `114`
- Selected fixture: `Brindabella Blues FC vs Canberra Ol.`
- Match id: `69194940`
- Kickoff UTC: `2026-05-30T05:00:00+00:00`
- Package: `sandbox/sportradar_http/examples/provider_validation/packages/1260_capital_npl_1.json`
- Error: `None`

### South Australia NPL Women (`18340`)

- Category: `women`
- Tournament: `Australia / South Australia NPL, Women`
- Season id: `138964`
- Fixture count: `92`
- Selected fixture: `Campbelltown City SC vs Salisbury Inter`
- Match id: `68049818`
- Kickoff UTC: `2026-05-29T10:00:00+00:00`
- Package: `sandbox/sportradar_http/examples/provider_validation/packages/18340_south_australia_npl_women.json`
- Error: `None`

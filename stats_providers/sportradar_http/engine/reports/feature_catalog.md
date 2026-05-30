# Sportradar Feature Catalog

- Generated at: `2026-05-26T21:30:04.276095+00:00`
- Scope: research-only feature definitions for `sandbox/sportradar_http`.

## Conventions

- Positive gap features favor the home team unless the definition says otherwise.
- Rates are normalized to `0..1` when the source metric is naturally a share.
- Raw goal features keep football units, usually goals per match, and are not probabilities.
- Missing evidence must remain `None`; the feature engine must not invent values.
- `attack_strength` is a context index, not a probability or model prediction.

## League Features

- `average_points_per_match`: mean table points_per_match across teams
- `league_away_win_rate`: away result share normalized 0..1; Statshub may provide percent, otherwise count / matches_played
- `league_btts_rate`: both teams to score total / matches_played, normalized 0..1
- `league_clean_sheet_rate`: clean sheet total / matches_played, normalized 0..1
- `league_draw_rate`: draw result share normalized 0..1; Statshub may provide percent, otherwise count / matches_played
- `league_goals_per_match`: goals_total / matches_played when available; raw goal average, not normalized
- `league_home_win_rate`: home result share normalized 0..1; Statshub may provide percent, otherwise count / matches_played
- `league_over25_rate`: over 2.5 goals share from overunder['2.5']; Statshub observed value is percent, normalized 0..1
- `season_progress`: current_round / max_rounds, normalized 0..1
- `table_compactness_top5_ppm_gap`: points-per-match rank1 minus rank5; raw PPM gap

## Match Features

- `attack_strength_away`: mean(away away-split goals_for_avg, home home-split goals_against_avg); raw goals context, not probability
- `attack_strength_home`: mean(home home-split goals_for_avg, away away-split goals_against_avg); raw goals context, not probability
- `btts_tendency_index`: mean(home home-split BTTS rate, away away-split BTTS rate), normalized 0..1 when available
- `defense_weakness_away`: away team's away-split goals conceded average; higher means weaker defensive context
- `defense_weakness_home`: home team's home-split goals conceded average; higher means weaker defensive context
- `form_gap`: home recent points minus away recent points over the normalized recent-match window; positive favors home
- `goals_against_avg_away_context`: away team's away-split goals conceded average from team scoring payload
- `goals_against_avg_home_context`: home team's home-split goals conceded average from team scoring payload
- `goals_for_avg_away_context`: away team's away-split goals scored average from team scoring payload
- `goals_for_avg_home_context`: home team's home-split goals scored average from team scoring payload
- `h2h_home_edge`: (home_team_h2h_wins - away_team_h2h_wins) / h2h_sample_size, range -1..1
- `h2h_sample_size`: number of normalized direct/versus H2H matches
- `injuries_count_away`: count of normalized missing/doubtful injuries assigned to away team
- `injuries_count_home`: count of normalized missing/doubtful injuries assigned to home team
- `live_pressure_away`: away dangerous pressure share from match_situation, normalized 0..1
- `live_pressure_home`: home dangerous pressure share from match_situation, normalized 0..1
- `live_score_state`: categorical score state from live_state/final score
- `over_tendency_index`: mean attack environments for both sides: attack_strength_home and attack_strength_away; raw expected-goals context
- `points_per_match_away`: away team table points / matches played; raw PPM
- `points_per_match_home`: home team table points / matches played; raw PPM
- `table_position_gap`: away table position minus home table position; positive means home is higher in the table

## Interpretation Notes

- `attack_strength_home = mean(home home-split goals_for_avg, away away-split goals_against_avg)`.
- `attack_strength_away = mean(away away-split goals_for_avg, home home-split goals_against_avg)`.
- `over_tendency_index = mean(attack_strength_home, attack_strength_away)`, so values are in raw goals-context units.
- `btts_tendency_index` is a `0..1` share when both teams have BTTS split rates.
- `h2h_home_edge` ranges from `-1..1`; positive means H2H evidence favors the home team.
- Live pressure shares use dangerous attack counts from `stats_match_situation` and sum to `1.0` when both sides have evidence.

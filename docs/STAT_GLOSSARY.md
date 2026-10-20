# Player and team statistics glossary

Statistics available in the warehouse, from PTS/REB/AST to Game Score, PER,
Win Shares, on/off and RAPM. This inventory separates **players** and **teams**
and lists exact SQL fields and source tables. Checked against code on 2026-10-20.
It describes calculated definitions and retained API measures, not a live-data audit.

Use the [table catalog](DATA_CATALOG.md) to choose a row grain and the
[column reference](GOLD_TABLE_REFERENCE.md) for every identifier, type and key.

## Contents

- [Units, notation and aggregation](#units-notation-and-aggregation)
- [Player statistics](#player-statistics)
- [Player formulas and interpretation](#player-formulas-and-interpretation)
- [Team statistics](#team-statistics)
- [Team formulas and interpretation](#team-formulas-and-interpretation)
- [Frontend display and availability](#frontend-display-and-availability)

## Units, notation and aggregation

| Symbol / convention | Meaning |
| --- | --- |
| PTS, AST, STL, BLK, TOV, PF | Points, assists, steals, blocks, turnovers, fouls committed. |
| FGM/FGA, 2PM/2PA, 3PM/3PA, FTM/FTA | Made/attempted field goals, two-pointers, three-pointers, free throws. |
| OREB, DREB, REB | Offensive, defensive, total rebounds. |
| `p`, `t`, `o` | Player, player's team, opponent in a given game. |
| `s` | Player time share: player seconds / game-clock seconds, not divided by five-player team seconds. |
| `sum(...)` | Sum over counted appearances/games in the selected scope, through the selected round where applicable. |
| `own_*`, `opp_*` | Club and opponent measures. Legacy team-season suffixes differ from newer round-table suffixes. |
| `on_*`, `off_*` | Team performance in stored stints with the player on court, and all other team stints in scope. |
| `home_*`, `away_*`, `last5_*`, `last10_*` | Alternative subsets within the selected scope, not additional independent games. |

Counts in a game are additive at the appropriate grain. In traditional season
`mode = 'perGame'`, counting fields and minutes are averages, but games/starts
remain counts. The Gold fallback generator divides traditional counting fields
and minutes only; advanced, scoring and misc fallback rows retain their metrics.
Do not apply one blanket division rule to all four tables.

Round tables are cumulative snapshots; choose one round. Ratios are calculated
from the relevant totals/contributions, not averages of rounded game ratios.
Never add `all`, phase and `PS` scopes together. `NULL` means unavailable or
undefined, not zero. Missing inputs can propagate into cumulative calculated
rates. Some event aggregates sum only usable games and have separate sample counts.

| Stored family | Example stored value | Frontend display |
| --- | --- | --- |
| Calculated `efg_pct`, `ts_pct`, `true_shooting_pct`, rebound/usage rates, `pie`, zone shares | `0.55` | `55%` (multiply by 100 once). |
| Traditional shooting `*_percentage`; API eFG/TS/rebound percentage fields | `55.0` | `55%` (already percentage points). |
| Points-source percentages in API scoring | `55.0` | `55%`; source values are retained. |
| Calculated `ft_rate`, `assist_ratio` | `0.25`, `0.65` | Ratio or percentage with an explicit label and denominator. |
| ORtg/DRtg/NetRtg, RAPM | `115`, `110`, `5` | Points per 100 possessions; no percent sign. |
| SRS/SOS/SOV/MOV | `5` | Points per game; no percent sign. |
| PER, Game Score, PIR | `20` | Rating/index value; no percent sign. |
| API `*_ratio`, `*_share`, other `*_rate` | Source-dependent | Do not infer scale or denominator from the suffix; uncertain definitions are marked below. |

eFG% and TS% can exceed 100% in a small sample. Do not clamp every fraction to
0-1. Rates, ratings, PIR, Game Score, PER, Win Shares and RAPM have different
meanings; they cannot be substituted for one another.

## Player statistics

The source links list every player-stat table containing the field. Table grain
controls whether a value is a game line, feed aggregate, round snapshot or
season fit. Definitions below distinguish special cases. Profile dimensions
(height, age, jersey, position, identity and dates) are in the column reference.

### Box-score production, shooting and appearances

| SQL statistic | Definition / units | Read from |
| --- | --- | --- |
| `points` | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `seconds_played` | Official playing time in seconds; player seconds or aggregate team player-seconds in box scores. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats), [`app_player_round_ratings`](GOLD_TABLE_REFERENCE.md#app_player_round_ratings), [`app_player_round_win_shares`](GOLD_TABLE_REFERENCE.md#app_player_round_win_shares), [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) |
| `pir` | Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `two_pointers_made` | Successful two-point field goals (2PM). | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional) |
| `two_pointers_attempted` | Two-point field-goal attempts (2PA), including makes. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional) |
| `three_pointers_made` | Successful three-point field goals (3PM). | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `three_pointers_attempted` | Three-point field-goal attempts (3PA), including makes. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `free_throws_made` | Successful free throws (FTM). | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `free_throws_attempted` | Free-throw attempts (FTA), including makes. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `field_goals_made` | Successful two- and three-point field goals (FGM), excluding free throws. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `field_goals_attempted` | All two- and three-point field-goal attempts (FGA), including blocked attempts. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `accuracy_made` | Raw source accuracyMade measure; meaning is not established by the warehouse. Do not treat it as FG%. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats) |
| `accuracy_attempted` | Raw source accuracyAttempted measure; meaning is not established by the warehouse. Do not treat it as FGA. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats) |
| `total_rebounds` | Offensive plus defensive rebounds (REB); official team totals can include team rebounds. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `defensive_rebounds` | Rebounds recovered after the opponent's missed shot (DREB). | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `offensive_rebounds` | Rebounds recovered after the player's or club's missed shot (OREB). | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `assists` | Official credited assists (AST), including EuroLeague assists that lead to free throws. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `steals` | Official credited steals (STL). | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `turnovers` | Lost possessions charged to the player or team (TOV). | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `blocks` | Opponent field-goal attempts blocked by the player or team (BLK). | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `blocks_against` | The player's or team's field-goal attempts blocked by opponents. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional) |
| `fouls_committed` | Personal fouls charged to the player or team (PF). | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `fouls_drawn` | Opponent fouls drawn by the player or team. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats), [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional) |
| `plus_minus` | Source point margin while the player was on court; raw points, not per 100 possessions. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats) |
| `started` | Primary source starter flag used in on-court reconstruction and appearance counts. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats) |
| `started_alt` | Alternate source starter flag retained separately. | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats) |
| `games_played` | Games/appearances in the selected row scope; see table notes for counted games and series fixture counts. | [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced), [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring), [`app_season_player_stats_misc`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_misc), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats), [`app_player_round_ratings`](GOLD_TABLE_REFERENCE.md#app_player_round_ratings), [`app_player_round_win_shares`](GOLD_TABLE_REFERENCE.md#app_player_round_win_shares) |
| `games_started` | Games in which the player started; cumulative appearance count or retained feed count. | [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring), [`app_season_player_stats_misc`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_misc), [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `minutes_played` | Playing time in minutes in season feeds; traditional perGame rows use minutes per appearance. | [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced), [`app_season_player_stats_misc`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_misc) |
| `two_pointers_percentage` | Two-point shooting percentage, 100 * 2PM / 2PA, on the feed's 0-100 scale. | [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional) |
| `three_pointers_percentage` | Three-point shooting percentage, 100 * 3PM / 3PA, on the feed's 0-100 scale. | [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional) |
| `free_throws_percentage` | Free-throw shooting percentage, 100 * FTM / FTA, on the feed's 0-100 scale. | [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional) |
| `is_calculated` | True for a row derived by Gold (PS or a missing perGame row), false for a copied feed row. | [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced), [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring), [`app_season_player_stats_misc`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_misc) |
| `min_games` | Games threshold: floor(distinct played rounds in scope / 2) + 1; FF uses 1. | [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced), [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring), [`app_season_player_stats_misc`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_misc) |
| `qualified` | Player season row has games_played >= min_games; this is not qualification for the playoffs. | [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional), [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced), [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring), [`app_season_player_stats_misc`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_misc) |
| `wins` | Games won in this row's scope; source player misc values follow the API. | [`app_season_player_stats_misc`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_misc) |
| `losses` | Games lost in this row's scope; source player misc values follow the API. | [`app_season_player_stats_misc`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_misc) |
| `double_doubles` | Source count of games reaching ten in at least two categories; derived PS uses points, rebounds, assists, steals and blocks. | [`app_season_player_stats_misc`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_misc) |
| `triple_doubles` | Source count of games reaching ten in at least three categories; derived PS uses points, rebounds, assists, steals and blocks. | [`app_season_player_stats_misc`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_misc) |

### API advanced and scoring measures

| SQL statistic | Definition / units | Read from |
| --- | --- | --- |
| `effective_field_goal_percentage` | API eFG percentage on the 0-100 scale; calculated efg_pct uses a fraction instead. | [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced) |
| `true_shooting_percentage` | API true-shooting percentage on the 0-100 scale; calculated ts_pct/true_shooting_pct use fractions. | [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced) |
| `offensive_rebounds_percentage` | API offensive rebound percentage on the 0-100 scale, retaining source team-minute conventions. | [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced) |
| `defensive_rebounds_percentage` | API defensive rebound percentage on the 0-100 scale, retaining source team-minute conventions. | [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced) |
| `rebounds_percentage` | API total rebound percentage on the 0-100 scale, retaining source team-minute conventions. | [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced) |
| `assists_to_turnovers_ratio` | API assists-to-turnovers ratio (AST/TOV), retained as supplied including source zero-denominator handling. | [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced) |
| `assists_ratio` | API assists ratio, retained without recomputation; denominator differs from calculated assist_ratio/ast_pct. | [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced) |
| `turnovers_ratio` | API turnovers ratio, retained without recomputation; not calculated tov_pct. | [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced) |
| `two_point_attempts_ratio` | API two-point attempt ratio; exact denominator and scale are not established by the warehouse. | [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced) |
| `three_point_attempts_ratio` | API three-point attempt ratio; exact denominator and scale are not established by the warehouse. | [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced) |
| `free_throws_rate` | API free-throw rate; definition differs from calculated FTM/FGA ft_rate. Do not substitute it. | [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced) |
| `possessions` | In calculated team rows: mean of the two clubs' possession estimates, summed for cumulative rows. API player feed possessions has a separate source definition. | [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced) |
| `two_point_attempts_share` | API two-point attempt share; denominator and scale are not established by the warehouse. | [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring) |
| `three_point_attempts_share` | API three-point attempt share; denominator and scale are not established by the warehouse. | [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring) |
| `free_throws_attempts_share` | API free-throw attempt share; denominator and scale are not established by the warehouse. | [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring) |
| `two_pointers_made_share` | API two-point makes share; denominator and scale are not established by the warehouse. | [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring) |
| `three_pointers_made_share` | API three-point makes share; denominator and scale are not established by the warehouse. | [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring) |
| `free_throws_made_share` | API free-throw makes share; denominator and scale are not established by the warehouse. | [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring) |
| `two_point_rate` | API two-point rate; denominator and scale are not established by the warehouse. | [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring) |
| `three_point_rate` | API three-point rate; denominator and scale are not established by the warehouse. | [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring) |
| `points_from_two_pointers_percentage` | API percentage of points from two-pointers, 0-100 scale. | [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring) |
| `points_from_three_pointers_percentage` | API percentage of points from three-pointers, 0-100 scale. | [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring) |
| `points_from_free_throws_percentage` | API percentage of points from free throws, 0-100 scale. | [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring) |

### Calculated rates, Game Score and PIE

| SQL statistic | Definition / units | Read from |
| --- | --- | --- |
| `ts_pct` | Calculated cumulative true shooting: PTS / (2 * (FGA + 0.44 * FTA)), a fraction. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `efg_pct` | (FGM + 0.5 * 3PM) / FGA, a fraction that can exceed 1. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats), [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) |
| `usg_pct` | Cumulative box-score usage estimate, ratio of summed usage contributions; not an average of game usage_pct. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `ast_pct` | Cumulative AST / sum(time share * team FGM - player FGM), a fraction; no free-throw-trip adjustment. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `orb_pct` | Offensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats), [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) |
| `drb_pct` | Defensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats), [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) |
| `trb_pct` | Total rebound share, a fraction; see glossary for player context and denominators. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats), [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) |
| `stl_pct` | Cumulative STL / sum(time share * estimated game possessions), a fraction. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `blk_pct` | Cumulative BLK / sum(time share * opponent 2PA), a fraction. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `tov_pct` | TOV / (FGA + 0.44 * FTA + TOV), a fraction. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats), [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) |
| `possessions_played` | Estimated on-court possessions: sum(player seconds / game seconds * estimated game possessions). | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `points_per_100` | 100 * cumulative points / possessions_played; rate per 100 estimated on-court possessions. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `rebounds_per_100` | 100 * cumulative total_rebounds / possessions_played; rate per 100 estimated on-court possessions. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `assists_per_100` | 100 * cumulative assists / possessions_played; rate per 100 estimated on-court possessions. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `steals_per_100` | 100 * cumulative steals / possessions_played; rate per 100 estimated on-court possessions. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `blocks_per_100` | 100 * cumulative blocks / possessions_played; rate per 100 estimated on-court possessions. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `turnovers_per_100` | 100 * cumulative turnovers / possessions_played; rate per 100 estimated on-court possessions. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `game_score_total` | Sum of Game Score over counted player appearances. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `game_score_average` | game_score_total / games_played, mean Game Score per appearance. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `pie` | Player Impact Estimate: sum(player PIE numerator) / sum(both teams' PIE numerators in those games), a fraction. | [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) |
| `game_score` | Hollinger Game Score from the player's game box score; see the exact weighted formula in the glossary. | [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) |
| `usage_pct` | Player share of used plays; actual on-court denominator when available, otherwise the game box-score estimate. | [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) |
| `assist_pct` | Player share of teammate scoring chances; on-court calculation also includes eligible free-throw trips. | [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) |
| `steal_pct` | Player steals / opponent possessions while on court (counted events or time-share estimate). | [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) |
| `block_pct` | Player blocks / opponent two-point attempts while on court (counted events or time-share estimate). | [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) |
| `true_shooting_pct` | PTS / (2 * (FGA + 0.44 * FTA)), a fraction that can exceed 1. | [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) |

### PER and Win Shares

| SQL statistic | Definition / units | Read from |
| --- | --- | --- |
| `uper` | Hollinger unadjusted PER per minute, using cumulative player/team totals and scope-round league constants. | [`app_player_round_ratings`](GOLD_TABLE_REFERENCE.md#app_player_round_ratings) |
| `aper` | Pace-adjusted uPER: uper * league pace / player's team-context pace. | [`app_player_round_ratings`](GOLD_TABLE_REFERENCE.md#app_player_round_ratings) |
| `per` | Cumulative aper normalized so the seconds-weighted league mean in this scope-round is 15. | [`app_player_round_ratings`](GOLD_TABLE_REFERENCE.md#app_player_round_ratings) |
| `off_win_shares` | Offensive estimated win contribution from points produced minus marginal offensive cost; see glossary. | [`app_player_round_win_shares`](GOLD_TABLE_REFERENCE.md#app_player_round_win_shares) |
| `def_win_shares` | Defensive estimated win contribution from stops and individual defensive rating; see glossary. | [`app_player_round_win_shares`](GOLD_TABLE_REFERENCE.md#app_player_round_win_shares) |
| `win_shares` | off_win_shares + def_win_shares; estimated wins, can be negative. | [`app_player_round_win_shares`](GOLD_TABLE_REFERENCE.md#app_player_round_win_shares) |
| `win_shares_per_40` | win_shares * 40 / (seconds_played / 60), estimated wins per 40 player-minutes. | [`app_player_round_win_shares`](GOLD_TABLE_REFERENCE.md#app_player_round_win_shares) |
| `game_uper` | Unadjusted PER per minute from this game's box score with phase-through-round league constants. | [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) |
| `game_aper` | game_uper * phase-through-round league pace / this game's team pace. | [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) |
| `game_per` | game_aper normalized to a seconds-weighted mean of 15 within its phase-round; NULL below 180 seconds. | [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) |

### On/off, RAPM and sample sizes

| SQL statistic | Definition / units | Read from |
| --- | --- | --- |
| `games` | Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `on_seconds` | Team stints with this player on court: Elapsed on-court time in complete stored stints, summed over the row's sample. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `on_possessions_for` | Team stints with this player on court: Team counted possessions closed during these stints. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `on_possessions_against` | Team stints with this player on court: Opponent counted possessions closed during these stints. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `on_points_for` | Team stints with this player on court: Points scored by this club or lineup in the row's game, stint or cumulative scope. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `on_points_against` | Team stints with this player on court: Points conceded by this club or lineup in the same sample. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `off_seconds` | Other team stints in the scope, including games missed: Elapsed on-court time in complete stored stints, summed over the row's sample. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `off_possessions_for` | Other team stints in the scope, including games missed: Team counted possessions closed during these stints. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `off_possessions_against` | Other team stints in the scope, including games missed: Opponent counted possessions closed during these stints. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `off_points_for` | Other team stints in the scope, including games missed: Points scored by this club or lineup in the row's game, stint or cumulative scope. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `off_points_against` | Other team stints in the scope, including games missed: Points conceded by this club or lineup in the same sample. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `on_ortg` | Team stints with this player on court: 100 * points_for / possessions_for from counted stints, offensive points per 100. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `on_drtg` | Team stints with this player on court: 100 * points_against / possessions_against from counted stints, defensive points allowed per 100. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `on_net_rating` | Team stints with this player on court: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `off_ortg` | Other team stints in the scope, including games missed: 100 * points_for / possessions_for from counted stints, offensive points per 100. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `off_drtg` | Other team stints in the scope, including games missed: 100 * points_against / possessions_against from counted stints, defensive points allowed per 100. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `off_net_rating` | Other team stints in the scope, including games missed: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `ortg_diff` | on_ortg - off_ortg; positive means the team's offense was better with the player on court. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `drtg_diff` | on_drtg - off_drtg; positive means the team's defense allowed more with the player on court. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `net_rating_diff` | on_net_rating - off_net_rating, unadjusted team on/off difference per 100 possessions. | [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) |
| `seconds` | Elapsed on-court time in complete stored stints, summed over the row's sample. | [`app_player_rapm`](GOLD_TABLE_REFERENCE.md#app_player_rapm) |
| `possessions_offense` | Counted offensive possessions contributing to this player's RAPM fit. | [`app_player_rapm`](GOLD_TABLE_REFERENCE.md#app_player_rapm) |
| `possessions_defense` | Counted defensive possessions contributing to this player's RAPM fit. | [`app_player_rapm`](GOLD_TABLE_REFERENCE.md#app_player_rapm) |
| `penalty` | Ridge penalty selected by whole-game cross-validation; same value for all players in a season. | [`app_player_rapm`](GOLD_TABLE_REFERENCE.md#app_player_rapm) |
| `offense` | Offensive RAPM coefficient in points per 100 possessions above the fitted baseline; positive is better. | [`app_player_rapm`](GOLD_TABLE_REFERENCE.md#app_player_rapm) |
| `defense` | Defensive RAPM coefficient in points prevented per 100 possessions; positive is better. | [`app_player_rapm`](GOLD_TABLE_REFERENCE.md#app_player_rapm) |
| `rapm` | offense + defense, regularized adjusted plus-minus in points per 100 possessions. | [`app_player_rapm`](GOLD_TABLE_REFERENCE.md#app_player_rapm) |

## Player formulas and interpretation

### Traditional production and shooting

PTS is official scored points. REB is OREB + DREB. FG% is FGM/FGA (the combined
player FG% has no dedicated stored column in these Gold tables); 2P%, 3P% and
FT% are made/attempted for the respective category. For a new frontend FG%
display, divide the stored made/attempted totals and return unavailable for
zero attempts. That is a display calculation, not an existing SQL field.

Official PIR is retained from the API, rather than recomputed here. Its standard
interpretation is positive actions (PTS + REB + AST + STL + BLK + fouls drawn)
minus missed field goals, missed free throws, TOV, shots blocked and fouls
committed. The stored source PIR is authoritative for this warehouse.
Double/triple doubles in derived PS misc rows count categories reaching ten
among points, total rebounds, assists, steals and blocks. API misc rows are retained.

```text
eFG = (FGM + 0.5 * 3PM) / FGA
TS  = PTS / (2 * (FGA + 0.44 * FTA))
TOV fraction = TOV / (FGA + 0.44 * FTA + TOV)

Game Score = PTS + 0.4*FGM - 0.7*FGA - 0.4*(FTA-FTM)
             + 0.7*OREB + 0.3*DREB + STL + 0.7*AST + 0.7*BLK
             - 0.4*PF - TOV

PIE numerator = PTS + FGM + FTM - FGA - FTA + DREB
                + 0.5*OREB + AST + STL + 0.5*BLK - PF - TOV
PIE = sum(player numerator) / sum(team numerator + opponent numerator)
```

`game_score_total` and `game_score_average` use counted appearances. PIE's
denominator includes both full teams in the games the player appeared in;
it is not restricted to events while the player was on court.

Implementations: [Silver advanced.py](../postgres_etl/advanced.py),
[player_rounds.py](../gold_etl/player_rounds.py),
[postseason.py](../gold_etl/postseason.py).

### Player rates: game events versus cumulative estimates

The seven time-dependent game rates use actual on-court events when play-by-play
and starters allow reconstruction. This affects `usage_pct`, `assist_pct`,
`orb_pct`, `drb_pct`, `trb_pct`, `steal_pct` and `block_pct`. A player never placed
on court by the walk has NULL rates. Zero-minute players also have NULL rates.

For on-court events, define `used = FGA + 0.44*FTA + TOV` and use only the events
attributed while the player is on court:

| Game rate | Actual on-court denominator / formula |
| --- | --- |
| Usage | Player used plays / team used plays. |
| Assist | Player assists / (team FGM - player FGM + team eligible FT trips - player eligible FT trips). |
| OREB% | Player OREB / (team OREB + opponent DREB). |
| DREB% | Player DREB / (team DREB + opponent OREB). |
| REB% | Player REB / (team REB + opponent REB). |
| Steal% | Player steals / opponent counted possessions ending while the player is on court. |
| Block% | Player blocks / opponent two-point attempts while the player is on court. |

An eligible FT trip groups consecutive same-club free throws at one clock,
ignoring fouls and substitutions; an and-one after a made field goal adds no
extra assist chance. This recognizes EuroLeague assists that lead to free throws.
Shot codes include older layup/dunk/blocked-attempt variants. Events follow
period/event order, including substitutions at the same clock.

Without usable event context (including pre-E2007), game rates use box-score
time-share estimates and are NULL below 180 played seconds. The cumulative
round table **always** uses its own box-score contributions:

```text
used_p = p.FGA + 0.44*p.FTA + p.TOV
used_t = t.FGA + 0.44*t.FTA + t.TOV

usg_pct = sum(used_p * game_seconds) / sum(player_seconds * used_t)
ast_pct = sum(p.AST) / sum(s*t.FGM - p.FGM)
orb_pct = sum(p.OREB) / sum(s*(t.OREB + o.DREB))
drb_pct = sum(p.DREB) / sum(s*(t.DREB + o.OREB))
trb_pct = sum(p.REB) / sum(s*(t.REB + o.REB))
stl_pct = sum(p.STL) / sum(s*estimated_game_possessions)
blk_pct = sum(p.BLK) / sum(s*o.2PA)
possessions_played = sum(s*estimated_game_possessions)
X_per_100 = 100 * sum(player X) / possessions_played
```

There is no round-level 180-second cutoff. A cumulative rate is not an average
of the new per-game on-court rates. Gold game rows omit Silver's `rate_source`;
the frontend cannot reliably determine estimate versus on-court mode from that
Gold row alone. Do not claim every E2007+ row necessarily used on-court events.
The stored source indicator is available only in local Silver.

Implementations: [on_court_rates.py](../postgres_etl/on_court_rates.py),
[advanced.py](../postgres_etl/advanced.py),
[player_rounds.py](../gold_etl/player_rounds.py).

### Hollinger PER

PER estimates box-score production per minute, adjusts for pace and normalizes
the seconds-weighted league mean to 15 within the selected scope and round.
It is not a points-per-100-possession value or an estimate of wins.
The warehouse uses the player's team context from games the player appeared
in, including each club when transferred, rather than the club's entire season.

The exact implemented uPER calculation is:

```text
League inputs are both sides of all counted games in the scope through round r.
q = team AST / team FGM in the player's appearance context
factor = 2/3 - (0.5*league AST/league FGM)/(2*league FGM/league FTM)
VOP = league PTS / (league FGA - league OREB + league TOV + 0.44*league FTA)
d = (league REB - league OREB) / league REB
f = league FTM/league PF - 0.44*(league FTA/league PF)*VOP

uPER = [3*3PM + (2/3)*AST + (2-factor*q)*FGM
        + 0.5*FTM*(2-q/3) - VOP*TOV
        - VOP*d*(FGA-FGM)
        - VOP*0.44*(0.44+0.56*d)*(FTA-FTM)
        + VOP*(1-d)*(REB-OREB) + VOP*d*OREB
        + VOP*STL + VOP*d*BLK - PF*f] / player_minutes

aPER = uPER * league_pace / player_team_context_pace
PER  = aPER * 15 / seconds_weighted_mean(aPER)
```

For game PER, the player and team box-score inputs are from that game; league
constants and league pace use the game's **phase** through its round. `game_per`
normalization uses player game lines within the same phase and round. Lines
below 180 seconds have NULL game_per but retain game_uper/game_aper and contribute
to the normalization mean. For cumulative PER there is no minimum-minutes filter.
Zero or missing denominators produce NULL, and small samples can be extreme.
Do not average game_per to obtain season per; read the final scope-round rating.

Implementations: [player_ratings.py](../gold_etl/player_ratings.py),
[game_advanced.py](../gold_etl/game_advanced.py).

### Win Shares

Win Shares applies the Basketball-Reference style offensive/defensive method to
EuroLeague box scores. Higher is better; values can be negative. Team and opponent
context comes from the player's appearances, while league context uses every
counted game in the scope through the round. It does not promise that player
shares sum exactly to the team's actual wins.

```text
league_PPP = league points / league estimated possessions
marginal_points_per_win = 0.32 * league points per team-game
                          * player_team_context_pace / league_pace

OWS = (points_produced - 0.92*league_PPP*individual_possessions)
      / marginal_points_per_win
DWS = (player_minutes / summed_team_player_minutes)
      * team_possessions * (1.08*league_PPP - individual_DRtg/100)
      / marginal_points_per_win
WS = OWS + DWS
WS/40 = WS * 40 / player_minutes
```

`points_produced` and `individual_possessions` are internal model quantities,
using assisted-scoring estimates, offensive rebound contribution, missed shots,
free throws and turnovers. Individual DRtg uses estimated stops from steals,
blocks, defensive rebounds and team/opponent context. They are **not** simply
player points, `possessions_played`, or the club's defensive_rating and are not
stored output columns. The full component equations are in `_offense`, `_defense`
and `_marginal_ppw` in [player_win_shares.py](../gold_etl/player_win_shares.py).
This model uses 0.4 in its free-throw possession components; do not replace those
with the 0.44 used by the separate basic possession estimate.

Bracketed ratios multiplying zero counts use zero-safe handling; other undefined
denominators/missing inputs yield NULL. `win_shares_per_40` uses EuroLeague's 40
minutes, not the NBA's 48. No blanket minutes qualification is applied.

### Player on/off

```text
on_ortg  = 100 * on_points_for / on_possessions_for
on_drtg  = 100 * on_points_against / on_possessions_against
on_net   = on_ortg - on_drtg
off_*    = the same calculations on the club's other complete stints
*_diff   = on value - off value
```

Off includes all other team stints in scope, including games missed by the player.
It is not limited to the player's appearances. Higher ortg_diff/net_rating_diff
is better; **lower drtg_diff is better**. Without off possessions, off ratings
and differences are NULL. This is team performance in context, with no adjustment
for teammate/opponent strength. Transfers produce one row per club.

Implementation: [player_on_off.py](../gold_etl/player_on_off.py).

### Regularized adjusted plus-minus (RAPM)

The model predicts a team's stint points per 100 counted possessions from an
intercept plus the five offensive player coefficients minus the five defensive
player coefficients. Stints are weighted by offensive possessions. The ridge
penalty shrinks coefficients toward zero and is chosen per season by whole-game
five-fold cross-validation, using 250 through 64000 on the configured grid.
Near ties prefer the stronger penalty (tolerance 0.01% of no-player error).

```text
predicted ORtg = baseline + sum(offense for five attackers)
                         - sum(defense for five defenders)
rapm = offense + defense
```

Positive offense means more points scored; positive defense means points
prevented. Both are favorable. Values are rounded to four decimals and stored
with sample seconds, offensive/defensive possessions and the selected penalty.
There is one player-season row, blended across clubs, with scope all only.
There is no fixed 15 league mean, no round history and no minutes cutoff.
Small/early-season samples can be heavily shrunk; these are fitted associations,
not a guarantee of individual causal impact or a directly observed box-score stat.

Implementation: [rapm.py](../gold_etl/rapm.py).

## Team statistics

Team means include official team box scores, legacy own/opponent season totals,
calculated team rows and lineup results. Exact own_/opp_ and split fields are
listed for searchability. Source team-season API feeds are Silver-only; they
are reference inputs, not additional Gold frontend tables.

### Official production and own/opponent totals

| SQL statistic | Definition / units | Read from |
| --- | --- | --- |
| `points` | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats), [`app_game_team_shot_zones`](GOLD_TABLE_REFERENCE.md#app_game_team_shot_zones), [`app_team_shot_zone_stats`](GOLD_TABLE_REFERENCE.md#app_team_shot_zone_stats) |
| `seconds_played` | Official playing time in seconds; player seconds or aggregate team player-seconds in box scores. | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `pir` | Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `two_pointers_made` | Successful two-point field goals (2PM). | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `two_pointers_attempted` | Two-point field-goal attempts (2PA), including makes. | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `three_pointers_made` | Successful three-point field goals (3PM). | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `three_pointers_attempted` | Three-point field-goal attempts (3PA), including makes. | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `free_throws_made` | Successful free throws (FTM). | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `free_throws_attempted` | Free-throw attempts (FTA), including makes. | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `field_goals_made` | Successful two- and three-point field goals (FGM), excluding free throws. | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats), [`app_game_team_shot_splits`](GOLD_TABLE_REFERENCE.md#app_game_team_shot_splits), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `field_goals_attempted` | All two- and three-point field-goal attempts (FGA), including blocked attempts. | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `accuracy_made` | Raw source accuracyMade measure; meaning is not established by the warehouse. Do not treat it as FG%. | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `accuracy_attempted` | Raw source accuracyAttempted measure; meaning is not established by the warehouse. Do not treat it as FGA. | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `total_rebounds` | Offensive plus defensive rebounds (REB); official team totals can include team rebounds. | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `defensive_rebounds` | Rebounds recovered after the opponent's missed shot (DREB). | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `offensive_rebounds` | Rebounds recovered after the player's or club's missed shot (OREB). | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `assists` | Official credited assists (AST), including EuroLeague assists that lead to free throws. | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `steals` | Official credited steals (STL). | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `turnovers` | Lost possessions charged to the player or team (TOV). | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `blocks` | Opponent field-goal attempts blocked by the player or team (BLK). | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `blocks_against` | The player's or team's field-goal attempts blocked by opponents. | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `fouls_committed` | Personal fouls charged to the player or team (PF). | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `fouls_drawn` | Opponent fouls drawn by the player or team. | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `plus_minus` | Source point margin while the player was on court; raw points, not per 100 possessions. | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) |
| `games_played` | Games/appearances in the selected row scope; see table notes for counted games and series fixture counts. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats), [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `own_points` | Team total: Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `own_field_goals_made2` | Team total: Successful two-point field goals (2PM). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `own_field_goals_attempted2` | Team total: Two-point field-goal attempts (2PA), including makes. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `own_field_goals_made3` | Team total: Successful three-point field goals (3PM). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `own_field_goals_attempted3` | Team total: Three-point field-goal attempts (3PA), including makes. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `own_free_throws_made` | Team total: Successful free throws (FTM). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats), [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `own_free_throws_attempted` | Team total: Free-throw attempts (FTA), including makes. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats), [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `own_field_goals_made_total` | Team total: Successful two- and three-point field goals (FGM), excluding free throws. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `own_field_goals_attempted_total` | Team total: All two- and three-point field-goal attempts (FGA), including blocked attempts. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `own_total_rebounds` | Team total: Offensive plus defensive rebounds (REB); official team totals can include team rebounds. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `own_defensive_rebounds` | Team total: Rebounds recovered after the opponent's missed shot (DREB). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats), [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `own_offensive_rebounds` | Team total: Rebounds recovered after the player's or club's missed shot (OREB). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats), [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `own_assistances` | Team total: Official credited assists (AST), including EuroLeague assists that lead to free throws. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `own_steals` | Team total: Official credited steals (STL). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `own_turnovers` | Team total: Lost possessions charged to the player or team (TOV). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats), [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `own_blocks_favour` | Team total: Opponent field-goal attempts blocked by the player or team (BLK). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `own_blocks_against` | Team total: The player's or team's field-goal attempts blocked by opponents. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `own_fouls_commited` | Team total: Personal fouls charged to the player or team (PF). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `own_fouls_received` | Team total: Opponent fouls drawn by the player or team. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `own_valuation` | Team total: Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `opp_points` | Opponent total: Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `opp_field_goals_made2` | Opponent total: Successful two-point field goals (2PM). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `opp_field_goals_attempted2` | Opponent total: Two-point field-goal attempts (2PA), including makes. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `opp_field_goals_made3` | Opponent total: Successful three-point field goals (3PM). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `opp_field_goals_attempted3` | Opponent total: Three-point field-goal attempts (3PA), including makes. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `opp_free_throws_made` | Opponent total: Successful free throws (FTM). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats), [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `opp_free_throws_attempted` | Opponent total: Free-throw attempts (FTA), including makes. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats), [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `opp_field_goals_made_total` | Opponent total: Successful two- and three-point field goals (FGM), excluding free throws. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `opp_field_goals_attempted_total` | Opponent total: All two- and three-point field-goal attempts (FGA), including blocked attempts. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `opp_total_rebounds` | Opponent total: Offensive plus defensive rebounds (REB); official team totals can include team rebounds. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `opp_defensive_rebounds` | Opponent total: Rebounds recovered after the opponent's missed shot (DREB). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats), [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `opp_offensive_rebounds` | Opponent total: Rebounds recovered after the player's or club's missed shot (OREB). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats), [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `opp_assistances` | Opponent total: Official credited assists (AST), including EuroLeague assists that lead to free throws. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `opp_steals` | Opponent total: Official credited steals (STL). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `opp_turnovers` | Opponent total: Lost possessions charged to the player or team (TOV). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats), [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `opp_blocks_favour` | Opponent total: Opponent field-goal attempts blocked by the player or team (BLK). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `opp_blocks_against` | Opponent total: The player's or team's field-goal attempts blocked by opponents. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `opp_fouls_commited` | Opponent total: Personal fouls charged to the player or team (PF). | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `opp_fouls_received` | Opponent total: Opponent fouls drawn by the player or team. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `opp_valuation` | Opponent total: Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. | [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) |
| `wins` | Games won in this row's scope; source player misc values follow the API. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `losses` | Games lost in this row's scope; source player misc values follow the API. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `points_for` | Points scored by this club or lineup in the row's game, stint or cumulative scope. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow), [`app_lineup_ratings`](GOLD_TABLE_REFERENCE.md#app_lineup_ratings) |
| `points_against` | Points conceded by this club or lineup in the same sample. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow), [`app_lineup_ratings`](GOLD_TABLE_REFERENCE.md#app_lineup_ratings) |
| `own_field_goals_made` | Team total: Successful two- and three-point field goals (FGM), excluding free throws. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `own_field_goals_attempted` | Team total: All two- and three-point field-goal attempts (FGA), including blocked attempts. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `own_three_pointers_made` | Team total: Successful three-point field goals (3PM). | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `own_assists` | Team total: Official credited assists (AST), including EuroLeague assists that lead to free throws. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `opp_field_goals_made` | Opponent total: Successful two- and three-point field goals (FGM), excluding free throws. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `opp_field_goals_attempted` | Opponent total: All two- and three-point field-goal attempts (FGA), including blocked attempts. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `opp_three_pointers_made` | Opponent total: Successful three-point field goals (3PM). | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `opp_assists` | Opponent total: Official credited assists (AST), including EuroLeague assists that lead to free throws. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `opp_efg_pct` | Opponent total: (FGM + 0.5 * 3PM) / FGA, a fraction that can exceed 1. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |
| `opp_tov_pct` | Opponent total: TOV / (FGA + 0.44 * FTA + TOV), a fraction. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |
| `opp_ft_rate` | Opponent total: FTM / FGA, made free throws per field-goal attempt; not FTA / FGA. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |
| `own_possessions_estimate` | Club box-score estimate: FGA + 0.44 * FTA - OREB + TOV. | [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |

### Possession efficiency and adjusted strength

| SQL statistic | Definition / units | Read from |
| --- | --- | --- |
| `game_minutes` | Game-clock minutes, 40 plus 5 per overtime; cumulative sum in team-round rows, not player-minutes. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |
| `possessions` | In calculated team rows: mean of the two clubs' possession estimates, summed for cumulative rows. API player feed possessions has a separate source definition. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |
| `mov` | (points_for - points_against) / games_played, mean margin in points per game. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `pythagorean_exponent` | Fixed exponent 10.25 used in this warehouse's expected-win model. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats) |
| `pythagorean_win_pct` | PF^10.25 / (PF^10.25 + PA^10.25), expected win fraction from cumulative scores. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `pythagorean_wins` | pythagorean_win_pct * games_played, expected wins. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `pace` | 40 * estimated possessions / game_minutes, possessions per regulation-length team game. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |
| `offensive_rating` | 100 * points_for / estimated possessions, points scored per 100 possessions. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |
| `defensive_rating` | 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |
| `net_rating` | Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced), [`app_lineup_ratings`](GOLD_TABLE_REFERENCE.md#app_lineup_ratings) |
| `efg_pct` | (FGM + 0.5 * 3PM) / FGA, a fraction that can exceed 1. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |
| `tov_pct` | TOV / (FGA + 0.44 * FTA + TOV), a fraction. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |
| `orb_pct` | Offensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |
| `drb_pct` | Defensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |
| `ft_rate` | FTM / FGA, made free throws per field-goal attempt; not FTA / FGA. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |
| `true_shooting_pct` | PTS / (2 * (FGA + 0.44 * FTA)), a fraction that can exceed 1. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |
| `assist_ratio` | AST / FGM in calculated team tables; not the API assists_ratio. | [`app_team_round_stats`](GOLD_TABLE_REFERENCE.md#app_team_round_stats), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats), [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) |
| `connected` | True if the played-game graph links every club in this scope-round; governs adjusted-rating availability. | [`app_team_round_ratings`](GOLD_TABLE_REFERENCE.md#app_team_round_ratings), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `league_offensive_rating` | 100 * league points / league estimated possessions in this scope through this round, both sides counted. | [`app_team_round_ratings`](GOLD_TABLE_REFERENCE.md#app_team_round_ratings), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `league_pace` | 40 * league estimated possessions / league game-clock minutes, both sides counted. | [`app_team_round_ratings`](GOLD_TABLE_REFERENCE.md#app_team_round_ratings), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `relative_offensive_rating` | Club offensive_rating minus league_offensive_rating; positive means better offense. | [`app_team_round_ratings`](GOLD_TABLE_REFERENCE.md#app_team_round_ratings), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `relative_defensive_rating` | Club defensive_rating minus league_offensive_rating; negative means better defense. | [`app_team_round_ratings`](GOLD_TABLE_REFERENCE.md#app_team_round_ratings), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `relative_pace` | Club pace minus league_pace, possessions per 40 minutes above/below the league. | [`app_team_round_ratings`](GOLD_TABLE_REFERENCE.md#app_team_round_ratings), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `srs` | Simple Rating System: MOV plus mean opponent SRS, solved with league mean zero; points per game. | [`app_team_round_ratings`](GOLD_TABLE_REFERENCE.md#app_team_round_ratings), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `sos` | Strength of schedule: mean opponent SRS over all counted games, equal to SRS - MOV. | [`app_team_round_ratings`](GOLD_TABLE_REFERENCE.md#app_team_round_ratings), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `sov` | Strength of victory: mean opponent SRS in games won; NULL without wins. | [`app_team_round_ratings`](GOLD_TABLE_REFERENCE.md#app_team_round_ratings), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `adj_offensive_rating` | Possession-weighted opponent-adjusted offensive rating, centered on league offensive rating. | [`app_team_round_ratings`](GOLD_TABLE_REFERENCE.md#app_team_round_ratings), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `adj_defensive_rating` | Possession-weighted opponent-adjusted defensive rating, centered on league offensive rating; lower is better. | [`app_team_round_ratings`](GOLD_TABLE_REFERENCE.md#app_team_round_ratings), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `adj_net_rating` | Possession-weighted opponent-adjusted net rating, centered on zero; higher is better. | [`app_team_round_ratings`](GOLD_TABLE_REFERENCE.md#app_team_round_ratings), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |

### Home, away and recent-game splits

| SQL statistic | Definition / units | Read from |
| --- | --- | --- |
| `home_games` | Local-side games in this scope through this round: Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `home_wins` | Local-side games in this scope through this round: Games won in this row's scope; source player misc values follow the API. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `home_mov` | Local-side games in this scope through this round: (points_for - points_against) / games_played, mean margin in points per game. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `home_offensive_rating` | Local-side games in this scope through this round: 100 * points_for / estimated possessions, points scored per 100 possessions. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `home_defensive_rating` | Local-side games in this scope through this round: 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `home_net_rating` | Local-side games in this scope through this round: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `home_pace` | Local-side games in this scope through this round: 40 * estimated possessions / game_minutes, possessions per regulation-length team game. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `away_games` | Road-side games in this scope through this round: Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `away_wins` | Road-side games in this scope through this round: Games won in this row's scope; source player misc values follow the API. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `away_mov` | Road-side games in this scope through this round: (points_for - points_against) / games_played, mean margin in points per game. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `away_offensive_rating` | Road-side games in this scope through this round: 100 * points_for / estimated possessions, points scored per 100 possessions. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `away_defensive_rating` | Road-side games in this scope through this round: 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `away_net_rating` | Road-side games in this scope through this round: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `away_pace` | Road-side games in this scope through this round: 40 * estimated possessions / game_minutes, possessions per regulation-length team game. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `last5_games` | Last up to five counted games in this scope: Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `last5_wins` | Last up to five counted games in this scope: Games won in this row's scope; source player misc values follow the API. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `last5_mov` | Last up to five counted games in this scope: (points_for - points_against) / games_played, mean margin in points per game. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `last5_offensive_rating` | Last up to five counted games in this scope: 100 * points_for / estimated possessions, points scored per 100 possessions. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `last5_defensive_rating` | Last up to five counted games in this scope: 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `last5_net_rating` | Last up to five counted games in this scope: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `last5_pace` | Last up to five counted games in this scope: 40 * estimated possessions / game_minutes, possessions per regulation-length team game. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `last10_games` | Last up to ten counted games in this scope: Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `last10_wins` | Last up to ten counted games in this scope: Games won in this row's scope; source player misc values follow the API. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `last10_mov` | Last up to ten counted games in this scope: (points_for - points_against) / games_played, mean margin in points per game. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `last10_offensive_rating` | Last up to ten counted games in this scope: 100 * points_for / estimated possessions, points scored per 100 possessions. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `last10_defensive_rating` | Last up to ten counted games in this scope: 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `last10_net_rating` | Last up to ten counted games in this scope: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |
| `last10_pace` | Last up to ten counted games in this scope: 40 * estimated possessions / game_minutes, possessions per regulation-length team game. | [`app_team_round_splits`](GOLD_TABLE_REFERENCE.md#app_team_round_splits), [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) |

### Event analytics, zones, lineup ratings and samples

| SQL statistic | Definition / units | Read from |
| --- | --- | --- |
| `counted_possessions` | Team possessions closed by the play-by-play state machine; summed in season-scope aggregates. | [`app_game_team_possessions`](GOLD_TABLE_REFERENCE.md#app_game_team_possessions), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `possession_seconds` | Sum of measurable possession durations in seconds, not necessarily all game-clock seconds. | [`app_game_team_possessions`](GOLD_TABLE_REFERENCE.md#app_game_team_possessions), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `avg_possession_seconds` | Game: timed seconds / timed possession count. Team aggregate: game averages weighted by counted possessions. | [`app_game_team_possessions`](GOLD_TABLE_REFERENCE.md#app_game_team_possessions), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `estimated_possessions` | Shared box-score possessions estimate copied for comparison; summed in season-scope aggregates. | [`app_game_team_possessions`](GOLD_TABLE_REFERENCE.md#app_game_team_possessions), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `lead_changes` | Times the leading team changes; identical on the two game-side rows. | [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow) |
| `ties` | Times the score becomes level above 0-0; identical on the two game-side rows. | [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow) |
| `time_leading_seconds` | Game-clock seconds the team led; summed over timed games in aggregate rows. | [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `time_trailing_seconds` | Game-clock seconds the team trailed; summed over timed games in aggregate rows. | [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `time_tied_seconds` | Game-clock seconds the score was tied, including 0-0; summed over timed games in aggregates. | [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `largest_lead` | Largest positive team margin in a game; maximum across games in season-scope aggregates. | [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `longest_run` | Most unanswered points scored in a game; maximum across games in season-scope aggregates. | [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `runs_6_plus` | Number of unanswered scoring runs of at least six points; summed across games in aggregates. | [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `clutch_seconds` | Seconds from elapsed second 2100 through game end (including overtime) with margin at most five points. | [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `clutch_points_for` | Team points scored from second 2100 onward when the pre-scoring margin is at most five points. | [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `clutch_points_against` | Opponent points scored from second 2100 onward when the pre-scoring margin is at most five points. | [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `fast_break_points` | Sum of positive shot points tagged fastbreak, including any flagged made free throws; NULL when flags are unrecorded. | [`app_game_team_shot_splits`](GOLD_TABLE_REFERENCE.md#app_game_team_shot_splits), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `second_chance_points` | Sum of positive shot points tagged second_chance, including any flagged made free throws; NULL when flags are unrecorded. | [`app_game_team_shot_splits`](GOLD_TABLE_REFERENCE.md#app_game_team_shot_splits), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `points_off_turnover_points` | Sum of positive shot points tagged points_off_turnover, including any flagged made free throws; distinct from the Boolean shot flag. | [`app_game_team_shot_splits`](GOLD_TABLE_REFERENCE.md#app_game_team_shot_splits), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `assisted_field_goals` | min(team AS event count, team made-field-goal event count); summed in aggregates, not shot-by-shot matching. | [`app_game_team_shot_splits`](GOLD_TABLE_REFERENCE.md#app_game_team_shot_splits), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `assisted_fg_pct` | assisted_field_goals / field_goals_made, a fraction. | [`app_game_team_shot_splits`](GOLD_TABLE_REFERENCE.md#app_game_team_shot_splits), [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `zone` | Source shot-zone label, preserved without a warehouse court taxonomy. | [`app_game_team_shot_zones`](GOLD_TABLE_REFERENCE.md#app_game_team_shot_zones), [`app_team_shot_zone_stats`](GOLD_TABLE_REFERENCE.md#app_team_shot_zone_stats) |
| `attempts` | Field-goal attempts in this source zone, including makes. | [`app_game_team_shot_zones`](GOLD_TABLE_REFERENCE.md#app_game_team_shot_zones), [`app_team_shot_zone_stats`](GOLD_TABLE_REFERENCE.md#app_team_shot_zone_stats) |
| `made` | Successful field goals in this source zone. | [`app_game_team_shot_zones`](GOLD_TABLE_REFERENCE.md#app_game_team_shot_zones), [`app_team_shot_zone_stats`](GOLD_TABLE_REFERENCE.md#app_team_shot_zone_stats) |
| `games` | Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. | [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats), [`app_lineup_ratings`](GOLD_TABLE_REFERENCE.md#app_lineup_ratings) |
| `timed_games` | Games with non-NULL time-leading data; denominator for time-based summaries. | [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `clutch_games` | Timed games with positive clutch_seconds, not all close final scores. | [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `flagged_games` | Games with recorded shot-split flags (non-NULL fast_break_points), denominator for flagged scoring coverage. | [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `lead_changes_per_game` | Mean of available per-game lead_changes values. | [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `ties_per_game` | Mean of available per-game ties values. | [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) |
| `fg_pct` | made / attempts in this zone, a fraction. | [`app_team_shot_zone_stats`](GOLD_TABLE_REFERENCE.md#app_team_shot_zone_stats) |
| `attempt_share` | Zone attempts / all zone-tagged field-goal attempts for the club in the scope, a fraction. | [`app_team_shot_zone_stats`](GOLD_TABLE_REFERENCE.md#app_team_shot_zone_stats) |
| `lineup_size` | Number of players in the combination: 2, 3 or 5. | [`app_lineup_ratings`](GOLD_TABLE_REFERENCE.md#app_lineup_ratings) |
| `seconds` | Elapsed on-court time in complete stored stints, summed over the row's sample. | [`app_lineup_ratings`](GOLD_TABLE_REFERENCE.md#app_lineup_ratings) |
| `possessions_for` | Team counted possessions closed during these stints. | [`app_lineup_ratings`](GOLD_TABLE_REFERENCE.md#app_lineup_ratings) |
| `possessions_against` | Opponent counted possessions closed during these stints. | [`app_lineup_ratings`](GOLD_TABLE_REFERENCE.md#app_lineup_ratings) |
| `ortg` | 100 * points_for / possessions_for from counted stints, offensive points per 100. | [`app_lineup_ratings`](GOLD_TABLE_REFERENCE.md#app_lineup_ratings) |
| `drtg` | 100 * points_against / possessions_against from counted stints, defensive points allowed per 100. | [`app_lineup_ratings`](GOLD_TABLE_REFERENCE.md#app_lineup_ratings) |

### Official standings ranks, records and split summaries

| SQL statistic | Definition / units | Read from |
| --- | --- | --- |
| `basic_position` | basic feed: Official rank in the source standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `basic_position_change` | basic feed: Source position movement label. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `basic_games_played` | basic feed: Source games played in this standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `basic_games_won` | basic feed: Source games won in this standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `basic_games_lost` | basic feed: Source games lost in this standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `basic_qualified` | basic feed: Source playoff/phase qualification flag, distinct from player leaderboard eligibility. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `basic_win_percentage` | basic feed: Source win percentage retained as supplied; verify its scale before formatting. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `basic_points_difference` | basic feed: Source points for minus points against. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `basic_points_for` | basic feed: Source cumulative points scored. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `basic_points_against` | basic feed: Source cumulative points conceded. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `basic_home_record` | basic feed: Source win-loss record text for home record; preserve its text format. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `basic_away_record` | basic feed: Source win-loss record text for away record; preserve its text format. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `basic_neutral_record` | basic feed: Source win-loss record text for neutral record; preserve its text format. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `basic_overtime_record` | basic feed: Source win-loss record text for overtime record; preserve its text format. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `basic_last_ten_record` | basic feed: Source win-loss record text for last ten record; preserve its text format. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `calendar_position` | calendar feed: Official rank in the source standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `calendar_position_change` | calendar feed: Source position movement label. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `calendar_games_played` | calendar feed: Source games played in this standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `calendar_games_won` | calendar feed: Source games won in this standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `calendar_games_lost` | calendar feed: Source games lost in this standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `calendar_qualified` | calendar feed: Source playoff/phase qualification flag, distinct from player leaderboard eligibility. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `streaks_position` | streaks feed: Official rank in the source standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `streaks_position_change` | streaks feed: Source position movement label. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `streaks_games_played` | streaks feed: Source games played in this standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `streaks_games_won` | streaks feed: Source games won in this standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `streaks_games_lost` | streaks feed: Source games lost in this standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `streaks_qualified` | streaks feed: Source playoff/phase qualification flag, distinct from player leaderboard eligibility. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `streaks_home_record` | streaks feed: Source win-loss record text for home record; preserve its text format. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `streaks_away_record` | streaks feed: Source win-loss record text for away record; preserve its text format. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `streaks_last10` | streaks feed: Source win-loss record text for last10; preserve its text format. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `streaks_home_last5` | streaks feed: Source win-loss record text for home last5; preserve its text format. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `streaks_away_last5` | streaks feed: Source win-loss record text for away last5; preserve its text format. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `streaks_longest_win_streak_current_season` | streaks feed: Source longest win streak current season, measured in games. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `streaks_longest_lose_streak_current_season` | streaks feed: Source longest lose streak current season, measured in games. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `streaks_longest_win_streak_any_season` | streaks feed: Source longest win streak any season, measured in games. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `streaks_longest_lose_streak_any_season` | streaks feed: Source longest lose streak any season, measured in games. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_position` | ahead_behind feed: Official rank in the source standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_position_change` | ahead_behind feed: Source position movement label. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_games_played` | ahead_behind feed: Source games played in this standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_games_won` | ahead_behind feed: Source games won in this standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_games_lost` | ahead_behind feed: Source games lost in this standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_qualified` | ahead_behind feed: Source playoff/phase qualification flag, distinct from player leaderboard eligibility. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_wins_percentage` | ahead_behind feed: Source wins percentage retained as supplied; verify its scale before formatting. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_quarter1_ahead` | ahead_behind feed: Source win-loss record text for games quarter1 ahead at that checkpoint. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_quarter1_behind` | ahead_behind feed: Source win-loss record text for games quarter1 behind at that checkpoint. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_quarter1_tied` | ahead_behind feed: Source win-loss record text for games quarter1 tied at that checkpoint. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_half1_ahead` | ahead_behind feed: Source win-loss record text for games half1 ahead at that checkpoint. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_half1_behind` | ahead_behind feed: Source win-loss record text for games half1 behind at that checkpoint. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_half1_tied` | ahead_behind feed: Source win-loss record text for games half1 tied at that checkpoint. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_quarter3_ahead` | ahead_behind feed: Source win-loss record text for games quarter3 ahead at that checkpoint. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_quarter3_behind` | ahead_behind feed: Source win-loss record text for games quarter3 behind at that checkpoint. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `ahead_behind_quarter3_tied` | ahead_behind feed: Source win-loss record text for games quarter3 tied at that checkpoint. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_position` | margins feed: Official rank in the source standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_position_change` | margins feed: Source position movement label. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_games_played` | margins feed: Source games played in this standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_games_won` | margins feed: Source games won in this standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_games_lost` | margins feed: Source games lost in this standings snapshot. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_qualified` | margins feed: Source playoff/phase qualification flag, distinct from player leaderboard eligibility. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_point_difference_1_to_5` | margins feed: Source win-loss record text for games with final margin 1 to 5 points. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_point_difference_6_to_10` | margins feed: Source win-loss record text for games with final margin 6 to 10 points. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_point_difference_11_to_15` | margins feed: Source win-loss record text for games with final margin 11 to 15 points. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_point_difference_more_than_15` | margins feed: Source win-loss record text for games with final margin more than 15 points. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_rebounds` | margins feed: Source comparison/split record text for rebounds; not a raw statistical total. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_assists` | margins feed: Source comparison/split record text for assists; not a raw statistical total. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_blocks` | margins feed: Source comparison/split record text for blocks; not a raw statistical total. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_three_pointers` | margins feed: Source comparison/split record text for three pointers; not a raw statistical total. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_two_pointers` | margins feed: Source comparison/split record text for two pointers; not a raw statistical total. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |
| `margins_free_throws` | margins feed: Source comparison/split record text for free throws; not a raw statistical total. | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) |

### Local Silver API team reference feeds

These four API tables are local-only and have no Gold/Neon projection.
Their own/opponent definitions and source units are retained for cross-checks.
For the opponents feeds, each metric is what opponents did against the keyed
club. Filter competition, season, phase_code and mode; join on club_code.
`team_ranking` is the source ranking, not an adjusted team rating.

### API team measures (including opponents)

| SQL statistic | Definition / units | Read from |
| --- | --- | --- |
| `games_played` | Games/appearances in the selected row scope; see table notes for counted games and series fixture counts. | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_advanced`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_advanced`](../postgres_etl/flat_schema.py) |
| `minutes_played` | Playing time in minutes in season feeds; traditional perGame rows use minutes per appearance. | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `points` | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `two_pointers_made` | Successful two-point field goals (2PM). | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `two_pointers_attempted` | Two-point field-goal attempts (2PA), including makes. | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `two_pointers_percentage` | Two-point shooting percentage, 100 * 2PM / 2PA, on the feed's 0-100 scale. | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `three_pointers_made` | Successful three-point field goals (3PM). | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `three_pointers_attempted` | Three-point field-goal attempts (3PA), including makes. | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `three_pointers_percentage` | Three-point shooting percentage, 100 * 3PM / 3PA, on the feed's 0-100 scale. | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `free_throws_made` | Successful free throws (FTM). | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `free_throws_attempted` | Free-throw attempts (FTA), including makes. | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `free_throws_percentage` | Free-throw shooting percentage, 100 * FTM / FTA, on the feed's 0-100 scale. | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `offensive_rebounds` | Rebounds recovered after the player's or club's missed shot (OREB). | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `defensive_rebounds` | Rebounds recovered after the opponent's missed shot (DREB). | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `total_rebounds` | Offensive plus defensive rebounds (REB); official team totals can include team rebounds. | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `assists` | Official credited assists (AST), including EuroLeague assists that lead to free throws. | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `steals` | Official credited steals (STL). | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `turnovers` | Lost possessions charged to the player or team (TOV). | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `blocks` | Opponent field-goal attempts blocked by the player or team (BLK). | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `blocks_against` | The player's or team's field-goal attempts blocked by opponents. | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `fouls_committed` | Personal fouls charged to the player or team (PF). | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `fouls_drawn` | Opponent fouls drawn by the player or team. | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `pir` | Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. | [`silver.season_team_stats_traditional`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_traditional`](../postgres_etl/flat_schema.py) |
| `effective_field_goal_percentage` | API eFG percentage on the 0-100 scale; calculated efg_pct uses a fraction instead. | [`silver.season_team_stats_advanced`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_advanced`](../postgres_etl/flat_schema.py) |
| `true_shooting_percentage` | API true-shooting percentage on the 0-100 scale; calculated ts_pct/true_shooting_pct use fractions. | [`silver.season_team_stats_advanced`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_advanced`](../postgres_etl/flat_schema.py) |
| `offensive_rebounds_percentage` | API offensive rebound percentage on the 0-100 scale, retaining source team-minute conventions. | [`silver.season_team_stats_advanced`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_advanced`](../postgres_etl/flat_schema.py) |
| `defensive_rebounds_percentage` | API defensive rebound percentage on the 0-100 scale, retaining source team-minute conventions. | [`silver.season_team_stats_advanced`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_advanced`](../postgres_etl/flat_schema.py) |
| `rebounds_percentage` | API total rebound percentage on the 0-100 scale, retaining source team-minute conventions. | [`silver.season_team_stats_advanced`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_advanced`](../postgres_etl/flat_schema.py) |
| `assists_to_turnovers_ratio` | API assists-to-turnovers ratio (AST/TOV), retained as supplied including source zero-denominator handling. | [`silver.season_team_stats_advanced`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_advanced`](../postgres_etl/flat_schema.py) |
| `assists_ratio` | API assists ratio, retained without recomputation; denominator differs from calculated assist_ratio/ast_pct. | [`silver.season_team_stats_advanced`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_advanced`](../postgres_etl/flat_schema.py) |
| `turnovers_ratio` | API turnovers ratio, retained without recomputation; not calculated tov_pct. | [`silver.season_team_stats_advanced`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_advanced`](../postgres_etl/flat_schema.py) |
| `two_point_rate` | API two-point rate; denominator and scale are not established by the warehouse. | [`silver.season_team_stats_advanced`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_advanced`](../postgres_etl/flat_schema.py) |
| `three_point_rate` | API three-point rate; denominator and scale are not established by the warehouse. | [`silver.season_team_stats_advanced`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_advanced`](../postgres_etl/flat_schema.py) |
| `free_throws_rate` | API free-throw rate; definition differs from calculated FTM/FGA ft_rate. Do not substitute it. | [`silver.season_team_stats_advanced`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_advanced`](../postgres_etl/flat_schema.py) |
| `points_from_two_pointers_percentage` | API percentage of points from two-pointers, 0-100 scale. | [`silver.season_team_stats_advanced`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_advanced`](../postgres_etl/flat_schema.py) |
| `points_from_three_pointers_percentage` | API percentage of points from three-pointers, 0-100 scale. | [`silver.season_team_stats_advanced`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_advanced`](../postgres_etl/flat_schema.py) |
| `points_from_free_throws_percentage` | API percentage of points from free throws, 0-100 scale. | [`silver.season_team_stats_advanced`](../postgres_etl/flat_schema.py), [`silver.season_team_stats_opponents_advanced`](../postgres_etl/flat_schema.py) |

### Game and shot observations

| SQL statistic | Definition / units | Read from |
| --- | --- | --- |
| `local_score` | Official local-side final score; NULL until a result is available. | [`app_games`](GOLD_TABLE_REFERENCE.md#app_games) |
| `road_score` | Official road-side final score; NULL until a result is available. | [`app_games`](GOLD_TABLE_REFERENCE.md#app_games) |
| `local_standings_score` | Source local-side score used for standings, retained separately from the final score. | [`app_games`](GOLD_TABLE_REFERENCE.md#app_games) |
| `road_standings_score` | Source road-side score used for standings, retained separately from the final score. | [`app_games`](GOLD_TABLE_REFERENCE.md#app_games) |
| `audience` | Reported attendance; source zero for unknown is stored as NULL. | [`app_games`](GOLD_TABLE_REFERENCE.md#app_games) |
| `score` | Points scored by this side in this period, not the cumulative score. | [`app_game_period_scores`](GOLD_TABLE_REFERENCE.md#app_game_period_scores) |
| `points` | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. | [`app_shots`](GOLD_TABLE_REFERENCE.md#app_shots) |
| `coord_x` | Shot x coordinate in the source coordinate system; no warehouse court-unit contract. | [`app_shots`](GOLD_TABLE_REFERENCE.md#app_shots) |
| `coord_y` | Shot y coordinate in the source coordinate system; no warehouse court-unit contract. | [`app_shots`](GOLD_TABLE_REFERENCE.md#app_shots) |
| `fastbreak` | Source flag that the shot was a fast-break action; NULL means unrecorded. | [`app_shots`](GOLD_TABLE_REFERENCE.md#app_shots) |
| `second_chance` | Source flag that the shot followed an offensive rebound; NULL means unrecorded. | [`app_shots`](GOLD_TABLE_REFERENCE.md#app_shots) |
| `points_off_turnover` | Boolean source flag for a shot after a turnover; it is not a points count. | [`app_shots`](GOLD_TABLE_REFERENCE.md#app_shots) |
| `points_a` | Live running score of source side A (local). | [`app_shots`](GOLD_TABLE_REFERENCE.md#app_shots), [`app_play_by_play`](GOLD_TABLE_REFERENCE.md#app_play_by_play) |
| `points_b` | Live running score of source side B (road). | [`app_shots`](GOLD_TABLE_REFERENCE.md#app_shots), [`app_play_by_play`](GOLD_TABLE_REFERENCE.md#app_play_by_play) |
| `start_seconds` | Interval or stint start in elapsed game seconds from tipoff. | [`app_game_player_on_court`](GOLD_TABLE_REFERENCE.md#app_game_player_on_court), [`app_game_team_lineup_stints`](GOLD_TABLE_REFERENCE.md#app_game_team_lineup_stints) |
| `end_seconds` | Interval or stint end in elapsed game seconds; duration is end minus start. | [`app_game_player_on_court`](GOLD_TABLE_REFERENCE.md#app_game_player_on_court), [`app_game_team_lineup_stints`](GOLD_TABLE_REFERENCE.md#app_game_team_lineup_stints) |

### Postseason pairing counts

| SQL statistic | Definition / units | Read from |
| --- | --- | --- |
| `games_played` | Number of fixtures in the pairing, INCLUDING scheduled fixtures; this implementation does not count played fixtures only. | [`app_postseason_series`](GOLD_TABLE_REFERENCE.md#app_postseason_series) |
| `club_a_wins` | Played fixtures won by club A in this pairing. | [`app_postseason_series`](GOLD_TABLE_REFERENCE.md#app_postseason_series) |
| `club_b_wins` | Played fixtures won by club B in this pairing. | [`app_postseason_series`](GOLD_TABLE_REFERENCE.md#app_postseason_series) |

Career `seasons_played` is a count of distinct loaded seasons, registration-based
for players; it does not prove game participation. Record `value` follows its
`metric`; exact metric strings and JSON coverage counts are documented in the
[table reference](GOLD_TABLE_REFERENCE.md#record-metric-values).

## Team formulas and interpretation

### Possessions, pace, efficiency and four factors

For a single team-game:

```text
own_possessions_estimate = FGA + 0.44*FTA - OREB + TOV
possessions = (own_possessions_estimate + opponent estimate) / 2
game_minutes = 40 + 5 * overtime_periods
pace = 40 * possessions / game_minutes
ORtg = 100 * points_for / possessions
DRtg = 100 * points_against / possessions
NetRtg = ORtg - DRtg

eFG = (FGM + 0.5*3PM) / FGA
TOV fraction = TOV / (FGA + 0.44*FTA + TOV)
OREB fraction = team OREB / (team OREB + opponent DREB)
DREB fraction = team DREB / (team DREB + opponent OREB)
FT rate = FTM / FGA
TS = PTS / (2*(FGA + 0.44*FTA))
Assist ratio = AST / FGM
```

These four-factor definitions use **made** free throws for FT rate. API
`free_throws_rate`, `turnovers_ratio` and `assists_ratio` use separate definitions.
Team round rates recompute from cumulative totals. A season pace is
`40*sum(possessions)/sum(game_minutes)`, not an average of game paces.
Game-clock minutes are not the sum of five players' minutes.

Implementations: [advanced.py](../postgres_etl/advanced.py),
[team_rounds.py](../gold_etl/team_rounds.py).

### Expected wins and strength of schedule

MOV = (PF - PA) / counted games. Pythagorean expected win fraction is
`PF^10.25 / (PF^10.25 + PA^10.25)` using cumulative points, and expected wins
multiply that fraction by counted games. The exponent 10.25 is fixed, not fitted
anew each season. Actual wins and expected wins answer different questions.

SRS solves `rating(team) = MOV(team) + mean(opponent ratings)` with mean zero.
SOS is the mean opponent SRS across all games; SOV uses only wins and is NULL
without wins. SRS does not include home-court correction or a margin cap here.
Relative ORtg/DRtg subtract the league offensive rating; relative pace subtracts
league pace. A negative relative DRtg represents better defense.

Adjusted ratings use possession-weighted opponent adjustment. Adjusted offense
and defense center on league rating, adjusted net on zero. A disconnected
game graph gives NULL SRS/SOS/SOV and adjusted ratings. A connected bipartite
graph can define adjusted net but cannot separate adjusted offense and defense.
This can occur in early rounds or phase-only postseason samples; NULL is not
evidence the table failed to load.

Implementations: [team_ratings.py](../gold_etl/team_ratings.py),
[team_rounds.py](../gold_etl/team_rounds.py).

### Home, away and recent form

Each `home_`, `away_`, `last5_`, `last10_` group contains games, wins, MOV,
offensive/defensive/net rating and pace using the same counted box-score games.
Windows use the most recent games in the scope ordered by round then game code,
not necessarily tipoff date. A group with no games has zero counts and NULL rates.
Final Four and other neutral games retain the source local/road designation.

Implementation: [team_splits.py](../gold_etl/team_splits.py).

### Counted possessions and score flow

Counted possessions use an event state machine. Made field goals, turnovers,
defensive rebounds after misses, qualifying final free throws and period ends
close possessions. Offensive rebounds continue a possession; technical free
throws and and-ones do not independently add one. Unexpected opposing action
closes a recorded possession. This event count stays separate from the 0.44
box-score estimate used by the basic ratings.

Possession length is measured from the preceding possession end or period start.
The game average uses possessions with measurable length. The season-scope
average instead weights the available game averages by their counted possessions,
as implemented; it is not necessarily total seconds / all counted possessions.

Lead changes and ties belong to the whole game and repeat on both side rows;
do not add the two sides. A tie is a return to level above 0-0. Time tied includes
0-0. Largest lead and longest unanswered run are per-game values and **maxima**
over season scopes, not sums. Runs of six or more are counts and are summed.

Clutch is time from elapsed second 2100 (last five minutes of regulation)
through game end, including all overtime, with the margin at most five points.
Scoring eligibility uses the margin **before** the scoring event. Missing score
event clocks make time measures NULL without necessarily removing scoring counts.

Implementations: [possessions.py](../postgres_etl/possessions.py),
[score_flow.py](../postgres_etl/score_flow.py),
[team_pbp.py](../gold_etl/team_pbp.py).

### Shot splits, zones and lineups

Flagged points sum positive shot points for each source flag. The implementation
does not restrict the flagged sums to field goals: any made shot row, including
a free throw if present and flagged, can contribute. If any relevant shot flag
is NULL in a game, all three flagged point totals for that game are NULL.
The three categories can overlap and should not be added as a scoring breakdown.

`assisted_field_goals = min(number of AS events, number of made FG events)`
per team-game. This is a capped event count, not a shot-by-shot assist matching
algorithm; EuroLeague assists can lead to free throws. The assisted FG fraction
is that count divided by event FGM. For aggregate rows it is sum(count) / sum(FGM).

Zone tables use field-goal attempts with nonempty source zones only. `fg_pct`
is made/attempts; `attempt_share` divides zone attempts by the club's zone-tagged
attempts in scope. A zone with no attempts has no row. Raw shot coordinates and
zone labels are retained without a warehouse contract for meters, orientation,
rim distance or a paint/midrange/above-break taxonomy.

Lineup ratings use counted possessions and points from complete five-on-five
stints. A pair/triple sums every stored five-man stint containing its members.
There are ten pairs, ten triples and one five-man lineup per full five, so
combination rows overlap. `ortg = 100*points_for/possessions_for`,
`drtg = 100*points_against/possessions_against`, `net_rating = ortg-drtg`.
They are unadjusted team results for that unit. Four-man units are not built.

Implementations: [shot_splits.py](../postgres_etl/shot_splits.py),
[shot_zones.py](../postgres_etl/shot_zones.py),
[team_shot_zones.py](../gold_etl/team_shot_zones.py),
[lineup_ratings.py](../gold_etl/lineup_ratings.py).

## Frontend display and availability

| Situation | Display / read rule |
| --- | --- |
| Ratio numerator is zero with a positive denominator | A measured zero is valid. |
| Missing input, zero denominator, absent advanced row | Display unavailable, not a fabricated zero. |
| Season PER or Win Shares | Read final snapshot in the selected scope; do not average game PER or sum snapshots. |
| Low-minute game PER | game_per is NULL below 180 seconds; game_uper/game_aper can remain present. |
| Per-game rate versus season rate | Preserve the on-court versus estimated distinction and the exact denominator. |
| RAPM defense versus defensive rating | Higher RAPM defense is better; lower DRtg or drtg_diff is better. |
| Lineup/on-off ranking | Show seconds and possessions; no built-in sample-size qualification. |
| Official season leaderboard | Use `qualified` and `min_games`; full-season derived rate tables have no automatic equivalent filter. |
| Official standings split text | Keep source record text; do not present it as a raw count or numerical percentage. |
| API field with unestablished definition | Keep the API label/source distinction until its definition is verified. |
| Historical event analytics | E2007+ and actual source availability; not every game is complete. |
| Local calculation exists but missing on frontend | Check exact SQL name, scope/mode, units, joins and published data freshness separately. |

The tables do not contain BPM/OBPM/DBPM, VORP, Estimated Wins Added, win
probability, WPA, tracking measures or fitted play-type statistics. See the
[catalog](DATA_CATALOG.md#statistics-that-have-no-stored-field). This work
documents warehouse availability; it does not change the frontend or publish data.

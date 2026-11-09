# Data dictionary

This is the authoritative reference for **how the pipeline calculates and checks its data**: Silver keys and naming rules, the formulas and rules behind every calculated table, the validation results recorded when each table was built, and the checks that run after a load.

For other questions, start elsewhere:

| Question | Document |
| --- | --- |
| Which table should the app read? | [Gold data catalog](DATA_CATALOG.md) |
| What does a column mean? | [Gold table reference](GOLD_TABLE_REFERENCE.md), [Silver table reference](SILVER_TABLE_REFERENCE.md) |
| What does a statistic measure? | [Statistics glossary](STAT_GLOSSARY.md) |
| Where does Silver data come from? | [Silver catalog](SILVER_CATALOG.md), [Bronze catalog](BRONZE_CATALOG.md) |

Validation figures (row counts, agreement percentages, sizes) describe the checkpoint at which they were recorded, not the current live data. The rules were checked against the code on 2026-10-20.

## Contents

- [Conventions used by calculated tables](#conventions-used-by-calculated-tables)
- [Silver](#silver)
  - [Silver table names and keys](#silver-table-names-and-keys)
  - [Standard column names](#standard-column-names)
  - [Source value rules](#source-value-rules)
  - [Post-load checks](#post-load-checks)
- [Calculated per-game tables](#calculated-per-game-tables)
  - [Derived per-game advanced tables](#derived-per-game-advanced-tables)
  - [`game_team_possessions`](#game_team_possessions)
  - [`game_team_score_flow`](#game_team_score_flow)
  - [`game_team_shot_splits`](#game_team_shot_splits)
  - [Shot zone codes](#shot-zone-codes-shotszone)
  - [`game_player_on_court`](#game_player_on_court)
  - [`game_team_lineup_stints`](#game_team_lineup_stints)
- [Gold source copies and page tables](#gold-source-copies-and-page-tables)
  - [Source copies](#source-copies)
  - [Season player qualification columns (30l)](#season-player-qualification-columns-30l)
  - [`app_standings`](#app_standings)
  - [Records tables](#records-tables)
  - [`app_team_season_stats`](#app_team_season_stats)
  - [`app_postseason_series`](#app_postseason_series)
  - [`app_players`](#app_players)
  - [`app_club_identities`](#app_club_identities)
- [Gold advanced statistics](#gold-advanced-statistics)
  - [Team round derivations (in memory)](#team-round-derivations-in-memory)
  - [`app_standings_stats`](#app_standings_stats)
  - [`player_round_stats`](#player_round_stats)
  - [`player_round_ratings`](#player_round_ratings)
  - [`player_round_win_shares`](#player_round_win_shares)
  - [`team_pbp_stats`](#team_pbp_stats)
  - [`player_on_off`](#player_on_off)
  - [`lineup_ratings`](#lineup_ratings)
  - [`player_rapm`](#player_rapm)
- [Neon contract](#neon-contract)

## Conventions used by calculated tables

These definitions apply throughout this document unless a section says otherwise.

| Term | Meaning |
| --- | --- |
| **Counted game** | A played game with a full box score for both sides. Forfeits (`game_stat_gaps` row `*`, for example E2001 game 264 and E2003 game 200) and unplayed games are not counted, so `games_played` can be one lower than the API's. |
| **Scope** | `all` (every phase of the season), one phase code (`RS`, `PI`, `PO`, `FF`, `TS`, …), or `PS` (`PI` + `PO` + `FF`). Scopes overlap; they are alternative views, not additive parts. |
| **Round number** | The round stored in `silver.games`, continuous across phases within a season. |
| **Cumulative snapshot** | Round tables store totals through each round. A club or player has a row for every round of the scope from its first counted game; a round it did not play repeats the previous values. |
| **Rates** | Fractions (`0.512`), not percentage points, unless stated. |
| **`NULL`** | A needed input was missing or a denominator was zero. In cumulative tables, one missing game value makes all later cumulative values `NULL`. |
| **Event order** | Play-by-play events are ordered by period rank, then the overtime number derived from `minute`, then `event_ordinal` (which restarts in each source period array). `play_number` is not chronological. |
| **Elapsed seconds** | `marker_time` (time left in the period) converted to seconds since tip-off: 10:00 per quarter, 5:00 per overtime. Every overtime has the period label `ExtraTime`; its number comes from `minute`. |
| **Field-goal event codes** | Made: `2FGM`, `3FGM`, `LAYUPMD`, `DUNK`. Missed: `2FGA`, `3FGA`, `LAYUPATT`, `2FGAB`, `3FGAB`. E2008-E2014 record many shots as layups, dunks and blocked attempts; with these codes the event totals equal the box score's field goals. |
| **Free-throw trip** | Consecutive free throws (`FTM`, `FTA`) of one club at the same clock, ignoring substitutions, timeouts and fouls between them. |
| **Game end** | 2,400 seconds plus 300 per overtime, counting overtimes from events that carry a clock. |

## Silver

### Silver table names and keys

The local `silver` schema holds 26 source tables, 7 calculated tables and `load_log`. The loader and the CSV exporter use `search_path = silver`, so a bare name such as `games` means `silver.games`. Exact columns, types, source JSON paths and keys are in [flat_schema.py](../postgres_etl/flat_schema.py).

Every primary key begins with `competition_code` and `season_code`; always filter on both. Codes such as `person_code` are text, which preserves leading zeroes. The table below shows the rest of each key.

| Table | Rest of the key | One row |
| --- | --- | --- |
| `seasons` | none | one competition season from the v2 catalogue |
| `clubs` | `club_code` | one club in one season |
| `people` | `person_key` | one deduplicated person in one season |
| `registrations` | `registration_key` | one person's club and role registration |
| `rounds` | `round_key` | one phase and round definition |
| `games` | `game_code` | one played or scheduled fixture |
| `game_officials` | `game_code`, `official_number` | one official assigned to a game |
| `game_period_scores` | `game_code`, `side`, `period_number` | one quarter or overtime score |
| `game_player_stats` | `game_code`, `side`, `person_key` | one player's game box score |
| `game_team_stats` | `game_code`, `side`, `stats_kind` | one team box-score row or total |
| `game_stat_gaps` | `game_code`, `stat_name` | one missing or unrecorded measure; `*` means no box score. There are no rows from E2012 on. |
| `play_by_play` | `game_code`, `period`, `event_ordinal` | one live event |
| `shots` | `game_code`, `shot_ordinal` | one shot attempt |
| `season_player_stats_*` (4 tables) | `phase_code`, `mode`, `entry_ordinal` | one player entry in a v3 feed |
| `season_team_stats_*` (2 tables) | `phase_code`, `mode`, `club_code` | one club in a v3 feed (accumulated mode only) |
| `standings_basic`, `standings_calendar`, `standings_streaks`, `standings_ahead_behind`, `standings_margins` | `phase_code`, `round_number`, `club_code` | one club snapshot after a round |
| `standings_calendar_streaks` | `phase_code`, `round_number`, `club_code`, `streak_ordinal` | one calendar streak |
| `standings_basic_form` | `phase_code`, `round_number`, `club_code`, `result_ordinal` | one recent result |

The keys of the calculated tables are given in their own sections below.

### Standard column names

The source JSON paths are unchanged, but the SQL columns use one name for each statistic across v2 and v3:

| Former column | Silver column |
| --- | --- |
| `assistances` | `assists` |
| `fouls_commited` | `fouls_committed` |
| `fouls_received` | `fouls_drawn` |
| `blocks_favour` | `blocks` |
| `valuation` | `pir` |
| `field_goals_made2`, `field_goals_attempted2` | `two_pointers_made`, `two_pointers_attempted` |
| `field_goals_made3`, `field_goals_attempted3` | `three_pointers_made`, `three_pointers_attempted` |
| `field_goals_made_total`, `field_goals_attempted_total` | `field_goals_made`, `field_goals_attempted` |
| `points_scored` | `points` |
| `time_played` | `seconds_played` |
| `possesions` | `possessions` |
| `quater1_*`, `quater3_*` | `quarter1_*`, `quarter3_*` |
| `longest_wins_streak_*`, `longest_loses_streak_*` | `longest_win_streak_*`, `longest_loss_streak_*` |
| `point_difference1to5`, `6to10`, `11to15`, `_more_than15` | `point_difference_1_to_5`, `_6_to_10`, `_11_to_15`, `_more_than_15` |
| `dorsal`, `dorsal_raw` | `jersey_number`, `jersey_number_raw` |

`game_stat_gaps.stat_name` uses these Silver names, or `*` for a game with no box score. Some Gold tables (`app_team_season_stats`, the records tables) keep the former names in their output.

### Source value rules

**Unrecorded statistics.** Source zeros that mean a statistic was not recorded become `NULL` and are listed in `game_stat_gaps`.

**Points corrections.** Box-score points are checked against the game score and the shooting makes (warnings `team_points_differ_from_score` and `points_differ_from_makes`). Only a provable error is corrected: when a team's makes equal its game score but its points do not, each player's points are set to their makes and their PIR moves by the same amount. The game gets a `points` gap row, with reason `points_corrected`, naming the players and the source values. This applies to U2004 games 103 and 138 and U2005 game 4. The API season feeds keep the source values, so Gold quality warns about those players and clubs.

**Fixtures and winners.** Future fixtures stay in `games` with `played = false` and `NULL` scores. Quarter and overtime scores are separate child rows. The source's `winner` object is the **season champion**; `match_winner_club_code` is the winner of a played game. `game_status` is the raw source field and can contradict the facts: some unplayed E2019 games are still `Confirmed`. Use `status`, which Silver derives.

**Person names and cities.** The source sends person names in capitals. Silver stores them in display form, keeping the `Surname, Given` order. The rules are in [text_clean.py](../postgres_etl/text_clean.py) and apply to every person-name column: `people` (`name`, `alias`, `alias_raw`, `passport_name`, `passport_surname`), the `person_name`, `player_name` and `coach_name` columns, and `game_officials.name` and `alias`.

- Words become title case: `GÖK, ERDAL` becomes `Gök, Erdal`.
- `II`, `III` and `IV` stay in capitals, and `JR` becomes `Jr.`: `BROWN III, JOHN` becomes `Brown III, John`, and `COWAN JR, ANTHONY` becomes `Cowan Jr., Anthony`.
- `Mc` names join and keep the inner capital: `MC DUFFIE` becomes `McDuffie`, and `MCKINLEY` becomes `McKinley`.
- Given names that the source writes in camel case somewhere (`DeJuan`, `DeAndre`, `LaRon` and others) are written that way everywhere.
- Two-letter initials stay in capitals: `PJ`, `TJ`, `AJ`.
- Stray spaces around commas are removed.
- `jersey_name` and `abbreviated_name` keep the source text.

`clubs.city` values sent in capitals become title case, so `ISTANBUL` becomes `Istanbul`. A few wrong values are mapped: `St Petersburg` becomes `Saint Petersburg`, and club names given as the city become the city (`BENFICA` becomes `Lisbon`). Club names and venue names keep the source text, because they change with sponsors. Bronze keeps every exact source value.

**Codes and labels.** The same file defines these rules:

- Each country has one code and one name in `people`, `clubs` and `game_officials`, including the `birth_country_*` columns. `UK` becomes `GBR`, `IVO` (Ivory Coast) becomes `CIV`, and `ZAI` becomes `COD`. `FYR` with the name `----` becomes `MKD`, North Macedonia. `LAD` (Adriatic League) and `NAT` (No country) become `NULL`.
- `registrations.role_name` uses sentence case without underscores: `Unified_Score_Crew` becomes `Unified score crew`, and the source typo `Assitant coach` becomes `Assistant coach`.
- `position` in `registrations` and `game_player_stats` is 1 (guard), 2 (forward) or 3 (center). The source's `-1` and `0` become `NULL`.
- In `games.group_name` and `group_raw_name`, words in capitals become title case: `Group SEMIFINAL A` becomes `Group Semifinal A`. `Semi-Final` is written `Semifinal`.

**Percentages.** v3 percentage strings such as `45.5%` become the number `45.5` (percentage points).

**Season feeds.** Player and team season stats contain only API rows; derived `PS` rows are built in Gold. A player row is one entry in a category, phase and mode feed, not a unique person, and `accumulated` and `perGame` feeds can list different players. The fetcher keeps the stronger stored response when the API answers stale or partial feeds (see [api_requests](../api_requests/README.md#stale-statistics-feeds)), and the load quality report flags missing or partial phase/mode feeds.

**Standings.** An answer with fewer clubs or games than the stored one is kept out. Gold `--quality-only` warns when the five standings feeds of a round disagree on games played or won, because the API caches each feed separately.

**Live player identities.** `player_code` is the upstream ID; `person_code` is the matched box-score `person_key`. Join on `person_code`.

**Provenance backfill (feature 16b).** All 27 cached EuroLeague seasons (E2000-E2026) were reloaded. All 727 table/season scopes kept their row counts, 3,987,204 source rows in total. The load wrote 742 log entries, including zero-row replacements, and a controlled E2025 `games` rerun added one more. Every current row matched its log entry. The provenance mechanism itself is described in the [Silver catalog](SILVER_CATALOG.md#provenance).

### Post-load checks

Every real load runs read-only quality checks for the selected seasons. To check stored data without loading:

```powershell
python postgres_etl/main.py -sc 2025 --quality-only
python postgres_etl/main.py -sc 2025 -tb games game_player_stats --quality-only
```

The checks:

- count loaded rows and flag empty selected tables,
- verify the result rules for played and unplayed games,
- check game, club and person references when both tables are selected (a partial load is checked only against its own tables), and
- check the provenance columns against `load_log`.

Primary keys already prevent duplicates. The checks do **not** prove that the upstream data is complete, that historical live feeds exist, or that every metric makes sporting sense. Use `--skip-quality-check` only to bypass the automatic pass on purpose. Tests are in `postgres_etl/tests/`.

## Calculated per-game tables

These Silver tables are built by the scripts in `postgres_etl/` from other Silver tables (see [postgres_etl/README.md](../postgres_etl/README.md#calculated-per-game-tables)). Each carries `load_id` and `loaded_at`. Gold copies them under `app_<name>` without those two columns, and all are published to Neon for every loaded season.

### Derived per-game advanced tables

| | `game_team_advanced` | `game_player_advanced` |
| --- | --- | --- |
| **Built by** | `python postgres_etl/advanced.py -sc <seasons>` | same |
| **Rest of the key** | `game_code`, `side` | `game_code`, `side`, `person_key` |
| **One row** | one club per counted game | one player box-score line per counted game |
| **Gold** | `app_game_team_advanced` (drops `opponent_club_code`, `phase_code`, `round_number`) | `app_game_player_advanced` (adds `club_code`, `seconds_played` and game PER; drops `rate_source`) |

Forfeits and unplayed games have no rows. These are **box-score estimates**; possessions counted from play-by-play are stored separately in [`game_team_possessions`](#game_team_possessions) and never replace them.

#### Formulas

| Column | Formula |
| --- | --- |
| `game_minutes` | 40, plus 5 per overtime in `game_period_scores` |
| `own_possessions_estimate` | `field_goals_attempted + 0.44 × free_throws_attempted − offensive_rebounds + turnovers` for the club |
| `possessions` | Mean of both clubs' estimates; the same on both rows |
| `pace` | `40 × possessions / game_minutes` |
| `offensive_rating`, `defensive_rating`, `net_rating` | `100 × points / possessions` for the club and its opponent; net is the difference |
| `efg_pct`, `opp_efg_pct` | `(field_goals_made + 0.5 × three_pointers_made) / field_goals_attempted` |
| `tov_pct`, `opp_tov_pct` | `turnovers / (field_goals_attempted + 0.44 × free_throws_attempted + turnovers)` |
| `orb_pct`, `drb_pct` | Own rebounds of a type / (own of that type + opponent's of the other type) |
| `ft_rate`, `opp_ft_rate` | `free_throws_made / field_goals_attempted` |
| `true_shooting_pct` | `points / (2 × (field_goals_attempted + 0.44 × free_throws_attempted))` |
| `assist_ratio` | `assists / field_goals_made` |
| `game_score` (player) | Hollinger: `points + 0.4 FGM − 0.7 FGA − 0.4 (FTA − FTM) + 0.7 OREB + 0.3 DREB + steals + 0.7 assists + 0.7 blocks − 0.4 fouls_committed − turnovers` |
| `tov_pct`, `efg_pct`, `true_shooting_pct` (player) | The club formulas applied to the player's own line |
| `usage_pct`, `assist_pct`, `orb_pct`, `drb_pct`, `trb_pct`, `steal_pct`, `block_pct` (player) | On-court rates (below) when the game has play-by-play. Otherwise Basketball-Reference box-score estimates using `seconds_played` and the club's `total` row, `NULL` below 180 seconds. The estimated `assist_pct` is also `NULL` when the player's minutes share of team baskets, minus their own baskets, is below one teammate basket. `NULL` for zero minutes either way. |
| `rate_source` (player, Silver only) | `on_court` or `estimate`: which form the seven rates above use |

#### On-court rates (feature 32)

For every box-score player whose game has play-by-play and starters, events are attributed by event order to the lineups on court, exactly as in [`game_team_lineup_stints`](#game_team_lineup_stints). The player's own events count only while the walk has them on court; team and opponent events count for every player on court at the time. **Plays** are field-goal attempts plus 0.44 × free throws (`FTM`, `FTA`) plus turnovers (`TO`). Team rebounds without a person count for the lineups.

| Column | On-court form |
| --- | --- |
| `usage_pct` | Player plays / team plays |
| `assist_pct` | Player `AS` / (team field goals made − player field goals made + team free-throw trips − player free-throw trips) |
| `orb_pct`, `drb_pct`, `trb_pct` | Player `O`, `D` or both / (team rebounds of that type + opponent rebounds of the other type), or all four for `trb_pct` |
| `steal_pct` | Player `ST` / opponent possessions closed while the player was on court (the [`game_team_possessions`](#game_team_possessions) counter) |
| `block_pct` | Player `FV` / opponent two-point attempts |

Rules and findings:

- The event codes `AS`, `ST`, `FV`, `TO`, `O` and `D` match the box score's assists, steals, blocks, turnovers and rebounds for every E2025 player-game, and for 99.7-99.9% in E2007 and E2015.
- EuroLeague also credits assists on fouls that lead to free throws (about 7-9% of `AS` events precede free throws), so `assist_pct` counts free-throw trips as chances.
- A trip belongs to the lineup at its first free throw and to the player who shoots that one. A run right after the club's made field goal at the same clock is an and-one and adds no trip.
- A box-score player whom the walk never puts on court gets `NULL` rates.
- `rate_source` is `estimate` before E2007 and for E2018 game 21, which has no play-by-play.
- The Silver check warns about any on-court rate outside 0-1. Over E2007-E2026 there is one: E2012 game 237 (Ponkrashov, 2 assists in 163 seconds), where an `AS` at 01:50 has no basket or trip of his club after it.
- For E2025 players with at least 10 minutes, on-court usage differs from the estimate by 0.006 at the median and 0.020 at the 90th percentile.

The minutes share used by the estimates was once 5× too small; the `silver-player-minutes-share` fix rebuilt the stored rows with the corrected share (seconds over game seconds). `player_round_stats` never used those columns.

#### Game PER (Gold `app_game_player_advanced` only)

| Column | Meaning |
| --- | --- |
| `game_uper` | Hollinger's unadjusted PER per minute from that game's line only, with the team's assist ratio for that game and league constants (factor, VOP, DRB%) summed over every counted game of the game's phase scope (`RS`, `PI`, `PO`, `FF`, …) through the game's round, exactly as in [`player_round_ratings`](#player_round_ratings) |
| `game_aper` | `game_uper × league pace (same scope, through the round) / the game's own team pace` |
| `game_per` | `game_aper × 15 / the seconds-weighted mean game_aper of the games in the same scope and round`, so the league mean is 15 per scope and round |

- All three are `NULL` when `seconds_played` is 0 or missing, an input is missing or a denominator is zero.
- `game_per` is also `NULL` below 180 seconds, where a few seconds give extreme values. Those lines keep `game_uper` and `game_aper` and still count toward the league mean, so other lines are unaffected.
- Zero-minute rows keep Silver's `game_score` but have `NULL` rates and PER.
- **Season PER is not an average of game PER.** Use `player_round_ratings` (the last round of the season).
- A player's first game ties `player_round_ratings.per` (scope `RS`, round 1) exactly.

`--quality-only` checks the round-1 ties against the round tables (to 0.00001, since those divide rounded sums; `usage_pct` only for `estimate` rows), that every `game_per` follows its formula, that no line under 180 seconds has a `game_per`, and the row shape and `NULL` handling. It warns where a percentage is below 0 or above 2.

### `game_team_possessions`

| | |
| --- | --- |
| **Built by** | `python postgres_etl/possessions.py -sc <seasons>` from `play_by_play`, `games` and `game_team_advanced` |
| **Seasons** | E2007 onward; earlier seasons have no play-by-play and no rows |
| **Rest of the key** | `game_code`, `side` |
| **One row** | one club per played game with events and a `game_team_advanced` row |

| Column | Meaning |
| --- | --- |
| `counted_possessions` | Possessions counted from the event stream |
| `possession_seconds` | Sum of the measurable possession lengths, in game seconds |
| `avg_possession_seconds` | `possession_seconds` / the number of possessions with a measurable length (`NULL` when none) |
| `estimated_possessions` | The box-score `possessions` of `game_team_advanced`, copied for comparison |

**Rules:**

- A possession ends, for the team that had it, on a made field goal, a turnover, a defensive rebound after a miss, the last made free throw of a trip, or the end of a period. An offensive rebound continues it.
- Technical free throws (after a technical, coach or bench technical event) count for nothing, and an and-one adds no possession.
- When the other club acts while a club is recorded as holding the ball, the earlier club's possession ends at that point.
- Length is the elapsed time from the previous possession's end (or the period start) to this end.

**Validation** over E2007-E2026 (10,098 club games):

- Counted minus estimated possessions averages +0.12 (standard deviation 1.38). 90.2% of club games are within 3%, 98.3% within 5% and 99.8% within 10%. The average possession lasts 17.0 seconds.
- E2007-E2009 agree less well (E2007 within 3%: 71%); E2019-E2025 agree better (93-95%).
- Event counts match the box score exactly for turnovers (99.4% of club games), free throws made and attempted, and field goals (once layups and dunks are included).
- `--quality-only` compares the stored rows with a fresh derivation and warns for club games whose counted possessions differ from the estimate by more than 10% (16 rows: 7 in E2007 and 9 in E2009).

### `game_team_score_flow`

| | |
| --- | --- |
| **Built by** | `python postgres_etl/score_flow.py -sc <seasons>` from `play_by_play` and `games` |
| **Seasons** | E2007 onward; the same rows as `game_team_possessions` |
| **Rest of the key** | `game_code`, `side` |
| **One row** | one club per played game whose events carry a running score |

| Column | Meaning |
| --- | --- |
| `points_for`, `points_against` | Final score from the running score (equal to `games.local_score` and `road_score` in every E2007-E2026 game) |
| `lead_changes`, `ties` | Times the leader differs from the previous leader; times the score becomes level above 0-0. The same on both rows. |
| `time_leading_seconds`, `time_trailing_seconds`, `time_tied_seconds` | Game seconds ahead, behind and level; they add up to the game end |
| `largest_lead` | Biggest own margin (0 when never ahead) |
| `longest_run`, `runs_6_plus` | Largest unanswered scoring streak, and how many streaks reached 6 points |
| `clutch_seconds`, `clutch_points_for`, `clutch_points_against` | Time and points in the last five minutes of regulation and in all overtime while the margin before the event was 5 or less |

**Rules:**

- `play_by_play.points_a` is the local team's running score and `points_b` the road team's. They are present on scoring events; a missing value keeps the previous one.
- An event that changes both scores breaks every run.
- The time and `clutch_seconds` columns are `NULL` for a game with a scoring event that has no usable clock: 20 club games in 10 games (7 in E2016, 1 in E2020 and 2 in E2022). Counts and points do not depend on the clock.
- A game with no score in its events has no row.

**Validation** over E2007-E2026 (10,098 club games): 5.6 lead changes and 4.3 ties per game, an average largest lead of 10.8 points, a longest run of 9.4 points and 3.1 runs of 6 or more per team; 53% of club games have clutch time. `--quality-only` compares with a fresh derivation and warns when a final score differs from `games` (none found).

### `game_team_shot_splits`

| | |
| --- | --- |
| **Built by** | `python postgres_etl/shot_splits.py -sc <seasons>` from `games`, `shots` and `play_by_play` |
| **Seasons** | E2007 onward; the same rows as `game_team_possessions` |
| **Rest of the key** | `game_code`, `side` |

| Column | Meaning |
| --- | --- |
| `fast_break_points`, `second_chance_points`, `points_off_turnover_points` | Points of the team's made shots (free throws included, since the feed flags them) whose `fastbreak`, `second_chance` or `points_off_turnover` flag is true. A shot with several flags counts in each. |
| `field_goals_made` | Made field-goal events in `play_by_play` |
| `assisted_field_goals`, `assisted_fg_pct` | The team's `AS` events, capped at its made field goals, and that count over `field_goals_made` |

**Rules and coverage:**

- The three point columns are `NULL` for a game in which any shot has a `NULL` flag, or which has no shots.
- Flag coverage: none before E2015 (except a few club games in E2008, E2009, E2013 and E2014), 76% of E2015 team games (382 of 500), and every game from E2016 on: 6,510 of the 10,098 club games.
- Assists are logged at other clock times than their shots, sometimes much later, so pairing assists with shots by clock undercounts badly. The `AS` count instead equals the box score's assists in 99.5% of club games (mean difference −0.003).
- The average assisted share is 58% (62% in E2025).

`--quality-only` compares with a fresh derivation and warns when assisted goals exceed made goals or a team's shot points differ from `games` (none found).

### Shot zone codes (`shots.zone`)

The per-game zone table `game_team_shot_zones` is no longer built; the web app derives its own zones from `app_shots` coordinates. Its findings still describe the feed's `shots.zone` codes:

- Counting field goals only, zone totals equal the box score's field goals made in every game, and its field goals attempted in 97-100% of games per season (a few shots have no zone).
- The codes are the feed's own letters. No names are assumed; this is what the data showed over E2007-E2026:

| Zone | Shots | Mean court x, y | Three-pointers | Made |
| --- | --- | --- | --- | --- |
| A | 29,247 | 65, 23 | 10% | 87% |
| B | 112,559 | −85, 95 | 0% | 57% |
| C | 102,786 | 96, 95 | 0% | 56% |
| D | 50,971 | −161, 178 | 0% | 43% |
| E | 38,561 | 160, 211 | 0% | 37% |
| F | 27,226 | −346, 318 | 10% | 40% |
| G | 29,981 | 320, 385 | 20% | 38% |
| H | 108,086 | −431, 515 | 99% | 36% |
| I | 109,581 | 433, 512 | 99% | 36% |
| J | 6,427 | −286, 673 | 100% | 32% |

### `game_player_on_court`

| | |
| --- | --- |
| **Built by** | `python postgres_etl/on_court.py -sc <seasons>` from `games`, `game_player_stats` and `play_by_play` |
| **Seasons** | E2007 onward |
| **Rest of the key** | `game_code`, `side`, `person_key`, `interval_ordinal` (the player's stretches, counted from 1 in time order) |
| **Columns** | `club_code`, `start_seconds`, `end_seconds` (elapsed game seconds) |

This is the base of the lineup tables.

**Rules:**

- A side starts with the players whose `started` flag is set. An `IN` adds a player and an `OUT` removes one, in event order. Players carry across periods, and everyone still on the floor is closed at the game end.
- Older seasons log period-start substitutions at times outside the period (`11:00`, or `06:00` in overtime); these are placed at the period start.
- An `IN` for a player already on court, an `OUT` for one who is not, and events without a person code are ignored.
- A player's `OUT` and `IN` at the same second join into one stretch; zero-length stretches are dropped.
- Every game's play-by-play ends with `EG`/`EP` events that have no clock and a minute one past the last overtime. Counting them once added a phantom overtime to the 236 overtime games; feature 29a fixed this here and in `game_team_score_flow` (where it had added 300 seconds to the final leader's time leading) and rebuilt the season slices.

**Validation** over E2007-E2026 (5,049 games, 322,528 stretches, 119,331 player-games):

- Summed on-court seconds differ from `seconds_played` by 7.2 seconds on average. 85.0% of player-games are within 5 seconds, 96.9% within 60 and 99.6% within 120.
- E2007-E2010 box scores have minute precision (mean difference 35-38 seconds, 79-84% within 60 seconds). E2011-E2025 have a mean difference of 0.3-4.3 seconds, with 93-99.5% of player-games within 5.
- 246 games (458 player-games) have a player more than 120 seconds off, 400 of those player-games in E2007-E2010. `--quality-only` reports this count per season as a `WARN`, and fails only when the stored rows differ from a fresh derivation.
- Hand check: E2025 game 31, player 004866 (started; out at 03:04 of Q1, back at 00:31 of Q1, out at 08:01 of Q4) has stretches 0-416, 569-1462 and 1584-1919, 1,644 seconds in total, equal to the box score's `seconds_played`.

### `game_team_lineup_stints`

| | |
| --- | --- |
| **Built by** | `python postgres_etl/lineups.py -sc <seasons>`, right after `game_player_on_court`, from the same tables |
| **Seasons** | E2007 onward |
| **Rest of the key** | `game_code`, `side`, `stint_ordinal` (counted from 1 over the stored stints of the game) |
| **One row** | one stint from one team's side; each stint has two rows |

| Column | Meaning |
| --- | --- |
| `club_code`, `opponent_club_code` | The team and its opponent |
| `start_seconds`, `end_seconds` | Elapsed game seconds, from the substitution that formed the lineups to the next one |
| `players`, `opponent_players` | The five `person_key`s on court for each team, sorted and joined by commas |
| `possessions_for`, `possessions_against` | Counted possessions that ended while the lineups were on court |
| `points_for`, `points_against` | Points scored by each team in the stint (from the running score) |

**Rules:**

- A stint is a stretch with the same five players on court for both teams. It uses the `game_player_on_court` walk, with a boundary at each substitution group that changes a lineup. Lineups carry across periods.
- Events are attributed by event order, not by clock. A substitution between two free throws at one clock time splits them, and a free throw made while a team is a player short belongs to an incomplete stint.
- Only stints where both teams have exactly five players are stored. A zero-length stint with no event is dropped.
- A counted possession belongs to the stint on court at the event that closes it; the possession that ends a period belongs to that period's last stint.

**Validation** over E2007-E2026 (5,049 games, 346,894 rows, 34.4 stints per team-game):

- A team's stint points equal its final score in 10,061 of 10,098 team-games (99.6%), and its stint possessions equal `counted_possessions` in 10,046 (99.5%; 323 possessions apart in total).
- A player's stint seconds differ from `game_player_on_court` by 0.13 seconds on average in E2025.
- `--quality-only` compares with a fresh derivation and warns for team-games whose stints cover less than 95% of the game: 12 team-games (6 games) in E2008, E2010, E2013, E2014 and E2017.
- Hand check: E2025 game 31's first stint runs 0-226 seconds (the first substitution is at 06:14 of Q1) with the five starters of each team.

## Gold source copies and page tables

Gold is built by `python gold_etl/main.py` (see [gold_etl/README.md](../gold_etl/README.md)). `--dry-run` reports Silver source and derived row counts without writing; `--quality-only` compares Gold keys and full values with Silver. Both read the local database only. Local connections search `silver` first, so use explicit `gold.` and `silver.` names in SQL.

### Source copies

Feature 30a copies 16 Silver tables into Gold with the same columns, types, `NULL`s and primary keys, without `load_id` and `loaded_at`: `seasons`, `clubs`, `people`, `registrations`, `rounds`, `games`, `game_officials`, `game_period_scores`, `game_player_stats`, `game_team_stats`, the four `season_player_stats_*` tables, `play_by_play` and `shots`. The eight per-game tables are copied the same way (two of them as projections, see [above](#derived-per-game-advanced-tables)).

Exceptions:

- **`app_registrations`** has one row per `(competition_code, season_code, person_key, club_code, role_code)`. A club can deregister a person and register them again in the same season; Gold merges those periods. `active` is true if any period is active, `start_at` is the earliest and `end_at` the latest known date, and every other column, including `registration_key`, comes from the latest period (greatest `start_at`, then `end_at`, then `external_id`; a missing date sorts first). Silver keeps every source registration.
- **Season player tables** copy only the non-`PS` API rows, then add calculated `perGame` rows and qualification columns (below). Feature 30b adds derived `PS` rows to the traditional and misc tables from played `PI`/`PO`/`FF` box scores; a source rerun leaves them in place. Missing box-score measures propagate as `NULL`, and percentages and per-game values round half-even to one decimal. A season without a played postseason has no `PS` rows. The advanced and scoring tables have no `PS` rows.

### Season player qualification columns (30l)

The four `app_season_player_stats_*` tables have three columns that Silver does not, so the web app needs no calculation:

| Column | Meaning |
| --- | --- |
| `is_calculated` | `false` on rows copied from the API feed; `true` on rows Gold derives (every `PS` row and the added `perGame` rows) |
| `min_games` | Games a player needs in that `(season_code, phase_code)` to qualify for leaderboards. One value per scope, the same in both modes. |
| `qualified` | `games_played >= min_games`, on every row |

**Calculated `perGame` rows.** The API lists every player in `accumulated` mode but only players above a games threshold in `perGame` mode. Gold adds the missing `perGame` rows (phases `RS`, `PI`, `PO`, `FF` and `all`) from the same player's `accumulated` row, so both modes cover the same players:

- In the traditional table, each counting column is the accumulated value divided by `games_played`, rounded half-even to one decimal; `minutes_played` is the unrounded quotient.
- Everything else is copied unchanged: percentages, the whole advanced, scoring and misc tables, `games_played`, `games_started`, the club fields, name, age and image. A traded player therefore keeps the feed's club code (for example `MCO;PAR`) in both modes.
- `player_ranking` is `NULL` on calculated rows, and their `entry_ordinal` continues after the feed's highest ordinal in the scope, so feed rows are never renumbered.
- Checked against the 13,889 existing pairs of E2024-E2026: every counting and copied column matches; percentages differ by 0.1 in about 0.2% of cells (the API's own rounding), which is why percentages are copied rather than recomputed.

**The threshold.** `min_games = floor(R / 2) + 1`, where `R` is the number of distinct played rounds in the scope in `silver.games` (`all` is the whole season, `PS` is `PI` + `PO` + `FF`). It is 1 for `FF`, where the feed lists every player.

- For E2024-E2026, no feed `perGame` row is below `min_games`, and no accumulated player at or above it lacks a feed row.
- The rule does not reproduce four older `PO` scopes (E2000, E2009, E2014, E2017), where the feed also lists players just below it; Gold quality prints a `WARN` for them.
- `PS` rows follow the same rule: every player has a `perGame` row, and `PS` `min_games` is 5 for E2024 and E2025 (9 postseason rounds).
- The current season is recomputed on every refresh, so `min_games` and `qualified` change as rounds are played.

The code is in `gold_etl/qualification.py` (threshold) and `gold_etl/per_game_rows.py` (derived rows).

### `app_standings`

Built from the seven `silver.standings_*` tables and `silver.clubs`.

| Rest of the key | One row | Use |
| --- | --- | --- |
| `phase_code`, `round_number`, `club_code` | one club in the standings of one phase and round, with every feed | Filter season, phase and round; order by `group_name`, `basic_position`, `club_code`. The latest round is `max(round_number)`. |

Rows exist exactly for the clubs in `basicstandings` (a quality check enforces this), so only for group-phase rounds. It was verified field by field against the web app's former 7-table standings query for all seasons (0 differences).

**Contract for the web app:**

- Columns map to `StandingEntry` mechanically: the feed prefix (`basic_`, `calendar_`, `streaks_`, `ahead_behind_`, `margins_`) plus the snake_case field name. For example `basic.winPercentage` → `basic_win_percentage`, `aheadBehind.quarter1Ahead` → `ahead_behind_quarter1_ahead`, `streaks.longestWinStreakCurrentSeason` → `streaks_longest_win_streak_current_season`, `margins.pointDifference1To5` → `margins_point_difference_1_to_5`.
- `clubCode`, `clubName`, `clubTvCode`, `crestUrl`, `groupName` → `club_code`, `club_name`, `club_tv_code`, `crest_url`, `group_name`.
- A feed object is `null` when all of its columns are `NULL` (that feed had no row for the club).
- `form` and `streak_history` (JSONB) are the `form` and `streakHistory` lists, already in API shape and order; `[]` when empty. Dates are strings like `2025-09-01T00:00:00.000Z`.
- `NUMERIC` columns (`basic_win_percentage`, `ahead_behind_wins_percentage`) arrive as strings from node-postgres.
- The seven former `app_standings_*` feed tables were retired from Neon in feature 23.

### Records tables

`app_records_player_seasons`, `app_records_single_games` and `app_records_team_seasons` are all-time top-50 leaderboards per metric, built by `gold_etl/records.py` from every loaded Silver season of the competition. Unlike other tables they are **not season-scoped**: `season_code` is a plain column saying when the record happened. Player and club names are on each row, so no join is needed to show one.

| Table | Key | One row | Metrics |
| --- | --- | --- | --- |
| `app_records_player_seasons` | `competition_code`, `metric`, `rank_ordinal` | one player's season total from `season_player_stats_traditional` (`phase_code = 'all'`, `mode = 'accumulated'`) | `points_scored`, `total_rebounds`, `assists`, `pir` |
| `app_records_single_games` | same | one player's line in one played game, from `game_player_stats` | `points`, `valuation`, `total_rebounds`, `assistances` |
| `app_records_team_seasons` | same | one club's season total (`stats_kind = 'total'`), summed from `game_team_stats` | `points`, `valuation`, `total_rebounds`, `assistances` |

- `rank_ordinal` is 1-50 per metric (fewer when fewer rows qualify), with no gaps or duplicates.
- Ties: player and team seasons by value descending, then `season_code`, then `person_key` or `club_code` ascending. Single games by value descending, then `season_code`, `game_code` and `person_key` ascending.
- The historical metric labels are kept: Silver's `points`, `pir` and `assists` supply the `points_scored`, `valuation` and `assistances` labels where used.
- The two game-level tables use only `played = TRUE` games, which excludes forfeits.
- The build rebuilds each selected table once per run from every loaded season, regardless of `-sc`, and Neon replaces the whole competition. `--quality-only` compares full rows with a fresh derivation.
- The design mirrors the web app's original `/records` routes (same metrics, filters and tie-breaks). The web app currently computes its own records from other tables and does not read these three (checked in `jmp-euroleague-2` on 2026-11-08).

### `app_team_season_stats`

Built from played `silver.games` and `silver.game_team_stats` `total` rows. It serves the web app's team stats by phase.

| Rest of the key | One row |
| --- | --- |
| `phase_code`, `club_code` | one club's totals in one phase of one season, from counted games |

- Columns: `club_name`, `games_played`, then `own_<measure>` and `opp_<measure>` (`NUMERIC`) for 20 measures with their historical names: `points`, `field_goals_made2/attempted2`, `field_goals_made3/attempted3`, `free_throws_made/attempted`, `field_goals_made_total/attempted_total`, `total_rebounds`, `defensive_rebounds`, `offensive_rebounds`, `assistances`, `steals`, `turnovers`, `blocks_favour`, `blocks_against`, `fouls_commited`, `fouls_received`, `valuation`.
- "Own" sums the club's own team row per game; "opponent" sums the other side's row in the same game. A missing measure or opponent total makes that aggregate `NULL`.
- Forfeits are not counted, so `games_played` can be one lower than the API's (5 instead of 6 for those clubs' `TS` rows in E2001 and E2003). The result still counts in `app_standings`.
- There is one row per phase actually present in the season's games (`RS`, `PI`, `PO`, `FF`, or older `TS`), and no synthetic all-phases row.

### `app_postseason_series`

Built from `silver.games`, one competition and season at a time. It reports only facts already in `app_games`: no bracket labels or seeds that the source does not carry.

| Rest of the key | One row |
| --- | --- |
| `phase_code`, `club_a_code`, `club_b_code` | every game two clubs played against each other in one postseason phase. `club_a_code < club_b_code` alphabetically, so a pairing never produces two rows. |

- EuroLeague phases are `PI`, `PO` and `FF` (not the `TS` group stage). EuroCup rules are in [gold_etl/README.md](../gold_etl/README.md#postseason-series-rules).
- `games_played` counts games between the pair, played or not. `club_a_wins` and `club_b_wins` count only played games. `winner_club_code` is the club with strictly more wins (or more aggregate points in a two-leg tie); `NULL` while tied, including a series in progress.
- `games` (JSONB, not null) lists every game between the pair ordered by `round_number`: `{gameCode, roundNumber, scheduledAt, localClubCode, roadClubCode, localScore, roadScore, winnerClubCode}`. The last three are `null` for an unplayed game.
- One definition covers every era without hard-coding a format. Today's `PO` is a best-of-5 (checked on E2025: two home games, two away, a fifth only at 2-2); older seasons show other game counts. `FF` and `PI` pairings do not repeat within a season, so each is a one-game row (E2025: three distinct `PI` pairings and a three-game `FF` with no third-place game).
- There is no "series decided" field, because that cannot be derived without a best-of-N target per era. `winner_club_code` and the game list show the state.

### `app_players`

Built from player registrations and people in every loaded Silver season, regardless of `-sc`, replacing the whole competition in one transaction.

| Key | One row |
| --- | --- |
| `competition_code`, `person_code` | one player with at least one `role_code = 'J'` registration (coaches, staff and referees are excluded) |

- `name`, `country_code`, `country_name`, `height_cm`, `weight_kg`, `birth_at`, `birth_country_code`, `birth_country_name`, `position`, `position_name` come from the player's latest season, since they can change slightly over time.
- `first_season_code`, `last_season_code` and `seasons_played` (integer, not null) give the career span over every player registration.
- `clubs` (JSONB, not null) lists `{seasonCode, clubCode, clubName}` per distinct season and club, ordered by season. Full per-season detail stays in `app_registrations`.
- Season history (`app_registrations`) and shared games (`app_game_player_stats`) are already joinable by `person_code`, which equals `person_key` for every player in local history. Career totals are not precomputed; sum `app_season_player_stats_traditional` by `person_code`.

### `app_club_identities`

Built from every loaded `silver.clubs` season, regardless of `-sc`, replacing the whole competition in one transaction.

- One row per `(competition_code, club_code)`; a name change does not create another identity.
- `name`, `crest_url`, `country_code` and `country_name` come from the club's latest loaded season. Missing values stay `NULL`.
- `first_season_code`, `last_season_code` and `seasons_played` (integer, not null) describe the club's loaded seasons.
- There is no season-by-season profile history; use `app_clubs` for that.

## Gold advanced statistics

All tables in this section are built with `python gold_etl/main.py -sc <seasons> -tb <name>` and published to Neon for every loaded season.

### Team round derivations (in memory)

Three derivations feed [`app_standings_stats`](#app_standings_stats). They are computed in memory and no longer stored or published. All three share the key `competition_code`, `season_code`, `scope`, `round_number`, `club_code`, the same rows, and the same inputs: counted games from `silver.games`, `silver.game_team_stats` (`total` rows) and `silver.game_team_advanced`. Eliminated clubs keep their final values.

#### `team_round_stats` (`gold_etl/team_rounds.py`)

| Columns | Meaning |
| --- | --- |
| `games_played`, `wins`, `losses`, `points_for`, `points_against` | Cumulative record and points |
| `own_*`, `opp_*` (`field_goals_made`, `field_goals_attempted`, `three_pointers_made`, `free_throws_made`, `free_throws_attempted`, `offensive_rebounds`, `defensive_rebounds`, `turnovers`, `assists`) | Cumulative club and opponent totals (in memory only) |
| `game_minutes`, `possessions` | Sums of the per-game `game_team_advanced` values (`game_minutes` in memory only) |
| `mov` | `(points_for − points_against) / games_played` |
| `pythagorean_win_pct`, `pythagorean_wins` | `PF^e / (PF^e + PA^e)`, and that times games, with `e` = 10.25 (`pythagorean_exponent`, in memory only) |
| `pace`, `offensive_rating`, `defensive_rating`, `net_rating` | The per-game formulas applied to cumulative totals |
| `efg_pct`, `tov_pct`, `orb_pct`, `drb_pct`, `ft_rate`, `true_shooting_pct`, `assist_ratio`, `opp_efg_pct`, `opp_tov_pct`, `opp_ft_rate` | The per-game formulas applied to cumulative totals (fractions, not averages of game values) |

**API cross-check** (warnings only, in `--quality-only -tb app_standings_stats`): each scope's final round is compared with the API's accumulated team feeds. `games_played` and the counting totals must match exactly; `efg_pct`, `true_shooting_pct`, `orb_pct` and `drb_pct` must agree within 0.06 percentage points (the API rounds to one decimal). The API's `all` scope is every phase, as here; `PS` has no API feed. The API's `turnovers_ratio`, `assists_ratio` and `free_throws_rate` use other definitions and are not compared. Across E2000-E2026 the only differences are the two forfeits (`games_played` one lower for the forfeit's club in the `all` and `TS` scopes).

#### `team_round_ratings` (`gold_etl/team_ratings.py`)

| Column | Meaning |
| --- | --- |
| `league_offensive_rating`, `league_pace` | `100 × points / possessions` and `40 × possessions / minutes` over every counted game in the scope, each game counted once per side |
| `relative_offensive_rating`, `relative_defensive_rating`, `relative_pace` | The club's value minus the league value (relative net rating equals `net_rating`, so it is not stored) |
| `connected` | True when every club in the scope and round can reach every other through played games |
| `srs` | Simple Rating System: solves `r_i = MOV_i + mean of opponents' r` with mean 0, from per-game margins (no home-court term or margin cap) |
| `sos`, `sov` | Mean opponent `srs` over all games (`srs − mov`) and over games won (`NULL` without wins) |
| `adj_net_rating`, `adj_offensive_rating`, `adj_defensive_rating` | Possession-weighted, opponent-adjusted ratings per 100 possessions. The weighted league mean of the offensive and defensive ratings is the league rating; of the net rating, 0. |

- `srs`, `sos`, `sov` and the adjusted ratings are `NULL` when `connected` is false: for example the playoff-only scopes `PI`, `PO` and often `FF`/`PS` (whose series form separate pairs), and `RS` rounds 1-2 before schedules link up.
- The adjusted offensive and defensive ratings are also `NULL` when the game graph is bipartite (`RS` rounds 1-2), because offense and defense cannot be separated; the adjusted net rating is still defined.
- `--quality-only` reports an error if a connected scope-round's `srs` sum or weighted `adj_net_rating` mean is not zero.

#### `team_round_splits` (`gold_etl/team_splits.py`)

| Group | Games included |
| --- | --- |
| `home_*` | The club was the `local` side |
| `away_*` | The club was the `road` side |
| `last5_*`, `last10_*` | The club's most recent 5 and 10 counted games in the scope, by `round_number` then `game_code` (fewer early in a scope) |

- Per group `g`: `g_games`, `g_wins`, `g_mov`, `g_offensive_rating`, `g_defensive_rating`, `g_net_rating` (per 100 possessions) and `g_pace` (per 40 minutes), using `game_team_advanced` possessions and minutes.
- A group with no games has zero counts and `NULL` rates; a missing input makes that group's rates `NULL`.
- Neutral-site games (such as the Final Four) keep the source's local/road designation.
- `--quality-only` errors if home plus away games or wins differ from `games_played` and `wins`, if a window's game count is not `min(N, games_played)`, or if a window's MOV differs from the cumulative MOV while the club has no more games than the window.

### `app_standings_stats`

One wide, page-shaped row per club, scope and round: a projection of the three in-memory derivations above (same rows, values not recomputed). Key: `competition_code`, `season_code`, `scope`, `round_number`, `club_code`. For a group phase, `scope = phase_code` joins it to `app_standings`; `scope` also takes `all` and `PS`.

| Columns | From |
| --- | --- |
| `club_name`, `games_played`, `wins`, `losses`, `points_for`, `points_against`, `possessions`, `mov`, `pythagorean_win_pct`, `pythagorean_wins`, `pace`, `offensive_rating`, `defensive_rating`, `net_rating`, `efg_pct`, `tov_pct`, `orb_pct`, `drb_pct`, `ft_rate`, `opp_efg_pct`, `opp_tov_pct`, `opp_ft_rate`, `true_shooting_pct`, `assist_ratio` | `team_round_stats` |
| `connected`, `league_offensive_rating`, `league_pace`, `relative_*`, `srs`, `sos`, `sov`, `adj_*` | `team_round_ratings` |
| `home_*`, `away_*`, `last5_*`, `last10_*` (`games`, `wins`, `mov`, `offensive_rating`, `defensive_rating`, `net_rating`, `pace`) | `team_round_splits` |

`--quality-only` checks the fresh derivation, the ratings and split invariants and the API cross-check above.

**Comparison with `app_standings`** (E2000-E2026; all 12,345 group-phase rows have a match): `games_played` differs in 191 rows (1.5%), `wins` in 135 and `points_for` in 2,858 (23%, typically 5-15 points). The largest gap is E2021's regular season (for example round 12, where `app_standings` lists 21-23 games per club and this table 12): the standings feed numbers rounds differently from the games there. The cause was not investigated. The other `games_played` and `wins` differences are in a few rounds of E2001 and E2003 (Top 16), E2012, E2020 and E2022. No gate is applied.

### `player_round_stats`

| | |
| --- | --- |
| **Sources** | `silver.game_player_stats`, `game_player_advanced` and the counted team games |
| **Key** | `competition_code`, `season_code`, `scope`, `round_number`, `person_key` |
| **Rows** | every scope round from the player's first appearance; idle rounds repeat the previous values |

An **appearance** is a counted game with `seconds_played > 0`; DNP rows do not count. `games_played` and `games_started` count appearances. `club_code` and `player_name` come from the latest appearance, so a player who changes club keeps one row with blended rates.

| Columns | Meaning |
| --- | --- |
| `seconds_played`, `points`, `field_goals_*`, `three_pointers_*`, `free_throws_*`, `offensive_rebounds`, `defensive_rebounds`, `total_rebounds`, `assists`, `steals`, `turnovers`, `blocks`, `fouls_committed`, `pir` | Cumulative totals |
| `ts_pct`, `efg_pct` | `PTS / (2 (FGA + 0.44 FTA))`, `(FGM + 0.5 3PM) / FGA` |
| `usg_pct`, `ast_pct`, `orb_pct`, `drb_pct`, `trb_pct`, `stl_pct`, `blk_pct`, `tov_pct` | Standard forms as ratios of sums over the player's games, each game with its own team and opponent; `s/T` is the player's share of the game on court (`seconds / (game_minutes × 60)`) |
| `possessions_played`, `*_per_100` | Estimated player possessions (sum of `s/T × game possessions`), and points, rebounds, assists, steals, blocks and turnovers per 100 of them |
| `game_score_total`, `game_score_average` | Sum and mean of `game_player_advanced.game_score` |
| `pie` | Player numerator over the numerator of both teams in the same games, with numerator `PTS + FGM + FTM − FGA − FTA + DREB + OREB/2 + AST + STL + BLK/2 − PF − TOV` |

**API cross-check** (warnings only, in `--quality-only`) against the accumulated traditional and advanced feeds for each scope's final round (`PS` has no feed):

- Games, counting totals and `pir` must match exactly, and minutes within 0.01. They do for all 23,274 comparable rows in E2000-E2026.
- For players with at least 100 minutes, `efg_pct` and `ts_pct` must agree within 0.06 percentage points and the rebound rates within 2 points (the API's team-minute conventions differ slightly).
- The API's `turnovers_ratio`, `assists_ratio` and `possessions` use other definitions and are not compared.
- The only differences across E2000-E2026 are two `efg_pct` warnings (E2007, a 0.7-point gap for 2 players).

### `player_round_ratings`

Hollinger PER per scope round. Same key and rows as `player_round_stats`; sources `silver.game_player_stats` and the counted games.

| Column | Meaning |
| --- | --- |
| `club_code`, `player_name`, `games_played`, `seconds_played` | Latest club and name, appearances and cumulative seconds |
| `uper` | Hollinger's unadjusted PER per minute from cumulative totals, with league constants (factor, VOP, DRB%) summed over every counted game of the scope through the round, and the player's team assist ratio |
| `aper` | `uper × league pace / the player's team pace` (over the games the player appeared in) |
| `per` | `aper × 15 / the seconds-weighted mean aper of the scope's players through the round`, so the league mean is 15 |

- Team context comes from the games the player played (each with that game's club), not the club's full-season totals as on Basketball-Reference, so values differ slightly for players who missed games.
- There is no minutes cutoff: values for players with few minutes are noisy and can be negative.
- The API has no PER, so `--quality-only` checks only the fresh derivation and the league-mean invariant.

### `player_round_win_shares`

Same key and rows as `player_round_stats`; sources `silver.game_player_stats` and the counted games.

| Column | Meaning |
| --- | --- |
| `club_code`, `player_name`, `games_played`, `seconds_played` | Latest club and name, appearances and cumulative seconds |
| `off_win_shares` | `(points produced − 0.92 × league points per possession × individual possessions) / marginal points per win` (Basketball-Reference's method) |
| `def_win_shares` | `minutes share × team possessions × (1.08 × league points per possession − individual defensive rating / 100) / marginal points per win`; the defensive rating uses stops and the stop percentage |
| `win_shares`, `win_shares_per_40` | `off_win_shares + def_win_shares`, and `win_shares × 40 / minutes played`. The rate uses 40 minutes, the length of a EuroLeague game (Basketball-Reference uses 48 for the NBA); the league mean is about 0.100. |

- **Marginal points per win** = `0.32 × league points per team game × (the player's team pace over their games / league pace)`.
- Player, club and opponent totals are summed over the games the player played (each with its own club); league values over every counted game of the scope through the round. Values therefore differ slightly from Basketball-Reference for players who missed games.
- A bracketed ratio whose count is zero (free-throw percentage with no attempts, no field-goal attempts, no team free throws) counts as 0. Any other zero denominator or a missing input gives `NULL`.
- Early rounds are noisy, and values can be negative. The API has no Win Shares.
- `--quality-only` checks the fresh derivation and prints `WARN` when a scope round with at least 30 games has total Win Shares more than 15% away from its game count (each game has one win). Across E2000-E2026 the totals are 0.90-1.07 of the games, mostly 1.03, so no warning is printed.

### `team_pbp_stats`

| | |
| --- | --- |
| **Sources** | `silver.games` (phase) and `game_team_possessions`, `game_team_score_flow`, `game_team_shot_splits` |
| **Seasons** | E2007 onward; earlier seasons build zero rows. A missing Silver table stops the build with the command that creates it. |
| **Key** | `competition_code`, `season_code`, `scope`, `club_code` (whole scope, not round snapshots) |

| From | Columns |
| --- | --- |
| all | `games` (games with a possessions row) |
| `game_team_possessions` | `counted_possessions`, `estimated_possessions`, `possession_seconds` (sums); `avg_possession_seconds` (per-game averages weighted by counted possessions) |
| `game_team_score_flow` | `lead_changes_per_game`, `ties_per_game` (means); `timed_games` and `time_leading_seconds`, `time_trailing_seconds`, `time_tied_seconds` (sums over games with time data); `largest_lead`, `longest_run` (maxima); `runs_6_plus`; `clutch_games` (timed games with clutch time), `clutch_seconds` (timed games); `clutch_points_for`, `clutch_points_against` (all games) |
| `game_team_shot_splits` | `flagged_games` (games with point splits); `fast_break_points`, `second_chance_points`, `points_off_turnover_points` (sums over flagged games); `field_goals_made`, `assisted_field_goals`, `assisted_fg_pct` (sum over sum) |

`NULL` means no usable game for that column; a club can have a row with some columns `NULL` when a source table has no rows for it. `--quality-only` checks the fresh derivation and that the `all` scope equals the sum of the phase scopes for every additive column. E2025 had 66 club-scope rows.

### `player_on_off`

| | |
| --- | --- |
| **Sources** | `game_team_lineup_stints` (phase from `silver.games`) and `game_player_stats` (names) |
| **Seasons** | E2007 onward. A missing stint table stops the build with the command that creates it. |
| **Key** | `competition_code`, `season_code`, `scope`, `club_code`, `person_key`; a player traded during a season has one row per club |

| Columns | Meaning |
| --- | --- |
| `player_name`, `games` | Name; games with the player on court in a stored stint |
| `on_seconds`, `on_possessions_for`, `on_possessions_against`, `on_points_for`, `on_points_against` | Sums over the club's stints with the player on court |
| `off_*` (the same five) | Sums over the club's other stored stints in the scope, including games the player missed |
| `on_ortg`, `on_drtg`, `on_net_rating`, `off_ortg`, `off_drtg`, `off_net_rating` | Points per 100 possessions; `NULL` without possessions |
| `ortg_diff`, `drtg_diff`, `net_rating_diff` | On minus off. A positive `drtg_diff` means a worse defense. |

A player who never sat has `NULL` off ratings and differences. `--quality-only` checks the fresh derivation and, per club and scope, that every player's on plus off equals the same team total and that the players' on-court seconds are five times the team's.

**Recorded sizes:** 990 rows in E2025 (all scopes); 18,670 over E2007-E2026, 6,225 in the `all` scope. A player's summed on-court point difference equals the summed box-score `plus_minus` exactly in 73% of player-club-seasons of E2012-E2026 (3,297 of 4,507), within 3 points in 83%, and differs by 1.9 points on average.

### `lineup_ratings`

| | |
| --- | --- |
| **Sources** | `game_team_lineup_stints` (phase from `silver.games`) and `game_player_stats` (names) |
| **Seasons** | E2007 onward. A missing stint table stops the build with the command that creates it. |
| **Key** | `competition_code`, `season_code`, `scope`, `club_code`, `lineup_size` (2, 3 or 5), `lineup` (sorted `person_key`s joined by commas) |

Every stored stint holds ten pairs, ten triples and one five-man group of the club's players, and each group sums the stints it was on court for.

| Columns | Meaning |
| --- | --- |
| `lineup_names` | Player names in lineup order joined by `; ` (the key where a name is missing) |
| `games` | Games in which the group shared the floor |
| `seconds`, `possessions_for`, `possessions_against`, `points_for`, `points_against` | Sums over those stints |
| `ortg`, `drtg`, `net_rating` | Points per 100 possessions; `NULL` without possessions |

Small samples are kept with their possessions; consumers filter. Four-man groups are not built. `--quality-only` checks the fresh derivation and, per club and scope, that the 2-man and 3-man rows each sum to ten times the 5-man rows for every summed column.

**Recorded sizes:** over E2007-E2026, 107,595 pair rows, 310,996 triple rows and 195,109 five-man rows (38,890, 121,767 and 87,544 in the `all` scope); E2025 has 6,296, 20,388 and 15,783. Hand check: E2025's most-used five-man lineup (club HTA) has 28 games, 16,079 seconds, 483 possessions for and 596 points, equal to the sums of its stint rows.

### `player_rapm`

| | |
| --- | --- |
| **Sources** | `game_team_lineup_stints` (both teams' lineups per stint), `game_player_stats` (names) and the played games of `silver.games` |
| **Seasons** | E2007 onward |
| **Requires** | NumPy, imported only by this table; without it the build stops with a message |
| **Key** | `competition_code`, `season_code`, `scope` (always `all`), `person_key`; a traded player has one row |

**Method:**

1. Each stint row with possessions is one observation: the team's points per 100 possessions, weighted by its counted possessions.
2. The prediction is an intercept, plus the `offense` coefficients of the five players on offense, minus the `defense` coefficients of the five on defense. A positive `defense` therefore means fewer points allowed.
3. Coefficients are ridge-penalized (the intercept is not). The penalty is chosen per season by 5-fold cross-validation over 250, 500, 1000, 2000, 4000, 8000, 16000, 32000 and 64000, with folds made of whole games. The chosen penalty is the strongest one whose error is within 0.01% of the no-player error of the best.
4. Small samples are not filtered: the penalty shrinks them toward zero, and their possessions are stored.

| Columns | Meaning |
| --- | --- |
| `player_name`, `seconds` | Name; on-court seconds in stored stints |
| `possessions_offense`, `possessions_defense` | Counted possessions on court on each side |
| `penalty` | The chosen penalty, the same on every row of a season |
| `offense`, `defense`, `rapm` | Points per 100 possessions relative to an average player, rounded to four decimals; `rapm = offense + defense` |

**Recorded results** over E2007-E2026 (6,164 rows; the full build takes about 25 seconds):

- Stint outcomes are noisy, so the best penalty improves the held-out error over a model without players by only a few tenths of a percent (0.40% in E2015, 0.10% in E2025).
- The chosen penalty is 1,000-8,000 for the 19 seasons before E2026, and 64,000 for E2026 (10 games, where cross-validation showed no improvement over the no-player model).
- RAPM correlates 0.87 with the on-court point margin per 100 possessions across the 3,052 player-seasons with more than 500 on-court possessions.
- `--quality-only` compares with a fresh derivation; a rerun reproduces the rows exactly.

## Neon contract

The publisher and its guards are described in [neon_publish/README.md](../neon_publish/README.md). Facts recorded here:

- All 40 Gold tables use the same `app_*` names as Neon `public`, with the same primary keys.
- Gold and Neon also share four secondary indexes: standings (`club_code`), play-by-play (`game_code, play_number` and `person_code`) and shots (`person_code`).
- Local Gold holds E2000-E2026. Neon holds every loaded EuroLeague season: E2000-E2026 for the catalog, box-score, standings and round tables, and E2007-E2026 for the play-by-play, shot and lineup tables (checked read-only on 2026-10-25).
- The complete API responses live only in the Bronze files. `etl_source_payloads`, a former PostgreSQL copy of them, was dropped in feature 23.

**Size history** (read-only `pg_database_size` and `pg_total_relation_size`):

| Date | Measurement |
| --- | --- |
| 2026-10-03 | After the E2025 and E2026 publishes: the nine per-game tables of 30h-30j take 24.8 MB (25 MB planned); the whole database is 197.9 MB of the 512 MB free tier. |
| 2026-10-25 | With every season published: the whole database is 1,851 MB. |

Use [database_size.sql](../neon_publish/database_size.sql) for a current measurement.

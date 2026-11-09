# Gold data catalog

Start here when choosing data for the web app. This catalog describes all **40 Gold tables**: what each one is for, what one row represents, and how to join and aggregate them safely. For every column of a table, follow its link to the [Gold table reference](GOLD_TABLE_REFERENCE.md); for the meaning of a statistic, see the [statistics glossary](STAT_GLOSSARY.md).

Names, columns and keys were checked against the code on 2026-10-20. This describes the code contract; it is not an audit of the live database or the frontend.

## Contents

- [Naming and competitions](#naming-and-competitions)
- [Find the frontend source](#find-the-frontend-source)
- [Keys and joins](#keys-and-joins)
- [Safe aggregation](#safe-aggregation)
- [Coverage and missing values](#coverage-and-missing-values)
- [Table catalog](#table-catalog)
- [Query examples](#query-examples)
- [Statistics that have no stored field](#statistics-that-have-no-stored-field)

## Naming and competitions

- Every table is `gold.app_*` locally and `public.app_*` on Neon, with the same columns and primary key. The examples use `gold`; use `public` for the published database.
- Build commands also accept logical names such as `player_round_stats`. These are not SQL table names.
- Tables use natural identifiers, not surrogate keys. Do not invent a `player_id`, and do not strip leading zeroes from person codes.
- **EuroLeague** (`competition_code = 'E'`) is built and published to Neon. **EuroCup** (`'U'`) fills the same tables locally only; its coverage and formats are in the [Silver catalog](SILVER_CATALOG.md#eurocup).
- A table being publishable does not mean a given season or recalculation is already live. Local builds and Neon publishing are separate steps.

## Find the frontend source

| Frontend need | Read from | Selection and cautions |
| --- | --- | --- |
| Season list, schedule, results | `app_seasons`, `app_games` | Filter competition and season; respect `status`, `played` and neutral venues. |
| Team profiles, logos, rosters | `app_clubs`, `app_registrations`, `app_people` | Season-specific. One registration row per person, club and role, so a transfer gives two rows. |
| Career profile and club history | `app_players`, `app_club_identities` | Competition-wide. Bridge player `person_key` to `person_code` through `app_people`. |
| Official standings, form, streaks | `app_standings` | Use `basic_position`; filter phase and round. |
| Team advanced standings | `app_standings_stats` | One wide team row; select a scope and one round. |
| Player points, rebounds, assists and season leaders | `app_season_player_stats_traditional` | Select phase and `mode`; use `qualified` where leaderboard rules call for it. |
| Calculated player rates, per-100, Game Score, PIE | `app_player_round_stats` | Select a scope and its latest round; never sum cumulative snapshots. |
| Player PER | `app_player_round_ratings` | `per`, `aper`, `uper`. Season PER is not the mean of game PER. |
| Player Win Shares | `app_player_round_win_shares` | `off_win_shares`, `def_win_shares`, `win_shares`, `win_shares_per_40`. |
| Player RAPM | `app_player_rapm` | `scope = 'all'`; `offense`, `defense`, `rapm`. No round column. |
| Player on/off and lineup combinations | `app_player_on_off`, `app_lineup_ratings` | Per club and scope; complete stints only. Show the sample possessions. |
| Game player box score plus advanced stats | `app_game_player_stats`, `app_game_player_advanced` | Join the full player-game key; advanced rows can be absent. |
| Game team box score plus advanced stats | `app_game_team_stats`, `app_game_team_advanced` | Filter `stats_kind = 'total'`; join the full side-game key. |
| Quarter scores, score chart, shot chart | `app_game_period_scores`, `app_play_by_play`, `app_shots` | Events use resolved person codes and event order. |
| Counted possessions, leads, clutch, scoring splits | `app_game_team_possessions`, `app_game_team_score_flow`, `app_game_team_shot_splits` | Per-game event measures; E2007 onward, subject to feed coverage. |
| Team season event summaries | `app_team_pbp_stats` | Whole scope, not round snapshots; check the coverage and sample columns. |
| Player substitution chart, lineup timeline | `app_game_player_on_court`, `app_game_team_lineup_stints` | Elapsed seconds from tip-off; stints store only complete lineups. |
| Historical leaders, postseason series | `app_records_*`, `app_postseason_series` | Records are competition-wide. A series leader does not prove the series is finished. |
| Missing-data explanations | `app_game_stat_gaps` | `NULL` means unavailable, never zero. |

## Keys and joins

Always filter **both** competition and season on season tables.

| Relationship | Join columns and rule |
| --- | --- |
| Game child → game | `competition_code`, `season_code`, `game_code` |
| Team-game advanced → team box score | Game key plus `side`, with box score `stats_kind = 'total'` |
| Player-game advanced → player box score | Game key plus `side`, `person_key` |
| Season person profile → box score | `competition_code`, `season_code`, `person_key` |
| Live event or shot → person profile | Resolved, non-`NULL` live `person_code` = `app_people.person_key` in the same competition and season. The raw `player_code` is not the join key. |
| Season person → career identity | `app_people.person_code = app_players.person_code`, plus competition |
| Club profile | Competition, season and `club_code`; `app_club_identities` uses competition and club only |
| Player round stats, PER, Win Shares | Competition, season, `scope`, `round_number`, `person_key`. `club_code` is the latest club, not part of the key. |
| Team advanced standings | Competition, season, `scope`, `round_number`, `club_code` |
| Official standings → team advanced standings | Competition, season, round and club, with `phase_code = scope`. Historical snapshots may not align exactly. |
| On/off → player | Competition, season, scope, club and player; a transferred player has one row per club |

**Season player feeds** have `entry_ordinal` in the key. It is a position in the API feed, not an identity. Do not assume one row per person and club. Transferred players can have a semicolon-separated club code such as `BAS;TEL`, which does not join to one `app_clubs` row; use registrations or player game rows for club-specific attribution.

## Safe aggregation

- **Scopes overlap.** `all`, the individual phases and `PS` are alternative views, not additive parts. `PS` means `PI` + `PO` + `FF`, not every historical non-`RS` phase. `TS` is its own historical phase.
- **Round tables are cumulative snapshots.** Pick one round per scope. Do not sum snapshots or average their percentages. An idle club or player keeps its previous totals.
- **Transfers.** Player round rows blend all clubs under the latest club label. For club-specific player analysis, use game rows or the club-keyed on/off table.
- **Round numbers** follow the stored games, not a renumbered list of played dates.
- **Percentages use two units.** Calculated rates are fractions (`0.55` displays as 55%). API player percentage columns are percentage points (`55.0` displays as 55%). Check the [glossary](STAT_GLOSSARY.md) before applying one formatter to everything.
- **`NUMERIC` values** can arrive as decimal strings, depending on the PostgreSQL client. Convert them explicitly at the app boundary.

## Coverage and missing values

- Box-score statistics exist from E2000 wherever the box scores exist.
- Play-by-play, shot, on-court, lineup, on/off and RAPM tables begin at E2007 and still depend on each game's source data.
- Scheduled games and forfeits without complete box scores produce no calculated game or round rows.
- A missing row, a `NULL` and a measured zero mean different things. Use a left join when attaching optional advanced or event detail to a schedule or box score.
- `app_game_stat_gaps` explains official box-score gaps. It does not list every missing derived rate; check the coverage and sample columns too.

No Neon query was made for this document, so do not infer the currently published coverage from it.

## Table catalog

Each link opens the table's full column reference. Grains are always within one competition and, unless stated as competition-wide, one season.

### Profiles, roster and schedule

| Table | Purpose | One row represents |
| --- | --- | --- |
| [`app_seasons`](GOLD_TABLE_REFERENCE.md#app_seasons) | Season selector and metadata | one competition-season |
| [`app_clubs`](GOLD_TABLE_REFERENCE.md#app_clubs) | Season-specific team names, crests and profiles | one club per season |
| [`app_people`](GOLD_TABLE_REFERENCE.md#app_people) | Season-specific person profiles; bridge between `person_key` and `person_code` | one person per season |
| [`app_registrations`](GOLD_TABLE_REFERENCE.md#app_registrations) | Rosters, jersey numbers, positions and registration dates | one person, club and role per season |
| [`app_rounds`](GOLD_TABLE_REFERENCE.md#app_rounds) | Round names, phase labels and date ranges | one round per season |
| [`app_games`](GOLD_TABLE_REFERENCE.md#app_games) | Schedule, results, status and venue | one fixture per season |
| [`app_game_officials`](GOLD_TABLE_REFERENCE.md#app_game_officials) | Referee assignments | one official slot per game |
| [`app_players`](GOLD_TABLE_REFERENCE.md#app_players) | Player identity across seasons, with career span and club history | one player per competition |
| [`app_club_identities`](GOLD_TABLE_REFERENCE.md#app_club_identities) | Club identity across seasons | one club per competition |

### Official box scores and season player feeds

| Table | Purpose | One row represents |
| --- | --- | --- |
| [`app_game_period_scores`](GOLD_TABLE_REFERENCE.md#app_game_period_scores) | Quarter and overtime scores | one side and period per game |
| [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats) | Official player box scores, including DNP lines | one player and side per game |
| [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) | Official team box scores and team-only contributions | one `stats_kind` per side and game |
| [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional) | Player season totals and per-game leaderboards | one feed entry per phase and mode |
| [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced) | API shooting efficiency, rebound rates and other ratios | one feed entry per phase and mode |
| [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring) | API shot mix and scoring distribution | one feed entry per phase and mode |
| [`app_season_player_stats_misc`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_misc) | Starts, wins and losses, double and triple doubles | one feed entry per phase and mode |

### Standings, records and postseason

| Table | Purpose | One row represents |
| --- | --- | --- |
| [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) | Official standings, form, streaks and splits | one club, phase and round snapshot |
| [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) | Team and opponent season box-score totals | one club and phase per season (phases present in games) |
| [`app_records_player_seasons`](GOLD_TABLE_REFERENCE.md#app_records_player_seasons) | All-time top player seasons | one rank slot per metric (competition-wide) |
| [`app_records_single_games`](GOLD_TABLE_REFERENCE.md#app_records_single_games) | All-time top individual games | one rank slot per metric (competition-wide) |
| [`app_records_team_seasons`](GOLD_TABLE_REFERENCE.md#app_records_team_seasons) | All-time top team seasons | one rank slot per metric (competition-wide) |
| [`app_postseason_series`](GOLD_TABLE_REFERENCE.md#app_postseason_series) | Play-in, playoff and Final Four pairings with their games | one sorted club pair per postseason phase |

### Calculated team statistics

| Table | Purpose | One row represents |
| --- | --- | --- |
| [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) | Team advanced stats: cumulative totals and ratings, league-relative and opponent-adjusted strength, home/away and last-5/last-10 form | one club, scope and round snapshot |
| [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) | Possessions, score flow, clutch and shot-split summaries | one club and scope per season |

### Calculated player and lineup statistics

| Table | Purpose | One row represents |
| --- | --- | --- |
| [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) | Cumulative player totals, rates, per-100, Game Score and PIE | one player, scope and round snapshot |
| [`app_player_round_ratings`](GOLD_TABLE_REFERENCE.md#app_player_round_ratings) | Cumulative Hollinger PER | one player, scope and round snapshot |
| [`app_player_round_win_shares`](GOLD_TABLE_REFERENCE.md#app_player_round_win_shares) | Offensive, defensive and total Win Shares | one player, scope and round snapshot |
| [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) | Team performance with a player on and off court | one player, club and scope per season |
| [`app_lineup_ratings`](GOLD_TABLE_REFERENCE.md#app_lineup_ratings) | Ratings for 2-, 3- and 5-man units | one lineup, size, club and scope per season |
| [`app_player_rapm`](GOLD_TABLE_REFERENCE.md#app_player_rapm) | Regularized adjusted plus-minus from lineup stints | one player per season (`scope = 'all'`) |

### Events and calculated game detail

| Table | Purpose | One row represents |
| --- | --- | --- |
| [`app_play_by_play`](GOLD_TABLE_REFERENCE.md#app_play_by_play) | Event timeline for game charts and event analysis | one event per game period |
| [`app_shots`](GOLD_TABLE_REFERENCE.md#app_shots) | Shot events with coordinates and flags | one shot per game |
| [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) | Player efficiency, on-court rates, Game Score and game PER | one player and side per game with a box score |
| [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) | Estimated possessions, pace, ratings and four factors | one side per game with a box score |
| [`app_game_team_possessions`](GOLD_TABLE_REFERENCE.md#app_game_team_possessions) | Counted possessions and their duration, next to the box-score estimate | one side per game with usable events |
| [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow) | Lead changes, runs, time ahead and behind, clutch scoring | one side per game with a running score |
| [`app_game_team_shot_splits`](GOLD_TABLE_REFERENCE.md#app_game_team_shot_splits) | Fast-break, second-chance, off-turnover and assisted scoring | one side per game with usable events |
| [`app_game_player_on_court`](GOLD_TABLE_REFERENCE.md#app_game_player_on_court) | Continuous on-court intervals | one interval per player, side and game |
| [`app_game_team_lineup_stints`](GOLD_TABLE_REFERENCE.md#app_game_team_lineup_stints) | Five-on-five stints with points and counted possessions | one stint per side and game |
| [`app_game_stat_gaps`](GOLD_TABLE_REFERENCE.md#app_game_stat_gaps) | Why an official box-score measure is unavailable | one `stat_name` per game |

## Query examples

These read-only examples use local Gold; use `public` on Neon. E2025 is only an example season.

### Player advanced leaderboard with PER and Win Shares

Choose one scope's latest round, and join on the full snapshot key. Joining on the player alone duplicates rows across rounds and scopes.

```sql
WITH latest AS (
    SELECT max(round_number) AS round_number
    FROM gold.app_player_round_stats
    WHERE competition_code = 'E' AND season_code = 'E2025' AND scope = 'all'
)
SELECT p.person_key, p.player_name, p.club_code, p.games_played,
       p.points, p.ts_pct, p.game_score_average, p.pie,
       r.per, w.win_shares, w.win_shares_per_40
FROM gold.app_player_round_stats AS p
JOIN latest USING (round_number)
LEFT JOIN gold.app_player_round_ratings AS r
  USING (competition_code, season_code, scope, round_number, person_key)
LEFT JOIN gold.app_player_round_win_shares AS w
  USING (competition_code, season_code, scope, round_number, person_key)
WHERE p.competition_code = 'E' AND p.season_code = 'E2025' AND p.scope = 'all'
ORDER BY r.per DESC NULLS LAST;
```

### Official standings with the matching advanced snapshot

Supply the round explicitly instead of taking a separate maximum per table. The left join keeps official rows even without advanced detail. Equal round numbers do not guarantee that historical feed totals match game-derived totals.

```sql
SELECT s.club_code, s.club_name, s.basic_position, s.basic_games_won,
       a.offensive_rating, a.defensive_rating, a.net_rating,
       a.srs, a.adj_net_rating, a.pythagorean_wins
FROM gold.app_standings AS s
LEFT JOIN gold.app_standings_stats AS a
  ON a.competition_code = s.competition_code
 AND a.season_code = s.season_code AND a.scope = s.phase_code
 AND a.round_number = s.round_number AND a.club_code = s.club_code
WHERE s.competition_code = 'E' AND s.season_code = 'E2025'
  AND s.phase_code = 'RS' AND s.round_number = 10
ORDER BY s.basic_position;
```

### Player game line with optional calculated detail

```sql
SELECT b.game_code, b.person_key, b.person_name, b.points, b.total_rebounds,
       b.assists, b.pir, a.game_score, a.usage_pct, a.game_per
FROM gold.app_game_player_stats AS b
LEFT JOIN gold.app_game_player_advanced AS a
  USING (competition_code, season_code, game_code, side, person_key)
WHERE b.competition_code = 'E' AND b.season_code = 'E2025' AND b.game_code = 31;
```

### Per-game player leaders, qualified players only

```sql
SELECT person_key, player_name, club_code, games_played, points,
       min_games, qualified, is_calculated
FROM gold.app_season_player_stats_traditional
WHERE competition_code = 'E' AND season_code = 'E2025'
  AND phase_code = 'RS' AND mode = 'perGame' AND qualified IS TRUE
ORDER BY points DESC NULLS LAST;
```

## Statistics that have no stored field

This repository does not build:

- BPM, OBPM, DBPM, VORP or Estimated Wins Added
- win probability or WPA
- tracking or play-type statistics
- four-man lineup ratings
- RAPM per phase or per round

A frontend field with one of these labels cannot be filled by renaming PER, PIE, RAPM or Win Shares. The calculated player round table also does not store every traditional box-score column. Check the exact [column reference](GOLD_TABLE_REFERENCE.md) before mapping a frontend label to a SQL column.

# Gold data catalog

Start here when choosing data for the frontend. This catalog explains **all 40
Gold tables**, what one row represents, and which table serves each use case.
The names, columns and keys were checked against the repository on 2026-10-20.
This is a code contract, not a live database or frontend completeness audit.

This catalog currently documents EuroLeague coverage. EuroCup coverage and rule
differences will be added when that implementation begins.

| Document | Use it for |
| --- | --- |
| [Bronze catalog](BRONZE_CATALOG.md) | API resource inventory, response shapes, versioned storage and source lineage. |
| [Silver catalog](SILVER_CATALOG.md) | Source/calculated table purposes, row grains, provenance and Gold lineage. |
| [Silver column reference](SILVER_TABLE_REFERENCE.md) | Every Silver column, type, key, nullable flag and source path. |
| [Gold data catalog](DATA_CATALOG.md) | Choose tables, understand row grain and joins, find frontend sources. |
| [Gold table reference](GOLD_TABLE_REFERENCE.md) | Every column of every Gold table: PostgreSQL type, nullability, key and meaning. |
| [Statistics glossary](STAT_GLOSSARY.md) | All documented player and team measures, formulas, units and limitations. |
| [Pipeline data dictionary](DATA_DICTIONARY.md) | Silver, provenance, calculation rules, historical checks and publishing operations. |

## Layers and naming

Bronze stores exact API responses. Silver holds typed source tables and calculated
per-game data. Gold builds app-facing projections and aggregates from Silver.
Neon publishes the registered Gold tables for the web app.

Every table below is `gold.app_*` locally and `public.app_*` on Neon, with the
same registered columns and primary key. Examples use `gold`; change the schema
to `public` for the published database. Build selectors can still use logical
names such as `player_round_stats`. They are not the physical SQL table names.

These tables use natural identifiers, not a dim/fact surrogate-key design.
Do not invent `player_id` or strip leading zeroes from person codes.
Publication eligibility does not prove that a particular season or refreshed
calculation is already live. Local rebuilding and Neon publication are separate;
live publication requires owner approval.

## Find the frontend source

| Frontend need | Read from | Selection / caution |
| --- | --- | --- |
| Season list, schedule, results | `app_seasons`, `app_games` | Include competition and season; respect `status`, `played` and neutral venues. |
| Team profiles, logos, rosters | `app_clubs`, `app_registrations`, `app_people` | Season-specific; registrations can have multiple rows per person. |
| Career profile and club history | `app_players`, `app_club_identities` | Competition-wide; bridge player `person_key` to `person_code` through `app_people`. |
| Official standings, form, streaks | `app_standings` | Use `basic_position`; filter phase and round. |
| Team advanced standings | `app_standings_stats` | Wide combined team row; select scope and one round. |
| Player PTS/REB/AST and season leaders | `app_season_player_stats_traditional` | Select phase and `mode`; use `qualified` where leaderboard rules call for it. |
| Calculated player rates, per-100, Game Score, PIE | `app_player_round_stats` | Select scope and latest scope round; cumulative snapshots must not be summed. |
| Player PER | `app_player_round_ratings` | `per`, `aper`, `uper`; season PER is not mean game PER. |
| Player Win Shares | `app_player_round_win_shares` | `off_win_shares`, `def_win_shares`, `win_shares`, `win_shares_per_40`. |
| Player RAPM | `app_player_rapm` | `scope = 'all'`; `offense`, `defense`, `rapm`; no round column. |
| Player on/off and lineup combinations | `app_player_on_off`, `app_lineup_ratings` | Per club/scope; complete stints only; keep sample possessions visible. |
| Game player box score plus advanced stats | `app_game_player_stats`, `app_game_player_advanced` | Join full player-game key; advanced rows can be absent. |
| Game team box score plus advanced stats | `app_game_team_stats`, `app_game_team_advanced` | Filter `stats_kind = 'total'`; join full side-game key. |
| Quarter scores, score chart, shot chart | `app_game_period_scores`, `app_play_by_play`, `app_shots` | Events use resolved person codes and event order. |
| Counted possessions, leads, clutch, scoring splits | `app_game_team_possessions`, `app_game_team_score_flow`, `app_game_team_shot_splits` | Per-game event measures; E2007+ subject to feed coverage. |
| Team season event summaries | `app_team_pbp_stats` | Whole scope, not round snapshots; inspect coverage/sample columns. |
| Player substitution chart, lineup timeline | `app_game_player_on_court`, `app_game_team_lineup_stints` | Elapsed seconds from tipoff; stints store only complete lineups. |
| Historical leaders, postseason series | `app_records_*`, `app_postseason_series` | Records are competition-wide; series leader is not proof a series is finished. |
| Missing-data explanations | `app_game_stat_gaps` | NULL is unavailable, never automatically zero. |

## Keys, joins and safe aggregation

| Relationship | Join columns / rule |
| --- | --- |
| Game child to game | `competition_code`, `season_code`, `game_code`. |
| Team-game advanced to team-game box score | Game key plus `side`, with box score `stats_kind = 'total'`. |
| Player-game advanced to player box score | Game key plus `side`, `person_key`. |
| Season person profile to box score | `competition_code`, `season_code`, `person_key`. |
| Live event/shot to person profile | Resolved non-NULL live `person_code` equals `app_people.person_key` in the same competition/season. Raw `player_code` is not the join key. |
| Season person to career identity | `app_people.person_code = app_players.person_code`, plus competition. |
| Club profile | Competition, season and `club_code`; `app_club_identities` uses competition and club only. |
| Player round stats/PER/Win Shares | Competition, season, `scope`, `round_number`, `person_key`; `club_code` is latest context, not part of the key. |
| Team round stats/ratings/splits | Competition, season, `scope`, `round_number`, `club_code`. |
| Official standings to calculated team stats | Competition, season, round and club, with `phase_code = scope`. Historical snapshot alignment can differ. |
| On/off to player | Competition, season, scope, club and player; a transferred player has separate club rows. |

Filter **both** competition and season in season tables. `all`, individual phases
and `PS` overlap; they are alternative views, not additive categories. `PS` means
PI + PO + FF, not every historical non-RS phase. `TS` is its own historical phase.
Round numbers follow the stored games, not a renumbered list of played dates.

Round tables contain cumulative snapshots. Pick one round per selected scope;
do not sum snapshots or average their percentages. A club/player that is idle
retains its previous cumulative totals. Transfers produce blended player-round
totals with the latest club label. For club-specific player analysis use game
rows or the explicitly club-keyed on/off table.

The season player feeds have `entry_ordinal` in the key. It is a feed position,
not a career identity. Do not assume the SQL schema guarantees one row per
person/club just because a feed normally returns it that way.
Transferred players can also have a semicolon-separated source club code such
as `BAS;TEL` in season feeds. That value does not join one `app_clubs` profile;
use the registration history or player game rows for club-specific attribution.

Calculated rates are generally fractions (`0.55` displays as `55%`); API player
percentage columns use percentage points (`55.0` displays as `55%`). Source
ratio/share fields need their own definitions. See the [glossary](STAT_GLOSSARY.md)
before applying a universal formatter. `NUMERIC` can arrive as a decimal string
depending on the PostgreSQL client; convert explicitly in the app boundary.

## Coverage and missing values

Box-score-derived statistics can exist from E2000 when the required box scores
exist. Play-by-play, shot, interval, lineup, on/off and RAPM tables begin at E2007
and still depend on the actual source for each game. Scheduled games and forfeits
without complete box scores do not generate the calculated game/round rows.

Use a left join when attaching optional advanced or event detail to a schedule
or official box score. Missing rows, NULL, and a measured zero are distinct.
`game_stat_gaps` describes official box-score gaps; it does not enumerate every
possible missing derived rate. Check coverage and the relevant sample columns.
No query against Neon was made for this documentation; do not infer currently
published season coverage from a local table definition.

## Table catalog

The following links open each table's complete column reference. The grain is
always within competition; include season unless the row says competition-wide.

### Profiles, roster and schedule

| Table | Purpose | One row represents |
| --- | --- | --- |
| [`app_seasons`](GOLD_TABLE_REFERENCE.md#app_seasons) | Season selector and season metadata. | one competition-season. |
| [`app_clubs`](GOLD_TABLE_REFERENCE.md#app_clubs) | Season-specific team names, crests and profiles. | one club per season. |
| [`app_people`](GOLD_TABLE_REFERENCE.md#app_people) | Season-specific person profiles and the bridge between person_key and person_code. | one person per season. |
| [`app_registrations`](GOLD_TABLE_REFERENCE.md#app_registrations) | Rosters, jersey numbers, positions and registration dates. | one person-club-role registration per season. |
| [`app_rounds`](GOLD_TABLE_REFERENCE.md#app_rounds) | Round names, phase labels and date ranges. | one round definition per season. |
| [`app_games`](GOLD_TABLE_REFERENCE.md#app_games) | Schedule, results, game status and venue details. | one fixture per season. |
| [`app_game_officials`](GOLD_TABLE_REFERENCE.md#app_game_officials) | Referee assignments for game details. | one official slot per game. |
| [`app_players`](GOLD_TABLE_REFERENCE.md#app_players) | One player identity across seasons, with career span and club history. | one player per competition and person_code. |
| [`app_club_identities`](GOLD_TABLE_REFERENCE.md#app_club_identities) | One club identity across seasons. | one club per competition. |

### Official box scores and season player feeds

| Table | Purpose | One row represents |
| --- | --- | --- |
| [`app_game_period_scores`](GOLD_TABLE_REFERENCE.md#app_game_period_scores) | Quarter and overtime scoring. | one side-period per game. |
| [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats) | Official player box scores, including DNP lines. | one player-side per game. |
| [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats) | Official team box scores and team-only contributions. | one stats_kind per side-game. |
| [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional) | Player season totals and per-game box-score leaderboards. | one feed entry per phase and mode. |
| [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced) | API player shooting efficiency, rebound rates and other reference ratios. | one feed entry per phase and mode. |
| [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring) | API player shot mix and scoring distribution. | one feed entry per phase and mode. |
| [`app_season_player_stats_misc`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_misc) | Player starts, wins/losses and double/triple doubles. | one feed entry per phase and mode. |

### Standings, records and postseason

| Table | Purpose | One row represents |
| --- | --- | --- |
| [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings) | Official standings page, form, streaks and standings splits. | one club-phase-round snapshot. |
| [`app_team_season_stats`](GOLD_TABLE_REFERENCE.md#app_team_season_stats) | Team and opponent season box-score totals. | one club-phase per season, for phases actually present in games. |
| [`app_records_player_seasons`](GOLD_TABLE_REFERENCE.md#app_records_player_seasons) | Historical top player-season leaderboards. | one rank slot per metric and competition. |
| [`app_records_single_games`](GOLD_TABLE_REFERENCE.md#app_records_single_games) | Historical top individual game performances. | one rank slot per metric and competition. |
| [`app_records_team_seasons`](GOLD_TABLE_REFERENCE.md#app_records_team_seasons) | Historical top team-season leaderboards. | one rank slot per metric and competition. |
| [`app_postseason_series`](GOLD_TABLE_REFERENCE.md#app_postseason_series) | Play-in, playoff and Final Four pairings with game lists. | one sorted club pair per postseason phase and season. |

### Calculated team statistics

| Table | Purpose | One row represents |
| --- | --- | --- |
| [`app_standings_stats`](GOLD_TABLE_REFERENCE.md#app_standings_stats) | One frontend-ready team advanced-stat row: cumulative totals and ratings, league-relative and opponent-adjusted strength, home/away and last-5/last-10 form. | one club-scope-round snapshot. |
| [`app_team_pbp_stats`](GOLD_TABLE_REFERENCE.md#app_team_pbp_stats) | Season-scope possessions, score flow, clutch and shot-split summaries. | one club-scope per season. |

### Calculated player and lineup statistics

| Table | Purpose | One row represents |
| --- | --- | --- |
| [`app_player_round_stats`](GOLD_TABLE_REFERENCE.md#app_player_round_stats) | Calculated cumulative player totals, rates, per-100 stats, Game Score and PIE. | one player-scope-round snapshot. |
| [`app_player_round_ratings`](GOLD_TABLE_REFERENCE.md#app_player_round_ratings) | Cumulative Hollinger PER for player comparisons. | one player-scope-round snapshot. |
| [`app_player_round_win_shares`](GOLD_TABLE_REFERENCE.md#app_player_round_win_shares) | Offensive, defensive and total estimated win contributions. | one player-scope-round snapshot. |
| [`app_player_on_off`](GOLD_TABLE_REFERENCE.md#app_player_on_off) | Team performance while a player is on or off court. | one player-club-scope per season. |
| [`app_lineup_ratings`](GOLD_TABLE_REFERENCE.md#app_lineup_ratings) | Ratings for pairs, triples and five-man units. | one lineup-size-lineup-club-scope per season. |
| [`app_player_rapm`](GOLD_TABLE_REFERENCE.md#app_player_rapm) | Regularized adjusted plus-minus from lineup stints. | one player per season with scope = all. |

### Events and calculated game detail

| Table | Purpose | One row represents |
| --- | --- | --- |
| [`app_play_by_play`](GOLD_TABLE_REFERENCE.md#app_play_by_play) | Event timeline for game charts and event-level analysis. | one event ordinal within a game period. |
| [`app_shots`](GOLD_TABLE_REFERENCE.md#app_shots) | Individual shot events, coordinates and shot flags. | one shot ordinal per game. |
| [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced) | Game-level player efficiency, on-court rates, Game Score and game PER. | one player-side per game with a counted box score. |
| [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced) | Game-level team estimated possessions, pace, ratings and four factors. | one side per game with a counted box score. |
| [`app_game_team_possessions`](GOLD_TABLE_REFERENCE.md#app_game_team_possessions) | Counted possessions and possession duration beside the box-score estimate. | one side per game with usable events and an advanced row. |
| [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow) | Lead changes, runs, time ahead/behind and clutch scoring. | one side per game with a running score. |
| [`app_game_team_shot_splits`](GOLD_TABLE_REFERENCE.md#app_game_team_shot_splits) | Fast-break, second-chance, turnover and assisted scoring. | one side per game with usable events. |
| [`app_game_player_on_court`](GOLD_TABLE_REFERENCE.md#app_game_player_on_court) | Continuous player on-court intervals. | one interval ordinal per player-side-game. |
| [`app_game_team_lineup_stints`](GOLD_TABLE_REFERENCE.md#app_game_team_lineup_stints) | Five-on-five stints with scoring and counted possessions. | one side-stint per game. |
| [`app_game_stat_gaps`](GOLD_TABLE_REFERENCE.md#app_game_stat_gaps) | Reasons an official box-score measure is unavailable. | one stat_name per game. |

## Query examples

These read-only examples use local Gold. Use `public` for the corresponding
published tables. E2025 is an example season, not an assertion of live coverage.

### One player advanced leaderboard, including PER and Win Shares

Choose a single scope's final stored round. Join the full snapshot key;
joining only on player duplicates rows across rounds and scopes.

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

### Official standings plus the corresponding advanced snapshot

Supply the desired round rather than taking a separate maximum for each table.
The LEFT JOIN retains official rows even if advanced detail is absent. An equal
round number does not prove historical feed totals align with game-derived totals.

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

### Official player game line plus optional calculated detail

```sql
SELECT b.game_code, b.person_key, b.person_name, b.points, b.total_rebounds,
       b.assists, b.pir, a.game_score, a.usage_pct, a.game_per
FROM gold.app_game_player_stats AS b
LEFT JOIN gold.app_game_player_advanced AS a
  USING (competition_code, season_code, game_code, side, person_key)
WHERE b.competition_code = 'E' AND b.season_code = 'E2025' AND b.game_code = 31;
```

### Official per-game player leaders, including qualification

```sql
SELECT person_key, player_name, club_code, games_played, points,
       min_games, qualified, is_calculated
FROM gold.app_season_player_stats_traditional
WHERE competition_code = 'E' AND season_code = 'E2025'
  AND phase_code = 'RS' AND mode = 'perGame' AND qualified IS TRUE
ORDER BY points DESC NULLS LAST;
```

## Statistics that have no stored field

BPM, OBPM, DBPM, VORP, Estimated Wins Added, win probability, WPA, tracking and
play-type model statistics are not built by this repository. A frontend field
with one of those labels cannot be filled by renaming PER, PIE, RAPM or Win Shares.
RAPM has no phase/round snapshots, four-man lineup ratings are not built, and
the calculated round player table does not store every traditional box-score
column. Use the exact [column reference](GOLD_TABLE_REFERENCE.md) before mapping
a frontend label to a SQL column.

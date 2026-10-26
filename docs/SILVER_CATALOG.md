# EuroLeague Silver data catalog

Silver is the local PostgreSQL layer of typed EuroLeague source data and calculated
game detail. This catalog covers **26 source tables, seven calculated tables and
one load-log table**. It describes the code contract checked on 2026-10-20;
no API fetch, database rebuild or live coverage query was performed.

Scope is EuroLeague (`competition_code = 'E'`, season codes such as `E2025`).
EuroCup coverage and rule differences will be documented when that work begins.

| Document | Purpose |
| --- | --- |
| [Bronze catalog](BRONZE_CATALOG.md) | API resources, response containers, storage and upstream lineage. |
| [Silver catalog](SILVER_CATALOG.md) | Table purposes, grain, sources, downstream use and query examples. |
| [Silver column reference](SILVER_TABLE_REFERENCE.md) | Every Silver column, type, nullability, key, source path and description. |
| [Gold catalog](DATA_CATALOG.md) | Choose the app-facing table for each frontend feature. |
| [Gold column reference](GOLD_TABLE_REFERENCE.md) | Published column contracts. |
| [Shared stats glossary](STAT_GLOSSARY.md) | Player/team metric formulas, units and interpretation. |
| [Pipeline dictionary](DATA_DICTIONARY.md) | Operational rules and historical verification notes. |

## What Silver owns

Bronze preserves response bytes. Silver extracts individual typed fields, normalizes
source spellings, resolves live player identities and records known gaps. Calculated
game tables enrich those rows with box-score and event-derived statistics. Gold
then creates season/scope/round aggregates, records, identities and page tables.

Use `silver.<table>` explicitly in analysis. The ETL connection's search path is
Silver, but the catalogs use schema-qualified names to avoid confusing similarly
named Gold tables. Silver itself is local; publication reads Gold, not Silver.

All 36 data tables have a primary key beginning with competition and season and
two required metadata columns, `load_id UUID` and `loaded_at TIMESTAMPTZ`.
`silver.load_log` records successful replacements, including zero-row replacements.
Missing input files cause a source table to be skipped; a missing source is not
the same as a successful empty replacement.

## Table catalog

Source paths below are logical resources beneath
`data/bronze/euroleague/<season>/`; `_catalog/v2/seasons` is competition-wide.
Each resource directory contains versioned `.json.gz` files, not one overwritten
JSON file. Paths and response shapes are explained in the Bronze catalog.

### Season, clubs, people and registration

| Table | Purpose / one row | Upstream | Gold use |
| --- | --- | --- | --- |
| [`silver.seasons`](SILVER_TABLE_REFERENCE.md#seasons) | Competition season names, dates and champion. Grain: one season. | `_catalog/v2/seasons` | [`app_seasons`](GOLD_TABLE_REFERENCE.md#app_seasons) |
| [`silver.clubs`](SILVER_TABLE_REFERENCE.md#clubs) | Season club profiles, names, crests and venue codes. Grain: one club-season. | `v2/clubs` | [`app_clubs`](GOLD_TABLE_REFERENCE.md#app_clubs); app_club_identities; names/crests in page and aggregate tables |
| [`silver.people`](SILVER_TABLE_REFERENCE.md#people) | Deduplicated season person profiles and identity bridge. Grain: one person-season. | `v2/season_people_pages/offset_*` | [`app_people`](GOLD_TABLE_REFERENCE.md#app_people); app_players (via player registrations) |
| [`silver.registrations`](SILVER_TABLE_REFERENCE.md#registrations) | Club/role registrations and roster details. Grain: one registration-season. | `v2/season_people_pages/offset_*` | [`app_registrations`](GOLD_TABLE_REFERENCE.md#app_registrations); app_players |
| [`silver.rounds`](SILVER_TABLE_REFERENCE.md#rounds) | Source round definitions and date ranges. Grain: one round definition-season. | `v2/rounds` | [`app_rounds`](GOLD_TABLE_REFERENCE.md#app_rounds) |

### Fixtures and official box scores

| Table | Purpose / one row | Upstream | Gold use |
| --- | --- | --- | --- |
| [`silver.games`](SILVER_TABLE_REFERENCE.md#games) | Every scheduled or played fixture with result, status and venue. Grain: one game-season. | `v2/games` | [`app_games`](GOLD_TABLE_REFERENCE.md#app_games); team/player round tables, standings_stats, records, postseason_series and event/lineup aggregates |
| [`silver.game_officials`](SILVER_TABLE_REFERENCE.md#game_officials) | Official assignments extracted from the fixture list. Grain: one official slot-game. | `v2/games` | [`app_game_officials`](GOLD_TABLE_REFERENCE.md#app_game_officials) |
| [`silver.game_period_scores`](SILVER_TABLE_REFERENCE.md#game_period_scores) | Quarter and overtime points extracted from fixtures. Grain: one side-period-game. | `v2/games` | [`app_game_period_scores`](GOLD_TABLE_REFERENCE.md#app_game_period_scores) |
| [`silver.game_player_stats`](SILVER_TABLE_REFERENCE.md#game_player_stats) | Official player box-score lines and registration context. Grain: one player-side-game. | `v2/game_stats/{game}` | [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats); player round stats/PER/Win Shares, game PER, PS player rows, app_records_single_games |
| [`silver.game_team_stats`](SILVER_TABLE_REFERENCE.md#game_team_stats) | Official team-only and complete team box scores. Grain: one stats_kind-side-game. | `v2/game_stats/{game}` | [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats); app_team_season_stats, team/player round calculations, app_records_team_seasons |
| [`silver.game_stat_gaps`](SILVER_TABLE_REFERENCE.md#game_stat_gaps) | Explicit explanations of missing official box-score measures. Grain: one stat_name-game. | `v2/game_stats/{game}` | [`app_game_stat_gaps`](GOLD_TABLE_REFERENCE.md#app_game_stat_gaps) |

### API player and team season statistics

| Table | Purpose / one row | Upstream | Gold use |
| --- | --- | --- | --- |
| [`silver.season_player_stats_traditional`](SILVER_TABLE_REFERENCE.md#season_player_stats_traditional) | Source player traditional statistics by phase and mode. Grain: one entry ordinal-phase-mode. | `v3/season_stats/players_traditional_{phase}_{mode}` | [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional) |
| [`silver.season_player_stats_advanced`](SILVER_TABLE_REFERENCE.md#season_player_stats_advanced) | Source player advanced statistics by phase and mode. Grain: one entry ordinal-phase-mode. | `v3/season_stats/players_advanced_{phase}_{mode}` | [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced) |
| [`silver.season_player_stats_scoring`](SILVER_TABLE_REFERENCE.md#season_player_stats_scoring) | Source player scoring statistics by phase and mode. Grain: one entry ordinal-phase-mode. | `v3/season_stats/players_scoring_{phase}_{mode}` | [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring) |
| [`silver.season_player_stats_misc`](SILVER_TABLE_REFERENCE.md#season_player_stats_misc) | Source player misc statistics by phase and mode. Grain: one entry ordinal-phase-mode. | `v3/season_stats/players_misc_{phase}_{mode}` | [`app_season_player_stats_misc`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_misc) |
| [`silver.season_team_stats_traditional`](SILVER_TABLE_REFERENCE.md#season_team_stats_traditional) | Source team traditional reference statistics. Grain: one club-phase-mode. | `v3/season_stats/teams_traditional_{phase}_{mode}` | No direct projection; API cross-checks for calculated round statistics |
| [`silver.season_team_stats_advanced`](SILVER_TABLE_REFERENCE.md#season_team_stats_advanced) | Source team advanced reference statistics. Grain: one club-phase-mode. | `v3/season_stats/teams_advanced_{phase}_{mode}` | No direct projection; API cross-checks for calculated round statistics |

### Official standings and child rows

| Table | Purpose / one row | Upstream | Gold use |
| --- | --- | --- | --- |
| [`silver.standings_basic`](SILVER_TABLE_REFERENCE.md#standings_basic) | Official positions, wins/losses, points and record splits. Grain: one club-phase-round. | `v3/standings/{phase}_{round}_basicstandings` | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings), merged/normalized into one page row |
| [`silver.standings_calendar`](SILVER_TABLE_REFERENCE.md#standings_calendar) | Official calendar standings snapshot. Grain: one club-phase-round. | `v3/standings/{phase}_{round}_calendarstandings` | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings), merged/normalized into one page row |
| [`silver.standings_streaks`](SILVER_TABLE_REFERENCE.md#standings_streaks) | Official streak and recent-form record summaries. Grain: one club-phase-round. | `v3/standings/{phase}_{round}_streaks` | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings), merged/normalized into one page row |
| [`silver.standings_ahead_behind`](SILVER_TABLE_REFERENCE.md#standings_ahead_behind) | Official win-loss records by score checkpoint. Grain: one club-phase-round. | `v3/standings/{phase}_{round}_aheadbehind` | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings), merged/normalized into one page row |
| [`silver.standings_margins`](SILVER_TABLE_REFERENCE.md#standings_margins) | Official result records by margin and statistical comparison. Grain: one club-phase-round. | `v3/standings/{phase}_{round}_margins` | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings), merged/normalized into one page row |
| [`silver.standings_calendar_streaks`](SILVER_TABLE_REFERENCE.md#standings_calendar_streaks) | Normalized child streaks of calendar standings. Grain: one streak ordinal-club-phase-round. | `v3/standings/{phase}_{round}_calendarstandings` | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings), merged/normalized into one page row |
| [`silver.standings_basic_form`](SILVER_TABLE_REFERENCE.md#standings_basic_form) | Normalized recent-result labels from basic standings. Grain: one result ordinal-club-phase-round. | `v3/standings/{phase}_{round}_basicstandings` | [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings), merged/normalized into one page row |

### Live events and shots

| Table | Purpose / one row | Upstream | Gold use |
| --- | --- | --- | --- |
| [`silver.play_by_play`](SILVER_TABLE_REFERENCE.md#play_by_play) | Raw typed live event timeline with resolved player identities. Grain: one event ordinal-period-game. | `live/{game}/play_by_play` | [`app_play_by_play`](GOLD_TABLE_REFERENCE.md#app_play_by_play) |
| [`silver.shots`](SILVER_TABLE_REFERENCE.md#shots) | Typed shot attempts, coordinates, zone and context flags. Grain: one shot ordinal-game. | `live/{game}/shooting_charts` | [`app_shots`](GOLD_TABLE_REFERENCE.md#app_shots) |

### Calculated game tables

| Table | Purpose / one row | Upstream | Gold use |
| --- | --- | --- | --- |
| [`silver.game_team_advanced`](SILVER_TABLE_REFERENCE.md#game_team_advanced) | Box-score estimated possessions, pace, ratings and four factors. Grain: one side-game. | `games, game_period_scores, game_team_stats, game_stat_gaps` | [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced); team/player round calculations, game PER context |
| [`silver.game_player_advanced`](SILVER_TABLE_REFERENCE.md#game_player_advanced) | Player Game Score, efficiency and on-court/estimated rates. Grain: one player-side-game. | `games, game_period_scores, game_team_stats, game_player_stats, game_stat_gaps, play_by_play` | [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced); app_player_round_stats Game Score totals |
| [`silver.game_team_possessions`](SILVER_TABLE_REFERENCE.md#game_team_possessions) | Counted possessions and their measurable lengths. Grain: one side-game. | `games, game_team_advanced, play_by_play` | [`app_game_team_possessions`](GOLD_TABLE_REFERENCE.md#app_game_team_possessions); app_team_pbp_stats |
| [`silver.game_team_score_flow`](SILVER_TABLE_REFERENCE.md#game_team_score_flow) | Running-score leads, runs, time ahead/behind and clutch. Grain: one side-game. | `games, play_by_play` | [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow); app_team_pbp_stats |
| [`silver.game_team_shot_splits`](SILVER_TABLE_REFERENCE.md#game_team_shot_splits) | Flagged scoring and capped assisted-field-goal counts. Grain: one side-game. | `games, shots, play_by_play` | [`app_game_team_shot_splits`](GOLD_TABLE_REFERENCE.md#app_game_team_shot_splits); app_team_pbp_stats |
| [`silver.game_player_on_court`](SILVER_TABLE_REFERENCE.md#game_player_on_court) | Reconstructed continuous player on-court stretches. Grain: one interval ordinal-player-side-game. | `games, game_player_stats, play_by_play` | [`app_game_player_on_court`](GOLD_TABLE_REFERENCE.md#app_game_player_on_court) |
| [`silver.game_team_lineup_stints`](SILVER_TABLE_REFERENCE.md#game_team_lineup_stints) | Complete five-versus-five intervals with scoring and possessions. Grain: one stint ordinal-side-game. | `games, game_player_stats, play_by_play` | [`app_game_team_lineup_stints`](GOLD_TABLE_REFERENCE.md#app_game_team_lineup_stints); app_player_on_off, app_lineup_ratings, app_player_rapm |

### Load metadata

| Table | Purpose / one row | Upstream | Gold use |
| --- | --- | --- | --- |
| [`silver.load_log`](SILVER_TABLE_REFERENCE.md#load_log) | One successful table/competition/season replacement, including zero-row loads. | Load writers | No published projection. |

## Lineage and layer differences

| Need | Bronze -> Silver -> Gold |
| --- | --- |
| Schedule/results | `v2/games` -> `silver.games` -> `gold.app_games`. The same response supplies officials and period scores. |
| Roster/career identity | People pages -> `silver.people`, `silver.registrations` -> season profiles/registrations and `gold.app_players`. |
| Official player stats | `v3/season_stats/players_*` -> four `silver.season_player_stats_*` tables -> the four Gold projections plus calculated rows/qualification. |
| Team efficiency | `v2/game_stats/*` + fixtures -> team box scores and `silver.game_team_advanced` -> team round tables and `gold.app_standings_stats`. |
| Player Game Score/PER/Win Shares | Box scores -> player/team Silver rows and game advanced -> player round stats/ratings/win shares and Gold game PER. PER/Win Shares are Gold calculations. |
| Official standings | Five v3 feeds -> seven normalized Silver tables -> one `gold.app_standings` page table. |
| Score flow and possessions | Live events + fixtures -> per-game Silver possessions/score-flow tables -> Gold copies and `gold.app_team_pbp_stats`. |
| Shot maps and scoring splits | Shots + events + fixtures -> Silver shot splits -> Gold game copies and team PBP summaries. |
| Lineups, on/off, RAPM | Starters + events + fixtures -> Silver intervals and complete stints -> Gold copies, lineup ratings, on/off and RAPM. |

The raw team API season feeds stay in Silver for comparison with calculated
Gold results. They do not have direct app tables. Gold `app_standings` merges
the seven Silver standings tables and turns child rows back into ordered JSON.

Gold source projections omit provenance. Gold season player tables add
`is_calculated`, `min_games`, `qualified`, missing `perGame` rows and, for
traditional/misc only, postseason `PS` rows. Silver retains only source phases
and modes. The Gold team-season table stores actual phase totals without
synthetic all/PS; round tables have their separate all/phase/PS scope model.

Silver `game_player_advanced.rate_source` distinguishes actual on-court rates
from box-score estimates. Gold omits this indicator and adds game_uper,
game_aper and game_per. Gold team advanced drops opponent, phase and round
context columns; join its game row for those values. Do not assume Silver and
Gold schemas are identical even when their metric values match.

## Coverage and interpretation

EuroLeague box-score and API season sources are supported from E2000, subject
to the actual response. Live event and shot sources begin at E2007 and still
have game-level gaps. A successful HTTP request, an empty Silver table and a
NULL rate describe different conditions. Scheduled games and forfeits without
complete box scores do not produce normal calculated-game rows.

`NULL` means unavailable or undefined. The loader converts empty numeric markers
and undefined percentages to NULL, stores unknown attendance as NULL and
identifies specified all-zero box-score measures as unrecorded. It does not
convert every zero into NULL. The original response remains in Bronze.

Source percentages keep their source scale; calculated ratios normally use
fractions. Use the shared glossary for each measure. Raw standings record text
must not be treated as a points/rebounds total.

Live `period` is text: FirstQuarter, SecondQuarter, ThirdQuarter, ForthQuarter
(the upstream spelling), ExtraTime. Chronology uses that explicit period rank,
overtime number derived from minute, then event_ordinal. Alphabetic period order
and play_number are both unsuitable. `person_code` in events/shots resolves to
the box-score `person_key`, not necessarily the career profile's person_code.

## Provenance: row -> replacement -> exact Bronze version

Each successful source-table replacement writes rows and the log entry in one
transaction. The log keeps older load IDs after a rerun; current rows reference
the latest successful replacement. `loaded_at` is load time, not API fetch time.

```sql
SELECT g.game_code, g.load_id, g.loaded_at, l.bronze_versions
FROM silver.games AS g
JOIN silver.load_log AS l
  ON l.competition_code = g.competition_code
 AND l.season_code = g.season_code
 AND l.table_name = 'games' AND l.load_id = g.load_id
WHERE g.competition_code = 'E' AND g.season_code = 'E2025'
LIMIT 20;
```

`bronze_versions` is a sorted deduplicated JSON array of actual paths relative to
`data/bronze/`. Auxiliary reads, such as game box scores used to resolve a live
player, are included. Calculated-table loads have an empty array because they
read Silver; their log does not record the exact upstream Silver load IDs.

## Read-only inspection examples

### One official player game line with optional calculated detail

```sql
SELECT b.game_code, b.person_key, b.person_name, b.points, b.assists,
       a.game_score, a.usage_pct, a.rate_source
FROM silver.game_player_stats AS b
LEFT JOIN silver.game_player_advanced AS a
  USING (competition_code, season_code, game_code, side, person_key)
WHERE b.competition_code = 'E' AND b.season_code = 'E2025'
  AND b.game_code = 31;
```

### Team total rows with club identity

```sql
SELECT b.game_code, b.side,
       CASE WHEN b.side = 'local' THEN g.local_club_code
            ELSE g.road_club_code END AS club_code,
       b.points, b.assists, b.total_rebounds
FROM silver.game_team_stats AS b
JOIN silver.games AS g USING (competition_code, season_code, game_code)
WHERE b.competition_code = 'E' AND b.season_code = 'E2025'
  AND b.stats_kind = 'total' AND g.played IS TRUE;
```

### Recent successful loads, including empty replacements

```sql
SELECT table_name, load_id, loaded_at, row_count, bronze_versions
FROM silver.load_log
WHERE competition_code = 'E' AND season_code = 'E2025'
ORDER BY loaded_at DESC, table_name
LIMIT 30;
```

Schema and derivations are documented from code. These examples were checked
against declared columns; they were not executed against a live database.
Use [postgres_etl/README.md](../postgres_etl/README.md) for load and quality commands.

# Silver data catalog

Silver is the local PostgreSQL layer of typed EuroLeague and EuroCup source data plus calculated per-game detail. This catalog describes its **26 source tables, 7 calculated tables and the load log**: what each holds, where it comes from, and which Gold tables use it. For every column, follow a table's link to the [Silver table reference](SILVER_TABLE_REFERENCE.md). For loading commands, see [postgres_etl/README.md](../postgres_etl/README.md).

This describes the code contract checked on 2026-10-20; no API fetch, rebuild or live coverage query was made for it. The examples use EuroLeague (`competition_code = 'E'`, seasons such as `E2025`). EuroCup rows (`'U'`, `U2025`) share every table; see [EuroCup](#eurocup).

## Contents

- [What Silver does](#what-silver-does)
- [Table catalog](#table-catalog)
- [Lineage from Bronze to Gold](#lineage-from-bronze-to-gold)
- [Coverage and interpretation](#coverage-and-interpretation)
- [EuroCup](#eurocup)
- [Provenance](#provenance)
- [Example queries](#example-queries)

## What Silver does

Bronze keeps the exact response bytes. Silver:

- extracts individual typed fields and normalizes source spellings,
- resolves live player identities to box-score `person_key`s,
- records known source gaps instead of hiding them, and
- adds calculated per-game tables from box scores and play-by-play.

Gold then builds season, scope and round aggregates, records, identities and page tables from Silver. Silver itself is never published; Neon is filled from Gold.

Every one of the 33 data tables has a primary key starting with `competition_code` and `season_code`, plus two required metadata columns, `load_id UUID` and `loaded_at TIMESTAMPTZ`. `silver.load_log` records each successful replacement, including zero-row ones. A missing input file skips its table, which is not the same as a successful empty replacement.

Use `silver.<table>` explicitly in analysis. The loader's connection sets `search_path = silver`, but schema-qualified names avoid confusion with the similarly named Gold tables.

## Table catalog

Upstream paths are Bronze resources under `data/bronze/euroleague/<season>/` (`_catalog/v2/seasons` is shared by all seasons). Each resource directory holds versioned `.json.gz` files; the [Bronze catalog](BRONZE_CATALOG.md) explains them.

### Season, clubs, people and registration

| Table | Purpose | One row | Upstream | Used by Gold |
| --- | --- | --- | --- | --- |
| [`seasons`](SILVER_TABLE_REFERENCE.md#seasons) | Season names, dates and champion | season | `_catalog/v2/seasons` | `app_seasons` |
| [`clubs`](SILVER_TABLE_REFERENCE.md#clubs) | Club profiles, names, crests, venue codes | club per season | `v2/clubs` | `app_clubs`, `app_club_identities`; names and crests in page tables |
| [`people`](SILVER_TABLE_REFERENCE.md#people) | Deduplicated person profiles and identity bridge | person per season | `v2/season_people_pages/offset_*` | `app_people`, `app_players` |
| [`registrations`](SILVER_TABLE_REFERENCE.md#registrations) | Club and role registrations, roster details | registration per season | `v2/season_people_pages/offset_*` | `app_registrations`, `app_players` |
| [`rounds`](SILVER_TABLE_REFERENCE.md#rounds) | Round definitions and date ranges | round per season | `v2/rounds` | `app_rounds` |

### Fixtures and official box scores

| Table | Purpose | One row | Upstream | Used by Gold |
| --- | --- | --- | --- | --- |
| [`games`](SILVER_TABLE_REFERENCE.md#games) | Every scheduled or played fixture with result, status and venue | game | `v2/games` | `app_games`; context for nearly every calculated table |
| [`game_officials`](SILVER_TABLE_REFERENCE.md#game_officials) | Referee assignments | official slot per game | `v2/games` | `app_game_officials` |
| [`game_period_scores`](SILVER_TABLE_REFERENCE.md#game_period_scores) | Quarter and overtime points | side and period per game | `v2/games` | `app_game_period_scores` |
| [`game_player_stats`](SILVER_TABLE_REFERENCE.md#game_player_stats) | Official player box-score lines | player and side per game | `v2/game_stats/{game}` | `app_game_player_stats`; player round stats, PER, Win Shares, game PER, `PS` rows, single-game records |
| [`game_team_stats`](SILVER_TABLE_REFERENCE.md#game_team_stats) | Official team-only and complete team box scores | `stats_kind` per side and game | `v2/game_stats/{game}` | `app_game_team_stats`; team-season totals, round calculations, team-season records |
| [`game_stat_gaps`](SILVER_TABLE_REFERENCE.md#game_stat_gaps) | Why an official box-score measure is missing | `stat_name` per game | `v2/game_stats/{game}` | `app_game_stat_gaps` |

### API player and team season statistics

| Table | Purpose | One row | Upstream | Used by Gold |
| --- | --- | --- | --- | --- |
| [`season_player_stats_traditional`](SILVER_TABLE_REFERENCE.md#season_player_stats_traditional) | Player traditional statistics | feed entry per phase and mode | `v3/season_stats/players_traditional_{phase}_{mode}` | `app_season_player_stats_traditional` |
| [`season_player_stats_advanced`](SILVER_TABLE_REFERENCE.md#season_player_stats_advanced) | Player advanced statistics | feed entry per phase and mode | `v3/season_stats/players_advanced_{phase}_{mode}` | `app_season_player_stats_advanced` |
| [`season_player_stats_scoring`](SILVER_TABLE_REFERENCE.md#season_player_stats_scoring) | Player scoring statistics | feed entry per phase and mode | `v3/season_stats/players_scoring_{phase}_{mode}` | `app_season_player_stats_scoring` |
| [`season_player_stats_misc`](SILVER_TABLE_REFERENCE.md#season_player_stats_misc) | Player miscellaneous statistics | feed entry per phase and mode | `v3/season_stats/players_misc_{phase}_{mode}` | `app_season_player_stats_misc` |
| [`season_team_stats_traditional`](SILVER_TABLE_REFERENCE.md#season_team_stats_traditional) | Team traditional reference statistics | club per phase and mode | `v3/season_stats/teams_traditional_{phase}_{mode}` | No Gold table; cross-check for calculated team totals |
| [`season_team_stats_advanced`](SILVER_TABLE_REFERENCE.md#season_team_stats_advanced) | Team advanced reference statistics | club per phase and mode | `v3/season_stats/teams_advanced_{phase}_{mode}` | No Gold table; cross-check for calculated team totals |

### Official standings

All seven tables are merged into one row per club, phase and round in `app_standings`; the two child tables become ordered JSON arrays there.

| Table | Purpose | One row | Upstream feed |
| --- | --- | --- | --- |
| [`standings_basic`](SILVER_TABLE_REFERENCE.md#standings_basic) | Positions, wins and losses, points, record splits | club per phase and round | `basicstandings` |
| [`standings_calendar`](SILVER_TABLE_REFERENCE.md#standings_calendar) | Calendar standings snapshot | club per phase and round | `calendarstandings` |
| [`standings_streaks`](SILVER_TABLE_REFERENCE.md#standings_streaks) | Streak and recent-form summaries | club per phase and round | `streaks` |
| [`standings_ahead_behind`](SILVER_TABLE_REFERENCE.md#standings_ahead_behind) | Win-loss records by score checkpoint | club per phase and round | `aheadbehind` |
| [`standings_margins`](SILVER_TABLE_REFERENCE.md#standings_margins) | Results by margin and statistical comparison | club per phase and round | `margins` |
| [`standings_calendar_streaks`](SILVER_TABLE_REFERENCE.md#standings_calendar_streaks) | Child streaks of the calendar standings | streak per club, phase and round | `calendarstandings` |
| [`standings_basic_form`](SILVER_TABLE_REFERENCE.md#standings_basic_form) | Recent-result labels from basic standings | result per club, phase and round | `basicstandings` |

Each feed is stored at `v3/standings/{phase}_{round}_{feed}`.

### Live events and shots

| Table | Purpose | One row | Upstream | Used by Gold |
| --- | --- | --- | --- | --- |
| [`play_by_play`](SILVER_TABLE_REFERENCE.md#play_by_play) | Typed event timeline with resolved player identities | event per period and game | `live/{game}/play_by_play` | `app_play_by_play` |
| [`shots`](SILVER_TABLE_REFERENCE.md#shots) | Shot attempts with coordinates, zone and context flags | shot per game | `live/{game}/shooting_charts` | `app_shots` |

### Calculated game tables

These are built from other Silver tables by the scripts described in [postgres_etl/README.md](../postgres_etl/README.md#calculated-per-game-tables).

| Table | Purpose | One row | Built from | Used by Gold |
| --- | --- | --- | --- | --- |
| [`game_team_advanced`](SILVER_TABLE_REFERENCE.md#game_team_advanced) | Box-score estimated possessions, pace, ratings, four factors | side per game | `games`, `game_period_scores`, `game_team_stats`, `game_stat_gaps` | `app_game_team_advanced`; round calculations, game PER |
| [`game_player_advanced`](SILVER_TABLE_REFERENCE.md#game_player_advanced) | Game Score, efficiency, on-court or estimated rates | player and side per game | the above plus `game_player_stats`, `play_by_play` | `app_game_player_advanced`; Game Score in `app_player_round_stats` |
| [`game_team_possessions`](SILVER_TABLE_REFERENCE.md#game_team_possessions) | Counted possessions and their lengths | side per game | `games`, `game_team_advanced`, `play_by_play` | `app_game_team_possessions`, `app_team_pbp_stats` |
| [`game_team_score_flow`](SILVER_TABLE_REFERENCE.md#game_team_score_flow) | Leads, runs, time ahead and behind, clutch | side per game | `games`, `play_by_play` | `app_game_team_score_flow`, `app_team_pbp_stats` |
| [`game_team_shot_splits`](SILVER_TABLE_REFERENCE.md#game_team_shot_splits) | Flagged scoring and capped assisted field goals | side per game | `games`, `shots`, `play_by_play` | `app_game_team_shot_splits`, `app_team_pbp_stats` |
| [`game_player_on_court`](SILVER_TABLE_REFERENCE.md#game_player_on_court) | Continuous on-court stretches | interval per player, side and game | `games`, `game_player_stats`, `play_by_play` | `app_game_player_on_court` |
| [`game_team_lineup_stints`](SILVER_TABLE_REFERENCE.md#game_team_lineup_stints) | Complete five-on-five stretches with points and possessions | stint per side and game | `games`, `game_player_stats`, `play_by_play` | `app_game_team_lineup_stints`, `app_player_on_off`, `app_lineup_ratings`, `app_player_rapm` |

### Load metadata

| Table | Purpose | One row | Used by Gold |
| --- | --- | --- | --- |
| [`load_log`](SILVER_TABLE_REFERENCE.md#load_log) | Successful table replacements, including zero-row loads | one replacement of a table, competition and season | Not published |

## Lineage from Bronze to Gold

| Need | Bronze → Silver → Gold |
| --- | --- |
| Schedule and results | `v2/games` → `games` (plus `game_officials`, `game_period_scores`) → `app_games` |
| Roster and career identity | people pages → `people`, `registrations` → season profiles, registrations and `app_players` |
| Official player season stats | `v3/season_stats/players_*` → four `season_player_stats_*` → four Gold tables plus calculated rows and qualification |
| Team efficiency | `v2/game_stats/*` and fixtures → team box scores and `game_team_advanced` → `app_standings_stats` |
| Player Game Score, PER, Win Shares | box scores → player and team Silver rows and per-game advanced → player round tables and game PER (PER and Win Shares are calculated in Gold) |
| Official standings | five v3 feeds → seven Silver tables → `app_standings` |
| Score flow and possessions | live events and fixtures → per-game Silver tables → Gold copies and `app_team_pbp_stats` |
| Shot maps and scoring splits | shots, events and fixtures → `game_team_shot_splits` → Gold copy and `app_team_pbp_stats` |
| Lineups, on/off, RAPM | starters, events and fixtures → on-court intervals and stints → Gold copies, lineup ratings, on/off and RAPM |

### Where Silver and Gold differ

Matching metric values do not mean identical schemas:

- Gold source projections omit `load_id` and `loaded_at`.
- Gold season player tables add `is_calculated`, `min_games`, `qualified` and the missing `perGame` rows; traditional and misc also add postseason `PS` rows. Silver keeps only the source phases and modes.
- The Gold team-season table stores actual phase totals without synthetic `all` or `PS` rows. Round tables have their own `all`/phase/`PS` scope model.
- Silver `game_player_advanced.rate_source` says whether a rate came from on-court events or a box-score estimate. Gold drops it and adds `game_uper`, `game_aper` and `game_per`.
- Gold `app_game_team_advanced` drops the opponent, phase and round columns; join the game row for them.
- The API team season feeds stay in Silver only, for comparison with calculated Gold results.

## Coverage and interpretation

### Coverage

- EuroLeague box scores and API season feeds are supported from E2000, subject to each response.
- Live events and shots begin at E2007 and still have gaps for individual games.
- Scheduled games and forfeits without complete box scores produce no calculated game rows.
- A successful HTTP request, an empty Silver table and a `NULL` rate describe different situations.

### Missing values

`NULL` means unavailable or undefined. The loader converts empty numeric markers and undefined percentages to `NULL`, stores unknown attendance as `NULL`, and marks specified all-zero box-score measures as unrecorded. It does not turn every zero into `NULL`. The original response stays in Bronze.

### Units

Source percentages keep their source scale; calculated ratios are normally fractions. Check the [glossary](STAT_GLOSSARY.md) for each measure. Raw standings record text is not a points or rebounds total.

### Play-by-play ordering and clocks

- `period` is text: `FirstQuarter`, `SecondQuarter`, `ThirdQuarter`, `ForthQuarter` (the upstream spelling) and `ExtraTime`.
- Chronological order is the period rank, then the overtime number derived from `minute`, then `event_ordinal`. Alphabetical period order and `play_number` both give wrong orders.
- `marker_time` is `NULL` on period markers (`BP`, `EP`, `EG`) and on events whose source clock contains control characters that PostgreSQL cannot store. E2026 game 100 has 19 such events (the `play_by_play_clock_unreadable` check warns). Calculated tables treat these events as having no clock.
- `person_code` in events and shots resolves to the box-score `person_key`, not necessarily the career profile's `person_code`.

## EuroCup

Checked on 2026-10-26 with read-only queries on local Silver and against [qualification.py](../gold_etl/qualification.py).

**Status.** Local only. `python pipeline.py -cp eurocup` refreshes the current season through Bronze, Silver and Gold. Nothing is published to Neon until the owner approves it.

**Coverage.** 25 seasons, U2002-U2026, with games and box scores (`data/bronze/eurocup/`). U2000 and U2001 are fetched but empty in the API. Play-by-play and shots begin at U2007. U2026 was in progress on the check date (64 of 224 games played).

### Phase codes

| Code | Meaning |
| --- | --- |
| `RS` | Regular season |
| `TS` (U2016-U2020), `L32` (U2013-U2015), `L16` (U2008-U2012) | Later group stages |
| `8F`, `4F`, `2F`, `Final` | Knockout rounds |
| `L32`, `L16` in U2007 | Two-leg knockouts, although the API marks them as groups |

`Final` can hold a final tournament (semifinals, final and third-place game), not only one final.

### Tie formats

Owner-confirmed. The full per-season table is in the [18c archive](../blueprint/history/features/18c-eurocup-postseason.md).

| Seasons | Knockout ties |
| --- | --- |
| U2002-U2015 | Two-leg aggregate in the phases listed in `TWO_LEG_PHASES`; the rest single games |
| U2016-U2018, U2020 | `4F`, `2F`, `Final` best-of-three |
| U2019 | Cancelled before the playoffs; no postseason and no champion |
| U2021-U2022 | Single games |
| U2023-U2025 | `8F`, `4F` single games; `2F`, `Final` best-of-three |
| U2026 | All knockouts best-of-three (none played yet) |

### Source quirks

| Quirk | Affected | Handling |
| --- | --- | --- |
| Drawn legs | 8 played legs in U2004, U2007, U2010, U2014 and U2015, all inside two-leg ties | The aggregate decides. Any other draw is an error (`draw_without_two_leg_tie`). |
| Cancelled games | 18 games: U2019's 12 `4F` games and 6 U2021 `RS` games (`status = cancelled`) | Left out of series and postseason totals. |
| Stat-sheet feed instead of play-by-play | 6 games: U2008 32, U2009 15, U2010 32, U2012 89, U2013 2 and 75; nearly every event sits at Q1 10:00 | Raw events stay in `play_by_play` (`play_by_play_without_clock` warns). Possessions, score flow, on-court intervals and lineup stints skip these games, and player rates use box-score estimates. Shot splits are kept because they do not depend on event order. |
| Phantom substitutions | U2026 games 10 and 18, and a few games in other seasons | On-court time and stints are kept as the feed gives them; `seconds_differ_from_box_score` and `stints_cover_little_of_the_game` flag the games. |
| Standings snapshot missing one result | U2011 VEF Riga (`L16` round 7); U2025 Hamburg (`RS` round 17) | The next round is right. `standings_played_not_won_plus_lost` flags them. Standings are not rebuilt from games, because official records can include deductions. |
| Round totals differ from the API season feeds | U2004 and U2005 (points corrections the feeds lack); U2002, U2003 and U2007 (only the API's own rate columns differ); U2026 (the feed can trail the box scores) | Expected; Gold quality prints `WARN` lines. |
| Box-score points contradict the game score | U2004 games 103 and 138, U2005 game 4 | Corrected at load and recorded as `points_corrected` in `game_stat_gaps`. |

## Provenance

Every row can be traced to the exact Bronze files it was loaded from: row → replacement in `load_log` → Bronze versions.

- Each source-table replacement writes its rows and its `load_log` entry in one transaction.
- The log keeps older load IDs after a rerun; current rows reference the latest replacement.
- `loaded_at` is the load time, not the API fetch time.
- `bronze_versions` is a sorted, deduplicated JSON array of paths relative to `data/bronze/`. It includes auxiliary reads, such as the box scores used to resolve a live player.
- Calculated tables have an empty array because they read Silver. Their log does not record which Silver loads they read.

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

## Example queries

These were checked against the declared columns, not run against a live database.

### Player game line with optional calculated detail

```sql
SELECT b.game_code, b.person_key, b.person_name, b.points, b.assists,
       a.game_score, a.usage_pct, a.rate_source
FROM silver.game_player_stats AS b
LEFT JOIN silver.game_player_advanced AS a
  USING (competition_code, season_code, game_code, side, person_key)
WHERE b.competition_code = 'E' AND b.season_code = 'E2025'
  AND b.game_code = 31;
```

### Team total rows with the club code

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

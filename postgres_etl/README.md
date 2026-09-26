# PostgreSQL loader for the bronze layer

`main.py` reads the latest version of each resource in the local bronze layer
(`data/bronze/<competition>/<season>/`, written by `api_requests`). It does
not call the EuroLeague APIs. The default output is a **column-first** set of
tables: the 25 the web app reads and the 7 local standings feeds are named
`app_*` (for example `app_games`), and the stat gaps `etl_flat_game_stat_gaps`
(see [Table names](../docs/DATA_DICTIONARY.md#table-names)).
Ordinary facts and metrics have named SQL columns;
repeated data gets child tables. JSONB is used only by the list columns of
page-shaped `app_*` tables such as `app_standings`. The complete source
responses stay in the bronze files.


## First load

From the repository root:

```powershell
python postgres_etl/main.py -sc 2025 --dry-run
python postgres_etl/main.py -sc 2025
```

The dry run requires no database connection. It checks source parsing, data
types, nullability, and primary-key uniqueness. The actual load requires
`psycopg2` (`python -m pip install psycopg2-binary`) and the settings in
`postgres_etl/config_connection.json`.

The default command creates and loads the flat tables. Replacement is
transactional and restricted to one
selected table, competition, and season. Rerunning E2025 refreshes only E2025
rows in the selected flat tables; E2026 and EuroCup rows remain separate.
Missing source files cause that table to be skipped, not emptied. The first
load after the rename to `app_*` names renames the old `etl_flat_*` tables in
place (all seasons, one transaction) and prints `Renamed local ...` lines.

## Retired tables

Tables the loader no longer creates (the `etl_flat_live_*` tables and
`etl_source_payloads`, feature 23) are dropped with:

```powershell
python postgres_etl/main.py --drop-retired --dry-run   # list them with row counts
python postgres_etl/main.py --drop-retired             # drop them
```

It drops only those named tables, all in one transaction, and a second run
reports that nothing is left. Bronze files are not touched.

## Selecting data

```powershell
python postgres_etl/main.py --list-tables
python postgres_etl/main.py -sc 2025 -tb games game_player_stats --dry-run
python postgres_etl/main.py -sc 2025 -tb games game_player_stats
python postgres_etl/main.py -sc all
python postgres_etl/main.py -sc 2020-2025 -tb games shots
python postgres_etl/main.py -cp eurocup -sc all
python postgres_etl/main.py -sc current
```

`-cp/--competition` selects `euroleague` (default) or `eurocup`.
`-sc/--season-code` accepts a year, full code, inclusive range, `current`,
`latest`, or `all`. The default is `latest` locally cached season. `all` loads
all locally cached seasons for that competition; it does not download them.
Missing requested seasons are reported and skipped. `-tb/--table` selects
names returned by `--list-tables`, without the `app_`/`etl_flat_` prefix. `all` is
the default. `--data-root` and `--config` override the default paths.

## Flat-table design

| Source | Flat tables |
| --- | --- |
| v2 seasons, clubs, people/rosters, rounds | `seasons`, `clubs`, `people`, `registrations`, `rounds` |
| v2 fixtures and game details | `games`, `game_officials`, `game_period_scores`, `game_player_stats`, `game_team_stats` |
| v3 season statistics | `season_stats_traditional`, `season_stats_advanced`, `season_stats_scoring`, `season_stats_misc` |
| v3 standings | `standings_basicstandings`, `standings_calendarstandings`, `standings_streaks`, `standings_aheadbehind`, `standings_margins`, `standings_calendar_streaks`, `standings_basic_form` |
| Live play and shooting feeds | `play_by_play`, `shots` |

The other legacy live feeds (Boxscore, Evolution, Comparison,
ShootingGraphic) are not loaded; v2 game data, play-by-play and shots cover
their content.

All flat tables have `competition_code` and `season_code` in their primary
keys. For example, `app_game_player_stats` has separate `points`,
`field_goals_made2`, `assistances`, and other statistic columns, rather than a
nested player-statistics object. V3 statistics and standings are split by
category/feed so unrelated metric columns do not become mostly NULL.
The season-stats load also adds derived postseason rows (`phase_code = 'PS'`,
Play-In + Playoffs + Final Four) to `season_stats_traditional` and
`season_stats_misc`, built from the box scores by `postseason.py`; see
`docs/DATA_DICTIONARY.md` for the rules.

Quarter and overtime scores are rows in `app_game_period_scores`.
`period_number` 1–4 denotes regulation; 5 and above denotes overtime. A game
without overtime simply has no overtime rows. Similarly, recent-form results
and calendar streaks each get their own child rows.

The v2 feed represents unplayed fixtures with placeholder `0–0` scores and
zero quarter scores. In the flat tables these fixtures still exist in
`app_games`, but their scores are SQL `NULL`, and they have no period-score
rows until played. The complete original response remains in the bronze
files.

The v2 game's `winner` object means **season champion**, not winner of that
particular game. `champion_club_code` and `match_winner_club_code` are distinct
columns. V3 percentage strings such as `"45.5%"` are stored as numeric `45.5`
(percentage points), so they can be compared and aggregated directly.

Some genuinely optional attributes (for example venue details or future-game
results) can still be NULL. Full nested source data and unusual or newly
introduced fields remain in the archive rather than being silently discarded.

## Query examples

```sql
SELECT game_code, played, local_club_code, road_club_code,
       local_score, road_score, match_winner_club_code
FROM public.app_games
WHERE season_code = 'E2025'
ORDER BY game_code;

SELECT game_code, side, period_number, score
FROM public.app_game_period_scores
WHERE season_code = 'E2025' AND period_number > 4
ORDER BY game_code, side, period_number;

SELECT game_code, person_key, points, field_goals_made2, assistances
FROM public.app_game_player_stats
WHERE season_code = 'E2025'
LIMIT 20;
```

## Code and verification

- `main.py`: CLI and local-season discovery.
- `flat_schema.py`: explicit SQL columns and source-field mappings.
- `flat_transform.py`: typed flattening and child-row expansion.
- `flat_loader.py`: transactional loading and dry-run checks.
- `quality.py`: read-only post-load checks for selected flat tables and seasons.
- `raw_transform.py`: reads bronze resources and derives keys (scores, periods, person codes).
- `shared.py`: makes the project-wide `common/` package importable from this folder.

The [data dictionary](../docs/DATA_DICTIONARY.md) documents table grains,
primary keys, required filters, and common analytical pitfalls. A normal
flat-table load automatically runs quality checks after writing. They report
empty selected tables, played/future-game result problems, and orphaned game,
club, or person references when both participating tables were selected.
Checks do not change database rows. A failed check returns a nonzero exit code
but does not roll back already committed table loads.

```powershell
python postgres_etl/main.py -sc 2025 --quality-only
python postgres_etl/main.py -sc 2025 -tb games clubs --quality-only
python postgres_etl/main.py -sc 2025 --skip-quality-check
```

`--quality-only` reads existing flat tables without loading them. It cannot
be combined with `--dry-run`. The optional
`--skip-quality-check` flag bypasses only the automatic post-load check.

```powershell
python -m unittest discover -s postgres_etl/tests -v
```

The E2025 flat schema was loaded into PostgreSQL and its read-only quality
check passed for all 33 tables and 361,356 rows. Other seasons still require
their own load and validation.

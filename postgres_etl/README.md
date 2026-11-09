# Silver loader (`postgres_etl`)

The Silver loader reads the newest version of each Bronze response and loads it into typed tables in the local PostgreSQL `silver` schema. It then calculates per-game tables from the loaded box scores and play-by-play. Silver holds source values only: Gold aggregates and postseason `PS` statistics rows are built later by [gold_etl](../gold_etl/README.md).

Related documentation:

- [Silver catalog](../docs/SILVER_CATALOG.md): what each table holds and where it comes from
- [Silver table reference](../docs/SILVER_TABLE_REFERENCE.md): every column, type and source JSON path
- [Data dictionary](../docs/DATA_DICTIONARY.md): calculation rules for the per-game tables
- [Statistics glossary](../docs/STAT_GLOSSARY.md): formulas and meaning of each statistic

## Contents

- [Running the loader](#running-the-loader)
- [Source tables](#source-tables)
- [Calculated per-game tables](#calculated-per-game-tables)
- [Load provenance](#load-provenance)
- [Quality checks](#quality-checks)
- [Example queries](#example-queries)
- [Testing](#testing)

## Running the loader

Run from the repository root. A real load needs `psycopg2` and the connection settings in `postgres_etl/config_connection.json`; a dry run needs neither.

```powershell
python postgres_etl/main.py --list-tables              # table names, no database
python postgres_etl/main.py -sc 2025 --dry-run         # parse and validate, no database
python postgres_etl/main.py -sc 2025                   # load one season
python postgres_etl/main.py -sc all                    # load every season in Bronze
python postgres_etl/main.py -sc 2025 --quality-only    # check stored rows only
```

| Option | Default | Meaning |
| --- | --- | --- |
| `-cp`, `--competition` | `euroleague` | `euroleague` or `eurocup`. |
| `-sc`, `--season-code` | `latest` | Years, full codes, inclusive ranges, `current`, `latest` or `all`, from the seasons present in Bronze. |
| `-tb`, `--table` | `all` | Tables from `--list-tables`. |
| `--dry-run` | off | Check parsing, types, required fields and duplicate keys without a database. |
| `--quality-only` | off | Run the read-only checks on stored rows without loading. |
| `--skip-quality-check` | off | Skip the checks that normally run after a load. |
| `--data-root`, `--config` | `data/`, `postgres_etl/config_connection.json` | Alternative Bronze root or connection file. |

The loader creates the `silver` schema if it is missing. The connection uses `search_path = silver`, so SQL and `-tb` use bare table names. A missing Bronze resource skips its table.

### What a load does

1. **Load source tables.** Each table and season is replaced in one transaction. If the transaction fails, both the rows and the provenance entry roll back.
2. **Calculate per-game tables.** Each calculation runs only when the load included one of its source tables (see [below](#calculated-per-game-tables)). A failed calculation check ends the run with exit code 1.
3. **Run quality checks.** If they fail, the run exits with code 1. The loaded rows are **not** rolled back; inspect the reported issues and reload.

## Source tables

`main.py` loads 26 tables:

| Source | Silver tables |
| --- | --- |
| v2 catalogue and people | `seasons`, `clubs`, `people`, `registrations`, `rounds` |
| v2 games and box scores | `games`, `game_officials`, `game_period_scores`, `game_player_stats`, `game_team_stats`, `game_stat_gaps` |
| v3 player statistics | `season_player_stats_traditional`, `season_player_stats_advanced`, `season_player_stats_scoring`, `season_player_stats_misc` |
| v3 team statistics (accumulated mode only) | `season_team_stats_traditional`, `season_team_stats_advanced` |
| v3 standings | `standings_basic`, `standings_calendar`, `standings_streaks`, `standings_ahead_behind`, `standings_margins`, `standings_calendar_streaks`, `standings_basic_form` |
| Live API | `play_by_play`, `shots` |

Every key starts with `competition_code` and `season_code`. Silver uses one name for each statistic across v2 and v3, for example `assists`, `pir`, `points`, `two_pointers_made` and `fouls_drawn`. The [data dictionary](../docs/DATA_DICTIONARY.md#standard-column-names) lists all names and their source fields.

## Calculated per-game tables

Each script derives one or two more Silver tables from the loaded data, one season at a time. `main.py` runs them automatically after a load, in the order below, when the load included one of the trigger tables. Each can also run alone with the same `-cp` and `-sc` options plus `--dry-run` (derive and count without writing) or `--quality-only` (check stored rows).

| Script | Silver table(s) | Contents | Runs after a load of |
| --- | --- | --- | --- |
| `advanced.py` | `game_team_advanced`, `game_player_advanced` | Possessions, pace, ratings, four factors, Game Score and player rates | `games`, `game_period_scores`, `game_team_stats`, `game_player_stats`, `game_stat_gaps`, `play_by_play` |
| `possessions.py` | `game_team_possessions` | Possessions counted from play-by-play events | `games`, `play_by_play` |
| `score_flow.py` | `game_team_score_flow` | Lead changes, ties, time leading and trailing, largest lead, scoring runs, clutch results | `games`, `play_by_play` |
| `on_court.py` | `game_player_on_court` | Each player's continuous stretches on the floor | `games`, `game_player_stats`, `play_by_play` |
| `lineups.py` | `game_team_lineup_stints` | Stretches with the same ten players on court, with possessions and points per team | `games`, `game_player_stats`, `play_by_play` |
| `shot_splits.py` | `game_team_shot_splits` | Fast-break, second-chance and off-turnover points; assisted field goals | `games`, `play_by_play`, `shots` |

```powershell
python postgres_etl/advanced.py -sc 2025 --dry-run
python postgres_etl/possessions.py -sc 2025 --dry-run
```

Notes on the calculations:

- **Player rates in `advanced.py`.** Usage, assist, rebound, steal and block percentages count the play-by-play events that happened while the player was on court (`on_court_rates.py`). Where a game has no play-by-play, they fall back to the box-score estimate with a 3-minute floor. The `rate_source` column records which method was used.
- **Play-by-play tables start at E2007.** Earlier games have no play-by-play, so `possessions.py`, `score_flow.py`, `on_court.py`, `lineups.py` and `shot_splits.py` produce no rows for them.
- **Shared code.** `score_flow.py` reuses the event ordering, clock and storage code of `possessions.py`. `lineups.py` uses the same substitution walk as `on_court.py`, which rebuilds stretches from the box-score starters and the `IN`/`OUT` events.
- **Retired table.** The official per-game shot zone table is no longer built; the web app derives its zones from `app_shots`.

The calculation rules for each table are in the [data dictionary](../docs/DATA_DICTIONARY.md#derived-per-game-advanced-tables).

## Load provenance

Every row can be traced to the exact Bronze files it came from:

- Every inserted row gets the load's UUID `load_id` and the UTC `loaded_at` timestamp.
- Each replacement of a table, competition and season appends one row to `silver.load_log` in the same transaction, even when it inserts zero rows. The log records `row_count` and `bronze_versions`, a sorted JSON array of Bronze file paths relative to `data/bronze/`.
- Reruns keep earlier log entries; current rows point to the newest load.
- Calculated tables also write a `load_log` entry, with an empty `bronze_versions` because their source is Silver.

The [Silver catalog](../docs/SILVER_CATALOG.md#provenance) has a query that traces rows back to their Bronze files.

## Quality checks

The checks run after every real load (unless `--skip-quality-check`) and with `--quality-only`. They report:

- source gaps, orphan rows and missing statistics feeds
- invalid fields on played games and other recorded anomalies
- rows without `load_id` or `loaded_at`, rows without a matching `load_log` entry, and row counts that differ from the log

## Example queries

One season's player box scores:

```sql
SELECT game_code, person_key, points, two_pointers_made, assists
FROM silver.game_player_stats
WHERE competition_code = 'E' AND season_code = 'E2025'
LIMIT 20;
```

More examples are in the [Silver catalog](../docs/SILVER_CATALOG.md#example-queries).

## Testing

```powershell
python -m unittest discover -s postgres_etl/tests
```

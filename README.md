# EuroleagueDataETL

Python 3.13 and PostgreSQL pipeline for EuroLeague and EuroCup data. The fetcher
stores exact versioned API responses in bronze. The loader builds 28 typed
tables in the local `silver` schema and runs quality checks, then derives two
per-game advanced tables (team and player) from the box scores. The local Gold
stage copies 16 source tables from Silver into `gold` and derives postseason
player stats, a page-shaped standings table, team-season totals, coverage,
all-time records and postseason series, plus cross-season player and club
identities. The in-place Neon schema cutover and first E2026 publish completed
on 2026-09-28 with owner approval and web-app coordination.

Each silver row has a `load_id` and UTC `loaded_at`. The append-only
`silver.load_log` records each table and season replacement, its row count,
and the exact bronze file versions read for that load.

## Refresh

Run from the repository root:

```powershell
python pipeline.py
python pipeline.py --skip-fetch
```

The first command fetches, loads Silver, builds and checks Gold, then publishes
to Neon. `--skip-fetch` uses cached bronze responses. Each run ends with a
summary and writes a log under `logs/refresh/`. `--dry-run-publish` performs
the local stages and a read-only Neon preview, retaining pending state. A failed
publish leaves the prior Neon rows visible and the pending state ready for retry.
New live publishing still requires the owner's explicit approval.

The loader needs `postgres_etl/config_connection.json` (copy the example,
then set your local PostgreSQL credentials). A dry run needs no database:

```powershell
python postgres_etl/main.py --list-tables
python postgres_etl/main.py -sc 2025 --dry-run
python postgres_etl/main.py -sc 2025
python postgres_etl/main.py -sc all
python postgres_etl/advanced.py -sc all --dry-run
python postgres_etl/possessions.py -sc 2007-2026 --dry-run
python postgres_etl/score_flow.py -sc 2007-2026 --dry-run
python postgres_etl/shot_splits.py -sc 2007-2026 --dry-run
python postgres_etl/shot_zones.py -sc 2007-2026 --dry-run
python postgres_etl/on_court.py -sc 2007-2026 --dry-run
python postgres_etl/lineups.py -sc 2007-2026 --dry-run
```

Build or inspect local Gold from already loaded Silver rows:

```powershell
python gold_etl/main.py --list-tables
python gold_etl/main.py -sc E2025 --dry-run
python gold_etl/main.py -sc all
python gold_etl/main.py -sc all --quality-only
python gold_etl/main.py -sc E2025 -tb app_records_player_seasons app_records_single_games app_records_team_seasons app_postseason_series
python gold_etl/main.py -sc all -tb app_players app_club_identities
python gold_etl/main.py -sc all -tb team_round_stats team_round_ratings team_round_splits player_round_stats player_round_ratings player_round_win_shares app_standings_stats team_pbp_stats team_shot_zone_stats player_on_off
```

The dry run and quality check read the local database without changing Gold.
The load replaces each season-scoped table slice in one transaction. Record
leaderboards use every loaded EuroLeague season and replace the selected table
once per run, regardless of `-sc`. The two identity tables likewise use all
loaded seasons of the selected competition. Selecting
traditional or misc player season stats also rebuilds their derived `PS` rows;
`-tb app_standings` builds only the standings page table. Select
`app_team_season_stats`, `app_coverage_seasons` or `app_coverage_games` to
build those derived tables alone. The Gold CLI does not fetch
data or publish to Neon. Use `-cp` for the competition and `-tb` for selected
table names.

Publish preview: `python neon_publish/main.py -sc E2025 --dry-run`.
See the [publisher guide](neon_publish/README.md) for all 26 targets, the
one-time migration, the 90% shrink guard, and live cutover approval.

## Layout

| Path | Purpose |
| --- | --- |
| [api_requests/](api_requests/README.md) | Fetch API responses into versioned bronze files. |
| [postgres_etl/](postgres_etl/README.md) | Load and check the local silver tables. |
| [gold_etl/](gold_etl/README.md) | Build and check local Gold source and derived tables. |
| [neon_publish/](neon_publish/README.md) | Gold-to-Neon preflight and guarded atomic publisher. |
| [tables_to_csv/](tables_to_csv/README.md) | Export silver tables to CSV. |
| [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) | Silver, Gold, and Neon app-table contracts. |
| `data/bronze/` | Exact source responses; the loader's only input. |
| `data/state/` | Refresh bookkeeping. |
| `logs/` | Per-run logs. |

## Tests

```powershell
cd api_requests; python -m unittest tests.test_scrapper; cd ..
python -m unittest discover -s postgres_etl/tests
python -m unittest discover -s gold_etl/tests
python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export
```

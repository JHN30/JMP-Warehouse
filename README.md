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
python gold_etl/main.py -sc all -tb team_round_stats team_round_ratings team_round_splits player_round_stats player_round_ratings player_round_win_shares app_standings_stats team_pbp_stats team_shot_zone_stats player_on_off lineup_ratings player_rapm
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
See the [publisher guide](neon_publish/README.md) for all 38 targets, the
one-time migration, the 90% shrink guard, and live cutover approval.

## Running everything

The commands below build every layer from scratch for EuroLeague (`-cp euroleague`
is the default), in order. Run them from the repository root.

**Setup, once.** Install `psycopg2`, `numpy` and `pandas` in Python 3.13 (numpy is
used only by the RAPM table). Copy `postgres_etl/config_connection.example.json` to
`postgres_etl/config_connection.json` and set the local PostgreSQL credentials. Put
the direct, non-pooled `NEON_DATABASE_URL` in `.env`; only the publish steps need it.

```powershell
# 1. Fetch API responses into bronze (exact, versioned).
python api_requests/main.py -sc 2000-2026

# 2. Load Silver: 28 typed tables plus quality checks. A load that includes the
#    game, box-score or play-by-play tables also rebuilds the derived Silver tables.
python postgres_etl/main.py -sc all

# 3. Optional: rebuild one derived Silver table on its own, in this order
#    (lineups needs possessions; on_court and lineups need E2007+ play-by-play).
python postgres_etl/advanced.py -sc all                  # per-game team and player advanced stats
python postgres_etl/possessions.py -sc 2007-2026         # counted possessions per team and game
python postgres_etl/score_flow.py -sc 2007-2026          # lead changes, time leading, runs, clutch
python postgres_etl/shot_splits.py -sc 2007-2026         # fast-break, second-chance, off-turnover points
python postgres_etl/shot_zones.py -sc 2007-2026          # attempts and makes per shot zone
python postgres_etl/on_court.py -sc 2007-2026            # each player's on-court stretches
python postgres_etl/lineups.py -sc 2007-2026             # five-man stints with possessions and points

# 4. Build Gold from Silver: 16 source tables, the derived app tables and every
#    local-only table (round stats, ratings, Win Shares, play-by-play aggregates,
#    on/off, lineup ratings, RAPM).
python gold_etl/main.py -sc all

# 5. Check everything without changing data. Expect "Gold quality: passed";
#    WARN lines are documented gaps in docs/DATA_DICTIONARY.md.
python postgres_etl/main.py -sc all --quality-only
python gold_etl/main.py -sc all --quality-only

# 6. Run the test suites (see Tests below).

# 7. Preview a Neon publish. Read-only.
python neon_publish/main.py --list-tables
python neon_publish/main.py -sc E2026 --dry-run

# 8. Publish one season to Neon. Only with the owner's explicit approval.
python neon_publish/main.py -sc E2026

# 9. Optional: export every silver and gold table to CSV (one file per table,
#    data/csv_export/euroleague/) for import into SSMS.
python tables_to_csv/main.py
```

The 38 tables listed by `--list-tables` reach Neon (the 12 added in 30g need the
reviewed one-time migration from `--print-migration` first, applied only with the owner's
approval). The Silver-derived tables (possessions, stints and so on) stay local.
For the current season, `python pipeline.py --dry-run-publish` runs fetch, load,
Gold and checks and previews the publish; plain `python pipeline.py` also
publishes to Neon.

## Layout

| Path | Purpose |
| --- | --- |
| [api_requests/](api_requests/README.md) | Fetch API responses into versioned bronze files. |
| [postgres_etl/](postgres_etl/README.md) | Load and check the local silver tables. |
| [gold_etl/](gold_etl/README.md) | Build and check local Gold source and derived tables. |
| [neon_publish/](neon_publish/README.md) | Gold-to-Neon preflight and guarded atomic publisher. |
| [tables_to_csv/](tables_to_csv/README.md) | Export every silver and gold table to one CSV file each, for SSMS. |
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

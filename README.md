# JMP Warehouse

**JMP Warehouse** is the data pipeline behind [JMP EuroLeague](https://www.jmpeuroleague.com/). It downloads EuroLeague API data, keeps the original responses, loads clean tables into a local PostgreSQL database, calculates advanced basketball statistics, and publishes the tables the web app reads to Neon.

The local database and CSV exports also serve historical analysis and the separate [JMP Rating](https://github.com/JHN30/JMP-Rating) project.

## Contents

- [Why it exists](#why-it-exists)
- [How the pipeline works](#how-the-pipeline-works)
- [Quick start](#quick-start)
- [Everyday commands](#everyday-commands)
- [Scheduled refresh](#scheduled-refresh)
- [Configuration](#configuration)
- [Testing](#testing)
- [Project layout](#project-layout)
- [Documentation map](#documentation-map)
- [Contributing](#contributing)

## Why it exists

EuroLeague data is spread across several APIs. Some endpoints overlap, some update late, and historical records have gaps or inconsistent identifiers. Keeping every original response makes it possible to trace a number back to its source and to rebuild the database without downloading everything again.

The pipeline also goes beyond the statistics the API supplies. Box scores, play-by-play, shots and substitutions are enough to calculate advanced player and team statistics, reconstruct lineups, and follow how performance changes through a season. Each statistic is calculated once, here, so the app and private analysis read the same numbers.

## How the pipeline works

```mermaid
flowchart LR
    API[EuroLeague APIs] --> B[Bronze<br/>exact responses]
    B --> S[Silver<br/>local PostgreSQL]
    S --> G[Gold<br/>local PostgreSQL]
    G --> N[Neon<br/>public schema]
    N --> APP[Web app]
    S --> CSV[CSV export]
    G --> CSV
```

| Layer | Where | Contents |
| --- | --- | --- |
| **Bronze** | `data/bronze/` | Exact API responses, gzipped and versioned, with request manifests. A new version is stored only when a response changes. |
| **Silver** | local schema `silver` | 26 typed source tables with consistent column names and load provenance, plus calculated per-game tables (advanced box-score stats, counted possessions, score flow, shot splits, on-court intervals, lineup stints). |
| **Gold** | local schema `gold` | 40 `app_*` tables built from Silver: source projections, standings, team-season totals, records, postseason series, player and club identities, and advanced statistics. |
| **Neon** | Neon schema `public` | The same 40 `app_*` tables, published one season at a time for the web app. |

The main capabilities are:

- **Refreshing the current season.** Changing data such as standings and season statistics is re-fetched for 48 hours after each game. Older, less complete answers from the API never replace a better stored version.
- **Advanced statistics.** Possessions, pace, ratings, four factors, Game Score, PIE, PER, Win Shares, strength-adjusted team ratings, and home/away and recent-form splits.
- **Play-by-play analytics.** Counted possessions, score flow and clutch results, shot splits, on-court intervals, lineup stints, on/off ratings, 2/3/5-man lineup ratings and RAPM.
- **Guarded publishing.** 40 fixed Gold-to-Neon mappings with schema, quality, row-count and shrink checks. All selected scopes commit in one transaction, and a failure rolls everything back.
- **CSV export.** Every Silver and Gold table as one CSV file, ready for SQL Server Management Studio.

### Key concepts

- **Season codes** start with the competition letter and the starting year: `E2025` is the 2025-26 EuroLeague season, `U2025` the same EuroCup season.
- **Coverage.** Local history and Neon both cover E2000 onward. Play-by-play, shot and lineup tables start at E2007, because the live API has no earlier data.
- **EuroCup** is built locally (Silver and Gold, postseason included) and is not published to Neon.
- **Missing values stay `NULL`.** Known gaps and source inconsistencies are reported by the quality checks instead of being filled with zero.
- **Two kinds of possessions.** Box-score estimates and possessions counted from play-by-play are stored separately.
- **Ranking qualification.** Player season statistics include calculated per-game rows where the API has none, a minimum-games threshold, and a `qualified` flag.

## Quick start

This builds one season in a local database. No Neon access is needed.

### Prerequisites

- Python 3.13
- PostgreSQL (developed with PostgreSQL 18 on Windows)
- PowerShell; all commands run from the repository root

### 1. Install

```powershell
git clone https://github.com/JHN30/JMP-Warehouse.git
cd JMP-Warehouse

python -m venv .venv
.\.venv\Scripts\Activate.ps1

# There is no dependency file yet. NumPy is needed only for RAPM.
python -m pip install requests psycopg2-binary numpy

Copy-Item postgres_etl/config_connection.example.json postgres_etl/config_connection.json
```

Create the database named in the configuration, then edit `postgres_etl/config_connection.json` with your connection settings (see [Configuration](#configuration)). The loaders create their own schemas and tables.

### 2. Build a season

```powershell
# Fetch API responses into Bronze (the fetcher takes start years, not codes)
python api_requests/main.py -sc 2025

# Validate the cached responses without a database
python postgres_etl/main.py -sc E2025 --dry-run

# Load Silver, including the calculated per-game tables
python postgres_etl/main.py -sc E2025

# Build Gold
python gold_etl/main.py -sc E2025
```

The first fetch of a full season takes a while: requests are spaced 2.5 seconds apart. Reruns reuse cached responses and resume interrupted downloads.

### 3. Verify

```powershell
python gold_etl/main.py -sc E2025 --quality-only
```

The check compares Gold with Silver, prints any problems, and ends with `Gold quality: passed` (exit code 0) or `Gold quality: failed` (exit code 1).

## Everyday commands

`pipeline.py` chains the stages: **Fetch → Load Silver → Build Gold → Check Gold → Publish**. Each run writes a log to `logs/refresh/refresh_<YYYYMMDD_HHMMSS>.log` and ends with a summary. When the fetch found nothing new and no publish is pending, it stops after the fetch.

### Local only

These commands never connect to Neon.

| Command | What it does |
| --- | --- |
| `python pipeline.py -cp eurocup` | Refreshes the current EuroCup season and ends with `OK (local only)`. |
| `python pipeline.py --all` | Fetches 2000 through the current season, reloads all Silver, rebuilds all Gold and checks it. |
| `python pipeline.py --all --skip-fetch` | Same as `--all`, using existing Bronze files only. |
| `python postgres_etl/main.py -sc E2025 --quality-only` | Checks stored Silver rows. |
| `python gold_etl/main.py -sc all --dry-run` | Shows Gold source and derived row counts without writing. |
| `python gold_etl/main.py -sc all --quality-only` | Checks every Gold table against Silver. |
| `python gold_etl/main.py -sc E2025 -tb app_standings_stats` | Rebuilds selected Gold tables. |
| `python tables_to_csv/main.py` | Exports every local table to CSV (`--dry-run` counts rows only). |

The two `--all` modes always rebuild, even when the fetch changed nothing, and leave the current-season publish pending for the next `python pipeline.py`. They reject `-sc`, `--dry-run-publish` and `--allow-shrink`. Both are also available as VS Code tasks.

### Neon preview (read-only on Neon)

| Command | What it does |
| --- | --- |
| `python pipeline.py --dry-run-publish` | Runs the full refresh locally, then previews the Neon changes. Publishing stays pending. |
| `python neon_publish/main.py --list-tables` | Lists the 40 Gold-to-Neon mappings. No database connection. |
| `python neon_publish/main.py -sc E2025 --dry-run` | Compares local and Neon row counts and schemas for one season. |

`--dry-run-publish` still fetches and writes local Silver and Gold. Only the Neon stage is read-only.

### Live publish

> [!WARNING]
> These commands write to the production Neon database that the web app reads. Run them only with the owner's explicit approval.

| Command | What it does |
| --- | --- |
| `python pipeline.py` | Refreshes the current EuroLeague season and publishes it to Neon. |
| `python neon_publish/main.py -sc E2026` | Publishes one season plus the competition-wide tables. |

A failed publish rolls back and leaves the previous Neon data in place. See [neon_publish/README.md](neon_publish/README.md) for the guards and options.

### Other `pipeline.py` options

| Option | Effect |
| --- | --- |
| `-sc 2025` / `-sc E2025` | Refresh a season other than the current one. |
| `--force` | Load and build even when the fetch changed nothing. |
| `--skip-fetch` | Use the existing Bronze files; implies `--force`. |
| `--allow-shrink` | Allow a Neon scope to shrink below 90% of its current rows. |
| `--hot-hours`, `--request-interval` | Passed to the fetcher; see [api_requests/README.md](api_requests/README.md#refreshing-the-current-season). |

Individual stages accept season codes, years, ranges such as `2000-2025`, and `current`, `latest` or `all`. The Neon publisher takes one season per run. Each stage README lists its exact options.

## Scheduled refresh

A Windows Task Scheduler task named `JMP Warehouse refresh` runs `python pipeline.py` every day at 06:00.

> [!WARNING]
> Every scheduled run publishes the current season to Neon. Registering the task is the owner's standing approval for that daily publish; removing it withdraws the approval.

```powershell
# Register the task, or update it after Python or the folder moves
powershell -ExecutionPolicy Bypass -File register_refresh_task.ps1

# Last run time, last result and next run time
Get-ScheduledTaskInfo -TaskName "JMP Warehouse refresh"

# Run it now (a live Neon publish)
Start-ScheduledTask -TaskName "JMP Warehouse refresh"

# Remove the task
powershell -ExecutionPolicy Bypass -File register_refresh_task.ps1 -Remove
```

How the task behaves:

- It runs hidden, only while the owner is logged on, with no stored password or admin rights.
- It uses the Python found on `PATH` at registration time and runs from the repository folder, so it reads `.env` and `postgres_etl/config_connection.json` like a manual run.
- If the computer was off or asleep at 06:00, it runs as soon as possible afterwards. It also runs on battery.
- It is stopped after 2 hours. A failed run is not retried the same day; the next day's run picks up all changes and retries any pending publish.
- If `NEON_DATABASE_URL` is missing, the run fails at the publish stage instead of waiting for input.

### Reading the last result

| Last result | Meaning | What to do |
| --- | --- | --- |
| `0` | Success | Nothing. |
| `1` (or another number) | The pipeline failed | Read the newest log in `logs/refresh/`. If no new log was written, check that the registered Python still exists and register the task again. |
| `0x41301` | Still running | Wait. |
| `0x41306` | Stopped at the 2-hour limit | Read the log for the slow stage. |

## Configuration

### Local PostgreSQL

`postgres_etl/config_connection.json`, copied from the committed [example](postgres_etl/config_connection.example.json):

```json
{
  "database": "jmp_euroleague",
  "user": "postgres",
  "password": "<your local PostgreSQL password>",
  "host": "localhost",
  "port": "5432"
}
```

### Neon

Only previews and publishing need Neon. Set `NEON_DATABASE_URL` in the environment or in a `.env` file at the repository root. Use a direct, non-pooled connection:

```dotenv
NEON_DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require
```

Both credential files are ignored by Git. The publisher checks the Neon schema before every publish but never runs migrations; applying one needs the owner's approval. See [neon_publish/README.md](neon_publish/README.md#schema-migrations).

## Testing

Unit tests use fixtures, fake API clients and fake database cursors. They do not call the real APIs or databases.

```powershell
# API extraction
Push-Location api_requests
python -m unittest tests.test_scrapper
Pop-Location

# Silver and Gold
python -m unittest discover -s postgres_etl/tests
python -m unittest discover -s gold_etl/tests

# Publishing and CSV export
python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export
```

There is no build, lint, format, typecheck or combined verify command yet. For data checks, use the `--dry-run` and `--quality-only` options of each stage.

## Project layout

| Path | Purpose |
| --- | --- |
| [pipeline.py](pipeline.py) | Current-season refresh and full local history rebuild |
| [register_refresh_task.ps1](register_refresh_task.ps1) | Registers or removes the daily 06:00 refresh task |
| [api_requests/](api_requests/README.md) | API extraction into Bronze, caching and refresh rules |
| [postgres_etl/](postgres_etl/README.md) | Silver loading, provenance, per-game calculations and quality checks |
| [gold_etl/](gold_etl/README.md) | Gold projections, aggregates and advanced statistics |
| [neon_publish/](neon_publish/README.md) | Guarded publishing to Neon and reviewed migrations |
| [tables_to_csv/](tables_to_csv/README.md) | CSV export of local tables |
| `common/` | Shared Bronze, database and season helpers |
| `docs/` | Data catalogs, column references and the statistics glossary |
| `blueprint/` | Project plans, workflow context and completed-work history |
| `data/`, `logs/` | Local data and run output, ignored by Git |

**Tech stack:** Python 3.13 with Requests, psycopg2-binary and NumPy (RAPM ridge regression); the standard library for compression, JSON, CSV and the command line; PostgreSQL 18 locally and Neon PostgreSQL for the app. The web app lives in a separate repository.

## Documentation map

| Read this | When you want to |
| --- | --- |
| [Gold data catalog](docs/DATA_CATALOG.md) | Find the Gold table behind a page or feature, and how to join it |
| [Gold table reference](docs/GOLD_TABLE_REFERENCE.md) | Look up any Gold column: type, nullability, key and meaning |
| [Statistics glossary](docs/STAT_GLOSSARY.md) | Understand a player or team statistic, its formula and its source |
| [Data dictionary](docs/DATA_DICTIONARY.md) | Read the calculation rules, the Neon contract and the post-load checks |
| [Silver catalog](docs/SILVER_CATALOG.md) | See what each Silver table holds and where it comes from |
| [Silver table reference](docs/SILVER_TABLE_REFERENCE.md) | Look up any Silver column and its source JSON path |
| [Bronze catalog](docs/BRONZE_CATALOG.md) | Trace a value back to the exact API response |

## Contributing

Contributions are welcome, especially to extraction, data quality, statistical formulas, documentation and tests. Useful starting points:

- Review transformation rules and advanced-stat formulas.
- Add regression tests for API quirks and historical edge cases.
- Report missing data, incorrect values or ideas through issues.

You can build and analyse the full local database with your own PostgreSQL; Bronze files, credentials and run output are not in the repository, and Neon access is not needed.

To submit a change:

1. Fork the repository and create a feature branch.
2. Read [AGENTS.md](AGENTS.md) and the [coding standards](blueprint/context/coding-standards.md).
3. Update the relevant tests, stage README and `docs/` pages with the code.
4. Open a pull request to `main`.

Planned and completed work is tracked in [blueprint/build-plan.md](blueprint/build-plan.md) and [blueprint/history/](blueprint/history/). JMP Rating, win probabilities and predictions belong to the separate [JMP Rating](https://github.com/JHN30/JMP-Rating) project.

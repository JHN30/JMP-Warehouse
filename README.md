# EuroleagueDataETL

Python + PostgreSQL pipeline that downloads EuroLeague and EuroCup data, loads
it into a local PostgreSQL database, and publishes the web-app tables to Neon.

```
API ──fetch──▶ data/bronze (exact responses) ──load──▶ local PostgreSQL ──publish──▶ Neon
   api_requests/                          postgres_etl/                neon_publish/
                                                       └──export──▶ CSV (tables_to_csv/)
```

## Run a refresh

Open the project in VS Code, then in its terminal (Terminal > New Terminal):

```powershell
python pipeline.py                     # refresh the current season: fetch, load, checks, publish
python pipeline.py --dry-run-publish   # the same, but Neon is only compared, never written
```

Or without typing: **Terminal > Run Task... > "Refresh current season"** (or
"Refresh current season (dry run)"). Both run the same command in the terminal.

- **Neon URL:** if the `NEON_DATABASE_URL` environment variable is set, it is
  used. Otherwise the command asks for it with hidden input, only when it is
  about to publish, and forgets it after the run. To set it once for your
  Windows user: Start menu > "Edit environment variables for your account" >
  New, name `NEON_DATABASE_URL`, value = the direct (non-pooled) Neon URL, then
  restart VS Code. (Avoid typing it into a terminal command: PowerShell keeps a
  plain-text command history.)
- **What you see:** the live output of every step, then a summary: the result
  (`OK`, `NOTHING TO DO`, `OK (dry run)`, or `FAILED at <step>` with what to do
  next), what the download changed, rows loaded with quality errors and
  warnings, and each Neon table's rows before -> after.
- **Log:** every run is saved to `logs/refresh/refresh_<date>_<time>.log`.
- **Options:** `-sc 2025` (another season), `--allow-shrink` (only after
  checking why a table would lose rows), `--force` (load and publish even if
  nothing changed), `--skip-fetch` (use the files already downloaded),
  `--help` for all.
- When nothing new was downloaded and nothing is waiting to be published, the
  run stops after the download and leaves Neon alone. A failed load or publish
  stays pending and is retried by the next run.

## Layout

| Path | What it is |
| --- | --- |
| [pipeline.py](pipeline.py) | Scheduled refresh: fetch → load (with quality checks) → publish. Stops after the fetch when nothing changed. |
| [api_requests/](api_requests/README.md) | **Fetch.** Rate-limited downloader for the v2/v3 APIs plus live play-by-play and shots. Writes to `data/bronze/`. |
| [postgres_etl/](postgres_etl/README.md) | **Load.** Turns bronze into typed tables in local PostgreSQL (`app_*` for the 24 web-app tables, `etl_flat_*` for the rest) and runs quality checks. |
| [neon_publish/](neon_publish/README.md) | **Publish.** Replaces seasons of the 24 `app_*` web-app tables in Neon (play-by-play and shots game by game), one transaction per season. |
| [tables_to_csv/](tables_to_csv/README.md) | **Export.** Local PostgreSQL tables → one CSV per season and table (e.g. for MSSQL analysis). |
| `common/` | Code shared by all stages: the bronze store, database connection, season-code helpers. |
| [docs/](docs/) | [Data dictionary](docs/DATA_DICTIONARY.md), [pipeline plan and status](docs/PIPELINE-ANALYSIS.md), and the original [handoff](docs/PIPELINE-HANDOFF.md) from the web-app repo. |
| `data/` | Local data, not code (see below). |
| `logs/` | One folder per tool with a log file per run. |
| [old/](old/README.md) | Code, logs and data retired in the 2026-09-24 cleanup, kept until you decide what to keep. Nothing reads it. |

### data/

- `bronze/<competition>/<season>/`: exact, gzipped, versioned API responses plus
  a request manifest. This is the only input of `postgres_etl`.
- `state/`: `pipeline.py` bookkeeping (pending publishes).
- `<competition>_csv/`: CSV exports created by `tables_to_csv`.

## Configuration

- Local PostgreSQL: `postgres_etl/config_connection.json` (database, user,
  password, host, port). It holds a password, so keep it out of version control
  (it is listed in `.gitignore`).
- Neon: the `NEON_DATABASE_URL` environment variable (direct, non-pooled URL).
  It is never written to a file.

## Tests

```powershell
cd api_requests; python -m unittest tests.test_scrapper; cd ..
python -m unittest discover -s postgres_etl/tests
python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export
```

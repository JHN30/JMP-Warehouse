# EuroleagueDataETL

Python + PostgreSQL pipeline that downloads EuroLeague and EuroCup data, loads
it into a local PostgreSQL database, and publishes the web-app tables to Neon.

```
API ──fetch──▶ data/bronze (exact responses) ──load──▶ local PostgreSQL ──publish──▶ Neon
   api_requests/                          postgres_etl/                neon_publish/
                                                       └──export──▶ CSV (tables_to_csv/)
```

One command runs the whole refresh for the current season:

```powershell
python pipeline.py            # needs the NEON_DATABASE_URL environment variable
```

## Layout

| Path | What it is |
| --- | --- |
| [pipeline.py](pipeline.py) | Scheduled refresh: fetch → load (with quality checks) → publish. Stops after the fetch when nothing changed. |
| [api_requests/](api_requests/README.md) | **Fetch.** Rate-limited downloader for the v2/v3 APIs plus live play-by-play and shots. Writes to `data/bronze/`. |
| [postgres_etl/](postgres_etl/README.md) | **Load.** Turns bronze into typed `etl_flat_*` tables in local PostgreSQL and runs quality checks. |
| [neon_publish/](neon_publish/README.md) | **Publish.** Replaces seasons of the 22 web-app tables in Neon, one transaction per season. |
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

# EuroleagueDataETL

Python 3.13 and PostgreSQL pipeline for EuroLeague and EuroCup data. The fetcher
stores exact versioned API responses in bronze. The loader builds 28 typed
tables in the local `silver` schema and runs quality checks. Neon publishing is
paused until feature 30 builds the gold layer. The web app continues reading
its existing Neon data during the pause.

Each silver row has a `load_id` and UTC `loaded_at`. The append-only
`silver.load_log` records each table and season replacement, its row count,
and the exact bronze file versions read for that load.

## Refresh

Run from the repository root:

```powershell
python pipeline.py
python pipeline.py --skip-fetch
```

The first command fetches and loads the current season. `--skip-fetch` loads
cached bronze responses. Each run ends with a summary and writes a log under
`logs/refresh/`. The summary says
`Publish:  paused (no gold tables until feature 30)`. The existing
`--dry-run-publish` option and VS Code task remain accepted while publishing
is paused; they do not connect to Neon.

The loader needs `postgres_etl/config_connection.json` (copy the example,
then set your local PostgreSQL credentials). A dry run needs no database:

```powershell
python postgres_etl/main.py --list-tables
python postgres_etl/main.py -sc 2025 --dry-run
python postgres_etl/main.py -sc 2025
python postgres_etl/main.py -sc all
```

## Layout

| Path | Purpose |
| --- | --- |
| [api_requests/](api_requests/README.md) | Fetch API responses into versioned bronze files. |
| [postgres_etl/](postgres_etl/README.md) | Load and check the local silver tables. |
| [neon_publish/](neon_publish/README.md) | Paused publisher; season transaction engine retained for feature 30. |
| [tables_to_csv/](tables_to_csv/README.md) | Export silver tables to CSV. |
| [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) | Silver table names, keys, columns, and historical gold reference. |
| `data/bronze/` | Exact source responses; the loader's only input. |
| `data/state/` | Refresh bookkeeping. |
| `logs/` | Per-run logs. |

## Tests

```powershell
cd api_requests; python -m unittest tests.test_scrapper; cd ..
python -m unittest discover -s postgres_etl/tests
python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export
```

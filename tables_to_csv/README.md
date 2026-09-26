# PostgreSQL tables to CSV

This tool exports the **current column-first PostgreSQL ETL tables**. It reads
the database; it does not call the EuroLeague APIs or change database rows.
Run it after loading data with `postgres_etl/main.py`.

The default export covers every available `app_*` and `etl_flat_*` table.
Table names come from
`postgres_etl/flat_schema.py`, so they stay aligned with the loader. The
previous seven `euroleague_header`/`euroleague_box_score`-style tables are not
used by this command.

## Run from the repository root

```powershell
python tables_to_csv/main.py --list-tables
python tables_to_csv/main.py -sc 2025 --dry-run
python tables_to_csv/main.py -sc 2025
```

`--dry-run` connects to PostgreSQL and counts rows but writes no CSV files.
To test only a couple of tables first:

```powershell
python tables_to_csv/main.py -sc 2025 -tb games clubs
```

Other selections:

```powershell
python tables_to_csv/main.py -sc all
python tables_to_csv/main.py -sc 2020-2025 -tb games shots
python tables_to_csv/main.py -cp eurocup -sc all
python tables_to_csv/main.py -sc current -tb games game_player_stats
```

`-cp/--competition` defaults to `euroleague`; `eurocup` is also accepted.
`-sc/--season-code` accepts a year (`2025`), full code (`E2025` or `U2025`),
inclusive range, `current`, `latest`, or `all`. The default is `latest` **in
the database**, not the newest season in the raw JSON cache. `current` uses
the same September season boundary as `postgres_etl`. `-tb/--table` accepts
logical names from `--list-tables`, without the `app_`/`etl_flat_` prefix. It defaults
to all flat tables that exist in the connected database. Missing explicitly
selected tables are an error; missing tables in an `all` run are reported and
skipped. Seasons not yet loaded into the selected tables are also reported and
skipped. If no requested season is available, the command fails.

`--config` selects a connection JSON file (default:
`postgres_etl/config_connection.json`). `--output-root` selects the parent
output directory (default: repository `data/`). The exporter uses the same
PostgreSQL search path as the connection and sets the session to read-only.

## Output

Files are separated by competition and season, for example:

```text
data/euroleague_csv/E2025/app_games.csv
data/euroleague_csv/E2025/app_game_player_stats.csv
data/euroleague_csv/E2025/app_play_by_play.csv
data/euroleague_csv/E2025/etl_flat_game_stat_gaps.csv
```

Files take the table's name, so the web-app tables export as `app_*.csv` since
their rename. Earlier exports named `etl_flat_games.csv` and so on are not
removed.

Each file contains all database columns, a header row, and only rows matching
its competition and season. Rows are ordered by the table's primary key. A
selected table with zero rows for that season produces a header-only CSV.
Rerunning a table replaces only its corresponding CSV, leaving other season
files untouched. A temporary file is used so a failed export does not replace
an existing completed CSV.

PostgreSQL streams the CSV directly to disk, avoiding a large pandas DataFrame
for tables such as play-by-play. CSV is a text format: PostgreSQL NULL becomes an empty
field, while a real empty string is quoted.

Progress, per-table row counts, and elapsed times are printed to the console
and saved under `logs/tables_to_csv/`. The final report shows the total
number of exported rows and output root. The database is never written by this
tool, but a CSV export can reflect a different snapshot than a later run if
the database has been refreshed in between.

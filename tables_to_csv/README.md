# PostgreSQL tables to CSV

This tool exports **every table in the local `silver` and `gold` schemas** as one
CSV file per table, so the data can be imported into SQL Server Management Studio
(SSMS) and analysed there. It reads the database; it does not call the EuroLeague
APIs or change database rows. Run it after loading Silver and building Gold.

Tables are discovered from the database itself, so new derived tables (possessions,
lineups, RAPM and so on) are included without a code change. That is currently 75
tables, about 10.8 million rows for EuroLeague; `play_by_play`, `shots` and the lineup
tables are the large files.

## Run from the repository root

```powershell
python tables_to_csv/main.py --list-tables
python tables_to_csv/main.py --dry-run
python tables_to_csv/main.py
```

`--list-tables` lists the tables found. `--dry-run` counts rows and writes no
files. The plain command writes every table.

Other selections:

```powershell
python tables_to_csv/main.py --layer gold
python tables_to_csv/main.py -tb games player_rapm
python tables_to_csv/main.py -sc 2020-2025 -tb games shots
python tables_to_csv/main.py -cp eurocup
```

- `--layer silver|gold|all` (default `all`) selects the schema.
- `-tb/--table` takes table names; a name that exists in both layers (for example
  `games`) exports both. Unknown names are an error.
- `-sc/--season-code` defaults to `all` and accepts a year, full code, inclusive
  range, `current`, `latest` or `all`. It filters tables that have a `season_code`
  column; other tables are exported whole. Seasons come from `silver.seasons`.
- `-cp/--competition` defaults to `euroleague` and filters tables that have a
  `competition_code` column.
- `--config` selects a connection JSON file (default
  `postgres_etl/config_connection.json`); `--output-root` the parent of the output
  folder (default: repository `data/`, which Git ignores).

## Output

```text
data/csv_export/euroleague/silver/games.csv
data/csv_export/euroleague/silver/play_by_play.csv
data/csv_export/euroleague/gold/team_round_stats.csv
data/csv_export/euroleague/gold/player_rapm.csv
```

Each file has a header row, all database columns (Silver tables include `load_id`
and `loaded_at`) and rows ordered by the table's primary key. A table with no
matching rows produces a header-only file. A rerun replaces only its own files,
through a temporary file, so a failed export never replaces a finished CSV.
Progress and row counts are printed and saved under `logs/tables_to_csv/`.

Format choices for SQL Server:

- Comma-delimited, UTF-8 **with a byte-order mark**, which SSMS uses to detect the
  encoding of player and club names.
- Booleans are written as `1` and `0` (SQL Server's `bit` does not read `t` and `f`).
- NULL is an empty field; a real empty string is quoted. Text with commas, quotes or
  line breaks is quoted, including the JSON columns in Gold.
- Timestamps such as `loaded_at` end in `+00` (UTC); import those columns as text or
  `datetimeoffset`.

Import in SSMS: right-click the database, **Tasks, Import Flat File**, pick a CSV and
check the proposed column types (the wizard guesses them; keep IDs such as
`person_key` as text). The tool writes no SQL scripts.

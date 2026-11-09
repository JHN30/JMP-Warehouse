# CSV export (`tables_to_csv`)

The exporter writes **every table in the local `silver` and `gold` schemas** to one CSV file per table, so the data can be imported into SQL Server Management Studio (SSMS) and analysed there. It only reads the database: it calls no API and changes no rows. Run it after loading Silver and building Gold.

Tables are discovered from the database itself, so new tables are included without a code change. For EuroLeague that is currently 74 tables (34 Silver, 40 Gold) and about 11.9 million rows. `play_by_play`, `shots` and the lineup tables are the largest files.

## Running the export

Run from the repository root:

```powershell
python tables_to_csv/main.py --list-tables     # the tables found, no files written
python tables_to_csv/main.py --dry-run         # row counts, no files written
python tables_to_csv/main.py                   # export every table
```

More selective exports:

```powershell
python tables_to_csv/main.py --layer gold
python tables_to_csv/main.py -tb games app_player_rapm
python tables_to_csv/main.py -sc 2020-2025 -tb games shots
python tables_to_csv/main.py -cp eurocup
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--layer` | `all` | `silver`, `gold` or `all`. |
| `-tb`, `--table` | every table | Table names. Gold tables carry the `app_` prefix (`app_games`), so `games` exports only the Silver table. Unknown names are an error. |
| `-sc`, `--season-code` | `all` | A year, full code, inclusive range, `current`, `latest` or `all`, resolved from `silver.seasons`. Filters tables that have a `season_code` column; other tables are exported whole. |
| `-cp`, `--competition` | `euroleague` | Filters tables that have a `competition_code` column. |
| `--config` | `postgres_etl/config_connection.json` | Connection settings file. |
| `--output-root` | repository `data/` | Parent of the `csv_export/` folder. `data/` is ignored by Git. |

## Output

```text
data/csv_export/euroleague/silver/games.csv
data/csv_export/euroleague/silver/play_by_play.csv
data/csv_export/euroleague/gold/app_standings_stats.csv
data/csv_export/euroleague/gold/app_player_rapm.csv
```

- Each file has a header row and every database column; Silver tables include `load_id` and `loaded_at`.
- Rows are ordered by the table's primary key.
- A table with no matching rows produces a header-only file.
- Each file is written through a temporary file, so a failed export never replaces a finished CSV. A rerun replaces only the files it writes.
- Progress and row counts are printed and saved under `logs/tables_to_csv/`.

### Format choices for SQL Server

| Choice | Reason |
| --- | --- |
| Comma-delimited UTF-8 **with a byte-order mark** | SSMS uses the mark to detect the encoding of player and club names. |
| Booleans as `1` and `0` | SQL Server's `bit` type does not read `t` and `f`. |
| `NULL` as an empty field; a real empty string is quoted | Keeps the two apart. |
| Text with commas, quotes or line breaks is quoted | Includes the JSON columns in Gold. |
| Timestamps such as `loaded_at` end in `+00` (UTC) | Import those columns as text or `datetimeoffset`. |

## Importing in SSMS

1. Right-click the database and choose **Tasks → Import Flat File**.
2. Pick a CSV file.
3. Check the proposed column types. The wizard guesses them; keep identifiers such as `person_key` as text.

The exporter writes no SQL scripts.

## Testing

```powershell
python -m unittest tables_to_csv.tests.test_csv_export
```

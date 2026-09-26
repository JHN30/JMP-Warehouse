# Publish to Neon

Copies the 25 web-app tables (14 v2/v3 tables, play-by-play and shots, `app_standings` and 8 other page-shaped tables; all named `app_*`) for selected
seasons from **local PostgreSQL** straight into **Neon**. It replaces the CSV
export + `psql \copy` route (now in `old/code/`: `neon_csv_import/` and
`import-e2025-e2026.psql`), which could only append and failed when a season was loaded twice.

## How a season is replaced

1. All selected tables for the season are read from one consistent local
   snapshot (read-only, `REPEATABLE READ`).
2. **One Neon transaction** then, for each table: creates it or adds missing
   columns if needed (never drops anything), `DELETE`s that season's rows,
   `COPY`s the new rows with an explicit column list, and checks that the Neon
   row count equals the local count.
3. `COMMIT`. Until then the web app keeps reading the previous rows, so it never
   sees a half-loaded season. Any error rolls the whole season back.

Other seasons are never touched. Running the same command again is safe.

**Safety guard:** if any table would lose more than 10% of its current Neon
rows for the season (for example after a failed or partial local load), the
publish is refused and Neon is unchanged. Pass `--allow-shrink` only when the
shrink is intended.

## Old table names

Until feature 22 the 21 v2/v3 tables were called `etl_flat_*` (the full list is
in [Table names](../docs/DATA_DICTIONARY.md#table-names)). The first publish of
each table renames it in Neon inside the season's transaction and keeps a
view under the old name, so the web app keeps working until it reads
the `app_*` names. A dry run prints `etl_flat_games: would be renamed to
app_games (old name kept as a view)` and changes nothing. If an old and a new
table both exist, the publish stops before any change and names both.

When the web app no longer reads the old names:

```powershell
python neon_publish/main.py --drop-old-names --dry-run   # list the views
python neon_publish/main.py --drop-old-names             # drop them
```

It drops only views, never a table, and a later publish does not recreate them.
This includes the old views of the 7 standings feed tables, which are no
longer published.

## Retired standings feed tables

The web app reads `app_standings`, so the 7 standings feed tables
(`app_standings_basicstandings` and the rest) stay local since feature 23. To
remove them from Neon, after `--drop-old-names`:

```powershell
python neon_publish/main.py --drop-retired --dry-run   # list them with row counts
python neon_publish/main.py --drop-retired             # drop them
```

It drops only those 7 tables, all in one transaction, without `CASCADE`: if an
old `etl_flat_standings_*` view still depends on one, nothing is dropped and it
says to run `--drop-old-names` first. The local tables are kept.

## Play-by-play and shots: only changed games

`app_play_by_play` and `app_shots` are large (E2025 alone is about 223,000 and
64,000 rows, about 130 MB in Neon), so they are not replaced as a whole season.
In the same season transaction, a checksum per game is compared between local
PostgreSQL and Neon (every column, UTC and ISO dates), and only games that are
new or differ are deleted and copied; games Neon has but local does not are
deleted. The output says, for example, `app_play_by_play: 7 of 402 game(s)
replaced`, and a dry run `... would be replaced`. The shrink guard and the
row-count check still use the season totals.

Publish them for **E2025 and E2026 only**; older seasons would not fit the
current Neon plan (about 1.5 GB for all seasons). First run for E2025, after
checking Neon's free storage:

```powershell
python neon_publish/main.py -sc 2025 -tb play_by_play shots --dry-run
python neon_publish/main.py -sc 2025 -tb play_by_play shots
```

The normal refresh (`pipeline.py`) then keeps the current season up to date.

## Running it

Load the season locally first (`postgres_etl/main.py`), or use
[`pipeline.py`](../pipeline.py), which does fetch → load → publish.

```powershell
$neonUrl = Read-Host 'Neon direct connection URL' -AsSecureString
$env:NEON_DATABASE_URL = [System.Net.NetworkCredential]::new('', $neonUrl).Password

python neon_publish/main.py -sc 2026 --dry-run   # compare row counts only
python neon_publish/main.py -sc 2026             # publish E2026
python neon_publish/main.py -sc 2025 2026        # several seasons, one transaction each
python neon_publish/main.py -sc 2026 -tb standings_basicstandings games
```

Use Neon's **direct (non-pooled)** URL. Put it in the `NEON_DATABASE_URL` entry
in the project's `.env` file; it is read only when publishing. An environment
variable takes precedence (`--neon-url-env` selects another one). The URL is
never logged.
`--config` selects the local connection JSON (default
`postgres_etl/config_connection.json`). Logs go to `logs/neon_publish/`.

## Tests

```powershell
python -m unittest neon_publish.tests.test_publish -v
```

The unit tests cover the guard and CLI. The database behaviour was verified
against a scratch schema in local PostgreSQL: first publish into empty tables,
re-publishing the same season, a byte-identical comparison of every table
against the source, the shrink guard, and re-adding a missing column.

# Local Gold source stage

`gold_etl/main.py` copies 16 source tables from the local PostgreSQL `silver`
schema into `gold`. It reads only the registered Silver columns, leaving
`load_id` and `loaded_at` in Silver. It keeps source names, values, NULLs,
types, and primary keys. It also derives traditional and misc player-season
`PS` rows from played PI/PO/FF box scores, and builds `gold.app_standings` from
the seven Silver standings feeds and Silver clubs. Advanced and scoring player
stats remain API-only.

Run from the repository root with the local connection settings in
`postgres_etl/config_connection.json`:

```powershell
python gold_etl/main.py --list-tables
python gold_etl/main.py -sc E2025 --dry-run
python gold_etl/main.py -sc all
python gold_etl/main.py -sc all --quality-only
python gold_etl/main.py -sc E2025 -tb games
python gold_etl/main.py -sc E2025 -tb season_player_stats_traditional season_player_stats_misc app_standings
```

`-cp` selects `euroleague` (default) or `eurocup`; `-sc` accepts codes, years,
ranges, `current`, `latest`, or `all` from locally loaded Silver seasons. `-tb`
selects registered table names. The dry run and quality check connect read-only.
A load replaces one source or derived table, competition, and season slice in
one transaction. Selecting traditional or misc stats handles the non-`PS`
source slice first, then its
derived `PS` slice; a source rerun preserves existing `PS` rows until they are
recalculated. `-tb app_standings` selects only the page table. The quality path
checks both source and derived values. The stage reads no Bronze files and never
writes Silver or Neon. Publishing and other derived Gold tables remain paused.

Run focused tests with `python -m unittest discover -s gold_etl/tests`.

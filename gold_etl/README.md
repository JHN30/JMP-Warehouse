# Local Gold source stage

`gold_etl/main.py` copies 16 source tables from the local PostgreSQL `silver`
schema into `gold`. It reads only the registered Silver columns, leaving
`load_id` and `loaded_at` in Silver. It keeps the same table names, values,
NULLs, types, and primary keys. The four season-player stats tables copy only
non-`PS` rows, leaving the future 30b `PS` slice alone on reruns.

Run from the repository root with the local connection settings in
`postgres_etl/config_connection.json`:

```powershell
python gold_etl/main.py --list-tables
python gold_etl/main.py -sc E2025 --dry-run
python gold_etl/main.py -sc all
python gold_etl/main.py -sc all --quality-only
python gold_etl/main.py -sc E2025 -tb games
```

`-cp` selects `euroleague` (default) or `eurocup`; `-sc` accepts codes, years,
ranges, `current`, `latest`, or `all` from locally loaded Silver seasons. `-tb`
selects registered table names. The dry run and quality check connect read-only.
A load replaces one table, competition, and season in one transaction. It reads
no Bronze files and never writes Silver or Neon. Publishing and the derived
Gold tables remain paused until later feature 30 parts.

Run focused tests with `python -m unittest discover -s gold_etl/tests`.

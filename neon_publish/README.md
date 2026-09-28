# Gold publishing to Neon

`python neon_publish/main.py` publishes one EuroLeague season from local
`gold` to Neon's `public.app_*` tables. The 16 source tables use the target
name `app_<source>`; the ten derived tables already begin with `app_`.
`--list-tables` prints every fixed mapping and scope without a database connection.

The three record tables and `app_players` and `app_club_identities` replace all
rows for competition `E` once per run. The other 21 tables replace only the
selected season. All selected scopes commit in one Neon transaction. A failed
preflight, shrink guard, COPY, or post-copy count check rolls the transaction
back. `play_by_play` and `shots` copy only games whose Gold rows differ, and
remove games no longer present locally.

```powershell
python neon_publish/main.py --list-tables
python gold_etl/main.py -sc E2025 --quality-only
python neon_publish/main.py -sc E2025 --dry-run
python neon_publish/main.py -sc E2025
```

Use `-tb games app_standings` to select registered tables. `-sc` accepts
`current`, a four-digit year, or an `EYYYY` code; it never publishes multiple
historical seasons. `--allow-shrink` overrides only the guard that refuses a
scope with fewer than 90% of its current Neon rows. Real publishing requires
passing Gold quality checks. The dry run reports local and Neon counts, schema
problems, proposed game changes, and shrink refusals without data or DDL writes.

Set `NEON_DATABASE_URL` to a direct non-pooled PostgreSQL URL in the environment
or the local `.env` file. Credentials are never printed. The web app reads
Neon in the separate `jmp-euroleague2` repository. The one-time in-place schema
cutover is [30f_in_place.sql](migrations/30f_in_place.sql), based on the read-only
Neon schema inspection. The approved migration and first E2026 publish completed
on 2026-09-28. The recurring publisher never runs migrations or drops columns.
Further live runs require owner approval. If publish fails, the old Neon
data remains visible; fix the problem and rerun. The pipeline keeps its pending
state until a publish commits.

```powershell
python -m unittest neon_publish.tests.test_publish
```

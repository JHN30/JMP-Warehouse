# Gold publishing to Neon

`python neon_publish/main.py` publishes one EuroLeague season from local
`gold` to Neon's `public.app_*` tables. The 16 source tables use the target
name `app_<source>`; the ten derived tables already begin with `app_`; the twelve
tables of features 26-29 added in 30g use `app_<name>` (`app_standings_stats` keeps its
name), plus the two per-game tables of 30h (`app_game_player_advanced`,
`app_game_team_advanced`) and the four per-game play-by-play tables of 30i
(`app_game_team_possessions`, `app_game_team_score_flow`, `app_game_team_shot_splits`,
`app_game_team_shot_zones`) and the three tables of 30j (`app_game_player_on_court`,
`app_game_team_lineup_stints`, `app_game_stat_gaps`), 47 targets in all.
`--list-tables` prints every fixed mapping and scope without a database connection.

The three record tables and `app_players` and `app_club_identities` replace all
rows for competition `E` once per run. The other 42 tables replace only the
selected season (the 21 tables added in 30g, 30h, 30i and 30j are season-scoped too). All selected scopes commit in one Neon transaction. A failed
preflight, shrink guard, COPY, or post-copy count check rolls the transaction
back. `play_by_play` and `shots` copy only games whose Gold rows differ, and
remove games no longer present locally.

```powershell
python neon_publish/main.py --list-tables
python gold_etl/main.py -sc E2025 --quality-only
python neon_publish/main.py -sc E2025 --dry-run
python neon_publish/main.py -sc E2025
```

The twelve tables added in 30g need a one-time reviewed migration first:
`python neon_publish/main.py --print-migration` prints it and
[30g_new_tables.sql](migrations/30g_new_tables.sql) is the same text (a test keeps them
equal). Apply it on the direct Neon connection only with the owner's approval and after
the web app agrees the contract. Until then a live publish stops at the schema preflight
("missing table") and rolls back, leaving Neon unchanged. Publish them for E2025 and E2026
only; all seasons would be about 1.5 GB.

The two tables added in 30h need their own one-time migration:
`python neon_publish/main.py --print-migration 30h` prints it and
[30h_game_advanced.sql](migrations/30h_game_advanced.sql) is the same text. The same approval
rule and the same "missing table" stop apply. The tables of 30i and 30j likewise (`--print-migration 30j`,
[30j_game_on_court_and_gaps.sql](migrations/30j_game_on_court_and_gaps.sql); `app_game_stat_gaps` stays
empty for E2025 and E2026). The four tables of 30i:
`python neon_publish/main.py --print-migration 30i` and
[30i_game_play_by_play.sql](migrations/30i_game_play_by_play.sql). Neon has only the owner role, so the migration
writes no `GRANT`; a read-only role added later needs its grants for every `app_*` table.

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

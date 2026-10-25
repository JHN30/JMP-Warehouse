# Gold publishing to Neon

`python neon_publish/main.py` publishes one EuroLeague season from local
`gold` to Neon's `public.app_*` tables. All 40 Gold sources have exactly
the same physical names as their Neon targets, for example
`gold.app_games -> public.app_games`. The publisher copies names as they are;
it never adds a prefix. The Gold-only migration is documented in
[gold_etl/README.md](../gold_etl/README.md) and does not change Neon.
Neon holds every locally loaded season: E2000-E2026 for the catalog, box-score, standings and round tables, and E2007-E2026 for the play-by-play, shot and lineup tables, whose source data starts in E2007 (checked read-only on 2026-10-25). Each publish selects one season.
`--list-tables` prints every fixed mapping and scope without a database connection.

The three record tables and `app_players` and `app_club_identities` replace all
rows for competition `E` once per run. The other 35 tables replace only the
selected season (the 16 current tables added in 30g, 30h, 30i and 30j are season-scoped too). All selected scopes commit in one Neon transaction. A failed
preflight, shrink guard, COPY, or post-copy count check rolls the transaction
back. `app_play_by_play` and `app_shots` copy only games whose Gold rows differ, and
remove games no longer present locally.

```powershell
python neon_publish/main.py --list-tables
python gold_etl/main.py -sc E2025 --quality-only
python neon_publish/main.py -sc E2025 --dry-run
python neon_publish/main.py -sc E2025
```

The twelve tables added in 30g needed a one-time reviewed migration first:
[30g_new_tables.sql](migrations/30g_new_tables.sql). Four of them were later retired (see
below), so `python neon_publish/main.py --print-migration` now prints only the eight current
tables, and a test checks that each of them is still created by the file as written. Apply it on the direct Neon connection only with the owner's approval and after
the web app agrees the contract. Until then a live publish stops at the schema preflight
("missing table") and rolls back, leaving Neon unchanged. These tables were first published
for E2025 and E2026 only; every loaded season has since been published.

The two tables added in 30h need their own one-time migration:
`python neon_publish/main.py --print-migration 30h` prints it and
[30h_game_advanced.sql](migrations/30h_game_advanced.sql) is the same text. The same approval
rule and the same "missing table" stop apply. The tables of 30i and 30j likewise (`--print-migration 30j`,
[30j_game_on_court_and_gaps.sql](migrations/30j_game_on_court_and_gaps.sql); `app_game_stat_gaps` stays
empty for E2025 and E2026). The four tables of 30i (`app_game_team_shot_zones` since retired):
`python neon_publish/main.py --print-migration 30i` and
[30i_game_play_by_play.sql](migrations/30i_game_play_by_play.sql). Neon has only the owner role, so the migration
writes no `GRANT`; a read-only role added later needs its grants for every `app_*` table.

[database_size.sql](database_size.sql) is a read-only query for the Neon size (whole database and
the ten largest tables); check it before publishing another season.

The three qualification columns (`is_calculated`, `min_games`, `qualified`) of the four
`app_season_player_stats_*` tables (30l) need a column migration first,
[30l_player_stats_qualification.sql](migrations/30l_player_stats_qualification.sql). Until it is
applied the preflight reports the missing columns and the publish refuses. Apply it with the
owner's approval, then publish every season (`E2024`, `E2025`, `E2026`) because the old rows
hold placeholder values until they are replaced.

Use `-tb app_games app_standings` to select registered physical tables. `-sc` accepts
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

Seven tables the web app no longer reads are no longer built or published:
`app_coverage_seasons`, `app_coverage_games`, `app_team_round_stats`, `app_team_round_ratings`,
`app_team_round_splits`, `app_game_team_shot_zones` and `app_team_shot_zone_stats`. Their Neon
copies were dropped on 2026-10-26 by
[drop_unused_app_tables.sql](migrations/drop_unused_app_tables.sql), after the app deploy.
Further live runs require owner approval. If publish fails, the old Neon
data remains visible; fix the problem and rerun. The pipeline keeps its pending
state until a publish commits.

```powershell
python -m unittest neon_publish.tests.test_publish
```

# Feature: Clean table names

**From build-plan:** feature 22
**Build attempt:** 1
**Status:** verified
**Branch:** feature/clean-table-names

## Goal

The 21 web-app tables that are published to Neon get clean `app_*` names
(`etl_flat_games` -> `app_games`) in local PostgreSQL and in Neon's `public`
schema. The web app keeps working during the switch: in Neon each renamed
table leaves a read-only view under its old name until the app repo has moved
to the new names, and one explicit command then removes those views.

Owner decisions (2026-09-24): rename both local and Neon; switch over with
rename plus old-name views; keep the `public` schema (the `app` schema and a
read-only role stay in feature 16).

## In scope

- New physical names for exactly these 21 logical tables, `app_<logical name>`:
  `seasons`, `clubs`, `people`, `registrations`, `rounds`, `games`,
  `game_officials`, `game_period_scores`, `game_player_stats`,
  `game_team_stats`, `season_stats_traditional`, `season_stats_advanced`,
  `season_stats_scoring`, `season_stats_misc`, `standings_basicstandings`,
  `standings_calendarstandings`, `standings_streaks`, `standings_aheadbehind`,
  `standings_margins`, `standings_calendar_streaks`, `standings_basic_form`.
  `app_standings` is unchanged. Every other local table (play-by-play, shots,
  live tables, `game_stat_gaps`, `etl_source_payloads`) keeps its name.
- Local migration: the first load or publish after this change renames the old
  local tables in place (`ALTER TABLE ... RENAME`), keeping all 27 seasons of
  rows. No views locally.
- Neon migration: the first real publish of a table renames it in Neon inside
  that season's existing transaction and creates `VIEW etl_flat_<name> AS
  SELECT * FROM app_<name>` in the same transaction, so the app sees either the
  old table or the view, never a gap.
- Dry runs (`--dry-run`, `pipeline.py --dry-run-publish`) report what would be
  renamed and change nothing in Neon.
- `python neon_publish/main.py --drop-old-names` (with optional `--dry-run`)
  drops the old-name views in Neon, only ever views, never a table.
- Quality checks, CSV export and all logs use the new names.
- Docs: the old -> new mapping and the three-step switchover for the web-app
  repo in `docs/DATA_DICTIONARY.md`, plus the READMEs and `AGENTS.md` Commands.

## Out of scope

- Column names stay exactly as they are (including source spellings such as
  `assistances`); only table names change.
- The Neon `app` schema and a read-only role (feature 16).
- Play-by-play and shots in Neon (feature 21; they will get `app_*` names there).
- Dropping or no longer publishing the 7 old standings tables now that
  `app_standings` exists; they are renamed like the others.
- Any change in the web-app repo. This feature delivers the mapping and the
  steps; the app switch is done there.
- Renaming indexes or primary-key constraints. Renamed tables keep
  `etl_flat_*_pkey` and `idx_flat_*` names; they are internal and harmless.
- Running the real Neon publish or `--drop-old-names` against Neon. Those are
  the owner's runs, after an explicit go-ahead.

## Build loop

`workflow.stepReview` is `feature` and `workflow.checkpointCommits` is
`disabled`: build all steps, running each step's focused check, then present
one review packet. `/complete` makes the single feature commit. The change
touches a migration of shared persisted data and adds a destructive command, so
the `when-sensitive` gate selects an independent review before `/complete`.

## Build steps

- [x] 1. **New names and the local migration.** In
  `postgres_etl/flat_schema.py`: a `PUBLISHED_TABLES` tuple (the 21 names plus
  `app_standings`, in the current `APP_TABLES` order), `physical_name` returning
  `app_<name>` for the 21, `legacy_name(name)` returning `etl_flat_<name>` for
  them (None otherwise), a pure `rename_actions(relkinds, names, keep_views)`
  that turns the current relation kinds (table / view / missing) of old and new
  names into actions, `rename_legacy_tables(cursor, names, keep_views,
  dry_run)` that reads the kinds, applies the actions in the caller's
  transaction and returns them, and `rename_local_tables(connection, log)` that
  runs it for all 21 tables without views in one committed transaction. Actions: old table + new missing -> rename (+ create the view
  when `keep_views`); new exists + old view or missing -> nothing; old and new
  both tables -> raise with both names and change nothing; neither -> nothing
  (the table is created later as today). `neon_publish/publish.py` takes
  `APP_TABLES = PUBLISHED_TABLES`. Replace the hard-coded `etl_flat_games`,
  `etl_flat_clubs` and `etl_flat_standings_basicstandings` in
  `postgres_etl/quality.py` with `physical_name`. The loader
  (`postgres_etl`, not in `--dry-run`) runs `rename_local_tables` before
  loading, and logs
  `Renamed local etl_flat_games -> app_games` per table.
  Tests: `physical_name` for a renamed table, a kept table (`play_by_play`),
  `app_standings` and `source_payloads`; `rename_actions` for all five cases
  with and without views; update the quality test fakes to the new names.
  Done when: the three test commands pass, and a real local
  `python postgres_etl/main.py -sc 2026` renames the 21 tables, the per-season
  row counts of every renamed table for all seasons equal the counts taken
  before the run, quality reports 0 errors, and a second run renames nothing.

- [x] 2. **Neon rename with old-name views.** `neon_publish/main.py` runs
  `rename_local_tables` (no views) right after connecting to local
  PostgreSQL, before `available_seasons`, so a standalone publish also works on
  a database that was not loaded since the change. In `publish_season`:
  `remote_counts` counts the new name when it exists, otherwise the old name
  when it is a table (so the shrink guard compares against the rows the app
  sees now); a both-tables conflict stops before any change with a message
  naming both; a dry run logs `  etl_flat_games: would be renamed to app_games
  (old name kept as a view)`; a real publish calls `rename_legacy_tables` with
  `keep_views=True` for the selected tables inside the season transaction,
  before `_ensure_table`, logging `  etl_flat_games: renamed to app_games (old
  name kept as a view)`. The row lines stay `  app_games: 380 -> 380 rows`, so
  the refresh summary keeps working. A view is created only at the moment of a
  rename, so a publish after `--drop-old-names` does not bring the views back.
  Tests: a fake cursor for `remote_counts` (new name, old table, missing) and
  for a dry run that must execute no DDL and log the rename line; a real-publish
  fake that records the rename and view statements in order before the DELETE
  and COPY. Done when: the three test commands pass. No Neon connection is made.

- [x] 3. **Command that removes the old names.** `python neon_publish/main.py
  --drop-old-names` connects to Neon, and for each of the 21 old names drops it
  only when it is a view (`DROP VIEW`), in one transaction, logging each drop;
  an old name that is still a table is reported and left alone (it means that
  table was never published after this change), a missing one is skipped.
  `--dry-run` lists what would be dropped. It needs no season, cannot be
  combined with `--table`/`--season-code`, and prints a warning that the web app
  must already use the `app_*` names. Tests: the drop plan (views only, never a
  table), argument conflicts, and a dry-run fake that executes no DDL. Done
  when: the three test commands pass and `python neon_publish/main.py --help`
  shows the option. No Neon connection is made.

- [x] 4. **Docs for the switchover.** `docs/DATA_DICTIONARY.md`: tables are
  now named `app_*`; a table with every old -> new name; the switchover for the
  app repo: (1) the owner publishes, which renames and keeps the old names as
  views, and the app keeps working unchanged; (2) the app repo moves every
  query (and any Drizzle table filter) to the `app_*` names and deploys;
  (3) the owner runs `--drop-old-names --dry-run`, then `--drop-old-names`.
  Note that the old-name views have the columns of the moment they were
  created and receive no new columns. Update `README.md`,
  `postgres_etl/README.md`, `neon_publish/README.md`, `tables_to_csv/README.md`
  (CSV files now carry `app_*` names for these tables) and the `AGENTS.md`
  Commands. Done when: `grep -rn "etl_flat_" --include=*.md . ` outside `old/`,
  `blueprint/history/` and `docs/PIPELINE-*.md` shows only tables that keep
  the old prefix or the documented old-name mapping, and the three test
  commands pass.

## Files / areas

- `postgres_etl/flat_schema.py` - `PUBLISHED_TABLES`, `physical_name`,
  `legacy_name`, `rename_actions`, `relation_kinds`, `rename_legacy_tables`,
  `rename_local_tables`
- `postgres_etl/flat_loader.py` (or `postgres_etl/main.py`, wherever the load
  connection opens) - local rename before loading
- `postgres_etl/quality.py` - hard-coded names
- `neon_publish/publish.py`, `neon_publish/main.py` - Neon rename, views,
  counts, dry run, `--drop-old-names`
- Tests: `postgres_etl/tests/test_flat_etl.py`, `test_quality.py`,
  `test_raw_etl.py` (if its name assertion changes), `neon_publish/tests/test_publish.py`
- Docs listed in step 4

## Data / contracts

- Name rule: published logical table `x` (other than `app_standings`) has the
  physical name `app_x` locally and in Neon; its legacy name is `etl_flat_x`.
- Rows, keys and columns are unchanged; a rename moves the table with all its
  seasons, indexes and constraints.
- Neon states per table: before (`etl_flat_x` table) -> after the first
  publish (`app_x` table + `etl_flat_x` view) -> after `--drop-old-names`
  (`app_x` table only). A fresh Neon database gets `app_x` only.
- Atomicity: in Neon the rename and view are part of the season's single
  transaction (`lock_timeout` 15 s already set); any failure rolls back to the
  old table. Locally all renames run in one transaction.
- Idempotency: running load, publish or `--drop-old-names` again changes
  nothing further.
- Refusals: both an `etl_flat_x` table and an `app_x` table present -> stop
  before any change and name both; `--drop-old-names` never drops a table.
- The refresh summary's `table: before -> after` lines show the new names.

## Testing

- `cd api_requests && python -m unittest tests.test_scrapper`
- `python -m unittest discover -s postgres_etl/tests`
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`
- Step 1's real local load of E2026 with before/after row counts.
- Not run here: anything against Neon. After `/complete`, the owner runs
  `python pipeline.py --dry-run-publish` (shows the planned renames), then the
  real refresh, and after the app repo has switched, `--drop-old-names`.

## Notes for the AI

- Build on the existing single-function naming: everything already calls
  `physical_name`, so the rename is one rule plus the migration helper. No new
  config, dependency or schema.
- Use `psycopg2.sql.Identifier` for every name in DDL, as the rest of
  `publish.py` does. Read relation kinds with `to_regclass` plus
  `pg_class.relkind` in `current_schema()`.
- Keep `rename_actions` pure (no database) so all cases are unit-tested; the
  executing helper stays thin.
- If the web app connects to Neon with a different role than the publisher,
  the new views need a `GRANT SELECT`; the app appears to use the owner role
  (item 16 adds a separate role later). Mention this in the switchover docs,
  do not add grants.
- Never touch Neon while building; no API requests. Local database writes in
  step 1 are expected.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":11881,"specSha256":"9986505b74059d0ee242bf33796f3963bec2745494f152026a0a0d1f2f4661fa","branch":"refs/heads/feature/clean-table-names","head":"260fef61cc231611d56f38bd80eb34e19f74c64a","baseRef":"refs/heads/main","baseCommit":"a298f9ec89400186e2b1340937b1687045d98d0a","sourceTree":"94399a6d70801e01b17c9c393456279c46ffbeaa","absentOptional":[]} -->

## Independent review

# Independent Review

**Status:** passed
**Target commit:** 260fef61cc231611d56f38bd80eb34e19f74c64a
**Base commit:** a298f9ec89400186e2b1340937b1687045d98d0a
**Base ref:** main
**Spec hash:** 9986505b74059d0ee242bf33796f3963bec2745494f152026a0a0d1f2f4661fa
**Prepared by:** claude
**Builder model:** claude-opus-5-5
**Requested reviewer:** claude
**Requested model:** claude-opus-5-5
**Requested execution:** automatic
**Requested at:** 2026-09-24T21:51:35+00:00
**Workflow:** regular
**Check required:** no
**Reviewer adapter:** claude
**Reviewer model:** claude-opus-5-5
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-09-24T21:55:27+00:00
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Handoff

Review the active spec and the complete `a298f9ec89400186e2b1340937b1687045d98d0a..260fef61cc231611d56f38bd80eb34e19f74c64a` delta in a fresh
session or isolated subagent without the builder conversation. Run all Audit lenses from scratch.
Run Check when required above. Do not edit product code, accept findings, or
reuse the existing findings as the review scope.

## Commands

- `git rev-parse HEAD`, `git merge-base main HEAD`, `sha256sum blueprint/context/current-feature.md`, `git status --porcelain --untracked-files=all`: pass (target, base and spec hash match; only `blueprint/context/review.md` modified)
- `cd api_requests && python -m unittest tests.test_scrapper`: pass (16 tests)
- `python -m unittest discover -s postgres_etl/tests`: pass (42 tests)
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass (37 tests)
- `python neon_publish/main.py --help`: pass (shows `--drop-old-names`)
- Read-only local PostgreSQL queries (relation kinds, `rename_actions` on the live state, `copy_expert` with a `psycopg2.sql` object on `COPY (SELECT 1) TO STDOUT`, DDL composed with `as_string`): pass

## Evidence

- Reviewed the full 17-file delta: `postgres_etl/flat_schema.py`, `flat_loader.py`, `quality.py`, `neon_publish/publish.py`, `main.py`, `tables_to_csv/main.py`, all changed tests and docs.
- Rename and view run through `rename_legacy_tables` inside the season's `with neon:` transaction after `SET LOCAL lock_timeout`, before `_ensure_table`, DELETE and COPY; any later error rolls both back (`neon_publish/publish.py:234-258`).
- Shrink guard counts the `app_*` table when it exists, else the old name only when it is a table, never a view (`publish.py:161-165`); covered by `test_counts_use_the_new_name_or_else_the_old_table` and the 375 -> 380 publish test.
- Conflicts (both tables, or a non-table `app_*`) raise in `remote_counts` before any DDL (`flat_schema.py:585-590`); tested for publish and pure planning.
- `--drop-old-names` drops only relkind `v` (`publish.py:175-176`) with `DROP VIEW` (no CASCADE), which PostgreSQL also refuses on a table; one transaction.
- Dry run executes only reads in Neon; test asserts no DDL and unchanged fake state.
- All identifiers in new DDL use `sql.Identifier` over constant names; composed SQL verified against a real connection: `ALTER TABLE "etl_flat_games" RENAME TO "app_games"`, `CREATE VIEW "etl_flat_games" AS SELECT * FROM "app_games"`, `DROP VIEW "etl_flat_games"`.
- Index names use the logical name (`idx_flat_<name>_...`), so reloads after the rename create no duplicate indexes.
- No remaining code path uses a hard-coded old name for the 21 tables (grep outside `old/`, logs and caches); `pipeline.py` summary regex does not match the new rename log lines.
- Local database now holds the 22 `app_*` tables and no `etl_flat_*` copy of them; `rename_actions` on the live state returns no actions (idempotent).
- `copy_expert` with a `psycopg2.sql` object (changed from `as_string`) works on the installed psycopg2 2.9.13.

## Findings

- F-04 [P3] open - Old-name views are called read-only but accept writes (docs wording; non-blocking)

## Remaining risk

- No lint, typecheck, build or combined Verify command exists in this project (build-plan item 17); none could run.
- No Neon run by design: the real rename, view creation, rollback on failure and `--drop-old-names` were proven only with `FakeDatabase`, which does not model commit or rollback. Atomicity rests on psycopg2 `with connection` semantics and PostgreSQL transactional DDL. The owner's `--dry-run-publish` then real refresh is the first real exercise.
- The first real publish holds ACCESS EXCLUSIVE locks on the renamed tables until COMMIT (about 6 s for the current season in recent logs), so web-app reads wait during that one transaction instead of seeing old rows; a lock wait or deadlock with an app query rolls the whole season back safely and the publish can be rerun.
- If the web app uses a different Neon role than the publisher, the new views need `GRANT SELECT` (documented, not automated).
- `--quality-only` and CSV export on a local database that was never loaded or published after this change report the 21 tables as missing until a load or publish renames them (loud, not silent).

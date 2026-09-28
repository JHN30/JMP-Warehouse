# Feature: Gold schema and source projections

**From build-plan:** feature 30a
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/gold-schema-and-source-projections`

## Goal

Create the local `gold` foundation from Silver so later Gold aggregates and
the publisher have a stable app-facing source layer. Keep Neon and the web app
unchanged while features 30b–30e add derived tables and 30f resumes publishing.

## In scope

- Build these 16 previously published source tables as `gold.<name>` from the
  same-named `silver` tables: `seasons`, `clubs`, `people`, `registrations`,
  `rounds`, `games`, `game_officials`, `game_period_scores`,
  `game_player_stats`, `game_team_stats`, four
  `season_player_stats_<category>` tables (`traditional`, `advanced`,
  `scoring`, `misc`), `play_by_play`, and `shots`.
- Give each Gold table the Silver source columns, types, and primary key,
  without Silver-only `load_id` and `loaded_at`. Copy source values exactly;
  retain Silver's clean names and NULL meaning. Gold uses the short table names
  in its own schema, not local `app_` or `etl_flat_` names.
- Add a local Gold CLI with the project competition, season, table, and dry-run
  selections. It reads Silver only and replaces one table/competition/season
  atomically. A failed replacement leaves that scope's prior Gold rows intact.
- Build every existing EuroLeague season locally from Silver, check row counts
  and representative value equality, and verify that a rerun is idempotent.
- Document the local Gold source layer and its command. Publishing stays paused.

## Out of scope

- The Silver schema, source transforms, bronze files, or Silver provenance.
- Derived `PS` rows and `app_standings` (30b); team season stats and coverage
  (30c); records and postseason series (30d); player and club identity (30e).
- Neon schema or data, the publisher, pipeline publish stage, and the web app
  (30f). Advanced analytics in features 19 and 25–29 stay separate.
- A general migration framework, a new dependency, or dropping existing tables.

## Build loop

`workflow.stepReview` is `feature`: finish the small steps and present one
review packet. Checkpoint commits are disabled; `/complete` owns the work
commit. Inspect existing local `gold` objects and record their row counts
before replacement. If an existing Gold table contains unaccounted data, stop
for the owner's decision rather than overwriting it. No Neon writes.

## Build steps

- [x] **Step 1 - Define Gold source contract and CLI** - add a `gold_etl/`
  stage whose 16-table registry references the registered Silver field and key
  definitions. Use fully qualified `silver` and `gold` relations; the shared
  local connection defaults to `silver`. Support `-cp`, `-sc`, `-tb`,
  `--list-tables`, and `--dry-run`. The dry run connects read-only and reports
  selected Silver counts without creating Gold objects. *Done when:* focused
  tests cover all 16 names, selection, empty and invalid requests, schema SQL,
  and a database-write-free dry run; existing ETL tests pass.
- [x] **Step 2 - Copy one scope transactionally** - create the `gold` schema
  and missing registered tables additively. For each selected table and scope,
  DELETE its prior Gold rows and INSERT the named Silver source columns in one
  transaction, keeping keys and values unchanged. For the four player-season
  tables, replace only non-`PS` rows so 30b's later derived rows survive a 30a
  rerun. A Silver table with zero rows replaces its Gold scope with zero rows;
  an absent requested season is rejected or skipped before any DELETE. *Done
  when:* fake-cursor tests
  cover success, empty source, rerun, insert failure and rollback, and no
  Silver/Neon writes; Gold retains a prior scope after failure.
- [x] **Step 3 - Validate Gold against Silver** - add read-only checks for a
  missing Gold table, row-count mismatch by competition/season, and
  source-column value mismatch. Compare only non-`PS` rows in the four
  player-season tables; PostgreSQL primary keys enforce non-null, unique keys.
  Use the source registry
  for identifiers and parameters for scope values. *Done when:* focused tests
  demonstrate each error, and a quality-only path reports actionable failures
  without changing either schema.
- [x] **Step 4 - Populate local Gold history** - record existing `gold`
  objects and counts first; build all locally loaded EuroLeague seasons from
  Silver without a fetch. Compare the count of every Gold table/season scope
  with Silver and compare representative full rows across v2, v3, and live
  families. Rerun E2025 `games` and confirm no duplicates or changed counts.
  *Done when:* the complete local load and quality checks pass, all 16 Gold
  tables have the intended primary keys and values, and `public`, Silver, and
  Neon remain unchanged.
- [x] **Step 5 - Document and final check** - update the root README,
  `docs/DATA_DICTIONARY.md`, `AGENTS.md` commands, and a `gold_etl/README.md`.
  Keep the historical web-app Gold reference marked paused until 30f. *Done
  when:* the docs describe the actual Gold scope and read-only dry run, the
  Gold dry run passes for E2025, and all declared unit suites plus the new
  Gold suite pass.

## Files / areas

- `gold_etl/main.py`, `schema.py`, `loader.py`, `quality.py`, `tests/`, and
  `README.md`: local Gold selection, source projection, checks, and guidance.
- `postgres_etl/flat_schema.py`: read its registered fields and keys; change it
  only if a focused test proves a missing reusable contract.
- `common/db.py`: use the existing local connection and explicit schema names.
- `README.md`, `docs/DATA_DICTIONARY.md`, `AGENTS.md`: document the new local
  stage and continuing publish pause.

## Data / contracts

- The 16 Gold source tables use the same natural primary keys and source field
  definitions as their Silver counterparts. No `load_id` or `loaded_at` is
  copied; those remain Silver provenance metadata. The source values, including
  JSONB and NULLs, are copied without renaming or aggregation.
- A Gold load reads `silver.<table>` and writes only `gold.<table>`. It never
  reads Bronze or writes Silver. The logical table name is the same in both
  schemas. `silver.load_log` is not a Gold table.
- `--dry-run` and quality-only checks are read-only. `-sc all` selects seasons
  present locally in Silver; a requested season absent from Silver is reported
  and skipped or rejected consistently with the existing loader CLI. A present
  season with zero rows in one selected source table clears that Gold scope.
- The four Gold season-player tables contain API rows only in 30a. Feature
  30b will add derived `PS` rows in Gold, leaving Silver's API-only rows intact.
  30a owns only the non-`PS` slice on every later rerun and validates that
  slice against Silver; 30b owns the `PS` slice.
- A completed local Gold build is a prerequisite for 30f's guarded Neon
  publish. Until 30f, `python pipeline.py` and `neon_publish/main.py` retain
  the pause behavior and do not connect to Neon.

## Testing

- New suite: `python -m unittest discover -s gold_etl/tests`.
- Existing suites: `cd api_requests && python -m unittest tests.test_scrapper`,
  `python -m unittest discover -s postgres_etl/tests`, and
  `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Unit tests use fake cursors and temporary fixtures, not a real database or
  API. Live evidence uses a read-only dry run, the local full build, count and
  sample-value SQL, and one controlled rerun. There is no combined Verify or
  browser test command.

## Notes for the AI

- The 16-table source list comes from the former `PUBLISHED_TABLES` registry
  before 16a, with the four renamed `season_player_stats_*` names. The seven
  standings feeds, four v3 team-stat feeds, and `game_stat_gaps` remain in
  Silver for later Gold derivations or quality checks.
- Prefer SQL `INSERT ... SELECT` with explicit registered columns over a
  Python row loop. Keep all identifiers registered and scope values
  parameterized. Do not create views or a general projection framework.
- Verify the local database's existing Gold state before replacing rows. If
  unexpected data exists, stop and seek a specific decision. Never modify
  Neon or activate publishing in 30a.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":8335,"specSha256":"f3e3db13d1f8d02ca2c92ce5da5461ef20db591929be4a3891052443d4288114","branch":"refs/heads/feature/gold-schema-and-source-projections","head":"5facc9b1c4d906eff355910de4f7403a96053548","baseRef":"refs/heads/main","baseCommit":"5826ffe8d1acd3cc52fb1629fd4f9a8485a12524","sourceTree":"c6a140f294ea964790003f5f17ec5aafff694407","absentOptional":[]} -->

## Independent review

# Independent Review

**Status:** passed
**Target commit:** 5facc9b1c4d906eff355910de4f7403a96053548
**Base commit:** 5826ffe8d1acd3cc52fb1629fd4f9a8485a12524
**Base ref:** main
**Spec hash:** f3e3db13d1f8d02ca2c92ce5da5461ef20db591929be4a3891052443d4288114
**Prepared by:** codex
**Builder model:** unknown (runtime did not expose exact model)
**Requested reviewer:** codex
**Requested model:** gpt-6-sol
**Requested execution:** automatic
**Requested at:** 2026-09-28T02:52:57.6817798+02:00
**Workflow:** regular
**Check required:** no
**Reviewer adapter:** codex
**Reviewer model:** gpt-6-sol
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-09-28T00:55:41Z
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Handoff

Review the active spec and the complete `5826ffe8d1acd3cc52fb1629fd4f9a8485a12524..5facc9b1c4d906eff355910de4f7403a96053548` delta in a fresh
session or isolated subagent without the builder conversation. Run all Audit lenses from scratch.
Run Check when required above. Do not edit product code, accept findings, or
reuse the existing findings as the review scope.

## Commands

- `git rev-parse HEAD; git merge-base main HEAD; Get-FileHash blueprint/context/current-feature.md -Algorithm SHA256; git status --short; git ls-files --others --exclude-standard`: pass; target, base, spec hash, and clean product tree match the request.
- `git diff --check 5826ffe8d1acd3cc52fb1629fd4f9a8485a12524..5facc9b1c4d906eff355910de4f7403a96053548`: pass.
- `python -m unittest discover -s gold_etl/tests`: pass, 15 tests.
- `python -m unittest discover -s postgres_etl/tests`: pass, 49 tests.
- `cd api_requests; python -m unittest tests.test_scrapper`: pass.
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass, 19 tests.
- `python gold_etl/main.py --list-tables`: pass, 16 registered tables.
- `python gold_etl/main.py -sc E2025 --dry-run`: pass, source counts reported with a read-only session.
- `python gold_etl/main.py -sc all --quality-only`: pass, Gold matched Silver across 27 locally loaded EuroLeague seasons.

## Evidence

- Reviewed the complete committed 30a delta, including `gold_etl/` source and tests, the Silver field/key registry and shared connection/season helpers, and changed documentation. The only working tree difference was this review record.
- Registered identifiers and parameterized scope values limit SQL input; Gold replacement uses a connection transaction around schema creation, deletion, and source insertion. The player-season predicate excludes future `PS` rows.
- Local read-only quality checks compared counts and source-column values for all selected scopes. No skipped or placeholder Gold tests were found.

## Findings

- None new in the feature 30a delta. Existing F-06 [P2] remains open in the ledger and predates this feature.

## Remaining risk

- Real PostgreSQL insert-failure rollback was not re-enacted in this read-only review; its fake-cursor test passed.
- Existing F-06 [P2] concerns refresh regression coverage outside the 30a delta.

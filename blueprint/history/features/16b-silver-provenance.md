# Feature: Silver provenance

**From build-plan:** feature 16b
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/silver-provenance`

## Goal

Trace every silver row to the successful table-and-season load that wrote it,
and trace that load to the exact bronze file versions it read. Preserve the 28
source tables and their data contracts from 16a. Rebuild existing silver rows
from bronze so historical rows have real provenance too.

## In scope

- Add `load_id` and `loaded_at` to each of the 28 silver source tables. One
  table/competition/season replacement uses one ID and one UTC timestamp for
  all its rows.
- Add `silver.load_log`: append one record for each successfully committed
  table/competition/season replacement, including zero-row loads. Record the
  row count and the exact bronze versions actually read, including catalog and
  auxiliary resources used while transforming rows.
- Keep the existing per-table/competition/season DELETE and INSERT transaction.
  The new log entry commits with those rows. A failed load rolls both back;
  a rerun keeps earlier log entries and gives the replacement rows a new ID.
- Add the columns to existing tables without inventing provenance for old rows.
  Reload all cached seasons, verify every row, then enforce non-null metadata.
- Extend read-only quality checks and documentation for provenance.

## Out of scope

- A direct bronze-file ID on each row: a load can use several files, and its
  `load_id` links to their complete list in `load_log`.
- Changes to the bronze files or their manifest format.
- Gold tables and Neon publishing (feature 30), per-record advanced stats
  (feature 25), or a general migration framework.
- A database drop or a new fetch from the EuroLeague API.

## Build loop

`workflow.stepReview` is `feature`: implement the small steps, then present one
review packet. Checkpoint commits are disabled; `/complete` owns the work
commit. The historical backfill replaces existing silver table/season rows
through the normal loader; record counts first and obtain the owner's approval
for that full rewrite before running it. No Neon data changes.

## Build steps

- [x] **Step 1 - Capture actual bronze versions** - adapt the existing bronze
  reader and `RawSeason`/`FlatSeason` so a table load collects each version path
  when it is actually read. Start collection before `files()` because page
  selection can read a source. Cover direct auxiliary `BronzeStore.read_json()`
  calls as well as the main row files. Deduplicate and sort the paths relative
  to `data/bronze/`; never log machine-specific absolute paths. *Done when:*
  temporary-bronze tests show the selected version after a resource changes,
  the catalog and auxiliary versions where used, and no version for an unread
  resource; the fetcher and ETL unit suites pass.
- [x] **Step 2 - Add the provenance schema** - define `silver.load_log` and
  the two source-table columns in `flat_schema.py`. Existing tables gain
  nullable columns for the transition; new tables have non-null columns. Keep
  source transform fields separate from loader-generated provenance and keep
  all 28 source-table names and primary keys. *Done when:* DDL tests cover all
  28 tables, the log key and types, and additive migration without a table drop;
  the ETL unit suite passes.
- [x] **Step 3 - Write rows and log atomically** - generate one UUID and UTC
  timestamp per table/competition/season load, write them on every inserted
  row, and append one log entry with the exact captured versions and inserted
  row count in the same transaction. Keep a skipped no-source table unchanged
  and make `--dry-run` database-free. *Done when:* fake-cursor tests cover a
  successful load, a zero-row load, a rerun, an insert/read failure and rollback,
  and dry run; existing loader tests and all declared suites pass.
- [x] **Step 4 - Backfill and verify locally** - record current counts per
  table/competition/season, run `python postgres_etl/main.py -sc all` in the
  background, and compare counts, investigating any change against the latest
  bronze data. Add read-only quality errors for missing row metadata, a missing
  matching log entry, or a mismatched logged row count. After a complete,
  passing backfill, enforce `NOT NULL` on both columns in all 28 source tables.
  *Done when:* the full load and quality report pass, every existing silver row
  has a matching load log record and one `loaded_at`, all 28 tables have non-null
  constraints, and a rerun of one table/season appends a log entry and points its
  current rows to the new ID. No `public` or Neon table changes.
- [x] **Step 5 - Document and final check** - update the root README,
  `postgres_etl/README.md`, and `docs/DATA_DICTIONARY.md` with the log grain,
  columns, bronze path format, query examples, and backfill result. Check whether
  the CSV exporter uses a fixed column list; if so, include the new row columns
  in exports and update its README. *Done when:* docs describe current behavior,
  `python postgres_etl/main.py -sc 2025 --dry-run` passes, and all three
  declared test commands pass.

## Files / areas

- `common/bronze.py`: report exact version paths on successful reads.
- `postgres_etl/raw_transform.py`, `flat_transform.py`: scope version tracking
  to one table load, including catalog and auxiliary reads.
- `postgres_etl/flat_schema.py`, `flat_loader.py`, `quality.py`: DDL, atomic log
  insertion, and read-only integrity checks.
- `postgres_etl/tests/`, plus focused bronze reader tests in
  `api_requests/tests/test_scrapper.py` where relevant.
- `README.md`, `postgres_etl/README.md`, `docs/DATA_DICTIONARY.md`; inspect
  `tables_to_csv/` only for the affected export contract.

## Data / contracts

- `load_id`: PostgreSQL `UUID NOT NULL`, generated with Python's `uuid4()` once
  for a successful table/competition/season replacement. It is metadata, not a
  source key and not part of the 28 source-table primary keys.
- `loaded_at`: PostgreSQL `TIMESTAMPTZ NOT NULL`, one timezone-aware UTC instant
  generated for that same load; every row and its log entry use the same value.
- `silver.load_log`: `competition_code TEXT NOT NULL`, `season_code TEXT NOT
  NULL`, `table_name TEXT NOT NULL`, `load_id UUID NOT NULL`, `loaded_at
  TIMESTAMPTZ NOT NULL`, `row_count BIGINT NOT NULL`, and `bronze_versions JSONB
  NOT NULL`. Its primary key is `(competition_code, season_code, table_name,
  load_id)`. It is metadata in `silver`, separate from the 28 source tables.
- `bronze_versions` is a sorted, deduplicated JSON array of relative POSIX file
  paths such as
  `euroleague/E2025/v2/games/<fetched_at>_<sha16>.json.gz`. These immutable
  paths identify the exact selected bronze versions; include `_catalog` paths
  and auxiliary reads when they contribute. An empty array is valid only when
  no bronze file was read; no-source skips do not create a log entry.
- `row_count` is the inserted row count and may be zero. A load log entry is
  append-only; replacing current rows never erases previous load history.
  Quality compares row counts only for the load IDs referenced by current rows;
  a historical entry keeps its original count after its rows are replaced.
- Source values, keys, deduplication, and quality rules from 16a remain the
  same. `--quality-only` does not write a log; `--dry-run` does not connect to
  PostgreSQL. A failed load leaves the prior table/season rows and log intact.
- During the additive backfill, old rows may temporarily have NULL provenance.
  No synthetic ID or timestamp is assigned to them. Completion requires all
  historical rows to be reloaded and both columns made non-null.

## Testing

- Unit commands: `cd api_requests && python -m unittest tests.test_scrapper`,
  `python -m unittest discover -s postgres_etl/tests`, and
  `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Focus tests on actual-read version capture, deterministic path ordering,
  catalog/auxiliary inputs, one ID/time per load, zero rows, atomic rollback,
  reruns, and quality errors. Use temporary bronze files and fake cursors; unit
  tests never need a real database or the EuroLeague API.
- Live evidence: E2025 dry run, full local reload and quality report, read-only
  SQL checking counts, non-null metadata, log joins, and one controlled rerun.
  There is no combined Verify command or browser test in this project.

## Notes for the AI

- Record actual files read rather than treating all candidate files as used.
  A game or shot transform may read box scores, play-by-play, or rosters to
  resolve people; the load log must capture those versions too.
- Keep the existing table/season transaction boundary and bare silver table
  names through the local connection's search path. Use parameterized SQL for
  values and registered table names for identifiers.
- Do not drop the 28 silver tables to migrate them. Preserve their row counts
  and previous rows on a failed replacement. Leave Neon untouched.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":9044,"specSha256":"7277e769b0ba811ff721673f834fbe615dd0be208ebcb41dcb61b96ce796b7ed","branch":"refs/heads/feature/silver-provenance","head":"2e714fdd648e389c8ef7f89b0e91a19386e21e98","baseRef":"refs/heads/main","baseCommit":"b577ebd8a009720fe161e7ffd1384115c493a9ea","sourceTree":"98d9300cc34ae75a5e84b7c03b27a0444b26b47b","absentOptional":[]} -->

## Independent review

# Independent Review

> **Generated file.** Holds the active independent-review request or latest
> receipt for the current work item. `/audit independent current` prepares a
> handoff against an approved checkpoint, a fresh reviewer context completes it,
> and `/complete` refuses stale, pending, or changes-requested review state.

**Status:** passed
**Target commit:** 2e714fdd648e389c8ef7f89b0e91a19386e21e98
**Base commit:** b577ebd8a009720fe161e7ffd1384115c493a9ea
**Base ref:** main
**Spec hash:** 7277e769b0ba811ff721673f834fbe615dd0be208ebcb41dcb61b96ce796b7ed
**Prepared by:** codex
**Builder model:** unknown (runtime did not expose exact model)
**Requested reviewer:** codex
**Requested model:** gpt-6-sol
**Requested execution:** automatic
**Requested at:** 2026-09-27T23:32:37.0634239Z
**Workflow:** regular
**Check required:** no
**Reviewer adapter:** codex
**Reviewer model:** gpt-6-sol
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-09-27T23:36:03Z
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Commands

- `git merge-base main HEAD`, `git diff --stat main..HEAD`, `git diff --name-status main..HEAD`: pass; base and 15-file delta match the request.
- `Get-FileHash blueprint/context/current-feature.md -Algorithm SHA256`, `git status --porcelain=v1 --untracked-files=all`: pass; spec hash matches and only review evidence differs from HEAD.
- `git diff --check main..HEAD`: pass.
- `cd api_requests && python -m unittest tests.test_scrapper`: pass.
- `python -m unittest discover -s postgres_etl/tests`: pass, 49 tests.
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass, 19 tests.
- Read-only local PostgreSQL metadata query: pass; 56 non-null provenance columns across 28 source tables and 743 load-log entries, including 15 zero-row entries.
- Read-only full-database row consistency query: unavailable; interrupted after 30 seconds due to an inefficient ad hoc correlated count.

## Evidence

- Reviewed the verified feature 16b spec and all changed code, tests, and documentation in the complete `b577ebd8a009720fe161e7ffd1384115c493a9ea..2e714fdd648e389c8ef7f89b0e91a19386e21e98` delta. Followed the bronze reader, raw and flat transforms, transactional loader, schema, quality checks, connection search path, CLI, and CSV export contract. Excluded generated data, logs, caches, retired code, and unrelated source.
- The bronze callback records the path selected by `read_bytes` after a successful decompression. Each table resets its dependency set before source selection, including lookup caches. The row INSERT and append-only log INSERT share the existing table/season transaction and one UUID and UTC timestamp.
- The quality queries check missing row metadata, matching log identity and time, and current row counts. Source table names are registered identifiers; inserted values are parameterized. Focused tests cover version selection, catalog and auxiliary reads, zero rows, reruns, rollback, and quality errors. No skipped, focused, or placeholder tests were found in the declared suites.
- Checked the Python, database, data, and testing rules in `blueprint/context/coding-standards.md`. There is no project lint, typecheck, build, security scan, performance benchmark, or browser test command.

## Findings

- None newly found. Existing F-05 and F-06 remain unchanged; neither is a P0 or P1 blocker.

## Remaining risk

- The independent full-database row consistency query did not complete; live evidence here is limited to schema constraints and log totals. The verified spec and documentation record the earlier full backfill and row checks.
- Existing F-06 [P2] remains open for refresh regression test coverage.

# Fix: Neon dry run scope-type mismatch and unavailable-count label

**Type:** Fix
**Status:** verified
**Branch:** fix/neon-dry-run-scope-type-and-unavailable-label
**Fixes:** F-09, F-10

## The problem

- **F-09 [P2]** `neon_publish/publish.py:128` `_remote_state` skips a Neon table only when preflight reports a missing table or missing scope column. If `competition_code` or `season_code` exists with the wrong type (for example integer), preflight reports `public.<target>.<column>: <type>, expected <type>`, but the preview still runs `_count` with a text parameter. Postgres raises `InvalidTextRepresentation`, so the dry run fails with a database error instead of reporting the schema problem (the same failure class as F-08).
- **F-10 [P3]** `neon_publish/main.py:61` prints `missing` for every `None` count. Since F-08, `None` also means an existing but incompatible table, so the label misleads.

## The fix

- In `_remote_state`, treat a reported type problem on a scope column as unavailable too: extend the existing skip condition with a helper matching `.{column}: ` followed by a type issue (the `public.<target>.<column>: <kind>, expected ...` form from `contract.inspect_target`), for `competition_code` and, for non-global tables, `season_code`. Same handling as the other unavailable cases: `counts[name] = None`, `sums[name] = {}` for game tables.
- In `main.py`, print `unavailable` instead of `missing` for a `None` count. The schema issues printed above already say whether the table is missing or incompatible; no new state is returned.
- Must not break: a real publish still refuses on any preflight problem; compatible tables still get counts and checksums.

## Build steps

- [x] 1. Repair both in `publish.py` and `main.py`, and add tests in `neon_publish/tests/test_publish.py`: integer `competition_code` and integer `season_code` (season-scoped table) yield `None` counts and no query error; a global table ignores `season_code`; a table with a non-scope type problem still gets counts; the CLI label reads `unavailable` for a `None` count.
  **Done when:** the new type-mismatch tests fail without the repair and pass with it, and `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export` passes.

## Verify

- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`
- No live Neon call; the dry-run behavior is exercised with the existing fake cursor tests.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":2457,"specSha256":"6a8b4ee02c7d45996f1013f49706dcc4062439c1114038c003f78aa7a605ab53","branch":"refs/heads/fix/neon-dry-run-scope-type-and-unavailable-label","head":"4a34023dc4fb7242b5bf5928c6a6c9e7089da703","baseRef":"refs/heads/main","baseCommit":"4a34023dc4fb7242b5bf5928c6a6c9e7089da703","sourceTree":"7c435e768fec424da72245b112d03b6dc17d4e2e","absentOptional":[]} -->

## Findings

### neon-dry-run-scope-type-and-unavailable-label/F-07 [P2] closed - Preflight misses stricter nullability on an expected column

**File:** neon_publish/contract.py:56
**Found:** 2026-09-28 by independent /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** `inspect_target` flags a Gold `NOT NULL` field mapped to a nullable Neon column, but accepts the reverse. A Neon column marked `NOT NULL` where Gold permits null passes preflight and dry run, then COPY can fail after the transaction begins. This violates the promised incompatible-schema preflight and leaves the operator with a misleading preview.
**Suggested fix:** Flag `nullable == "NO"` when the Gold field does not specify `NOT NULL`, and cover both nullability directions with a preflight test.
**Resolution:** Fixed on `fix/neon-preflight-nullability-and-preview`: `inspect_target` now reports a Neon `NOT NULL` column whose Gold field is nullable and not a key column; covered by `NullabilityTests` in `neon_publish/tests/test_publish.py`. Awaiting `/audit` re-review. Re-reviewed by /audit 2026-09-29 (scope: neon_publish; all lenses): the new `elif` in `inspect_target` reports a Neon NOT NULL column whose Gold field is nullable and non-key, the key exemption is correct because Gold key fields are NOT NULL, and `NullabilityTests` cover both directions. Closed.

### neon-dry-run-scope-type-and-unavailable-label/F-08 [P2] closed - Preview queries incompatible targets after preflight reports missing columns

**File:** neon_publish/publish.py:132
**Found:** 2026-09-28 by independent /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** `_remote_state` still counts every existing incompatible table using the scope columns, and calls `game_rows` for incompatible play-by-play or shots tables. If `competition_code`, `season_code`, or `game_code` is missing, the read-only preview raises a database error before it can return its count and migration report. These are precisely the schema differences preflight is meant to report.
**Suggested fix:** Avoid querying columns that preflight found missing; report unavailable remote counts or game plans for that table while preserving the schema issues, and test a missing scope or game-code column.
**Resolution:** Fixed on `fix/neon-preflight-nullability-and-preview`: `_remote_state` skips counts and per-game rows for a table missing a needed scope or `game_code` column, so the dry run reports instead of failing; covered by `PreviewOfIncompatibleTargetsTests`. Awaiting `/audit` re-review. Re-reviewed by /audit 2026-09-29 (scope: neon_publish; all lenses): `_remote_state` no longer queries a table missing a needed scope or `game_code` column, every game table still gets a `sums` entry so `_snapshot` cannot KeyError, and a real publish still refuses on any preflight problem. Adjacent gaps in the same preview path are recorded separately as F-09 and F-10. Closed.

### neon-dry-run-scope-type-and-unavailable-label/F-09 [P2] closed - Preview still queries scope columns whose Neon type is wrong

**File:** neon_publish/publish.py:139
**Found:** 2026-09-29 by /audit (scope: neon_publish; lenses: quality, security, performance, tests)
**Why it matters:** F-08 skipped queries for missing columns, but `_count` still filters an existing `competition_code` or `season_code` column with a text parameter when preflight has already reported a different type. A local read-only check of the same predicate shape (`WHERE competition_code = 'E'` on an integer column) raises `InvalidTextRepresentation`. The dry run then fails with a database error instead of returning the counts and schema report, the same failure class as F-08 for another difference preflight reports.
**Suggested fix:** Extend the unavailable-table test to include a reported type problem on a scope column (the `public.<target>.<column>: <type>, expected <type>` issue), and test an integer `competition_code` or `season_code`.
**Resolution:** Closed 2026-09-29 by /audit current: `_wrong_type` matches only the `public.<t>.<col>: <kind>, expected ...` form (not the NOT NULL or missing-column issues), applies to competition_code and, for non-global tables, season_code; tests cover both columns, a global table, and non-scope type problems.

### neon-dry-run-scope-type-and-unavailable-label/F-10 [P3] closed - Dry run prints "missing" for an existing table whose count is unavailable

**File:** neon_publish/main.py:61
**Found:** 2026-09-29 by /audit (scope: neon_publish; lens: quality)
**Why it matters:** After F-08, `_remote_state` returns `None` for existing incompatible tables as well as missing ones, and the CLI prints `missing` for every `None`. The schema issues above it explain the difference, but the count line is misleading for a table that exists.
**Suggested fix:** Print `unavailable` for a `None` count when the table exists (or distinguish the two cases in the returned state) and test the label for both.
**Resolution:** Closed 2026-09-29 by /audit current: CLI prints `unavailable` for a None count; test asserts the label and that `missing` is absent.

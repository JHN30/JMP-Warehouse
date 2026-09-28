# Fix: Neon preflight nullability and incompatible-table preview

**Type:** Fix
**Status:** verified
**Branch:** fix/neon-preflight-nullability-and-preview
**Fixes:** F-07, F-08

## The problem

Both findings are gaps in the read-only Neon schema preflight that feature 30f
added, found by its independent review (`neon_publish/contract.py`,
`neon_publish/publish.py`):

- **F-07.** `inspect_target` reports a Gold `NOT NULL` field mapped to a nullable
  Neon column, but not the reverse. A Neon column that is `NOT NULL` where Gold
  allows NULL passes preflight and dry run, then `COPY` can fail after the
  transaction has begun, so the preview promised more than the publish can do.
- **F-08.** `_remote_state` counts every existing target table with its scope
  columns and, for `play_by_play` and `shots`, reads per-game rows, even when
  preflight has already reported a missing `competition_code`, `season_code` or
  `game_code` column. The query then fails with a database error (and aborts the
  read-only transaction), so the dry run cannot return the counts and migration
  report it exists to give. These are exactly the differences preflight reports.

## The fix

- **F-07:** in `inspect_target`, when a Neon column is `NOT NULL` (`is_nullable`
  `NO`), the Gold field must also be required: `NOT NULL` in its kind or a column of
  the Gold primary key. Otherwise report `public.<target>.<column>: NOT NULL in Neon
  but nullable in Gold`. Existing checks are unchanged.
- **F-08:** in `_remote_state`, do not query a table whose preflight issues include a
  missing column that its queries need: `competition_code` (and `season_code` for
  season-scoped tables) for the count, and `game_code` for the per-game rows. Such a
  table gets `counts[name] = None` (unavailable) and an empty checksum map, the same
  as a missing table, so the plan replaces every game and shrink checks skip it.
  The schema issues are still logged. Other problem tables keep the current
  behavior (count, and `game_rows` for game tables).
- Must not break: the 26-table allowlist, a real publish still refuses when any
  preflight problem exists, no DDL or writes in dry run, redaction, and the current
  messages for existing checks.
- No new abstraction; a small helper for the "needed columns are present" test is
  enough.

## Build steps

- [x] **Step 1 - Repair both and test.** Implement the two changes with focused
  tests in `neon_publish/tests/test_publish.py`. *Done when:* tests cover (F-07)
  a Neon `NOT NULL` column for a nullable Gold field reported, a `NOT NULL` Neon
  column for a Gold `NOT NULL` or key field accepted, and both directions on one
  table; (F-08) a target missing `competition_code`, `season_code` or `game_code`
  gives a dry run that returns without querying that table and still lists the
  missing columns, a season-scoped table missing only `game_code` is still counted,
  a real publish of such a table still raises the preflight error, and an ordinary
  problem table is queried as before; `python -m unittest
  neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export` passes along
  with the other declared suites.

## Verify

- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`,
  `python -m unittest discover -s gold_etl/tests`, `python -m unittest discover -s
  postgres_etl/tests`, and `cd api_requests && python -m unittest tests.test_scrapper`.
- No Neon call is made (`python neon_publish/main.py --list-tables` only lists the 26
  tables); live behavior is covered by the fake-connection tests.
- On `/complete`, F-07 and F-08 are marked `fixed` by `/implement` and re-reviewed by
  `/audit` before they close.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":3708,"specSha256":"4429d3f6366c8d19e6e0b21f8cf25be59d8962db78fb048fd41f8a037aa27ee8","branch":"refs/heads/fix/neon-preflight-nullability-and-preview","head":"0f24ca318c057124276967f782d13921f5568a15","baseRef":"refs/heads/main","baseCommit":"0f24ca318c057124276967f782d13921f5568a15","sourceTree":"7677149b9e26b9adbbcef5e40ba6fc52e9137fbd","absentOptional":[]} -->

# Fix: UTC timestamps and view wording

**Type:** Fix
**Status:** verified
**Branch:** fix/utc-timestamps-and-view-wording
**Fixes:** F-03, F-04

## The problem

**F-03 - zone-aware dates in `TIMESTAMP` columns.** `cast` in
`postgres_etl/flat_transform.py` returns `parse_source_timestamp(value)` for
both `TIMESTAMP` and `TIMESTAMPTZ` columns. A source date with a zone offset
(`...Z` or `+02:00`) becomes a zone-aware `datetime`; bound to a `TIMESTAMP`
(without time zone) column, PostgreSQL converts it through the session time
zone. `app_standings.streak_history` (via `js_iso`) already converts such
values to UTC, so the two would disagree whenever the session time zone is not
UTC. Today nothing differs: no source date in a `TIMESTAMP` column carries an
offset (the 14-digit UTC form is only used by `shots.shot_at`, a `TIMESTAMPTZ`
column), and the local session time zone is `GMT`. The rule is still
session-dependent and should not be.

**F-04 - "read-only" views that accept writes.** `docs/DATA_DICTIONARY.md:46`
and `neon_publish/README.md:31` call the old-name Neon views "read-only". A
plain `CREATE VIEW etl_flat_x AS SELECT * FROM app_x` is automatically
updatable, so writes through the old name would reach `app_x`. Nothing writes
through them (the app only reads), so this is wording only.

## The fix

- One rule for zone-aware dates: move the "aware -> UTC, zone dropped" step
  that `js_iso` does today into a small helper in
  `postgres_etl/raw_transform.py` (next to `parse_source_timestamp`), use it in
  `js_iso`, and use it in `cast` for `TIMESTAMP` columns. `TIMESTAMPTZ`
  columns keep the aware value (correct as is). Zone-less values are unchanged.
- Reword the two docs lines to "a view under the old name" (no "read-only").
- Must not break: every stored value today stays identical (no source value
  has an offset), `app_standings` output is unchanged, and `TIMESTAMPTZ`
  columns (`games.scheduled_at`, `shots.shot_at`) still store the exact instant.
  No schema change, no new dependency, no enforcement of read-only views
  (a trigger or grants would be machinery with no current requirement).

## Build steps

- [x] 1. **Zone-aware dates stored as UTC in `TIMESTAMP` columns (F-03).**
  Add the helper, use it in `js_iso` and in `cast` for `TIMESTAMP` only. Tests
  in `postgres_etl/tests/`: `cast("2025-09-01T12:00:00+02:00", "TIMESTAMP")`
  is the zone-less `2025-09-01 10:00:00`; a `Z` value and the 14-digit form
  give the same UTC wall time; a zone-less value is unchanged;
  `TIMESTAMPTZ` still returns the aware value; `js_iso` output is unchanged for
  the existing cases. Mark F-03 `fixed`.
  Done when: the three test commands in `AGENTS.md` pass, and a local reload of
  E2025 and E2026 for the tables with `TIMESTAMP` columns leaves every
  `TIMESTAMP` value identical to before the reload (compared per table) with
  0 quality errors.

- [x] 2. **Docs wording (F-04).** Replace "read-only view" in
  `docs/DATA_DICTIONARY.md` and `neon_publish/README.md` with wording that just
  says a view is kept under the old name. Mark F-04 `fixed`.
  Done when: `grep -rn "read-only view" --include=*.md .` outside `old/` and
  `blueprint/history/` finds nothing, and the three test commands pass.

## Verify

- The three test commands in `AGENTS.md` pass, including the new cast tests.
- Step 1's before/after comparison of `TIMESTAMP` values shows no difference.
- No Neon access and no API requests are needed.
- The change touches only data parsing and docs, so the `when-sensitive`
  independent review is not expected to be selected; `/audit current` can
  re-review F-03 and F-04 to close them.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":3716,"specSha256":"8d266584fb7b9663ff182c743c854a1eb72ed8358132af857315929da8a3398d","branch":"refs/heads/fix/utc-timestamps-and-view-wording","head":"0b3f1aa8d1d5c72d5ecd3021bc5e7dd40039541e","baseRef":"refs/heads/main","baseCommit":"0b3f1aa8d1d5c72d5ecd3021bc5e7dd40039541e","sourceTree":"c0fb6c6bd880f25e88fc3acd33fae0837d683cf0","absentOptional":[]} -->

## Findings

### utc-timestamps-and-view-wording/F-03 [P3] closed - Zone-aware dates would be stored differently in TIMESTAMP columns

**File:** postgres_etl/flat_transform.py:60
**Found:** 2026-09-24 by /audit (scope: current; lens: quality)
**Why it matters:** Parsing is now one rule, but storage still differs for a
source date that carries a zone offset: `app_standings.streak_history` converts
it to UTC, while the older `TIMESTAMP` (without time zone) columns such as
`etl_flat_standings_calendar_streaks.start_at` receive the aware value and
PostgreSQL converts it through the session time zone. No source date has an
offset today (all streak and round dates are zone-less), so nothing differs yet.
**Suggested fix:** Only if an offset ever appears: normalize aware values to UTC
before binding them to `TIMESTAMP` columns (or move those columns to
`TIMESTAMPTZ` together with the app). None needed now; no current requirement is
lost by leaving it.
**Resolution:** fixed in `fix/utc-timestamps-and-view-wording`: a new `utc_wall_time` helper in `postgres_etl/raw_transform.py` turns a zone-aware value into zone-less UTC; `cast` uses it for `TIMESTAMP` columns and `js_iso` uses it too, so both follow one rule and no session time zone can shift a value. `TIMESTAMPTZ` columns keep the aware value. Test: `test_timestamp_columns_store_zone_aware_dates_as_utc`. A local reload of E2025 and E2026 left every `TIMESTAMP` value in all 7 affected tables identical. Awaiting re-review.

Re-reviewed 2026-09-25 by /audit (scope: current; all lenses): **closed.** `cast` (`postgres_etl/flat_transform.py:59-62`) now returns `utc_wall_time(...)` for `TIMESTAMP` and the aware value for `TIMESTAMPTZ`; every flat value goes through `cast` (`flat_transform.py:85`), so no `TIMESTAMP` column bypasses the rule. `js_iso` uses the same helper, so its output is unchanged (existing js_iso assertions still pass). The new test covers `+02:00`, `Z`, the 14-digit form, zone-less values and `TIMESTAMPTZ`. No new defect; 43 postgres_etl tests pass.

### utc-timestamps-and-view-wording/F-04 [P3] closed - Old-name views are called read-only but accept writes

**File:** postgres_etl/flat_schema.py:619
**Found:** 2026-09-24 by /audit independent (scope: current; lens: quality)
**Why it matters:** The spec, `docs/DATA_DICTIONARY.md:46` and
`neon_publish/README.md:31` describe the Neon `etl_flat_*` views as read-only.
`CREATE VIEW etl_flat_x AS SELECT * FROM app_x` is a simple single-table view,
which PostgreSQL makes automatically updatable: `INSERT`, `UPDATE` and `DELETE`
through the old name change rows in `app_x`. Nothing in this repository writes
through the old names (an old-version publish would fail on `COPY` into a view
and roll back), and the web app only reads, so no data is at risk today. The
docs just promise a guarantee the code does not give.
**Suggested fix:** Reword the two docs lines to say "view" (or "view that the
app reads") instead of "read-only view". Adding a trigger, rule or role grants
to enforce read-only would be machinery for no current requirement. No current
requirement is lost.
**Resolution:** fixed in `fix/utc-timestamps-and-view-wording`: both docs lines now say a view is kept under the old name, without "read-only". No code change. Awaiting re-review.

Re-reviewed 2026-09-25 by /audit (scope: current; all lenses): **closed.** `docs/DATA_DICTIONARY.md:46` and `neon_publish/README.md:30-31` now say the old name is kept as a view; no project doc outside `old/` and `blueprint/history/` still calls these views read-only.

# Findings

> **Generated file.** The findings ledger: review findings raised by `/audit`
> against the work in progress, each with a durable ID, severity (P0-P3), and
> status. `/implement` marks repaired findings `fixed`, a later `/audit` pass
> moves them to `closed`, and `/complete` refuses to merge while any P0 or P1
> finding is `open` or `fixed`, then archives resolved findings with the work
> and resets this file.

### F-03 [P3] unverified - Zone-aware dates would be stored differently in TIMESTAMP columns

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
**Resolution:**

### F-04 [P3] open - Old-name views are called read-only but accept writes

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
**Resolution:**

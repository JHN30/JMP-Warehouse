# Findings

> **Generated file.** The findings ledger: review findings raised by `/audit`
> against the work in progress, each with a durable ID, severity (P0-P3), and
> status. `/implement` marks repaired findings `fixed`, a later `/audit` pass
> moves them to `closed`, and `/complete` refuses to merge while any P0 or P1
> finding is `open` or `fixed`, then archives resolved findings with the work
> and resets this file.

### F-01 [P3] open - js_iso re-parses streak dates separately from the TIMESTAMP cast

**File:** postgres_etl/raw_transform.py:127
**Found:** 2026-09-24 by /audit (scope: current; lens: quality, tests; independent review)
**Why it matters:** `app_standings.streak_history` dates come from `js_iso`, while
`etl_flat_standings_calendar_streaks.start_at`/`end_at` (what the app reads today)
come from `cast(value, "TIMESTAMP")` in `flat_transform.py:60`. The two parsers
already differ: `cast` accepts the 14-digit `YYYYMMDDHHMMSS` form and `js_iso` does
not, and a zone-aware source value is converted to UTC by `js_iso` but stored
through the session time zone by the TIMESTAMP column. A bad value also raises a
bare `fromisoformat` error from inside the raw row generator, without the table,
field and season context the coding standards require. Today this is latent:
read-only SQL found 0 streak differences across 12,325 rows and every stored
streak timestamp is zone-less midnight. The `js_iso` zone-aware and
fractional-second branches have no unit test.
**Suggested fix:** Keep one parsing rule. Either reuse the existing TIMESTAMP
parsing (move the parse part of `cast` to a helper both modules can import) and
format its result, or drop the zone-aware branch if the source is always
zone-less. Wrap a parse failure in a `ValueError` naming `app_standings`, the
field and the season, and add a test for a zone-aware or fractional value. No
current requirement is lost.
**Resolution:**

### F-02 [P3] open - js_iso is wedged into the module constants block

**File:** postgres_etl/raw_transform.py:137
**Found:** 2026-09-24 by /audit (scope: current; lens: quality; independent review)
**Why it matters:** `js_iso` was inserted between `STANDINGS_FILE` and
`LIVE_TEAM_MARKER`, so the constant follows the function body with no blank
lines (PEP 8 E305) and the constants block is split, unlike the rest of the file.
**Suggested fix:** Move `LIVE_TEAM_MARKER` up next to `STANDINGS_FILE` (or move
`js_iso` below the constants) with two blank lines around the function. No
behaviour change; no current requirement is lost.
**Resolution:**

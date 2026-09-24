# Fix: Unify streak date parsing

**Type:** Fix
**Status:** verified
**Branch:** fix/unify-streak-date-parsing
**Fixes:** F-01, F-02

## The problem

`app_standings.streak_history` dates are formatted by `js_iso` in
`postgres_etl/raw_transform.py`, which parses source timestamps with its own rule.
Every other timestamp column goes through `cast(value, "TIMESTAMP")` in
`postgres_etl/flat_transform.py`. The two rules already differ:

- `cast` accepts the 14-digit `YYYYMMDDHHMMSS` form; `js_iso` rejects it.
- A bad value makes `js_iso` raise a bare `fromisoformat` error from inside the
  row generator, without the table, field and season context the coding
  standards require (F-01).
- `js_iso`'s zone-aware and fractional-second branches have no test (F-01).
- `js_iso` sits between two module constants, splitting the constants block and
  breaking PEP 8 spacing (F-02).

The issue is latent today: all stored streak dates are zone-less midnight, and the
feature 9 equivalence check found 0 differences.

## The fix

- One parsing rule: move the timestamp parsing out of `cast` into a helper in
  `raw_transform.py`, named for example `parse_source_timestamp`. It accepts a
  `datetime`, the 14-digit form (as UTC), or ISO 8601 with an optional `Z` or
  offset. `cast` keeps its behaviour by calling the helper; `raw_transform` owns
  the helper because `flat_transform` already imports from it, and the reverse
  import would be circular.
- `js_iso` formats the helper's result: zone-aware values are converted to UTC,
  zone-less values are read as UTC, and the output is `YYYY-MM-DDTHH:MM:SS.mmmZ`,
  unchanged for today's data.
- A parse failure in `_standings_page_rows` is re-raised as `ValueError` naming
  `app_standings`, the field (`streak_history.startAt` or `.endAt`), the
  standings file and the season.
- Move `js_iso` below the constants block, so `STANDINGS_FILE` and
  `LIVE_TEAM_MARKER` stay together, with two blank lines around the function (F-02).
- Must not break: the loaded values of every existing `TIMESTAMP`/`TIMESTAMPTZ`
  column, and `app_standings` output (still 0 differences against the app's
  current query). No new dependency, module or configuration.

## Build steps

- [x] 1. **Shared parser, context errors, tidy placement.** Add the helper, make
  `cast` and `js_iso` use it, add the contextual error in `_standings_page_rows`,
  and move `js_iso` below the constants. Tests: 14-digit value, zone-aware offset
  converted to UTC, fractional seconds kept to milliseconds, `None`/empty giving
  `None`, and an invalid date raising `ValueError` that mentions `app_standings`
  and the season. Existing timestamp tests keep passing.
  Done when: the three test commands in `AGENTS.md` pass, and
  `python postgres_etl/main.py -sc all -tb app_standings games standings_calendar_streaks --dry-run`
  succeeds for all seasons.

## Verify

- The three test commands in `AGENTS.md` are green, including the new `js_iso`
  and parser tests.
- All-season dry run of `app_standings`, `games` (TIMESTAMPTZ) and
  `standings_calendar_streaks` (TIMESTAMP) succeeds.
- Reload `app_standings` and `standings_calendar_streaks` locally, then rerun the
  feature 9 equivalence comparison: 0 differences.
- `/audit` re-reviews the repair, so F-01 and F-02 can move from `fixed` to `closed`.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":3318,"specSha256":"6b5a4aa8abf2763bc9ceca76c2a65e43bc3071f9d3518215e0cd5bef1bde23eb","branch":"refs/heads/fix/unify-streak-date-parsing","head":"a6eb78c24e63545874c2db8ff987f51d48ea306b","baseRef":"refs/heads/main","baseCommit":"a6eb78c24e63545874c2db8ff987f51d48ea306b","sourceTree":"f079af5e218fedfaa6e32a1788f7d40ad3abd1b3","absentOptional":[]} -->

## Findings

### unify-streak-date-parsing/F-01 [P3] closed - js_iso re-parses streak dates separately from the TIMESTAMP cast

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
**Resolution:** fixed in `fix/unify-streak-date-parsing`: `parse_source_timestamp` in `raw_transform.py` is now the single parsing rule for `cast` (TIMESTAMP/TIMESTAMPTZ) and `js_iso`; bad streak dates raise a `ValueError` naming `app_standings`, the field, the standings file, the club and the season; tests cover the 14-digit form, offsets, fractional seconds, empty values and a bad date. Closed 2026-09-24 by /audit (scope: current; all lenses): re-review of `raw_transform.py` and `flat_transform.py` confirms one parser for all 15 timestamp columns and `js_iso`, the contextual error is raised and tested, the 14-digit, offset and fractional branches are tested, and the all-season dry run plus the standings equivalence check still show 0 differences. No new defect in the repair.

### unify-streak-date-parsing/F-02 [P3] closed - js_iso is wedged into the module constants block

**File:** postgres_etl/raw_transform.py:137
**Found:** 2026-09-24 by /audit (scope: current; lens: quality; independent review)
**Why it matters:** `js_iso` was inserted between `STANDINGS_FILE` and
`LIVE_TEAM_MARKER`, so the constant follows the function body with no blank
lines (PEP 8 E305) and the constants block is split, unlike the rest of the file.
**Suggested fix:** Move `LIVE_TEAM_MARKER` up next to `STANDINGS_FILE` (or move
`js_iso` below the constants) with two blank lines around the function. No
behaviour change; no current requirement is lost.
**Resolution:** fixed in `fix/unify-streak-date-parsing`: `LIVE_TEAM_MARKER` moved next to `STANDINGS_FILE`; `parse_source_timestamp` and `js_iso` follow the constants block with PEP 8 spacing. Closed 2026-09-24 by /audit (scope: current; all lenses): the constants block is contiguous and both functions have two blank lines around them.

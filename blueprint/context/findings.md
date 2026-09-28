# Findings

> **Generated file.** The findings ledger: review findings raised by `/audit`
> against the work in progress, each with a durable ID, severity (P0-P3), and
> status. `/implement` marks repaired findings `fixed`, a later `/audit` pass
> moves them to `closed`, and `/complete` refuses to merge while any P0 or P1
> finding is `open` or `fixed`, then archives resolved findings with the work
> and resets this file.

### F-05 [P3] unverified - A legitimate correction that lowers an accumulated feed would be refused

**File:** api_requests/scrapper.py:497
**Found:** 2026-09-27 by /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the guard treats any drop in clubs or total games of an
accumulated feed as stale. If EuroLeague ever corrects a feed downward (for
example removing a duplicated player or an annulled game), the correction is
refused until later games lift the totals above the stored ones. After the
season's last game that never happens, so the stored version would stay. No
such correction has been observed; the manifest keeps the refused answer.
**Suggested fix:** none needed unless it happens. If it does, the `rejected`
manifest records show it; a one-off manual re-fetch without the guard (or a
`--refresh-current` override flag) would accept the correction.
**Resolution:**

### F-07 [P2] open - Preflight misses stricter nullability on an expected column

**File:** neon_publish/contract.py:56
**Found:** 2026-09-28 by independent /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** `inspect_target` flags a Gold `NOT NULL` field mapped to a nullable Neon column, but accepts the reverse. A Neon column marked `NOT NULL` where Gold permits null passes preflight and dry run, then COPY can fail after the transaction begins. This violates the promised incompatible-schema preflight and leaves the operator with a misleading preview.
**Suggested fix:** Flag `nullable == "NO"` when the Gold field does not specify `NOT NULL`, and cover both nullability directions with a preflight test.
**Resolution:**

### F-08 [P2] open - Preview queries incompatible targets after preflight reports missing columns

**File:** neon_publish/publish.py:132
**Found:** 2026-09-28 by independent /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** `_remote_state` still counts every existing incompatible table using the scope columns, and calls `game_rows` for incompatible play-by-play or shots tables. If `competition_code`, `season_code`, or `game_code` is missing, the read-only preview raises a database error before it can return its count and migration report. These are precisely the schema differences preflight is meant to report.
**Suggested fix:** Avoid querying columns that preflight found missing; report unavailable remote counts or game plans for that table while preserving the schema issues, and test a missing scope or game-code column.
**Resolution:**

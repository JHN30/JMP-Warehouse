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

### F-08 [P3] unverified - The roughly 25 MB Neon size for 30h-30j is an estimate, not a measurement

**File:** blueprint/context/current-feature.md:76
**Found:** 2026-10-02 by /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the figure comes from Silver table sizes scaled by row counts. Neon was
153 MB of the 512 MB free tier when measured, so there is headroom, but nothing has been
published yet to confirm the real size, including primary-key index overhead.
**Suggested fix:** after the migrations are applied and E2025 and E2026 are published,
compare `pg_database_size` with the 153 MB baseline.
**Resolution:**

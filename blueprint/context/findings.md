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

### F-06 [P2] open - Refresh regression tests were removed during the publish pause

**File:** neon_publish/tests/test_publish.py:23
**Found:** 2026-09-27 by independent /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** The former `RefreshCommandTests` covered load failure and retry state, fetch no-op, summary parsing, and reporting stats feeds kept from an earlier fetch. The replacement has one successful `--skip-fetch` test. A regression in the normal fetch path or the pending-load state can now pass all configured suites while `python pipeline.py` skips or misreports a needed load.
**Suggested fix:** Restore focused fake-stage tests for a changed fetch, unchanged fetch, load failure and retry, and the kept-feed summary, using the paused publishing contract.
**Resolution:**

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

### F-20 [P3] open - The Neon preflight looks up seasons with a hard-coded EuroLeague code

**File:** neon_publish/main.py:56
**Found:** 2026-10-26 during the feature 18 brief
**Why it matters:** the publish preflight checks `silver.seasons` with competition `E`
hard-coded. Harmless today, because the publisher refuses any other competition
(`neon_publish/publish.py:179`), but it must change when EuroCup publishing is approved.
**Suggested fix:** pass the competition through when EuroCup publishing is built; no
change needed before then.
**Resolution:**

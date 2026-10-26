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

### F-11 [P3] open - The unattended missing-URL branch the scheduled run relies on has no unit test

**File:** pipeline.py:219
**Found:** 2026-10-24 by /audit independent (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the spec's unattended-safety contract is that the scheduled
run "never waits at a hidden prompt" and fails with "FAILED at Publish (missing
Neon URL)". The task action provides the non-console stdin (probe: the exact
action string gives `stdin.isatty()` False in a new hidden console, against True
without the empty pipe). The Python half is `resolve_neon_url`'s
`if not interactive: return None, ...` branch and `refresh`'s missing-URL return.
No test covers that case. Tests at neon_publish/tests/test_publish.py:765 and :870
pass `interactive=False` only with a URL present, and :843 only checks that the
prompt waits for Gold quality. If that guard regressed, `getpass` on Windows reads
the console directly, not stdin. The scheduled run would then hang in its hidden
window until the 2-hour limit, with no log result or summary. The code is correct
today; this is a coverage gap on behavior the feature now depends on.
**Suggested fix:** add one unit test that calls `refresh(build_parser().parse_args(["--skip-fetch"]), "E2025", ...)`
with a passing stage runner, `environ={}`, a missing `dotenv_path`,
`interactive=False` and a prompt that fails the test. Assert the result is
`(1, "FAILED at Publish (missing Neon URL)", ...)` and that `neon_publish/main.py`
never ran. No current requirement would be lost.
**Resolution:**

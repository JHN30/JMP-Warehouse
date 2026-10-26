# Fix: Test the points-correction skips and share the gap reasons

**Type:** Fix
**Status:** verified
**Branch:** fix/test-the-points-correction-skips-and-share-the-gap-reasons
**Fixes:** F-22, F-23, F-24

## The problem

The F-14 points correction in `postgres_etl/raw_transform.py` has two follow-ups from its audit.

- **F-22 (tests).** `test_points_are_corrected_only_when_the_makes_prove_them`
  (`postgres_etl/tests/test_raw_etl.py:195`) covers one corrected team and one team left as
  given. No test covers the four paths that must leave the source untouched:
  1. `points` is unrecorded for the game (`"points" in gaps`).
  2. The game has no player box score (`NO_BOX_SCORE`).
  3. A player's shooting make is missing (`made_points` returns `None`).
  4. The game has no score (unplayed, or not in `games`).

  A regression in any of these would silently rewrite source values.
- **F-23 (fragile coupling).** `postgres_etl/quality.py:245-247` tells
  `unrecorded_stat_nulled` and `points_corrected` apart with
  `row.reason LIKE '%corrected%'`. The two reason strings are literals in
  `raw_transform.py:513` and `:523`. Rewording either one would silently move rows between
  the two warnings. An unrecorded `points` gap and a correction both use
  `stat_name = 'points'`, so `stat_name` alone cannot separate them.

## The fix

- Move the two reason texts into module constants in `raw_transform.py`:
  - `UNRECORDED_REASON = "0 for every player: not recorded; stored as NULL"`
  - `CORRECTED_REASON = "team makes equal the score but points do not; points (and PIR by the same amount) corrected from the makes: "`

  The gap rows use these constants. The stored text stays byte for byte the same, so the
  Silver rows already loaded keep matching and nothing needs reloading.
- Import both constants in `quality.py`, which already imports `raw_transform` through
  `flat_transform`, so no import cycle is added. Then match on them exactly:
  - `unrecorded_stat_nulled`: `row.stat_name <> '*' AND row.reason = '<UNRECORDED_REASON>'`
  - `points_corrected`: `row.stat_name = 'points' AND row.reason LIKE '<CORRECTED_REASON>%%'`

  Neither constant contains `'`, `%` or `_`, so both are safe as fixed SQL literals. They
  are code constants, not input. A comment at the constants notes this.
- Add one test for the four skip paths, asserting unchanged player points and PIR, and no
  `points` correction row. Only the test changes behavior coverage. No columns, tables or
  warning names change.

Must not break:
- the existing F-14 test
- `test_points_checks_are_season_scoped_warnings`
- the stored reason text
- the current warning counts

## Build steps

- [x] 1. Share the reason constants between `raw_transform.py` and `quality.py`, and match
  on them in the two gap checks. Update the `NOT LIKE` assertion in
  `test_points_checks_are_season_scoped_warnings`, which should now assert that each query
  contains its constant.
  **Done when:**
  - `python -m unittest discover -s postgres_etl/tests` passes.
  - A read-only SQL count over all of `silver.game_stat_gaps` (E and U) gives the same
    `unrecorded_stat_nulled` and `points_corrected` counts with the old and new predicates.
- [x] 2. Add `test_points_correction_skips_unproven_games` to `test_raw_etl.py`, covering the
  four skip paths above:
  - game 1 with `points` 0 for every player
  - a game with an empty player list
  - game 1 with one player missing `fieldGoalsMade3`
  - unplayed game 2, and a game code not in `games`

  Every case except the empty player list uses a box score the correction would otherwise
  rewrite: team makes equal the score, points do not. An empty player list has nothing to
  rewrite, so that case only asserts there is no correction row. In each case, assert
  unchanged `points` and `valuation`, and no gap row whose reason starts with
  `CORRECTED_REASON`.
  **Done when:**
  - The test passes.
  - It fails when the `"points" in gaps` skip is removed. Check this with a temporary
    local mutation, which is not committed.
  - The F-22 and F-23 findings are marked `fixed`.

- [x] 3. Repair F-24. The "no box score" case still has the road player `C`, so the game is
  never `NO_BOX_SCORE`. Give each case its own road side and an empty road player list for
  that case, so the game has no players at all. Assert that its only gap row is `*`, which
  proves the no-box-score path was reached. The other cases stay as they are.
  **Done when:**
  - The test passes.
  - A temporary local mutation that drops the `gaps == NO_BOX_SCORE` skip is checked, and
    the result is recorded either way. With no players there is nothing to correct, so the
    mutant is expected to survive.
  - F-24 is marked `fixed`.

## Verify

- `python -m unittest discover -s postgres_etl/tests`
- Same counts with the old and new predicates, from a read-only query on local Postgres.
- Optional: `python postgres_etl/main.py -cp eurocup -sc 2005 --quality-only` still shows
  `points_corrected (1 row(s))` and no errors.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":5021,"specSha256":"48e629196ce8799656506a6c6028a2dc975e6e21f7483524f3c3a558c98ed8ba","branch":"refs/heads/fix/test-the-points-correction-skips-and-share-the-gap-reasons","head":"f6bc2e0d5bc8cffa7be699bbff76e65d5bf45daf","baseRef":"refs/heads/main","baseCommit":"f6bc2e0d5bc8cffa7be699bbff76e65d5bf45daf","sourceTree":"0b87447f33168da833edfd91c72cc6413d17df9c","absentOptional":[]} -->

## Findings

### test-the-points-correction-skips-and-share-the-gap-reasons/F-11 [P3] closed - The unattended missing-URL branch the scheduled run relies on has no unit test

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
**Resolution:** fixed 2026-10-26 on fix/test-the-unattended-missing-neon-url-branch: added `test_unattended_run_without_neon_url_fails_without_prompting` in neon_publish/tests/test_publish.py (missing-URL failure, no prompt, no publish stage, pending kept); it fails when the `if not interactive` guard is removed. Closed 2026-10-26 by /audit (scope: F-11; lens: tests): re-reviewed the test against pipeline.py:211-222 and :424-427. The suite passes (64 tests), and a mutation run that forces `interactive=True` inside `resolve_neon_url` makes the test fail. The failing prompt's AssertionError is not swallowed, because `refresh` only catches ValueError and KeyboardInterrupt. No new defect.

### test-the-points-correction-skips-and-share-the-gap-reasons/F-22 [P3] closed - The points correction's skip paths have no tests

**File:** postgres_etl/tests/test_raw_etl.py:195
**Found:** 2026-10-26 by /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the one new test covers a corrected team and a team left as given.
Nothing tests that the correction is skipped when `points` is unrecorded for the game
(`"points" in gaps`), when the game has no box score (`*`), when a player's makes are
missing (`made_points` returns `None`), or when the game is unplayed (no score). A
regression there would silently rewrite source values.
**Suggested fix:** add one test with those four cases, asserting unchanged points and
no `points` gap row. No current requirement would be lost.
**Resolution:** fixed 2026-10-26 on fix/test-the-points-correction-skips-and-share-the-gap-reasons: added `test_points_correction_skips_unproven_games` in postgres_etl/tests/test_raw_etl.py, with five cases: points unrecorded, no box score, a make missing, an unplayed game and a game not in `games`. Each case except the empty box score has makes equal to the score and wrong points. Temporary mutations kill the test: dropping the `"points" in gaps` skip fails the unrecorded case, counting a missing make as 0 fails the missing-make case, and giving unscored games a score fails the unplayed and not-in-games cases. Removing the `score is None` guard survives because `made_points(total) != score` already skips those sides, so that guard is redundant and was left as it is. Closed 2026-10-26 by /audit (scope: current; all lenses). I re-reviewed the new test against raw_transform.py:58-77 and :500-503. Three skips are each exercised by a case that fails when that skip is removed: points unrecorded, a make missing, and no score (unplayed or not in `games`). The no-box-score skip is already covered by `test_forfeit_without_players_gets_null_team_stats`, which asserts `["*"]` as the only gap row for a game with no players. The new test's "no box score" case does not reach that path; that is recorded separately as F-24. The original gap is gone.

### test-the-points-correction-skips-and-share-the-gap-reasons/F-23 [P3] closed - Gap warnings tell corrections from unrecorded stats by reason text

**File:** postgres_etl/quality.py:245
**Found:** 2026-10-26 by /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** `unrecorded_stat_nulled` and `points_corrected` separate rows of
`game_stat_gaps` with `reason LIKE '%corrected%'`. Rewording either reason in
`raw_transform.py` would silently move rows between the two warnings.
**Suggested fix:** share one reason prefix constant between `raw_transform.py` and
`quality.py` (or match on the full corrected-reason prefix), keeping the current
`game_stat_gaps` columns. No current requirement would be lost.
**Resolution:** fixed 2026-10-26 on fix/test-the-points-correction-skips-and-share-the-gap-reasons: `UNRECORDED_REASON` and `CORRECTED_REASON` are now constants in raw_transform.py and are used for the gap rows, with the stored text unchanged. quality.py matches `reason = UNRECORDED_REASON` and `reason LIKE CORRECTED_REASON || '%'`, and test_quality.py asserts both predicates and that neither constant contains `'`, `%` or `_`. A read-only count over local silver.game_stat_gaps is the same with the old and new predicates: unrecorded E 2564 and U 1857, corrected U 3, and the two together cover all 4424 non-`*` rows. Closed 2026-10-26 by /audit (scope: current; all lenses). Both reasons now come from shared constants in raw_transform.py:34-36. quality.py:246-248 matches them exactly, or as a prefix, so rewording a reason changes the code and the check together. The constants are code, not input, and test_quality.py asserts they contain no `'`, `%` or `_`. A read-only count on local Silver gives the same counts with the old and new predicates. No new defect.

### test-the-points-correction-skips-and-share-the-gap-reasons/F-24 [P3] closed - The skip test's "no box score" case still has a box score

**File:** postgres_etl/tests/test_raw_etl.py:244
**Found:** 2026-10-26 by /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the case clears only the local players, while the road side keeps
player `C`. `box_score_gaps` (raw_transform.py:39) returns `NO_BOX_SCORE` only when both
sides have no players, so the case never reaches the `gaps == NO_BOX_SCORE` skip it is named
for. It only shows that an empty local side has nothing to correct. The path itself is
covered by `test_forfeit_without_players_gets_null_team_stats`, so this is a misleading
case name rather than a coverage hole.
**Suggested fix:** drop the case, or give it an empty road player list too, so the game
has no box score. Leave the rest of the test as it is. No current requirement would be lost.
**Resolution:** fixed 2026-10-26 on fix/test-the-points-correction-skips-and-share-the-gap-reasons: each case now has its own road side. The "no box score" case has no players on either side and asserts `*` as its only gap row, so it reaches the `NO_BOX_SCORE` path. Mutation: dropping the `gaps == NO_BOX_SCORE` skip survives, because with no players `points_corrections` finds nothing to fix. That skip is redundant for correctness, like the `score is None` guard. Dropping the `"points" in gaps` skip still fails the unrecorded case. Closed 2026-10-26 by /audit (scope: F-24; lens: tests). In test_raw_etl.py:244 both sides of the "no box score" case now have empty player lists, so `box_score_gaps` returns `NO_BOX_SCORE`, and the case asserts `["*"]` as its only gap. The other cases keep their own road sides, so the unrecorded case still has 0 points for every player. tests.test_raw_etl passes. No new defect.

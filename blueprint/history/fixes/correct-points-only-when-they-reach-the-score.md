# Fix: Correct points only when they reach the score

**Type:** Fix
**Status:** verified
**Branch:** fix/correct-points-only-when-they-reach-the-score
**Fixes:** F-21

## The problem

`points_corrections` (`postgres_etl/raw_transform.py:58`) rewrites a side's player points
from their shooting makes when the team's makes equal the game score but its points do
not. The corrected team total at `raw_transform.py:538` is then the source total plus the
players' changes, and nothing checks it against the score. It equals the score only when
the source total equals the sum of the source player points.

That holds for every game today: no team total differs from its player sum in either
competition, and all three corrected games, U2004 games 103 and 138 and U2005 game 4,
end at their scores. A future source side with an inconsistent total would still get a
`points` correction row saying the points were "corrected from the makes", while
`team_points_differ_from_score` kept firing for the same side.

## The fix

- In `points_corrections`, add one more condition for correcting a side: after the
  correction, its player points must add up to the game score. That is, the sum over
  players of the corrected value, or the source value where unchanged, equals `score`.
  A player with no recorded points makes the sum unknown, and the side is then left as
  given.
- If the condition fails, nothing changes for that side: no corrected values and no
  `points` gap row. The existing `team_points_differ_from_score` and
  `points_differ_from_makes` warnings keep showing it.
- No change to `with_points`, the stored reason text, columns or warnings.

Must not break:
- the three current corrections, U2004 games 103 and 138 and U2005 game 4
- `test_points_are_corrected_only_when_the_makes_prove_them`
- `test_points_correction_skips_unproven_games`

## Build steps

- [x] 1. Add the condition and a case to `test_points_correction_skips_unproven_games`:
  makes equal the score and points are wrong, but one player's source points are off
  from the total, so the corrected players would not reach the score. The case expects
  unchanged points and no correction row.
  **Done when:**
  - `python -m unittest discover -s postgres_etl/tests` passes.
  - The new case fails without the condition (temporary local mutation, not committed).
  - A read-only, in-memory run of `RawSeason(...).rows("game_stat_gaps")` for EuroCup
    U2004 and U2005 still yields exactly the three `points` correction rows, with the same
    reasons, so no reload is needed.
  - F-21 is marked `fixed`.
- [x] 2. Repair the reopened F-21. The corrected team total is the source total plus the
  players' change, so it still misses the score when the source total differs from the
  source player sum. Also require that the source total equals the source player sum,
  with every player's points recorded, before correcting a side. Add a case with an
  inconsistent total: players 30 + 60 = 90, total 95, team makes 80 = score.
  **Done when:**
  - The tests pass, and the new case fails without the added condition.
  - The in-memory U2004 and U2005 correction rows are unchanged.
  - F-21 is marked `fixed`.

## Verify

- `python -m unittest discover -s postgres_etl/tests`
- The in-memory U2004 and U2005 check above.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":3297,"specSha256":"e5d20df026a2a1c6bfed3e88296e9b35670d9a4c87c307b71c5467284a14dfdc","branch":"refs/heads/fix/correct-points-only-when-they-reach-the-score","head":"3ebce6f6ee49028c62d0db72b8bb9d61c62e8514","baseRef":"refs/heads/main","baseCommit":"3ebce6f6ee49028c62d0db72b8bb9d61c62e8514","sourceTree":"fadef3c97df1608c238440072b06ac995ebd054d","absentOptional":[]} -->

## Findings

### correct-points-only-when-they-reach-the-score/F-21 [P3] closed - A points correction can leave the team total off the score while saying it was corrected

**File:** postgres_etl/raw_transform.py:536
**Found:** 2026-10-26 by /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the corrected team total is the source total plus the players'
point changes, not a value checked against the score. That equals the score only when
the source total equals the sum of its players' points. Today it always does (0 team
totals differ from their player sums in either competition), so all three corrected
games end at their scores; a future source row with an inconsistent total would get a
`points` correction row while `team_points_differ_from_score` still fires.
**Suggested fix:** in `points_corrections`, correct a side only when its corrected
player points add up to the game score; otherwise leave it as given (the warnings
already show it). No current requirement would be lost.
**Resolution:** fixed 2026-10-26 on fix/correct-points-only-when-they-reach-the-score: `points_corrections` now corrects a side only when its corrected player points, which must all be recorded, add up to the game score. A new case, 'players miss the score', in `test_points_correction_skips_unproven_games` passes, and it fails when the condition is removed. An in-memory derivation of `game_stat_gaps` for EuroCup U2004 and U2005 gives the same 3 correction rows with identical reasons, so no reload is needed. Re-reviewed 2026-10-26 by /audit (scope: F-21; all lenses) and reopened, because the repair is incomplete. The new condition guarantees that the corrected players reach the score, but the corrected team total (raw_transform.py:538) is still the source total plus the players' change, so it misses the score whenever the source total differs from the source player sum, which is the case this finding describes. Probe: players 30 + 60 = 90, source total 95, team makes 80 = score. `points_corrections` returns {0: 20}, and the corrected total is 95 - 10 = 85, not 80. Suggested repair: also require the source total to equal the source player sum before correcting a side, so that the total then lands on the score. Add a test case for an inconsistent total. Fixed again 2026-10-26 as step 2: `points_corrections` now also requires the source total to equal the source players' points, with all of them recorded, so a corrected total always lands on the score. The new case 'total off its players' passes, and it fails without that condition. The audit probe (players 90, total 95, score 80) now returns no correction. The in-memory U2004 and U2005 correction rows are unchanged. Closed 2026-10-26 by /audit (scope: F-21; all lenses). With the source total equal to the players' sum and the corrected players at the score, the corrected total (source total plus the players' change) equals the score by construction. In-memory probes against raw_transform.py:58-82: a consistent, provable side is corrected to 80; a total off its players and unrecorded player points are both left as given; float points still correct to 80.0. The three current EuroCup corrections are unchanged. No new defect.

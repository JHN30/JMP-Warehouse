# Fix: Check box-score points against the game score

**Type:** Fix
**Status:** verified
**Branch:** fix/check-box-score-points-against-the-game-score
**Fixes:** F-14

## The problem

Silver never compares box-score points with the game score or with the shooting
makes, so a wrong source `points` value flows into the per-game and per-round
ratings unseen. Read-only check over every played game (2026-10-26):

- **Team `total` rows:** EuroLeague 0 of 13,346 differ; EuroCup 14 of 9,758:

  | Kind | Rows | Games | Meaning |
  |---|---|---|---|
  | A. points = makes, differ from score | 9 | U2003/40; U2004/14, 49, 81, 110, 125; U2005/21, 91, 113 | the box score itself is incomplete; not repairable from it |
  | B. makes = score, points differ | 3 | U2004/103 road, U2004/138 local, U2005/4 road | the `points` field is wrong; the makes prove the right value |
  | C. points = score, makes differ | 2 | U2002/34 local, U2007/193 road | a shooting make is off; points are right |

- **Player rows whose points differ from 2 x twos + 3 x threes + free throws:**
  E 2 (E2007/126: Clancy 18 vs 16, Ricci 8 vs 10, team consistent); U 8: the kind B
  players (U2004/103 Slezas 0 vs 23; U2004/138 Fetisov 4 vs 0 with 0 seconds,
  Langdon 12 vs 11; U2005/4 Brun 11 vs 0), the kind C players (U2002/34 Zanus 8 vs
  12, U2007/193 Helmanis 8 vs 7) and a swap (U2007/60 Barrett 14 vs 17, Ekanga 18 vs
  15, team consistent).

## The fix

Decisions (approving this spec approves them):

1. **Warn on every mismatch.** Two Silver quality `WARN` checks on played games:
   `team_points_differ_from_score` (team `total` points vs `local_score` /
   `road_score`) and `points_differ_from_makes` (player and team rows whose points
   differ from their makes). Known source problems stay visible, as elsewhere.
2. **Correct only kind B,** where the evidence is unambiguous: in a played game
   whose team makes equal the game score but whose team points do not, each player
   row of that team whose points differ from his makes gets `points` set to his
   makes and `pir` changed by the same amount (PIR counts points one for one); the
   team `total` points become the sum of the corrected players. This fixes 3 games
   and 4 players (Slezas +23, Fetisov -4, Langdon -1, Brun -11). Each corrected
   game gets one `silver.game_stat_gaps` row (`stat_name` `points`, a reason naming
   the players and source values), so it stays visible, and a `points_corrected`
   `WARN` counts them.
3. **Leave kinds A and C and the swaps as the source gives them,** warned only: no
   rule can tell which value is right.

Where: the correction belongs in the Silver transform of the v2 game stats
(`postgres_etl/raw_transform.py`, next to the existing `box_score_gaps` handling),
so Silver stores corrected values and Gold needs no change. The checks go in
`postgres_etl/quality.py` with the other game checks.

Must not break: EuroLeague Silver and Gold values (E has no kind B game; its only
change is the 2 E2007/126 rows in the new `points_differ_from_makes` warning),
every other quality check, and the Silver row counts.

## Build steps

- [x] 1. **Checks and the kind B correction, with tests.** Unit tests: a kind B team
  is corrected (player points and PIR, team total) and gets one `game_stat_gaps`
  row; kinds A and C and a swap are left unchanged; the checks keep the
  two-parameter season scope. **Done when:** Silver tests pass.
- [x] 2. **Reload and rebuild the affected seasons.** Reload Silver for U2004 and
  U2005 (`python postgres_etl/main.py -cp eurocup -sc 2004-2005`, which also reruns
  the per-game Silver steps), then rebuild EuroCup Gold (`-cp eurocup -sc all`,
  since records and identities use every season). **Done when:** the 3 games show
  team points equal to the score, the 4 players carry their corrected points and
  PIR, U2005 game 4 no longer has the `true_shooting_pct` warning, and EuroCup
  Silver and Gold quality have 0 errors.
- [x] 3. **Check EuroLeague.** Run EuroLeague Silver `--quality-only` (only the new
  warning rows for E2007) and confirm no EuroLeague value changed, so its Gold
  needs no rebuild. **Done when:** both hold and all four test suites pass.

## Verify

- Silver tests, then all declared suites.
- `python postgres_etl/main.py -cp eurocup -sc 2002-2026 --quality-only`: 0 errors;
  `team_points_differ_from_score` 9 rows (kind A; kind C rows match the score, so
  they appear only under `points_differ_from_makes`),
  `points_differ_from_makes` 6 rows (4 players: Zanus, Helmanis, Barrett, Ekanga;
  2 kind C team rows), `points_corrected` 3 games.
- U2005 game 4: ASV total points 58, Brun 0 points and PIR 1.
- `python gold_etl/main.py -cp eurocup -sc all --quality-only`: 0 errors and no
  U2005 `true_shooting_pct` warning.
- `python postgres_etl/main.py -sc 2007 --quality-only`: 0 errors,
  `points_differ_from_makes` 2 rows.

## Results (2026-10-26)

- Silver tests 204 (2 new); all declared suites pass.
- `python postgres_etl/main.py -cp eurocup -sc 2004-2005` reloaded (exit 0). U2004
  game 103 ASV 85 (Slezas 0 -> 23, PIR 28), U2004 game 138 83 (Fetisov 4 -> 0, PIR 0;
  Langdon 12 -> 11, PIR 7), U2005 game 4 ASV 58 (Brun 11 -> 0, PIR 1); each game has
  a `game_stat_gaps` `points` row naming the players and source values.
- EuroCup Silver `--quality-only` U2002-U2026: 0 errors; `points_corrected` 3,
  `team_points_differ_from_score` 9, `points_differ_from_makes` 6 (4 players,
  2 team totals).
- EuroLeague Silver `-sc 2007 --quality-only`: 0 errors, `points_differ_from_makes`
  2 rows (E2007 game 126). No EuroLeague value changed; EuroLeague Gold checksums are
  identical to the 18c baseline (14 tables).
- EuroCup Gold rebuilt (`-cp eurocup -sc all`, exit 0) and `--quality-only` passed:
  the U2005 `true_shooting_pct` warning is gone; warnings 39 (was 21). The new lines
  are the corrected players and clubs now differing from the API season feeds, which
  keep the source values (for example Brun 66 vs API 77 and ASV 1,029 vs 1,040, both
  the 11 invented points).
- Docs: the correction rule and the new warnings in `docs/DATA_DICTIONARY.md`.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":6227,"specSha256":"32d6d9ee1d086b1f5a742db0cfced291766b2609e1e5fc078b22d4703c5ea716","branch":"refs/heads/fix/check-box-score-points-against-the-game-score","head":"4892e6aacf2447acb7f74e419a042118f9bac37f","baseRef":"refs/heads/main","baseCommit":"4892e6aacf2447acb7f74e419a042118f9bac37f","sourceTree":"d53a05481ec40b321fec509883baef88f511923f","absentOptional":[]} -->

## Findings

### check-box-score-points-against-the-game-score/F-14 [P2] closed - Silver accepts a team box score whose points do not match the game score

**File:** postgres_etl/quality.py:161
**Found:** 2026-10-26 by owner review during feature 18c (EuroCup postseason)
**Why it matters:** in U2005 game 4 (AMS 76-58 ASV, RS round 1) the source gives
ASV's Stephen Brun (`KSK`) 11 points and PIR 12 in 4 minutes with 0/1 twos, 0/1
threes and no free throws. ASV's team `total` row then says 69 points, while the game
result is 58 and ASV's makes add up to 58 (19x2 + 2x3 + 14). Nothing in Silver
compares team box-score points with the game score, so the wrong 69 flows into ASV's
per-game and per-round ratings and team totals; only Gold's
`true_shooting_pct below 0 or above 2` warning catches the player row. Owner wants
this fixed.
**Suggested fix:** add a Silver quality check for played games whose team `total`
points differ from `local_score`/`road_score` (and, as a second check, points that
differ from 2x two-pointers + 3x threes + free throws). Then decide with the owner
whether to correct a proven source error in Silver (for example points from the
shooting makes, recorded in `game_stat_gaps` or a corrections list) or only warn.
Run it over both competitions to see how many games are affected.
**Resolution:** fixed 2026-10-26 on fix/check-box-score-points-against-the-game-score: Silver warns `team_points_differ_from_score` and `points_differ_from_makes`, and corrects only provable cases (team makes equal the score, points do not) from the makes, PIR by the same amount, listed as `game_stat_gaps` `points` rows (`points_corrected`): U2004 games 103 and 138, U2005 game 4 (Brun 11 -> 0, ASV 69 -> 58). Other mismatches stay as the source gives them, warned. Closed 2026-10-26 by /audit (scope: current; lenses: quality, security, performance, tests): re-read postgres_etl/raw_transform.py and postgres_etl/quality.py on the fix branch; the checks exist and are season-scoped warnings, the three games now match their scores in Silver (U2005 game 4 ASV 58, Brun 0 points, PIR 1), and Silver tests pass (204). Follow-ups recorded as F-21 to F-23 (P3).

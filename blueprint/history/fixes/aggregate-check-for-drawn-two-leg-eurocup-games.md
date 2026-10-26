# Fix: Aggregate check for drawn two-leg EuroCup games

**Type:** Fix
**Status:** verified
**Branch:** fix/aggregate-check-for-drawn-two-leg-eurocup-games

## The problem

`python postgres_etl/main.py -cp eurocup -sc 2002-2026 --quality-only` fails with
`ERROR games: played_missing_winner` in U2004, U2007, U2010, U2014 and U2015
(8 games). Every one is a played draw in a two-leg EuroCup tie decided on aggregate,
so a single leg can end level:

| Season | Game | Phase | Result | Other leg | Aggregate |
|---|---|---|---|---|---|
| U2004 | 219 | 8F | PAM 85-85 JOV | 211 JOV 70-76 PAM | PAM 161-155 |
| U2007 | 274 | L32 | NYM 61-61 ZGO | 290 ZGO 68-66 NYM | ZGO 129-127 |
| U2007 | 285 | L32 | ASV 69-69 GAL | 301 GAL 76-75 ASV | GAL 145-144 |
| U2007 | 309 | L16 | RED 80-80 BES | 317 BES 81-69 RED | BES 161-149 |
| U2010 | 148 | 4F | GOE 66-66 TRE | 152 TRE 84-62 GOE | TRE 150-128 |
| U2014 | 283 | 8F | LIE 81-81 KSK | 291 KSK 97-81 LIE | KSK 178-162 |
| U2015 | 277 | 8F | BER 82-82 MUN | 285 MUN 84-75 BER | MUN 166-157 |
| U2015 | 299 | 4F | STR 91-91 NOV | 295 NOV 85-94 STR | STR 185-176 |

U2015 game 299 went to two overtimes to break the level aggregate (65-74 after
regulation, 12-12 in OT1, 14-5 in OT2), and still ended 91-91.

The Silver transform is already right: `match_winner_club_code` is NULL when the
scores are equal ([raw_transform.py:376-381](../../postgres_etl/raw_transform.py#L376-L381)).
The rule at [quality.py:164-165](../../postgres_etl/quality.py#L164-L165) assumes a
played game always has a winner, which holds for EuroLeague (0 draws in E2000-E2026)
but not for the EuroCup format.

## The fix

In `postgres_etl/quality.py`, for the `games` table:

- `played_missing_winner` (ERROR) counts only played games with a NULL winner and
  unequal scores (`row.local_score IS DISTINCT FROM row.road_score`).
- New `draw_without_two_leg_tie` (ERROR) counts played draws that are not a valid
  leg of a two-leg tie. A draw is valid only when, in the same competition, season
  and phase:
  - the two clubs met exactly twice (in either home/away order), and
  - the other game has the clubs reversed, is played with both scores, and
  - the aggregate of the two games is not level.

Both stay plain `scoped_count` predicates on `games`, like the neighbouring checks.
Add `draw_without_two_leg_tie` to the docs where the Silver game checks are listed,
if they are listed.

Limit: phase flags are unreliable (U2007 L32 and L16 were two-leg knockout ties but
the API marks them as group phases), so the rule does not require a knockout phase.
A drawn group game would pass if the aggregate of the two group meetings had a
winner; no such game exists in E2000-E2026 or U2002-U2026.

Out of scope (separate work, build-plan item 18): deciding `app_postseason_series`
and other Gold win/loss counts by aggregate for two-leg ties. The
`standings_played_not_won_plus_lost` warnings in U2011 and U2025 are a different
rule in seasons without draws.

Must not break: every other quality check, and EuroLeague quality results.

## Build steps

- [x] 1. Split the winner rule and add the two-leg draw rule, with unit tests in
  `postgres_etl/tests/test_quality.py` (the games-only ERROR set includes the new
  code, `played_missing_winner` excludes equal scores, and the new query keeps the
  usual two-parameter season scope). **Done when:** the Silver tests pass.

## Verify

- `python -m unittest discover -s postgres_etl/tests` passes.
- `python postgres_etl/main.py -cp eurocup -sc 2002-2026 --quality-only` reports
  0 errors in every season (warnings unchanged).
- `python postgres_etl/main.py -sc 2000-2026 --quality-only` still reports 0 errors.
- Negative check, inside a transaction that is rolled back: set U2015 game 295 to a
  score that levels the aggregate; the new query counts both legs for U2015 (2),
  because with one leg drawn the aggregate can only be level when the other leg is
  drawn too. Set
  `match_winner_club_code` to NULL on a non-drawn game; `played_missing_winner`
  counts 1. Roll back and confirm the rows are unchanged.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":4159,"specSha256":"81af55786f3fe3326b7344c9ce27a98b5fb90fa210179bc2ea8ad2b2ca0bf15d","branch":"refs/heads/fix/aggregate-check-for-drawn-two-leg-eurocup-games","head":"4ff4e50674129c821cceb91c53674e40eb295cfa","baseRef":"refs/heads/main","baseCommit":"4ff4e50674129c821cceb91c53674e40eb295cfa","sourceTree":"6cae78b22f69ff1367e3aa9b082333618dec5a85","absentOptional":[]} -->

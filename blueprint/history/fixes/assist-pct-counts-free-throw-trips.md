# Fix: Assist % counts free-throw trips

**Type:** Fix
**Status:** verified
**Branch:** fix/assist-pct-counts-free-throw-trips

## The problem

Feature 32's on-court `assist_pct` in `silver.game_player_advanced` divides the
player's assists by his teammates' made field goals while he was on court.
EuroLeague also credits an assist for a pass that leads to a shooting foul and
free throws (about 7-9% of `AS` events directly precede the club's free throws),
so a short stint can exceed 1. E2007-E2026 has 16 such rows (3 in E2025: Clark
III 1.25, De Larrea 1.33, Toliopoulos 2.0), reported by the Silver warning
`on_court_rate_out_of_range`.

## The fix

Count the chances an assist can be credited on: teammates' made field goals
plus teammates' free-throw trips while the player was on court.

- In `postgres_etl/on_court_rates.py`, add an `ft_trips` count. A trip is a run
  of `FTM`/`FTA` events of one club at the same period and `marker_time` with no
  other play event (`possessions.PLAYS`) between them; substitutions, fouls,
  timeouts and other non-play events do not split it. A trip that directly
  follows the same club's made field goal at the same `marker_time` is an
  and-one and is not counted (its assist belongs to the basket). The trip goes
  to the lineup on court at its first free throw; it is the player's own trip
  when he shoots that first free throw.
- In `postgres_etl/advanced.py`, on-court `assist_pct` =
  player `AS` / ((team fgm - player fgm) + (team ft_trips - player ft_trips)).
- Unchanged: the box-score estimate (`rate_source = 'estimate'`, no
  play-by-play to find trips), every other rate, the per-round tables (27a keep
  the Basketball-Reference form), Gold code, and the Neon schema. Gold's copy
  picks up the new values when rebuilt.

## Build steps

- [x] 1. **Trips and the new denominator.** Add `ft_trips` to the counts and use
  it in `assist_pct`, with unit tests for: a two-shot trip split by a
  substitution (one trip, first lineup), an and-one (no trip), two trips at
  different clocks, and an assist on free throws giving `assist_pct` 1.0 where
  it was 2.0 before.
  Done when `python -m unittest discover -s postgres_etl/tests` passes.
- [x] 2. **Rebuild and document.** Run `python postgres_etl/advanced.py -sc all`
  and `python gold_etl/main.py -sc all -tb game_player_advanced`, then
  `--quality-only` for both. Update the `assist_pct` row and the warning note in
  `docs/DATA_DICTIONARY.md`.
  Done when Silver quality has no ERROR, `on_court_rate_out_of_range` reports
  no rows in any season (any remaining row is listed with its cause in the
  evidence), Gold quality has no failure beyond the 11 known E2000-E2007 ones,
  and the evidence records the median change of `assist_pct` for E2025 players
  with at least 10 minutes.

## Verify

- All four configured test suites pass.
- `python postgres_etl/advanced.py -sc 2025 --quality-only` shows 0 errors and
  no `on_court_rate_out_of_range` warning.
- Clark III (E2025 game 35), De Larrea (162) and Toliopoulos (399) have
  `assist_pct` at or below 1.0.
- Republishing E2025/E2026 to Neon remains a separate owner-approved step.

## Evidence

- Tests: API 46, Silver 212 (3 new), Gold 280, publisher/CSV 72 pass.
- Local rebuild: `python postgres_etl/advanced.py -sc all` (E2000-E2026, 0
  errors) and `python gold_etl/main.py -sc all -tb game_player_advanced`.
- `on_court_rate_out_of_range`: 16 rows before, 1 after: E2012 game 237,
  Ponkrashov (CSK), 2 assists in 163 seconds. His `AS` at 01:50 is followed by
  CSK fouls and the opponent's free throws, with no CSK basket or trip; the box
  score also lists 2 assists, so the feed has an assist without a scoring chance.
- E2025: Clark III 0.50 (game 35, was 1.25), De Larrea 1.00 (game 162, was
  1.33), Toliopoulos 1.00 (game 399, was 2.0).
- E2025 players with at least 10 minutes (7,307): `assist_pct` changes by
  -0.0205 at the median and -0.0857 at the 10th percentile versus feature 32's
  field-goal-only denominator.
- Gold quality `-sc all`: exactly the 11 known E2000-E2007 failures, nothing new.
- Not run: Neon access or publish.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":4123,"specSha256":"ea75114748279f541091aba012d6b3fd62248a166a5f646e2674421fa77a4424","branch":"refs/heads/fix/assist-pct-counts-free-throw-trips","head":"031362173d17cb459313f2f3d24ff75ed354fda5","baseRef":"refs/heads/main","baseCommit":"031362173d17cb459313f2f3d24ff75ed354fda5","sourceTree":"48cd31ce1bd457d08c67df7ab1753a7264160465","absentOptional":[]} -->

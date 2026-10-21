# Fix: Gold game-advanced quality false failures

**Type:** Fix
**Status:** verified
**Branch:** fix/gold-game-advanced-quality-false-failures

## The problem

`python gold_etl/main.py -sc all --quality-only` fails on six historical seasons
(E2000, E2001, E2002, E2003, E2006, E2007), which blocks publishing them to Neon.
The data matches Silver; two checks in `check_game_advanced_invariants`
(`gold_etl/quality.py`) are wrong:

1. **Zero-minute rates** (E2000, E2001, E2003, E2006, E2007; 8 player-games).
   Old box scores record some players with 0 seconds but real stats (for example
   E2007 game 163, Stelmahers 1/1 2PT; E2001 game 52, Fanan 1 TOV). Silver computes
   `efg_pct`, `true_shooting_pct` and `tov_pct` from shots and turnovers only
   (`postgres_etl/advanced.py` `_efg`, `_true_shooting`, `_tov_pct`), so they are
   valid without minutes. The check expects every rate in `GAME_PLAYER_RATES` to be
   NULL when `seconds_played` is 0 or NULL.
2. **Round-1 tie joins on player only** (E2002; 1 row). Player `AXY` played two
   round-1 games for two clubs (game 11 for WRO, 780 s, game score -4.8; game 12
   for CSK, 0 s, game score 0). The tie joins `player_round_stats` on `person_key`
   without `club_code`, so the CSK game is compared with the WRO round row.

## The fix

In `gold_etl/quality.py`, `check_game_advanced_invariants`:

- Run the zero-minute check only on the minute-based rates: every
  `GAME_PLAYER_RATES` column except `efg_pct`, `true_shooting_pct` and `tov_pct`.
  Usage, assist, rebound, steal, block and PER columns must stay NULL at 0 seconds.
- Add `AND t.club_code = a.club_code` to the round-1 tie join, so each game row is
  compared with the round row of its own club (applies to all five ties).

Must not break: no data, builder, Silver or Neon change; the range check and the other
invariants stay as they are; every currently passing season still passes. Update
`gold_etl/README.md` or `docs/` only where they describe these two checks.

## Build steps

1. [x] Adjust the two checks and add unit tests in `gold_etl/tests/test_game_advanced.py`
   (zero-minute query excludes the three shot rates and still covers the others; the
   tie query joins on `club_code`).
   **Done when:** `python -m unittest discover -s gold_etl/tests` passes and
   `python gold_etl/main.py -sc all --quality-only` no longer reports the zero-minute
   or round-1 lines.

## Verify

- `python -m unittest discover -s gold_etl/tests`
- `python gold_etl/main.py -sc E2002 --quality-only` and `-sc E2007 --quality-only` pass.
- `python gold_etl/main.py -sc all --quality-only` ends with `Gold quality: passed`
  (only `WARN` lines remain).


<!-- blueprint:completion {"schemaVersion":1,"specBytes":2667,"specSha256":"15409d9bae13d124bdcb9e8d02f368c802fc709d89c6f365418f3e1f5f9fe063","branch":"refs/heads/fix/gold-game-advanced-quality-false-failures","head":"d93f583cf280459ea0efcb27b41decaff9e8649f","baseRef":"refs/heads/main","baseCommit":"d93f583cf280459ea0efcb27b41decaff9e8649f","sourceTree":"d13f3803d61486cd2aa7ad7688f539fa80478a77","absentOptional":[]} -->

# Fix: Ignore play-by-play without a game clock

**Type:** Fix
**Status:** verified
**Branch:** fix/ignore-play-by-play-without-a-game-clock
**Fixes:** F-15, F-25

## The problem

F-15 reported two on-court rates above 100%:
- U2008 game 32, player `000529`: `assist_pct` 2.0
- U2009 game 15, player `002042`: `assist_pct` 1.67

The cause is the source play-by-play, not the rate formula. In 6 EuroCup games almost
every event is stamped `FirstQuarter 10:00` and listed player by player, like a stat
sheet. The rest are empty period markers. This was checked read-only against local
`silver.play_by_play` on 2026-10-26:

| Game | Events | Largest share at one (period, marker_time) |
|---|---|---|
| U2008 32 | 324 | 0.99 |
| U2009 15 | 375 | 0.98 |
| U2010 32 | 42 | 1.00 |
| U2012 89 | 436 | 0.99 |
| U2013 2 | 415 | 0.99 |
| U2013 75 | 20 | 0.80 |

Every other game in E and U has at most 0.34. The modules below sort events by clock and
walk them, so in these games `IN`/`OUT` events land in arbitrary places:
- `000529` gets an `OUT` right after his stats, giving no on-court time but 2 assists
  against 1 teammate basket.
- `002042` gets an `IN` and no `OUT`, so he is on court for 2,400 s against 1,415 s in the
  box score.

The same wrong data reaches every play-by-play table for these games, plus the Gold
tables built from them:
- `game_team_possessions` (`possessions.py`)
- `game_team_score_flow` (`score_flow.py`)
- `game_team_shot_splits` (`shot_splits.py`)
- `game_player_on_court` (`on_court.py`)
- `game_team_lineup_stints` (`lineups.py`)
- the on-court rates in `game_player_advanced` (`on_court_rates.py`)

## The fix

- **One rule, in `possessions.py`, which every module already imports from.** Add
  `CLOCKLESS_SHARE = 0.5` and `events_by_game(events)`, which:
  - groups events by `game_code`, as each module does today
  - leaves out any game where more than `CLOCKLESS_SHARE` of its events share one
    `(period, marker_time)`

  Each of the six modules replaces its own grouping loop with this helper. The existing
  `code not in by_game` checks then treat these games like games without play-by-play:
  - no possession, score-flow, shot-split, on-court or stint rows
  - box-score estimates (`rate_source = 'estimate'`) in `game_player_advanced`

  This is the same path the code already takes for a game with no events, so nothing new
  happens downstream.
- **Make the gap visible.** Add a Silver quality warning, `play_by_play_without_clock`
  (WARN) on `play_by_play` in `postgres_etl/quality.py`. It counts the games over the same
  threshold, so the 6 games show up in the quality report instead of disappearing
  silently. The rows stay in `silver.play_by_play` and Bronze unchanged.
- No schema or column changes, and EuroLeague output stays identical, since no E game
  is over the threshold.
- The threshold is a fixed constant, not configuration. Real games peak at 0.34 and
  broken ones are at 0.80 or more.

Must not break:
- games with real play-by-play
- the existing tests of the six modules
- the round-1 ties between the per-game and round tables in Gold quality

## Build steps

- [x] 1. Add `CLOCKLESS_SHARE` and `events_by_game` to `possessions.py`, and use the helper
  in all six modules. Add a unit test in `postgres_etl/tests` with:
  - a normal game, which is kept
  - a game with more than half of its events at one moment, which is dropped
  - a game exactly at the threshold, which is kept, because the rule is strictly more
    than half

  Add one module-level test, for example in on_court or advanced, showing that a
  clockless game yields no on-court rows and estimate rates.
  **Done when:** `python -m unittest discover -s postgres_etl/tests` passes.
- [x] 2. Add the `play_by_play_without_clock` warning to `quality.py`, with its test in
  `test_quality.py` (severity `WARN`, two season `%s` parameters).
  **Done when:**
  - The tests pass.
  - A read-only count with the warning's SQL over local Silver gives exactly the 6 games
    above, and 0 for E.
- [x] 3. Rebuild locally:
  - Silver, for each affected season (U2008, U2009, U2010, U2012, U2013):
    `python postgres_etl/advanced.py -cp eurocup -sc <s>`, plus `possessions.py`,
    `score_flow.py`, `shot_splits.py`, `on_court.py` and `lineups.py` with the same
    arguments.
  - Gold: `python gold_etl/main.py -cp eurocup -sc 2008 2009 2010 2012 2013`.

  **Done when:**
  - Silver `--quality-only` for those seasons shows no `on_court_rate_out_of_range` and
    shows `play_by_play_without_clock` for the 6 games.
  - Gold `--quality-only` for those seasons has 0 errors.
  - The 6 games have no rows in the five play-by-play tables, and their player rows in
    `game_player_advanced` are `estimate`.
  - F-15 is marked `fixed`.
- [x] 4. Repair F-25. `shot_splits.py` keeps its own per-game grouping. Its assist count
  is order-independent, and its splits come from the shots feed, so the clockless games
  keep correct shot-split rows.
  - Add a test showing a clockless game still gets its splits.
  - Rebuild `shot_splits.py -cp eurocup -sc 2008 2009 2010 2012 2013` and Gold
    `-tb game_team_shot_splits team_pbp_stats` for those seasons.
  - Update the docs line.

  **Done when:**
  - The tests pass, and the new test fails if shot splits use `events_by_game`.
  - The 6 games have shot-split rows again.
  - Silver and Gold quality for those seasons have 0 errors.
  - F-25 is marked `fixed`.

## Verify

- `python -m unittest discover -s postgres_etl/tests` and
  `python -m unittest discover -s gold_etl/tests`
- `python postgres_etl/advanced.py -cp eurocup -sc 2008 2009 --quality-only` shows no
  `on_court_rate_out_of_range`.
- EuroLeague is untouched: no E season is rebuilt, and the threshold query finds no E game.

## Implementation notes

- **Minimum game size.** The rule also needs `CLOCKLESS_MIN_EVENTS = 20`, the size of
  the smallest stat-sheet feed. Without it, small test fixtures (one to a few events, or
  no `marker_time`) were dropped as clockless. In local Silver only U2013 games 1 and 46
  have fewer than 20 events; they have 4 events each, at different moments.
- **Shared SQL.** The rule has an SQL form, `CLOCKLESS_GAMES_SQL` in `possessions.py`,
  which is shared by the new warning and by the lineups `stints_cover_little_of_the_game`
  check. That check now excludes these games. Otherwise it would warn about the stints
  that were dropped on purpose.
- **Docs.** `docs/SILVER_CATALOG.md` lists the 6 games in its EuroCup quirks.
- **Results, all local.**
  - The shared SQL finds exactly the 6 games across every E and U season.
  - The Silver rebuild of U2008, U2009, U2010, U2012 and U2013 has 0 errors.
  - The 6 games have no rows in the five play-by-play tables, and their 134 player rows
    are `estimate`.
  - No EuroCup on-court rate is above 1.
  - Gold build and `--quality-only` for those seasons: passed, with no warnings.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":6913,"specSha256":"dc930d3b8e31b14ebf41e4cfb077c5f0e82e2ab0775b002aca4e7aba2db67a10","branch":"refs/heads/fix/ignore-play-by-play-without-a-game-clock","head":"f2c932e105c6a83fbf1d9199fd6ca9f4516f9f41","baseRef":"refs/heads/main","baseCommit":"f2c932e105c6a83fbf1d9199fd6ca9f4516f9f41","sourceTree":"0c7573087ffa7d6cd64111949ce81d51e18cb2fe","absentOptional":[]} -->

## Findings

### ignore-play-by-play-without-a-game-clock/F-15 [P3] closed - On-court assist % above 100% for two EuroCup players

**File:** postgres_etl/advanced.py:309
**Found:** 2026-10-26 during feature 18a (EuroCup Gold), Silver warning `on_court_rate_out_of_range`
**Why it matters:** two on-court rows exceed the 0-1 range: U2008 game 32 player
`000529` (assist_pct 2.0, usage_pct 0.92, 1,912 s) and U2009 game 15 player `002042`
(assist_pct 1.67, 1,415 s). Either the on-court intervals miss part of the player's
time (so too few teammate baskets are counted), or the play-by-play is incomplete for
those games. The values reach `app_game_player_advanced` and the round tables.
**Suggested fix:** inspect both games' on-court intervals against box-score minutes and
the play-by-play; fix the reconstruction if it is wrong, otherwise keep the warning and
document the source gap.
**Resolution:** fixed 2026-10-26 on fix/ignore-play-by-play-without-a-game-clock. Cause: U2008 game 32 and U2009 game 15 are among 6 EuroCup stat-sheet feeds, where nearly every event sits at Q1 10:00, so the on-court walk placed IN/OUT arbitrarily. `possessions.events_by_game` now leaves out any game of at least 20 events where more than half of its events share one (period, marker_time), and all six play-by-play modules use it. The new `play_by_play_without_clock` warning lists them. After the local rebuild, no EuroCup on-court rate is above 1, the 6 games use estimates, and Gold quality passed. Re-reviewed 2026-10-26 by /audit (scope: F-15; all lenses) and kept `fixed`. The original defect is gone, and the rule is correct for the five modules that walk events in clock order (possessions, score_flow, on_court, lineups and on_court_rates). However, the repair also drops shot-split rows that do not depend on order; that is recorded as F-25. Closed 2026-10-26 by /audit (scope: F-15 and F-25; all lenses). I re-reviewed the final diff. `events_by_game` and `_clockless` in possessions.py match `CLOCKLESS_GAMES_SQL` (the same 20-event minimum and 0.5 share, constants in the code, `game_code` never NULL). The five modules that use the rule all walk events in clock order. The rates above 1 are gone (0 in U), and the 6 games use estimates. No new defect beyond F-25, which is now repaired.

### ignore-play-by-play-without-a-game-clock/F-25 [P3] closed - The clock rule also drops correct shot splits

**File:** postgres_etl/shot_splits.py:59
**Found:** 2026-10-26 by /audit (scope: F-15; lenses: quality, security, performance, tests)
**Why it matters:** `shot_splits.derive_rows` now groups events with `events_by_game`,
so the 6 clockless games get no `game_team_shot_splits` rows. Nothing this module uses
depends on event order:
- `_assists` (shot_splits.py:22) only counts made field goals and `AS` events per club,
  and its docstring says assists cannot be paired by time anyway.
- The splits themselves come from the separate shots feed, which these games have:
  116, 144, 8, 165, 147 and 8 shots.

So these rows were right before the fix, and the fix removes them.
**Suggested fix:** let `shot_splits.py` keep plain per-game grouping instead of
`events_by_game`, then rebuild `shot_splits.py -cp eurocup -sc 2008 2009 2010 2012 2013`
and the Gold copy for those seasons. Note in the `play_by_play_without_clock` docs line
that shot splits are kept. No current requirement would be lost.
**Resolution:** fixed 2026-10-26 on fix/ignore-play-by-play-without-a-game-clock: `shot_splits.py` is back to its original per-game grouping and is identical to main. `test_a_game_without_a_clock_keeps_its_splits` passes, and it fails when shot splits use `events_by_game`. The Silver and Gold rebuilds for U2008, U2009, U2010, U2012 and U2013 restore 12 shot-split rows (2 per game) in both layers, with 0 Silver errors, and Gold quality passes. The docs line in SILVER_CATALOG.md now says shot splits are kept. Closed 2026-10-26 by /audit (scope: F-15 and F-25; all lenses). `git diff main -- postgres_etl/shot_splits.py` is empty, so the module is unchanged by this fix. The new test pins the clockless game keeping its splits. Silver and Gold each hold 12 shot-split rows for the 6 games. The only Gold reader, team_pbp.py, was rebuilt for those seasons and passed quality. No new defect.

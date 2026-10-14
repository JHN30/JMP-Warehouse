# Fix: Forfeit games null team season totals

**Type:** Fix
**Status:** verified
**Branch:** `fix/forfeit-games-null-team-season-totals`

## The problem

`gold.app_team_season_stats` (the source of the app's
`/seasons/:season/team-stats` and `/teams/:club/team-stats` routes) has every
`own_*` and `opp_*` measure NULL, with `games_played` 6, for four rows:

| Season | Phase | Clubs | Forfeit game |
| --- | --- | --- | --- |
| E2001 | TS | TEL, ULK | 264 (TEL 2-0 ULK) |
| E2003 | TS | TEL, PAM | 200 (TEL 20-0 PAM) |

Cause, confirmed in `gold_etl/team_season.py` `derive_rows`: both forfeits
are `played = true` (`game_status` `Walkover`) and Silver stores a `total`
`game_team_stats` row for each side with every measure NULL (their
`game_stat_gaps` row is `stat_name = '*'`, no box score). The game passes the
played filter, counts as an appearance, and the deliberate 30c rule "any
missing game value makes the aggregate NULL" then nulls every total for both
clubs.

These are the only two `Walkover` games and the only two `*` gaps in local
Silver (E2000-E2026). `team_round_stats` and the tables built on it already
exclude games without a full box score, so they use 5 games for these clubs.

## The fix

- In `derive_rows`, skip a game that has a `game_stat_gaps` row with
  `stat_name = '*'` (no box score), as `team_round_stats` effectively does.
  `read_rows` reads those game codes for the scope with one parameterized
  query and passes them in. Keying on the canonical no-box-score marker rather
  than `game_status = 'Walkover'` also covers any later game without a box
  score.
- `games_played` counts only the included games, so these four rows read 5.
  The app divides totals by `games_played`; the API's feed says 6 and divides
  5-game totals by 6, which understates per-game values. This is an accepted,
  documented difference from the API, the same as `team_round_stats`.
- Keep the 30c rule for partial gaps: a single missing measure in a counted
  game still makes that aggregate NULL (for example `fouls_received` in
  E2000-E2002 stays NULL).
- Must not change any other row. A read-only simulation of this rule against
  local Silver changed exactly the four rows above, kept the same row keys,
  left no NULL measure in them, and matched the API's season totals (for
  example TEL E2001 TS: 408 points for, 370 against, 168 rebounds).
- No schema, Silver, Neon, or quality-module change: `quality.py` recomputes
  expected rows through `read_aggregate_rows`, so it follows the new rule.

Expected rows after the fix:

| Season | Club | `games_played` | `own_points` | `opp_points` |
| --- | --- | --- | --- | --- |
| E2001 | TEL | 5 | 408 | 370 |
| E2001 | ULK | 5 | 395 | 458 |
| E2003 | TEL | 5 | 432 | 406 |
| E2003 | PAM | 5 | 418 | 401 |

## Build steps

- [x] **Step 1 - Exclude no-box-score games from team season totals** -
  update `gold_etl/team_season.py` (`derive_rows` takes the no-box-score game
  codes; `read_rows` queries `silver.game_stat_gaps` for `stat_name = '*'`).
  Add a test in `gold_etl/tests/test_team_season.py`: a club with a forfeit
  game whose `total` rows are all NULL gets totals from its other games and
  `games_played` excluding the forfeit, and its opponent likewise; the
  existing partial-NULL test still passes. Update the
  `app_team_season_stats` section of `docs/DATA_DICTIONARY.md` (forfeits not
  counted, `games_played` can be one lower than the API's, naming E2001 game
  264 and E2003 game 200). *Done when:* `python -m unittest discover -s
  gold_etl/tests` passes.
- [x] **Step 2 - Rebuild and check local Gold** - rebuild the two affected
  seasons and run the read-only checks. *Done when:* the four rows match the
  table above, no other `app_team_season_stats` row changed (compare a
  before/after snapshot of the table), and `python gold_etl/main.py -sc all
  -tb app_team_season_stats --quality-only` passes.

## Verify

- `python -m unittest discover -s gold_etl/tests`
- `python gold_etl/main.py -sc E2001 E2003 -tb app_team_season_stats`
- `python gold_etl/main.py -sc all -tb app_team_season_stats --quality-only`
- Read-only SQL: the four rows above have `games_played` 5 and no NULL
  measure; the total row count is unchanged (1,120).

## Out of scope

- Publishing E2001 and E2003 to Neon. The live app changes only after a
  separate, owner-approved publish; the app's "totals unavailable" note can be
  removed after that.
- Other tables and the Silver representation of forfeits.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":4482,"specSha256":"8a7818dd9f5d0d553ea5a434aa64ae62c83b2c1ea16f6d692dce811979bf143a","branch":"refs/heads/fix/forfeit-games-null-team-season-totals","head":"d141dbaf61b2130e6abad70d69024fd4504b7138","baseRef":"refs/heads/main","baseCommit":"d141dbaf61b2130e6abad70d69024fd4504b7138","sourceTree":"a017c5710aeb4f2f7b8fa0427d2cd98811e1a805","absentOptional":[]} -->

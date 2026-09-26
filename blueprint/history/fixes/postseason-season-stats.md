# Fix: Postseason season stats

**Type:** Fix
**Status:** verified
**Branch:** `fix/postseason-season-stats`

## The problem

- The web app needs per-phase season stats (RS, PI, PO, FF) plus one combined
  postseason view (Play-In + Playoffs + Final Four). The EuroLeague v3
  statistics API cannot combine phases: `PhaseTypeCode=PO,FF` and `PI,PO,FF`
  both return 0 rows (probed 2026-09-26).
- The API's no-phase `perGame` request has returned `{"total":0,"players":[]}`
  for E2026 on every refresh since 2026-09-24. The loader stores it silently, so
  `app_season_stats_traditional` and `app_season_stats_advanced` have no
  `phase_code = 'all'`, `mode = 'perGame'` rows for E2026 and nothing flags it.
  (The web-app side, leaders reading `all`, is handled in `jmp-euroleague2`.)

## The fix

**1. Derived `phase_code = 'PS'` rows** in `season_stats_traditional` and
`season_stats_misc` only (advanced and scoring: none), both modes, built from
the stored v2 game list and box scores of played `PI`, `PO` and `FF` games.

- A pure builder in a new `postgres_etl/postseason.py` returns v3-shaped payload
  dicts; `RawSeason.rows("season_player_stats")` yields them after the bronze
  files, so load, dry run and quality checks cover them with no new load step
  and every season-stats load rebuilds them. No PS rows when the season has no
  played PI/PO/FF game.
- Rules, each checked against the API's own E2025 `PO` rows (games played,
  started, points, minutes and double-doubles already match exactly for all 99
  players when computed from `app_game_player_stats`):

| Column | Rule |
| --- | --- |
| Who is included | players with `timePlayed > 0` in at least one included game |
| per-game rows | only players with more than half of their own club's postseason games (owner decision 2026-09-26; the API's per-game feeds likewise drop players under half of the phase's games) |
| `gamesPlayed` / `gamesStarted` | games with `timePlayed > 0` / games with `startFive` |
| `minutesPlayed` | `sum(timePlayed) / 60`; perGame divides by games, unrounded |
| counting stats, `pir` | sums (`pir` = `valuation`, `foulsDrawn` = `foulsReceived`, `blocks` = `blocksFavour`, `assists` = `assistances`); perGame = sum / games, rounded to 1 decimal, half to even like the API |
| `*Percentage` | `100 * made / attempted` from totals, 1 decimal half to even, same in both modes; `NULL` when attempted is 0 (data rule: NULL = unavailable; the API writes 0 here) |
| `wins` / `losses` | included games the player's club won / lost |
| `doubleDoubles` / `tripleDoubles` | games with >= 10 in 2 / 3 of points, rebounds, assists, steals, blocks |
| misc table | identical in both modes, `minutesPlayed` is the per-game average (mirrors the API's misc quirk) |
| identity | name and club from the player's latest included box score; age, image and club image/TV codes copied from the player's API row in the same season when one exists, else `NULL`; `playerRanking` `NULL` |
| `entry_ordinal` | the fetcher's sort statistic desc (minutes for traditional, games played for misc), then minutes desc, then `person_key`; the API's own tie order is undocumented |

- A measure that is unrecorded (a `game_stat_gaps` gap, stored `NULL`) in any
  of the player's included games makes that measure `NULL`, not a partial sum.
- Must not break: API-sourced rows for every phase, `records.py` (reads only
  `phase_code = 'all'`), coverage counts (distinct players, unchanged), and the
  Neon publish (PS rows ride the normal season replace).

**2. Quality warning `season_stats_phase_mode_missing`** (`WARN`) for each of
the four season-stats tables when `games` is also checked: counts the expected
(phase, mode) pairs with no rows, where expected phases are `all` plus every
phase of the season's played games, times `accumulated` and `perGame`. `PS` is
not expected (derived).

**3. Docs:** `docs/DATA_DICTIONARY.md` (the `PS` phase, its rules, which tables
have it) and `postgres_etl/README.md` if it lists phases.

## Build steps

1. [x] **Builder + tests.** `postseason.py` with unit tests for the table's rules
   (sums, per-game rounding, percentages and the zero-attempt NULL,
   wins/losses, double/triple-doubles, gaps, ordinals, misc modes). *Done when*
   the tests pass and a read-only script, running the builder on E2025 `PO`
   games alone, matches the API's E2025 `PO` rows on every traditional and misc
   column (any mismatch is explained or the rule is fixed).
2. [x] **Wire into the load + docs.** *Done when* `--dry-run` for E2025 shows the
   extra rows, a real load of E2025 has PS rows (traditional and misc, both
   modes) equal in count to the distinct players with `timePlayed > 0` in
   PI/PO/FF, and E2026 has none.
3. [x] **Quality warning + test.** *Done when* a check-selection test passes and
   `--quality-only -sc 2026` reports the warning on traditional and advanced
   (the missing `all`/`perGame`), while E2025 reports none.

## Verify

- All three test commands in `AGENTS.md` pass.
- `python postgres_etl/main.py -sc 2025 2026 --dry-run`, then the real load and
  its quality report.
- Read-only SQL: PS row counts per table and mode for E2025; spot-check one
  player's PS points = PI + PO + FF API accumulated points.
- `python neon_publish/main.py -sc 2025 -tb season_stats_traditional season_stats_misc --dry-run`
  shows the added rows. The real publish needs the owner's yes.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":5489,"specSha256":"5065bb67f4ba77c8a7b182dcf014c4cc96b73698fb44267c4144165e1d6e2bad","branch":"refs/heads/fix/postseason-season-stats","head":"763bf62b436fc0cfd6dd4bc415286a25a73cf056","baseRef":"refs/heads/main","baseCommit":"763bf62b436fc0cfd6dd4bc415286a25a73cf056","sourceTree":"50d30afac5702484757ef3d9e69bb790e545ef56","absentOptional":[]} -->

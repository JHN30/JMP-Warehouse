# Feature: Postseason series

**From build-plan:** feature 13
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/postseason-series`

## Goal

Precompute one row per postseason matchup (play-in, playoff, or Final Four)
from the `games` table, so the app can show a series/matchup view (who played
whom, the game-by-game results, and who's ahead or who won) without
reassembling it from individual games itself.

No existing app or Express contract to mirror here (unlike features 11 and
12) — this is a new derived table, so the design below is deliberately
conservative: it reports only facts directly observable in `app_games`, and
invents no bracket-position labels (e.g. "Quarterfinal 1", "9th-12th place")
that the source data doesn't carry.

## In scope

- `app_postseason_series` - one row per `(season, phase, unordered club
  pair)`, for `phase_code IN ('PI', 'PO', 'FF')` only (matching the
  build-plan's exact wording: play-in, playoff, Final Four — not the older
  `TS` "Top 16" group-stage phase, which is round-robin group play, not
  postseason).
- A "series" is simply every game two clubs played against each other in one
  phase of one season. This one definition already covers every era without
  hardcoding a format:
  - **PO** (playoffs): today a best-of-5 quarterfinal (confirmed against
    E2025's actual data: 2 home, 2 away, then a deciding 5th game only when
    tied 2-2). Older seasons show smaller PO game counts per season
    (best-of-3 in some years) — the row just reports however many games
    were actually played between the pair; it never assumes a fixed series
    length.
  - **FF** (Final Four): each semifinal pairing and the final are each a
    single game between two clubs that don't repeat, so each naturally
    becomes its own 1-game "series" row. No semifinal/final label is
    invented.
  - **PI** (play-in): confirmed against E2025 (`BAR`-`RED`, `PAN`-`MCO`,
    `MCO`-`BAR` — three distinct pairings, not one pair playing twice), each
    pairing is its own single-elimination game and becomes its own 1-game
    row. No bracket-slot label is invented.
- Wins are counted only from `games.played = TRUE`; `winner_club_code` is
  whichever club has strictly more wins so far (`NULL` while tied, including
  a series still in progress).
- Games not yet played (scheduled but not started) still count toward
  `games_played`-in-the-row's game list, with `NULL` scores, so an
  in-progress series' upcoming game is visible.
- This table IS season-scoped like feature 12 (not feature 11's records
  tables): it fits the normal per-season load, quality checks, and Neon
  publish path.

## Out of scope

- The `TS` (Top 16) phase and any other round-robin group-stage grouping —
  not postseason, not requested.
- Inventing bracket-position labels (round name, seed number, "which
  quarterfinal") not present in the source data.
- Any change to `jmp-euroleague2` to read from this table — coordinated
  later, like every other app-facing table so far.
- A dedicated "series is decided" status field. Whether a series is finished
  isn't reliably derivable without hardcoding a best-of-N target per era, so
  it's deliberately not stored; `winner_club_code` plus the game list already
  show the state (mid-series ties show `NULL` winner and fewer games than a
  full series).

## Build loop

Per `blueprint/config.json` (`workflow.stepReview: "feature"`), one review
packet after all steps; checkpoint commits disabled. `/complete` makes the
final commit.

## Build steps

- [x] **Step 1 - Schema** - Add `app_postseason_series` to
  `postgres_etl/flat_schema.py` using the normal `table()` helper (season-scoped),
  key `(competition_code, season_code, phase_code, club_a_code, club_b_code)`.
  `club_a_code`/`club_b_code` are the pair's two club codes in a deterministic
  order (alphabetically by `club_code`) so the same pairing never produces two
  rows. Add to `PUBLISHED_TABLES`. *Done when:* `python postgres_etl/main.py
  --list-tables` lists the new name.
- [x] **Step 2 - Local aggregation** - Add the series computation to
  `postgres_etl/aggregates.py` (alongside the feature-12 functions, same
  season-scoped module): group `app_games` rows by `(competition_code,
  season_code, phase_code, unordered club pair)` for `phase_code IN ('PI',
  'PO', 'FF')`, and for each group build a row with the counted wins, the
  winner (or `NULL` if tied), and a `games JSONB` array (one entry per game
  in the pairing: `gameCode`, `roundNumber`, `scheduledAt`, `localClubCode`,
  `roadClubCode`, `localScore`, `roadScore`, `winnerClubCode`, ordered by
  `round_number`). Replace that season's rows (delete then insert) inside one
  transaction, same shape as the feature-12 tables. *Done when:* running it
  against the local dev database for one season with a `PO` phase (for
  example `E2025`) produces one row per quarterfinal pairing, and a manual
  check of one row's `club_a_wins`/`club_b_wins`/`winner_club_code` against
  the actual E2025 quarterfinal results is correct.
- [x] **Step 3 - Wire into the loader** - Route `app_postseason_series`
  through the same aggregate-table path added in feature 12 (respecting
  `-sc`, `--dry-run`, `--quality-only`). *Done when:*
  `python postgres_etl/main.py -sc current -tb app_postseason_series`
  refreshes only that table for the requested season(s).
- [x] **Step 4 - Quality checks** - In `postgres_etl/quality.py`, add checks
  gated on `app_postseason_series` in the same style as the feature-12
  checks: `club_a_wins`/`club_b_wins` are non-negative and each is at most
  the row's game count; `winner_club_code`, when not `NULL`, is one of
  `club_a_code`/`club_b_code` and matches whichever of the two has strictly
  more wins; every game in the `games` array belongs to that row's
  `club_a_code`/`club_b_code` pair (an orphan/mismatch check, same pattern as
  `app_coverage_games_key_mismatch`). *Done when:* `python postgres_etl/main.py
  --quality-only -tb app_postseason_series` reports 0 errors after a fresh
  Step 2/3 run.
- [x] **Step 5 - Neon publish** - Add `app_postseason_series` to the normal
  per-season publish path; expect no new `neon_publish/publish.py` logic
  needed, same as feature 12. *Done when:* `python neon_publish/main.py
  --dry-run -tb app_postseason_series` reports the planned per-season
  replace.
- [x] **Step 6 - Data dictionary** - Document `app_postseason_series` in
  `docs/DATA_DICTIONARY.md`: key, the pairing/grouping definition, the
  `games` JSONB shape, the winner rule, and the explicit note that `TS` and
  bracket-position labels are out of scope. *Done when:* the doc is
  consistent with the Step 1 schema.
- [x] **Step 7 - Tests** - Add unit tests under `postgres_etl/tests/` for the
  Step 2 grouping/winner logic: correct pairing regardless of which club is
  `local`/`road` in a given game, a tied/in-progress series yields a `NULL`
  winner, an unplayed game still appears in the game list with `NULL`
  scores, and a play-in-style season (three distinct one-game pairings,
  not one pair playing twice) produces three separate rows. *Done when:*
  `python -m unittest discover -s postgres_etl/tests` passes, including the
  new tests.

## Files / areas

- `postgres_etl/flat_schema.py` - new table definition, `PUBLISHED_TABLES`.
- `postgres_etl/aggregates.py` - new series-computation function, added to
  `AGGREGATE_TABLES`.
- `postgres_etl/main.py` - no change expected (already routes
  `AGGREGATE_TABLES` generically from feature 12).
- `postgres_etl/quality.py` - new checks for the table.
- `postgres_etl/tests/` - new tests (in `test_aggregates.py` or a focused
  addition).
- `docs/DATA_DICTIONARY.md` - new table documentation.

## Data / contracts

- Key: `(competition_code, season_code, phase_code, club_a_code,
  club_b_code)`, `club_a_code < club_b_code` alphabetically.
- Columns: `club_a_name`, `club_b_name`, `games_played` (count of games
  between the pair, played or not), `club_a_wins`, `club_b_wins` (counted
  only from `played = TRUE` games), `winner_club_code` (nullable TEXT — the
  club with strictly more wins, `NULL` while tied), `games` (JSONB NOT NULL,
  array ordered by `round_number`).
- `games` array entries: `{gameCode, roundNumber, scheduledAt, localClubCode,
  roadClubCode, localScore, roadScore, winnerClubCode}` — `localScore`,
  `roadScore`, `winnerClubCode` are `null` for a not-yet-played game.
- Scope: `phase_code IN ('PI', 'PO', 'FF')` only; `TS` and `RS` never
  produce rows here.
- Rebuild is per-season and idempotent, same as feature 12: a season's rows
  are fully replaced from that season's current local `app_games` data;
  unrelated seasons are untouched.

## Testing

- `python -m unittest discover -s postgres_etl/tests` covers the grouping,
  winner-derivation, and unplayed-game handling (Step 7).
- Manual verification per step's *Done when* above: `--list-tables`,
  `--quality-only`, `neon_publish/main.py --dry-run` output, and one manual
  cross-check of a real PO series (E2025) against known results.
- No UI to test; this is a data pipeline change only.

## Notes for the AI

- This table has no existing Express/app contract to match — don't invent
  one. Keep the derived facts strictly to what `app_games` already contains
  (pairing, scores, round order); don't add seeding, bracket names, or
  series-length assumptions.
- Reuse the feature-12 season-scoped aggregate pattern
  (`postgres_etl/aggregates.py`, `AGGREGATE_TABLES`, `validate_aggregates`)
  rather than building a parallel mechanism.
- Never leave Neon with a half-replaced season for this table: same
  per-season transaction safety bar as every other table.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":9700,"specSha256":"c9cc4763ab37cb5900db294a88c94160bb08d59bc30ac628d735f30185a8d3fa","branch":"refs/heads/feature/postseason-series","head":"b5b913cc54bba2a2093f65cb24ab207a078946ed","baseRef":"refs/heads/main","baseCommit":"b3aecff7b97c750fe81af247e93e0266a2289141","sourceTree":"280c44339124b736cd163824d97f11d3f94e7351","absentOptional":[]} -->

## Independent review

**Status:** passed
**Target commit:** b5b913cc54bba2a2093f65cb24ab207a078946ed
**Base commit:** b3aecff7b97c750fe81af247e93e0266a2289141
**Base ref:** refs/heads/main
**Spec hash:** c9cc4763ab37cb5900db294a88c94160bb08d59bc30ac628d735f30185a8d3fa
**Prepared by:** claude
**Builder model:** claude-sonnet-5
**Requested reviewer:** claude
**Requested model:** runtime default (exact model not known until reviewer starts)
**Requested execution:** automatic
**Requested at:** 2026-09-25T13:12:21Z
**Workflow:** regular
**Check required:** no

## Handoff

Review the active spec and the complete `b3aecff7b97c750fe81af247e93e0266a2289141..b5b913cc54bba2a2093f65cb24ab207a078946ed` delta in a fresh
session or isolated subagent without the builder conversation. Run all Audit lenses from scratch.
Do not edit product code, accept findings, or reuse the existing findings as the review scope.

**Reviewer adapter:** claude
**Reviewer model:** claude-sonnet-5
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-09-25T13:16:24Z
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Commands

- `python -m unittest discover -s postgres_etl/tests`: pass (84 tests, OK)
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass (47 tests, OK)
- `cd api_requests && python -m unittest tests.test_scrapper`: pass (16 tests, OK)
- `python postgres_etl/main.py --list-tables`: pass (`app_postseason_series` listed, confirming Step 1's *Done when*)

## Evidence

- Reviewed the full `b3aecff7b97c750fe81af247e93e0266a2289141..b5b913cc54bba2a2093f65cb24ab207a078946ed`
  diff across all 8 changed files: `postgres_etl/flat_schema.py`,
  `postgres_etl/aggregates.py`, `postgres_etl/quality.py`,
  `postgres_etl/tests/test_aggregates.py`, `postgres_etl/tests/test_flat_etl.py`,
  `neon_publish/tests/test_publish.py`, `docs/DATA_DICTIONARY.md`, and
  `blueprint/context/current-feature.md`, against the verified spec.
- `flat_schema.py`: `app_postseason_series` uses the standard `table()` helper;
  key resolves to `(competition_code, season_code, phase_code, club_a_code,
  club_b_code)` as specified; added to `AGGREGATE_TABLES` and
  `PUBLISHED_TABLES`. The pre-existing duplicated `AGGREGATE_TABLES` literal in
  `aggregates.py` is removed in favor of importing the single definition from
  `flat_schema.py` (matches the commit message's stated latent-bug fix).
- `aggregates.py` `_postseason_series_select_sql()`: verified column-by-column
  against `games`' real physical columns (`local_club_code`, `road_club_code`,
  `local_club_name`, `road_club_name`, `local_score`, `road_score`,
  `match_winner_club_code`, `round_number`, `scheduled_at`, `phase_code`, all
  present in `flat_schema.py`'s `games` table definition). `LEAST`/`GREATEST`
  on `local_club_code`/`road_club_code` produce the deterministic
  `club_a_code`/`club_b_code` pairing regardless of local/road side; the
  matching `club_a_name`/`club_b_name` `CASE` branches align with the same
  comparison. Wins are counted only `WHERE played IS TRUE`; `games_played`
  uses unfiltered `count(*)` so unplayed games still count and appear in the
  `jsonb_agg` list with `NULL` score/winner (sourced straight from `games`).
  `winner_club_code` is `NULL` on a tie via the `CASE ... ELSE NULL` branch.
  All season/competition scoping uses bound parameters
  (`%(competition_code)s`, `%(season_code)s`); the `phase_code IN (...)` list
  is built only from the hardcoded `POSTSEASON_PHASES` tuple, never from
  request input, so there is no injection surface. `POSTSEASON_SERIES_COLUMNS`
  insert-column order matches the SELECT's output order exactly.
- `build_aggregates()`: the new dry-run probe and the real DELETE-then-INSERT
  block both follow the exact structure of the three pre-existing aggregate
  tables (same season-scoped transaction shape, same logging style); the
  dry-run path never issues `INSERT`, confirmed by
  `test_postseason_series_dry_run_and_real_run` and by reading the code path
  (probe runs under `readonly=True` then `connection.rollback()`).
- `quality.py`: three new checks (`postseason_series_wins_out_of_range`,
  `postseason_series_winner_mismatch`, `postseason_series_game_club_mismatch`)
  match the spec's Step 4 rules exactly and follow the existing `scoped_count`
  / raw-`%s`-scoped-SQL conventions used by `app_coverage_games_key_mismatch`.
  Confirmed both `%s` placeholders in each new query align with
  `check_season`'s `scope = (competition_code, season_code)` binding.
- `docs/DATA_DICTIONARY.md`: new `app_postseason_series` section matches the
  schema and spec (key, columns, `games` shape, winner rule, explicit `TS`/
  bracket-label out-of-scope note); table counts (30 -> 31) match the schema
  change and the updated test assertions.
- Tests: `PostseasonSeriesSqlTests` pins the SQL constructs (phase filter,
  symmetric pairing, tie-to-NULL winner, played-only win counting, unplayed
  games retained) rather than executing against a real database; this matches
  the project's own testing standard (`coding-standards.md`: "Unit tests never
  call ... a real database"; "real database behaviour" is verified by dry run
  or a real load, not unit tests) and the pre-existing no-DB `SqlShapeTests`
  pattern already used for the team-season-stats SQL in the same file. The
  actual grouping/winner behavior was verified manually against real E2025
  data per the spec's Step 2 evidence, which is outside this review's
  reachable local-repo evidence and was not independently re-verified here.
  `test_aggregate_only_selection_skips_the_flat_loader`-style routing tests
  and the dry-run/real-run DELETE-before-INSERT ordering test both pass.
- No tracked, staged, unstaged, or untracked path differs from `Target commit`
  except `blueprint/context/review.md` itself (confirmed via `git status`),
  consistent with the reference contract's freshness rule.

## Findings

- None

## Remaining risk

- The actual grouping/winner SQL behavior against real playoff/play-in data
  was verified by the builder against E2025 (per the spec's Step 2 *Done
  when*), not independently re-run against a live database in this review;
  this project's own testing standard treats that as dry-run/manual
  verification, not a unit-test gap.
- `build_aggregates()` now repeats the same per-table dry-run/insert block a
  fourth time (previously three); this follows the existing pattern exactly
  and is not a regression introduced by this change, but the function itself
  was already long before this feature and remains a standing duplication
  candidate if a fifth aggregate table is added later.
- Pre-existing, out-of-scope open finding F-01 (season-stats API flapping on
  game nights) is unrelated to this diff and was left untouched.

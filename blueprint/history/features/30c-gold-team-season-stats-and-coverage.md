# Feature: Gold team season stats and coverage

**From build-plan:** feature 30c
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/gold-team-season-stats-and-coverage`

## Goal

Rebuild the three season-scoped team totals and data-coverage tables in local
`gold` from Silver, preserving their published page contracts while Neon
publishing remains paused.

## In scope

- Derive `gold.app_team_season_stats` from played Silver games and their `total`
  team box scores, with one club row per phase actually present.
- Derive `gold.app_coverage_seasons` and `gold.app_coverage_games` from Silver
  games, box scores, standings, registrations, player stats, shots and events.
  Preserve the eight ordered coverage items and the historical status rules.
- Register the three tables in the existing Gold CLI, including table selection,
  read-only dry run and quality-only modes, transactional per-season replacement,
  and an all-season local rebuild.
- Update the Gold README, root README, data dictionary and agent commands for
  these local outputs and the continuing publish pause.

## Out of scope

- Bronze or Silver changes, external fetching, Neon writes, web-app changes,
  and activation of the refresh publisher (30f).
- Records and postseason series (30d), identity (30e), and advanced-statistics
  features 19 and 25–29. Do not add synthetic all-phase team rows.

## Build loop

`workflow.stepReview` is `feature`: finish the small steps and present one
review packet. Checkpoint commits are disabled; `/complete` owns the work
commit. Because this feature replaces persisted Gold season slices, inventory
their current local rows before the first replacement. Stop for a specific
decision if unexpected user data occupies those tables. After verification,
obtain the configured independent review against an approved checkpoint.

## Build steps

- [x] **Step 1 - Define and derive team totals** - register the exact
  `app_team_season_stats` key and columns in `gold_etl/schema.py`, then derive
  own and opponent totals from `silver.games` and
  `silver.game_team_stats` using only played games and `stats_kind = 'total'`.
  Use the historical output column names from the data dictionary and map
  current clean Silver names through `postgres_etl/flat_schema.py`. Preserve
  unavailable measures as NULL, not zero. *Done when:* focused fixtures cover
  both sides, each present phase including historical `TS`, missing box scores,
  missing measures, unplayed/forfeit games and no qualifying rows; the Gold
  unit suite passes.
- [x] **Step 2 - Derive coverage rows** - register season and game coverage
  keys with `items JSONB NOT NULL`. Compute eight ordered objects with the
  historical keys, labels, count types and statuses from the data dictionary
  and feature 12's archived contract. Base season rows on `silver.seasons`
  and game rows on every `silver.games` row, including scheduled games. Use
  current Silver table/column names while preserving the approved shot and
  play-by-play coverage change. *Done when:* fixture tests cover zero
  applicable games, no data, partial/incomplete/full availability, distinct
  club/person/game counts, scheduled games, and game rows whose three
  season-wide items equal the season row; the Gold suite passes.
- [x] **Step 3 - Store, select and check derived slices** - extend the Gold
  loader, CLI and quality module for all three tables. `-tb` can select each
  one; default/all includes them after the existing 30a/30b tables. Each
  table/competition/season replacement is atomic and rerunnable, including
  zero-row clearing where valid. Dry run and quality-only connect read-only;
  quality recomputes from Silver and compares full keys, values and JSON items,
  not counts alone. Use registered identifiers and parameterized scope values.
  *Done when:* fake-cursor tests cover table creation, selection, empty slices,
  stale-row removal, rollback on insert failure, missing tables, value drift and
  read-only modes; no Silver or Neon write path exists.
- [x] **Step 4 - Rebuild local history and document it** - record pre-build
  Gold counts, build the three outputs for all locally loaded EuroLeague
  seasons, and run read-only equality checks across all of them. Compare
  representative team totals and both coverage scopes with their Silver
  inputs; rerun E2025 and confirm unchanged counts and complete rows. Update
  `gold_etl/README.md`, root `README.md`, `docs/DATA_DICTIONARY.md` and
  `AGENTS.md`. *Done when:* full local Gold quality passes, the targeted
  comparisons and rerun are recorded, and all four declared unit suites pass.

## Files / areas

- `gold_etl/schema.py`, focused derivation modules, `loader.py`, `quality.py`,
  `main.py`, `tests/` and README.
- `postgres_etl/flat_schema.py`: read the Silver column registry and clean-name
  mappings; do not change Silver.
- `docs/DATA_DICTIONARY.md`, root `README.md`, `AGENTS.md`: Gold contracts and
  commands. Feature 12's archive is a read-only historical coverage reference.

## Data / contracts

- All three keys include `competition_code` and `season_code`.
  `app_team_season_stats` adds (`phase_code`, `club_code`);
  `app_coverage_seasons` has one row per loaded season;
  `app_coverage_games` adds `game_code` and has one row per Silver fixture.
- Team stats store `club_name`, `games_played`, and `own_` / `opp_` NUMERIC
  values for the 20 historical measures listed in the data dictionary. For a
  published name such as `field_goals_made2`, preserve the numeral placement;
  current Silver uses `two_pointers_made` for that input. For a
  club's played game, own measures come from its `total` row and opponent
  measures from the opposite side's `total` row. `games_played` counts that
  club's played games with an own `total` row. Group only by actual phase;
  do not produce an `all` or `PS` row. A missing source measure or required
  opposing box score leaves the affected aggregate NULL rather than zero.
  Derive the display name deterministically from that season's Silver club
  row, with a game-side name fallback when the club row is absent.
- Each coverage `items` value is an array of exactly eight objects in this
  order: `boxScores`, `periodScores`, `officialStandings`, `rosters`,
  `playerPhotos`, `seasonStatistics`, `shotLocations`, `playByPlay`. Each object
  has `key`, `label`, `status`, `availableCount`, `applicableCount`; preserve the
  exact historical labels from the feature 12 archive. The first, second,
  fifth, seventh and eighth items use game-status rules; the others use
  roster-status rules. Applicable zero gives `notYetApplicable`; available
  zero gives `unavailable`; available at least applicable gives `available`;
  otherwise the status is `partial` or `incomplete`, respectively.
- Season counts follow the data dictionary exactly: distinct games with team
  totals, period scores, shots and play-by-play against played games; distinct
  clubs in basic standings or registrations against distinct season clubs;
  distinct players with a headshot in played game-player rows against played
  games; distinct players in Silver traditional season stats against distinct
  season clubs. Keep the historical player-versus-game/club denominator quirk.
  For a game row, items 1, 2, 5, 7 and 8 narrow all counts to that game and
  use applicable 1 only when it is played; items 3, 4 and 6 copy the season
  counts and statuses. The shot and play-by-play items read the actual Silver
  tables rather than hardcoding unavailability.
- `-sc all` selects seasons loaded in Silver. A missing Gold table is a quality
  error. An ordinary load replaces only the requested table/competition/season
  slice; failure retains its prior rows. No Bronze read or Neon write occurs.

## Testing

- Focused tests: `python -m unittest discover -s gold_etl/tests`.
- Existing suites: `cd api_requests && python -m unittest tests.test_scrapper`,
  `python -m unittest discover -s postgres_etl/tests`, and
  `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Unit tests use fixtures and fake cursors, without API or database access.
  Live evidence is the local full build, read-only Gold quality/SQL comparisons
  and a controlled E2025 rerun. There is no browser or combined Verify command.

## Notes for the AI

- Reuse 30a/30b's registered schema, season selection, transactional loader and
  read-only quality patterns. Keep the three derivations focused; do not add a
  general aggregation framework or dependency.
- Use current Silver names (`standings_basic`, `season_player_stats_traditional`,
  `headshot_url`, `played`, `stats_kind`) where the historical dictionary still
  shows retired app table names. Do not let Gold-derived `PS` rows alter the
  Silver-based `seasonStatistics` coverage count.
- Check current local Gold objects and counts before replacing anything. Keep
  Neon and the web app untouched; publish remains feature 30f.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":8989,"specSha256":"86a80cb2233ff6be62150f01aa4a3fcde5608c13666155f6edbe7c47dbef43be","branch":"refs/heads/feature/gold-team-season-stats-and-coverage","head":"2242188eacddec42875af3873f1966410161b907","baseRef":"refs/heads/main","baseCommit":"5b1a4f1c58e22264b6e3d4b10fb25fed1033a6e0","sourceTree":"c14b89307e7d7e557938f6f79930b573f00f72fc","absentOptional":[]} -->

## Independent review

# Independent Review

**Status:** passed
**Target commit:** 2242188eacddec42875af3873f1966410161b907
**Base commit:** 5b1a4f1c58e22264b6e3d4b10fb25fed1033a6e0
**Base ref:** main
**Spec hash:** 86a80cb2233ff6be62150f01aa4a3fcde5608c13666155f6edbe7c47dbef43be
**Prepared by:** codex
**Builder model:** unknown (runtime did not expose exact model)
**Requested reviewer:** codex
**Requested model:** gpt-6-sol
**Requested execution:** automatic
**Requested at:** 2026-09-28T13:58:00Z
**Workflow:** regular
**Check required:** no
**Reviewer adapter:** codex
**Reviewer model:** gpt-6-sol
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-09-28T14:00:43Z
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Commands

- `python -m unittest discover -s gold_etl/tests`: pass, 49 tests.
- `cd api_requests && python -m unittest tests.test_scrapper`: pass.
- `python -m unittest discover -s postgres_etl/tests`: pass, 49 tests.
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass, 19 tests.
- `python gold_etl/main.py -sc E2025 -tb app_team_season_stats app_coverage_seasons app_coverage_games --quality-only`: pass.
- `python gold_etl/main.py -sc all --quality-only`: pass, E2000 through E2026.
- Read-only SQL inspection of Gold table columns, row counts, and coverage JSON item lengths: pass.

## Evidence

- Reviewed complete `5b1a4f1c58e22264b6e3d4b10fb25fed1033a6e0..2242188eacddec42875af3873f1966410161b907` delta, all 15 changed files, against the verified spec, Silver schema, data dictionary, and feature 12 archive.
- Exact HEAD, `main` merge base, spec SHA-256, and clean product worktree matched the request before and after review.
- All 20 team measures map to existing Silver team-stat columns; registered schema has 46 team columns and the coverage tables have 3 and 4 columns.
- Gold has 27 season coverage rows for 27 Silver seasons and 7,065 game coverage rows for 7,065 Silver games; all persisted coverage arrays have eight items.
- Load and quality paths use registered table names and parameterized scope values; read-only modes set a read-only transaction. No Silver or Neon write path was introduced.

## Findings

- None in the reviewed delta. Existing F-05 (unverified P3) and F-06 (open P2) remain unchanged in the ledger.

## Remaining risk

- Existing F-06 records reduced refresh regression test coverage outside this feature; existing F-05 tracks an unobserved fetch correction case.
- No combined Verify, lint, typecheck, security scan, or performance benchmark command is declared. Audit used code inspection, declared unit suites, and local read-only database checks.

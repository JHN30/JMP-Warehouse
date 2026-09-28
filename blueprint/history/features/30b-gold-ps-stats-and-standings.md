# Feature: Gold PS stats and standings

**From build-plan:** feature 30b
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/gold-ps-stats-and-standings`

## Goal

Rebuild the two former derived outputs locally from Silver: postseason `PS`
player-season statistics in Gold and the page-shaped `gold.app_standings` table.
Keep the 30a source projections intact and Neon publishing paused.

## In scope

- Derive `phase_code = 'PS'` rows for `gold.season_player_stats_traditional`
  and `gold.season_player_stats_misc` from played PI, PO, and FF games and their
  Silver box scores. Preserve the former postseason rules described below.
  Advanced and scoring remain API-only: the former builder had no defensible
  box-score derivation for those categories.
- Build `gold.app_standings` from the seven `silver.standings_*` tables and
  `silver.clubs`, using `silver.standings_basic` as the exact row/key driver.
  Preserve the historical page contract in `docs/DATA_DICTIONARY.md` and the
  feature 9 archive, with current clean Silver column names.
- Extend the local Gold CLI's season/table selection, read-only dry run, and
  read-only quality path for these derived outputs. Rebuild each derived
  table/competition/season slice transactionally and idempotently.
- Build and validate all locally loaded EuroLeague seasons without fetching.
  Update documentation for the new local outputs and the publish pause.

## Out of scope

- Changing Bronze or Silver data, the 16 Gold source projection contracts,
  Neon, the web app, or the paused pipeline publisher.
- New advanced/scoring `PS` estimates; team season stats and coverage (30c),
  records and postseason series (30d), cross-season identity (30e), and Gold
  publishing (30f). Features 19 and 25–29 remain separate.
- A new framework or dependency, compatibility views, and table drops.

## Build loop

`workflow.stepReview` is `feature`: finish the small steps, then present one
review packet. Checkpoint commits are disabled; `/complete` owns the work
commit. This changes persisted derived data, so obtain the selected independent
review against an approved immutable checkpoint after verification. Before
replacing local derived rows, record any existing `gold.app_standings` and `PS`
row counts. If unexpected data exists, stop for the owner's decision. No Neon
writes.

## Build steps

- [x] **Step 1 - Derive postseason rows from Silver** - add a focused Gold
  postseason transform using `silver.games` and `silver.game_player_stats`,
  with same-season Silver player and club data only for optional display fields.
  Port the former builder's played-phase filter, participation rule, metric
  math, NULL propagation, per-game qualification, sorting and rounding without
  reading Bronze. *Done when:* pure fixture tests cover PI/PO/FF, excluded RS
  and unplayed games, zero-minute players, missing measures, zero attempts,
  overtime minutes, double/triple doubles, a player changing clubs, and an
  empty postseason; the existing Gold tests pass.
- [x] **Step 2 - Store and select `PS` rows** - write only the `PS` slice of
  Gold traditional and misc tables in one transaction per table and scope.
  Keep 30a's non-`PS` slice untouched. Extend `-tb`, `--dry-run`, and
  `--quality-only` so selecting either table handles its source and `PS` slices
  in a defined order; a default/all run includes both. *Done when:* fake-cursor
  tests cover named columns, stable keys and ordinals, zero-row clearing,
  reruns, rollback after insert failure, absent seasons before DELETE, and
  read-only dry run and quality checks; neither Silver nor Neon is written.
- [x] **Step 3 - Define and build page-shaped standings rows** - register
  `gold.app_standings` with the historical key and field types. Derive one row
  per `silver.standings_basic` key, left joining the other four parent feeds,
  using club crest and the two ordered child feeds for JSONB lists. Preserve
  missing-feed NULL semantics and UTC ISO millisecond date strings. *Done when:*
  fixture tests verify all field mappings, missing feeds/clubs, ordered empty
  and populated lists, null dates, and duplicate-key rejection against the
  former app-table contract.
- [x] **Step 4 - Load and validate standings** - add transactional per-scope
  replacement for `gold.app_standings` and make it selectable in the existing
  Gold CLI, including `--list-tables`, read-only dry run, and quality-only
  checks. Check exact key parity with `silver.standings_basic` and complete
  field/list equality with Silver, not counts alone. *Done when:* focused
  tests cover empty seasons, missing feeds, stale row removal, rollback on
  failure, missing table, mismatched keys/values, and read-only modes.
- [x] **Step 5 - Build local history and document it** - inventory existing
  derived Gold objects and `PS` counts first, then rebuild all locally loaded
  EuroLeague seasons from Silver. Verify source-slice equality still passes,
  `PS` count/value rules and standings key/value parity pass for each season,
  and an E2025 rerun changes no count or row. Update `gold_etl/README.md`,
  root `README.md`, `docs/DATA_DICTIONARY.md`, and `AGENTS.md` commands while
  marking only the derived local contract active; Neon remains paused. *Done
  when:* local full build and read-only quality pass, representative postseason
  and standings rows are compared with their Silver inputs, an E2025 rerun is
  idempotent, and all four declared unit suites pass.

## Files / areas

- `gold_etl/`: new postseason and standings derivation modules, Gold table
  registry/loader/quality/CLI extensions, tests, and README.
- `postgres_etl/flat_schema.py`: source column and key definitions; read and
  reuse rather than changing Silver. Historical `postgres_etl/postseason.py`
  and feature 9's archived contract are read-only rule references.
- `docs/DATA_DICTIONARY.md`, root `README.md`, `AGENTS.md`: current local Gold
  derived tables, commands, and continued Neon pause.

## Data / contracts

- `PS` means played PI/PO/FF games only. A player contributes one appearance
  for a box-score row with `seconds_played > 0` and a real person key (not a
  synthetic `unknown-*` placeholder). Aggregate by
  person key across those phases. `games_played` counts those appearances;
  `games_started` counts Silver `started = true`; minutes are the sum of
  `seconds_played / 60`, including overtime. Counting measures are summed from
  the matching clean Silver game-player columns (points, made/attempted 2s,
  3s and free throws, rebounds, assists, steals, turnovers, blocks, fouls and
  PIR). A measure is NULL if any contributing game has it NULL. Percentages
  use total made/attempted, are NULL for missing or zero attempts, and round
  to one decimal with half-even rounding. Per-game counting measures use the
  same rounding; minutes keep their exact fraction.
- Both `accumulated` and `perGame` modes have traditional and misc `PS` rows.
  Per-game rows require the player's appearances to exceed half the postseason
  games played by the club on their latest appearance. Misc wins/losses use
  game scores; double/triple doubles count games with at least two/three of
  points, rebounds, assists, steals and blocks at 10 or more. Misc counts are
  identical in both modes and its minutes are per game. Use the latest
  postseason appearance for player name and club; optional age/images/club TV
  fields come from deterministic same-season Silver API rows and stay NULL
  when absent. Sort traditional by minutes and misc by games played, then
  minutes, then person key; assign zero-based `entry_ordinal` within each
  category and mode. No played postseason means no `PS` rows.
- `gold.app_standings` has primary key (`competition_code`, `season_code`,
  `phase_code`, `round_number`, `club_code`). Base club/group fields and all
  prefixed feed columns use the historical data-dictionary contract. Parent
  feeds absent for a basic row yield NULL in every column of that feed. `form`
  and `streak_history` are JSONB arrays ordered by `result_ordinal` and
  `streak_ordinal`; empty arrays are `[]`. Date members use UTC ISO strings
  with three milliseconds digits or JSON null. No basic rows clears the Gold
  season slice. No row-order contract exists; consumers order by group,
  basic position, club code.
- `-sc all` means seasons in `silver.seasons`. `-tb app_standings` selects only
  standings; selecting traditional or misc includes the source projection and
  its owned `PS` slice; selecting advanced or scoring remains source-only.
  `--dry-run` and `--quality-only` connect read-only. Ordinary loads replace
  one derived table/competition/season slice atomically; failures preserve the
  prior slice. Registered identifiers and parameterized scope values only.
  Neon stays unchanged until 30f.

## Testing

- New and extended focused tests: `python -m unittest discover -s gold_etl/tests`.
- Existing suites: `cd api_requests && python -m unittest tests.test_scrapper`,
  `python -m unittest discover -s postgres_etl/tests`, and
  `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Unit tests use fixtures and fake cursors, never an API or database. Live
  evidence is the local Gold build, read-only quality/SQL comparisons across
  all available seasons, representative full rows, and a controlled rerun.
  There is no browser test or combined Verify command.

## Notes for the AI

- Translate the former `postseason.py` rules from v2 JSON to Silver columns;
  do not restore its Bronze read path. The former builder produced traditional
  and misc only. Use the feature 9 archive and current data dictionary for
  `app_standings`'s former published contract, but build it locally in `gold`.
- Reuse the 30a season selection, connection, source registry and per-scope
  transaction pattern. Keep derived output ownership separate from 30a's
  non-`PS` source-copy slice. Do not create a general transformation framework.
- Check the actual current local Gold state before any replacement. Do not
  infer that source-projection quality proves derived-row quality. Do not
  publish to Neon or modify the web app.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":10197,"specSha256":"5e58ecec9f18a94ac27d46bd9ed240cacd89435abe5f970c61917d106c020bac","branch":"refs/heads/feature/gold-ps-stats-and-standings","head":"0ae8f19c8c47771ff0bf7d5b4c2c824e5d04b817","baseRef":"refs/heads/main","baseCommit":"61694c47a87a5bc772dac3154a2519de60cfcb2b","sourceTree":"9829c39ba73a2376cb621323642d40a223a85dc9","absentOptional":[]} -->

## Independent review

# Independent Review

**Status:** passed
**Target commit:** 0ae8f19c8c47771ff0bf7d5b4c2c824e5d04b817
**Base commit:** 61694c47a87a5bc772dac3154a2519de60cfcb2b
**Base ref:** main
**Spec hash:** 5e58ecec9f18a94ac27d46bd9ed240cacd89435abe5f970c61917d106c020bac
**Prepared by:** codex
**Builder model:** unknown (runtime did not expose exact model)
**Requested reviewer:** codex
**Requested model:** gpt-6-sol
**Requested execution:** automatic
**Requested at:** 2026-09-28T12:51:55Z
**Workflow:** regular
**Check required:** no
**Reviewer adapter:** codex
**Reviewer model:** gpt-6-sol
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-09-28T12:58:34Z
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Commands

- `git rev-parse HEAD`, `git merge-base main HEAD`, SHA-256 of `blueprint/context/current-feature.md`, and `git status --short --untracked-files=all`: pass; target, base and spec hash match, with only this review record dirty.
- `python -m unittest discover -s gold_etl/tests`: pass (38 tests).
- `python -m unittest discover -s postgres_etl/tests`: pass (49 tests).
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass (19 tests).
- `cd api_requests && python -m unittest tests.test_scrapper`: pass (24 tests).
- `python gold_etl/main.py -sc all --quality-only`: pass (E2000-E2026, 17 selected tables).
- Read-only E2025 SQL count probe: pass (standings basic/Gold 760/760; eligible players/traditional PS/misc PS 124/124/124; advanced/scoring PS 0/0). The first shell invocation had a PowerShell quoting syntax error before database access; the corrected probe passed.
- `git diff --check 61694c47a87a5bc772dac3154a2519de60cfcb2b..0ae8f19c8c47771ff0bf7d5b4c2c824e5d04b817`: pass.

## Evidence

- Reviewed the complete 16-file `61694c47a87a5bc772dac3154a2519de60cfcb2b..0ae8f19c8c47771ff0bf7d5b4c2c824e5d04b817` delta, including the spec, four documentation files, Gold schema, CLI, loaders, quality checks, derivations and five test files. Followed the Silver schema and archived feature 9 and postseason contracts. Excluded generated state, existing unrelated findings, and third-party code.
- Postseason reads played PI/PO/FF Silver games and positive-minute real-person box scores, propagates missing measures, computes half-even per-game values, and writes only the PS slice. Standings uses the basic feed as its key driver, registered feed names and columns, ordered JSON lists, UTC millisecond dates, and a per-scope transaction. Quality checks compare complete derived row values; all-season local quality passed.
- Security: SQL identifiers come from registered tables and scope values are parameterized. Performance: seasonal reads and in-memory grouping are bounded by the selected season; no new network or Neon path. Tests: no skipped, focused, or placeholder tests found in the Gold suite.
- Applicable standards checked: Python standard-library-first approach, registered SQL identifiers and parameterized values, transactional local scope replacement, NULL preservation, unittest fixtures, and no Neon writes. No source, spec, or configuration file was edited by this reviewer.

## Findings

- None. No findings ledger entry was added or changed; existing F-05 and F-06 are outside this feature's delta.

## Remaining risk

- The historical Neon `app_standings` copy was not queried; local Gold quality compares against a fresh Silver derivation, and the archived page contract was checked in source.
- No lint, typecheck, security scanner, or profiling command is configured for this project.

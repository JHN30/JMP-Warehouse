# Feature: Silver schema and clean names

**From build-plan:** feature 16a
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/silver-schema-and-clean-names`

## Goal

Make the local database follow the medallion layers agreed on 2026-09-27. The
28 cleaned source tables live in a `silver` schema with clean table names and
one standard column name per stat, and hold API data only. Today's gold code
(page and aggregate tables) is removed, because feature 30 rebuilds gold from
silver. Neon publishing pauses until then. All old local `public` tables are
dropped and every season is rebuilt from bronze.

## In scope

- A `silver` schema. Local connections use `search_path = silver`, so table
  names in SQL are the bare silver names (`games`, not `app_games`).
- 28 silver tables with the names and column renames in Data / contracts.
  The same stat has the same column name in v2 and v3 tables.
- Remove the derived `PS` rows from the season player stats tables (API data
  only in silver).
- Remove today's gold code and its tests:
  - `records.py`, `players.py`, `aggregates.py`, `postseason.py`;
  - the `app_standings` page builder (`standings_page` source);
  - the gold table definitions in `flat_schema.py`;
  - the gold-only quality checks (app_standings key parity, team season stats
    negatives, coverage item keys, team stats points cross-check);
  - the loader's gold dispatch in `main.py`.
- Remove the one-time commands and code: `--drop-retired` (loader and
  publisher), `--drop-old-names`, the legacy `etl_flat_*` rename-on-load and
  rename-on-publish, and the `RENAMED_TABLES`, `RETIRED_*` and
  `legacy_name`/`rename_*`/`drop_*` helpers.
- Pause Neon publishing:
  - `neon_publish` keeps its season-publish engine (one transaction per season,
    shrink guard, per-game diff) but has no tables to publish;
  - its CLI says publishing is paused until feature 30;
  - `pipeline.py` skips the publish stage when there is nothing to publish and
    reports `Publish:  paused (no gold tables until feature 30)`.
- Drop every table in local `public` (`app_*`, `etl_flat_*`, 37 today),
  after recording their row counts, then rebuild all seasons into `silver`.
- Update the docs: data dictionary (silver tables and names; the gold "Web-app
  tables" section kept as reference but marked paused), `README.md`,
  `postgres_etl/README.md`, `neon_publish/README.md`, `tables_to_csv/README.md`,
  `api_requests/README.md` (loaded-into column), `AGENTS.md` Commands.

## Out of scope

- Provenance columns and the load log (16b).
- Any gold table, the player and club identity tables, and publishing to Neon
  again (feature 30).
- Per-record enrichment (feature 25).
- Changing Neon: it keeps its current tables and data untouched. The web app
  keeps reading Neon as it is; it is updated after feature 30 (owner decision:
  no compatibility views).
- Bronze and the fetcher (unchanged, apart from the README's loaded-into
  column).

## Build loop

`workflow.stepReview` is `feature`: build all steps, then one review packet.
Checkpoint commits are disabled; `/complete` makes the feature commit. Step 4
drops local tables: ask the owner before the drop. Neon is never touched.

## Build steps

- [x] **Step 1 - Silver schema and names** - in `postgres_etl/flat_schema.py`:
  - rename the tables (logical name = silver table name);
  - apply one column-name map when fields are built, so every table uses the
    names below;
  - `physical_name()` returns the bare silver name.

  `common/db.connect()` sets `search_path` to `silver`, and the loader creates
  the schema if missing (`CREATE SCHEMA IF NOT EXISTS silver`). The
  `game_stat_gaps.stat_name` values use the new column names. Update the
  loader, quality checks, CSV export and their tests. *Done when:*
  - `python postgres_etl/main.py --list-tables` lists exactly the 28 names;
  - `python postgres_etl/main.py -sc 2025 --dry-run` passes;
  - `python -m unittest discover -s postgres_etl/tests` passes;
  - a test asserts that no silver column keeps an old name from the map.
- [x] **Step 2 - Remove gold and one-time code** - delete the modules, tests,
  table definitions, quality checks and CLI options listed in scope. Stop
  appending derived `PS` rows in `raw_transform.py`. *Done when:*
  - a search of the code and tests (excluding `blueprint/history/`, `old/` and
    `data/`) finds no `app_`, `etl_flat_`, `drop_retired`, `drop_old_names`,
    `records`, `postseason` or `standings_page` reference, except in docs that
    describe history;
  - all test suites pass.
- [x] **Step 3 - Pause publishing** - apply the `neon_publish` and `pipeline.py`
  changes from scope. The engine tests keep testing the engine with example
  table names. *Done when:*
  - `python neon_publish/main.py --dry-run` prints the paused message, touches
    nothing and needs no Neon URL;
  - a pipeline test shows the summary line `Publish:  paused (no gold tables
    until feature 30)` and no Neon URL prompt;
  - the three test commands pass.
- [x] **Step 4 - Drop `public` and rebuild silver** - with the owner's yes:
  1. record the row count per season of every `public` table (read-only);
  2. drop all `app_*` and `etl_flat_*` tables in `public`;
  3. run `python postgres_etl/main.py -sc all` in the background.

  *Done when:*
  - `public` has no `app_*` or `etl_flat_*` table;
  - `silver` has the 28 tables for E2000-E2026;
  - the quality report has 0 errors;
  - each silver table's row count per season equals its old table's count,
    except `season_player_stats_traditional` and `_misc`, which are lower by
    exactly the old `PS` rows. The comparison is in the review packet.
- [x] **Step 5 - Docs** - update the docs listed in scope. *Done when:*
  - no current doc describes an `app_*` or `etl_flat_*` table as a local table
    being built;
  - the gold section of the data dictionary starts with a "paused until
    feature 30" note;
  - `AGENTS.md` Commands no longer lists the drop commands and says publishing
    is paused.

## Files / areas

- `common/db.py`
- `postgres_etl/`:
  - changed: `flat_schema.py`, `flat_loader.py`, `flat_transform.py`,
    `raw_transform.py`, `quality.py`, `main.py`;
  - removed: `records.py`, `players.py`, `aggregates.py`, `postseason.py` and
    their tests;
  - other tests updated.
- `neon_publish/publish.py`, `neon_publish/main.py`, `neon_publish/tests/`
- `pipeline.py`
- `tables_to_csv/` (names only; export reads `silver` through the search path)
- Docs: `docs/DATA_DICTIONARY.md`, `README.md`, `postgres_etl/README.md`,
  `neon_publish/README.md`, `tables_to_csv/README.md`,
  `api_requests/README.md`, `AGENTS.md`

## Data / contracts

**Silver tables** (schema `silver`; keys unchanged, every key still starts with
`competition_code`, `season_code`):

| Silver table | Was (local) |
| --- | --- |
| `seasons`, `clubs`, `people`, `registrations`, `rounds`, `games`, `game_officials`, `game_period_scores`, `game_player_stats`, `game_team_stats`, `play_by_play`, `shots` | `app_<same name>` |
| `game_stat_gaps` | `etl_flat_game_stat_gaps` |
| `season_player_stats_traditional`, `_advanced`, `_scoring`, `_misc` | `app_season_stats_*` (without `PS` rows) |
| `season_team_stats_traditional`, `_advanced`, `_opponents_traditional`, `_opponents_advanced` | `etl_flat_season_team_stats_*` |
| `standings_basic`, `standings_calendar`, `standings_streaks`, `standings_ahead_behind`, `standings_margins`, `standings_calendar_streaks`, `standings_basic_form` | `app_standings_basicstandings`, `_calendarstandings`, `_streaks`, `_aheadbehind`, `_margins`, `_calendar_streaks`, `_basic_form` |

**Column names** (applied in every table that has the column; the source JSON
paths do not change):

| Old column | Silver column |
| --- | --- |
| `assistances` | `assists` |
| `fouls_commited` | `fouls_committed` |
| `fouls_received` | `fouls_drawn` |
| `blocks_favour` | `blocks` |
| `valuation` | `pir` |
| `field_goals_made2` / `field_goals_attempted2` | `two_pointers_made` / `two_pointers_attempted` |
| `field_goals_made3` / `field_goals_attempted3` | `three_pointers_made` / `three_pointers_attempted` |
| `field_goals_made_total` / `field_goals_attempted_total` | `field_goals_made` / `field_goals_attempted` |
| `points_scored` | `points` |
| `time_played` (seconds) | `seconds_played` |
| `possesions` | `possessions` |
| `quater1_*`, `quater3_*` | `quarter1_*`, `quarter3_*` |
| `longest_wins_streak_*` / `longest_loses_streak_*` | `longest_win_streak_*` / `longest_loss_streak_*` |
| `point_difference1to5`, `6to10`, `11to15`, `_more_than15` | `point_difference_1_to_5`, `_6_to_10`, `_11_to_15`, `_more_than_15` |
| `dorsal` / `dorsal_raw` | `jersey_number` / `jersey_number_raw` |

- Types, keys, `NULL` rules and cleaning are unchanged; only names change.
- `game_stat_gaps.stat_name` holds silver column names (for example
  `plus_minus`, `fouls_drawn`), or `*` for no box score.
- The web app is not changed. It keeps reading Neon's current tables until
  feature 30, so it shows no new data in the meantime.

## Testing

- Commands: `cd api_requests && python -m unittest tests.test_scrapper`,
  `python -m unittest discover -s postgres_etl/tests`,
  `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Logic that needs tests:
  - the column-name map (no old name survives, keys intact);
  - `stat_name` values;
  - `physical_name` and the search path;
  - the publish pause in the CLI and the pipeline.
- Live evidence: the E2025 dry run, and the full rebuild with the row-count
  comparison (step 4). No combined Verify command exists (build-plan item 17).

## Notes for the AI

- Prefer the search path over schema-qualifying every query. Keep the bare
  `"name"` quoting already used in SQL.
- Capture the old row counts before dropping anything.
- `pipeline.py` must still fetch and load the current season. Only publishing
  pauses.
- Many existing tests assert `app_*` names; update the names in them, don't
  delete the tests (except those for removed gold or one-time code).


<!-- blueprint:completion {"schemaVersion":1,"specBytes":10079,"specSha256":"74113b455bf219499d5443d22617e3431f3567f73e9e06a6ca08b35a5bc66f8d","branch":"refs/heads/feature/silver-schema-and-clean-names","head":"96bf52df5520433e812336196c111d39accfc009","baseRef":"refs/heads/main","baseCommit":"2db3ed0392506f30ea10219e9a504dd784d800bc","sourceTree":"acd45f267f55201b67c26a3e254601082afd3f87","absentOptional":[]} -->

## Findings

### 16a/F-04 [P3] closed - The pipeline summary does not report stats feeds kept from an earlier fetch

**File:** pipeline.py:309
**Found:** 2026-09-27 by /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** `python pipeline.py` is the owner's normal command. The
`[kept]` lines print while the fetch runs, but the final Refresh summary reads
only `changed_resources` and `failed_requests` from the fetch summary file, so
a feed kept from an earlier fetch is not mentioned where the owner looks. The
owner asked for a visible warning when the API answers badly.
**Suggested fix:** read `kept_resources` from the fetch summary (default `[]`
for older files) and add it to the `Fetch:` summary line, e.g. `…, 2 stats
feed(s) kept from an earlier fetch (API answered worse)`, with a
`build_summary` test.
**Resolution:** closed on 2026-09-27 by independent /audit: `pipeline.py` reads `kept_resources` at line 314 and `build_summary` lists the count and resource paths at lines 157-160. The previous dedicated summary test was removed in this feature; see F-06 for the separate coverage loss.

## Independent review

# Independent Review

**Status:** passed
**Target commit:** 96bf52df5520433e812336196c111d39accfc009
**Base commit:** 2db3ed0392506f30ea10219e9a504dd784d800bc
**Base ref:** main
**Spec hash:** 74113b455bf219499d5443d22617e3431f3567f73e9e06a6ca08b35a5bc66f8d
**Prepared by:** codex
**Builder model:** unknown (runtime did not expose exact model)
**Requested reviewer:** codex
**Requested model:** gpt-6-sol
**Requested execution:** automatic
**Requested at:** 2026-09-27T18:52:17.2347733+02:00
**Workflow:** regular
**Check required:** no
**Reviewer adapter:** codex
**Reviewer model:** gpt-6-sol
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-09-27T19:02:08.5194635+02:00
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Commands

- `git rev-parse HEAD main; git merge-base main HEAD`: pass, checkpoint and base match request.
- `Get-FileHash blueprint/context/current-feature.md -Algorithm SHA256`: pass, exact spec hash matches request.
- `git status --porcelain=v1 --untracked-files=all`: pass, only review and findings evidence differs from target.
- `git diff --check 2db3ed0..96bf52d`: pass.
- `python -m unittest tests.test_scrapper` from `api_requests/`: pass.
- `python -m unittest discover -s postgres_etl/tests`: pass, 38 tests.
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass, 19 tests.
- `python postgres_etl/main.py -sc 2025 --dry-run`: pass, 28 tables and 322,106 rows validated.
- `python postgres_etl/main.py --list-tables`: pass, 28 silver table names.
- `python neon_publish/main.py --dry-run`: pass, paused without a Neon connection.

## Evidence

- Reviewed the complete recorded `2db3ed0392506f30ea10219e9a504dd784d800bc..96bf52df5520433e812336196c111d39accfc009` delta, including source, tests, plans, READMEs, and data dictionary. Traced affected callers in `common/`, `postgres_etl/`, `tables_to_csv/`, `neon_publish/`, and `pipeline.py`.
- Checked project coding standards and the verified active spec; source paths and column mapping remain separate, all 28 source tables use bare silver names, and the publisher CLI remains paused.
- Excluded retired `old/`, bronze `data/`, generated logs, and Git internals from source review. No browser flow applies to this project.
- No skipped or focused tests were found in the selected suites.

## Findings

- F-04 closed; F-06 open [P2]. F-05 remains unverified and was not used to scope this review.

## Remaining risk

- F-06: refresh failure, retry, and kept-feed summary paths lack dedicated regression tests after the test rewrite.
- The live PostgreSQL row-count comparison and quality report recorded by the build were not independently repeated in this code audit; Check was not required.

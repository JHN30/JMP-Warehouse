# Feature: Gold records and postseason series

**From build-plan:** feature 30d
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/gold-records-and-postseason-series`

## Goal

Rebuild the three all-time record leaderboards and the postseason matchup table in local `gold` from typed `silver` data. Keep the existing app-facing table contracts ready for feature 30f to publish.

## In scope

- `gold.app_records_player_seasons`, `gold.app_records_single_games`, and `gold.app_records_team_seasons`: top 50 per metric across every locally loaded EuroLeague season. They are competition-scoped, not season-scoped.
- `gold.app_postseason_series`: one row per season, postseason phase, and unordered club pair, including scheduled games in the pairing.
- Gold schema registration, deterministic derivation, transactional replacement, read-only dry run and quality checks, focused tests, and current documentation.

## Out of scope

- Neon publishing and refresh-pipeline integration (30f); the web app remains on its current Neon data.
- Player and club identity tables (30e), advanced stats (25-29), and any change in the web-app repo.
- EuroCup records, new record metrics, inferred bracket labels, or a series-complete flag. Season-scoped series can use the CLI's supported competition selection.
- Reworking Silver data or restoring retired `postgres_etl/records.py` and aggregate loaders.

## Build loop

Follow `workflow.stepReview: "feature"`: complete the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; no step commits are required. `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Register four Gold tables.** Add the three record tables with key `(competition_code, metric, rank_ordinal)` and `season_code` as a data column. Add `app_postseason_series` with key `(competition_code, season_code, phase_code, club_a_code, club_b_code)`. Preserve the historical app-facing row fields and types documented in `docs/DATA_DICTIONARY.md` and the feature 11/13 archives; check those exact fields before coding. Use the current `gold_etl/schema.py` registry and table creation pattern. *Done when:* schema tests confirm the four names, columns, types, keys, and `gold_etl/main.py --list-tables` lists them without a database connection.
- [x] **Step 2 - Derive the global record rows.** Read all locally loaded EuroLeague seasons from `silver`, with no Bronze or Gold source dependency. Player-season records use traditional season stats with `phase_code = 'all'` and `mode = 'accumulated'`, for `points_scored` (Silver `points`), `total_rebounds`, `assists`, and `pir`. Single-game records use played games joined to player box scores, for `points`, `valuation`, `total_rebounds`, and `assistances`. Team-season records sum `stats_kind = 'total'` rows for played games by season and club, for the same four game metrics. Exclude unavailable metric values, keep names on each record row, rank 1 through at most 50 per metric, and use the dictionary's exact deterministic tie-break order. A selected record table is replaced for the entire competition in one transaction; each record table is independent. *Done when:* focused derivation and replacement tests cover ties, a metric with fewer than 50 rows, played-game filtering, season aggregation, null values, complete-history selection, rerun stability, and rollback on write failure.
- [x] **Step 3 - Derive postseason series.** Read `silver.games` for `PI`, `PO`, and `FF`; group by season, phase, and alphabetically ordered club codes. Preserve the historical fields and `games` JSONB keys from the dictionary. Include scheduled games with null result fields, count wins only for played games, and set `winner_club_code` only when one club has strictly more wins. Order the JSON game list by round and a stable game-code tie-break; serialize `scheduledAt` as a JSON date string in the same UTC convention used by the app-facing game data. Replace one competition/season slice transactionally. *Done when:* focused tests cover reversed home/away pairings, multi-game playoffs, one-game PI/FF pairings, ties, scheduled games, exclusion of `TS`, ordering, and rollback on write failure.
- [x] **Step 4 - Wire the Gold CLI and equality checks.** Add all four tables to `--list-tables`, `-tb`, `--dry-run`, `--quality-only`, and the default `all` selection. Run each selected record table once per invocation over full local EuroLeague history, independent of `-sc`; `-sc` still scopes series and existing tables. Reject a EuroCup records selection clearly. Keep dry run and quality connections read-only. Compare each persisted table's complete keys and values with a fresh Silver derivation, including ordered JSON games, rather than relying on counts alone. Keep other Gold paths unchanged. *Done when:* CLI and quality tests show correct selection, full-history record behavior, season-scoped series behavior, missing-table and value-drift failures, and no writes in read-only modes; `python -m unittest discover -s gold_etl/tests` passes.
- [x] **Step 5 - Document and verify local data.** Update `gold_etl/README.md`, `docs/DATA_DICTIONARY.md`, and the relevant command/status text in `README.md` and `AGENTS.md`. Build the four tables for every locally loaded season, then run Gold quality checks. Inspect the top record per metric, row/rank counts, and representative PI/PO/FF pairings against read-only Silver queries, including a partial or tied series when available. Record the observed counts and commands in the review packet. *Done when:* documentation matches the implemented schema and CLI; the four table builds and read-only quality checks pass against the local database. If the database is unavailable, report the blocker and leave this step incomplete.

## Files / areas

- `gold_etl/schema.py`, `gold_etl/main.py`, `gold_etl/loader.py`, `gold_etl/quality.py`
- New Gold derivation module(s) beside `gold_etl/team_season.py`; focused tests under `gold_etl/tests/`
- `gold_etl/README.md`, `docs/DATA_DICTIONARY.md`, `README.md`, `AGENTS.md`

## Data / contracts

- Records are global leaderboards within `competition_code = 'E'`. Primary key is `(competition_code, metric, rank_ordinal)`; `season_code` identifies the season of a ranked row. Values are numeric and rows are self-contained with the historical player or club identity and display fields. Ranking is dense, 1-50 per metric, with fewer rows when fewer qualify. Player-season and team-season ties use value descending, season ascending, then person or club key ascending. Single-game ties also use game code ascending before person key.
- Series primary key is `(competition_code, season_code, phase_code, club_a_code, club_b_code)`, where `club_a_code < club_b_code`. `games_played` counts all games in the pairing, including scheduled games. Win counts use only `played = TRUE`; a tied series has a null winner. `games` is a non-null JSONB array of `{gameCode, roundNumber, scheduledAt, localClubCode, roadClubCode, localScore, roadScore, winnerClubCode}` entries. Unplayed entries have null scores and winner. No bracket status or inferred format is stored.
- Reads come from `silver`, writes stay in local `gold`; no Silver, Bronze, Neon, or web-app writes. Parameterize competition and season values; table names must come from the registered allowlist. A failed replacement preserves the prior committed Gold rows. Empty source selections yield empty derived tables or slices rather than stale rows.
- Historical feature 11/13 archives and `docs/DATA_DICTIONARY.md` define existing app-facing field names. Where an exact field, type, or serialization detail is unclear, inspect those records before implementation and preserve the existing contract rather than inventing a new one.

## Testing

- Focused unit tests: `python -m unittest discover -s gold_etl/tests` (49 existing tests passed while drafting).
- Regression suites before completion: `python -m unittest discover -s postgres_etl/tests`, `cd api_requests && python -m unittest tests.test_scrapper`, and `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Local database: `python gold_etl/main.py -sc all -tb app_records_player_seasons app_records_single_games app_records_team_seasons app_postseason_series`, then matching `--quality-only`; also exercise `--dry-run` and one-table selections. Check global record rank sequences and representative series against read-only Silver queries. No combined Verify command is declared.

## Notes for the AI

- Current Gold has 16 source tables plus standings, team-season stats, and two coverage tables. Follow their transactional and equality-check patterns, with a separate global path for the three record tables.
- A record rebuild needs every loaded Silver season even when `-sc` names only one. Make that CLI behavior visible in output so users do not mistake it for a season-only rebuild.
- Do not write to Neon or resume `pipeline.py` publishing. Do not hardcode a best-of-N series rule.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":9142,"specSha256":"5aaceb4a0984174c2cd39808732a22d15c003f683cae8255450196f8d273ab90","branch":"refs/heads/feature/gold-records-and-postseason-series","head":"1fe74fde667bbfb02c213f86386a4f7681378cfa","baseRef":"refs/heads/main","baseCommit":"dad3663e5fb761ca1a37e32b56bc3310f6b56573","sourceTree":"eca1833815a3afd1ed147f374ae904ba0b7932cc","absentOptional":[]} -->

## Independent review

# Independent Review

**Status:** passed
**Target commit:** 1fe74fde667bbfb02c213f86386a4f7681378cfa
**Base commit:** dad3663e5fb761ca1a37e32b56bc3310f6b56573
**Base ref:** refs/heads/main
**Spec hash:** 5aaceb4a0984174c2cd39808732a22d15c003f683cae8255450196f8d273ab90
**Prepared by:** codex
**Builder model:** unknown (runtime did not expose exact model)
**Requested reviewer:** codex
**Requested model:** gpt-6-sol
**Requested execution:** automatic
**Requested at:** 2026-09-28T15:05:36.649Z
**Workflow:** regular
**Check required:** no
**Reviewer adapter:** codex
**Reviewer model:** gpt-6-sol
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-09-28T15:07:20Z
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Commands

- `python -m unittest discover -s gold_etl/tests`: pass (62 tests).
- `python -m unittest discover -s postgres_etl/tests`: pass (49 tests).
- `cd api_requests && python -m unittest tests.test_scrapper`: pass.
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass (19 tests).
- `python gold_etl/main.py -sc all -tb app_records_player_seasons app_records_single_games app_records_team_seasons app_postseason_series --quality-only`: pass.
- `python gold_etl/main.py --list-tables`: pass.

## Evidence

- Reviewed the full `dad3663e5fb761ca1a37e32b56bc3310f6b56573..1fe74fde667bbfb02c213f86386a4f7681378cfa` delta, including derivations, schema, loader, CLI, quality checks, tests, and documentation; compared the new fields and rules with Silver schema and feature 11/13 contracts.
- Read-only equality checks passed for all 27 locally loaded EuroLeague seasons. SQL parameters and registered table names preserve the existing database trust boundary; each replacement uses a transaction.
- HEAD, recorded merge base, exact spec hash, and working tree matched the pending request. Only this review evidence file differed from the target before completion.

## Findings

- None. Existing F-05 (unverified) and F-06 (P2 open) were outside this feature delta and remain unchanged in the ledger.

## Remaining risk

- No lint, typecheck, build, security scanner, or performance benchmark command is declared for this project.
- The reviewer ran read-only database equality checks; the prior local build and representative source-data checks were not repeated because Audit does not write product data.

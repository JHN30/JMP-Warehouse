# Feature: Gold player and club identity

**From build-plan:** feature 30e
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/gold-player-and-club-identity`

## Goal

Build cross-season player and club identity tables in local `gold` from loaded `silver` people, player registrations, and clubs. Make them available to Gold's build, dry-run, and equality-check commands without publishing to Neon.

## In scope

- `gold.app_players`: restore the documented player identity contract, one row per player within a competition, using every locally loaded season.
- `gold.app_club_identities`: one row per club within a competition, with its latest profile and season span. This name stays distinct from the season-scoped `gold.clubs` source table.
- Schema registration, deterministic derivation, transactional replacement, read-only dry run and quality checks, focused tests, and documentation.

## Out of scope

- Neon publishing, refresh-pipeline integration, and web-app changes (30f); the web app continues reading its existing Neon data.
- Career stat totals, player head-to-head results, full club profile history, and advanced stats (25-29).
- Changes to Silver, Bronze, season-scoped Gold copies, or other Gold derivations.

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; no step commits are required. `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Register both identity tables.** Add `app_players` and `app_club_identities` to `gold_etl/schema.py` with the fields, types, and competition-wide keys below. Preserve the documented `app_players` names and JSON shape. *Done when:* schema tests verify exact columns, types, and keys, and `--list-tables` lists both names without a database connection.
- [x] **Step 2 - Derive player identities.** Read `silver.registrations` with `role_code = 'J'` and matching `silver.people` and `silver.clubs` rows across all loaded seasons. Produce one player row per `(competition_code, person_code)`, with latest known profile, player season span, and ordered distinct season/club JSON entries. Use deterministic tie-breaks within a season. Treat missing or conflicting player codes as integrity errors. Replace the selected competition's rows in one transaction, including an empty result. *Done when:* tests cover multiple seasons and clubs, repeated registrations, non-player roles, missing optional fields, latest-row selection, identity conflicts, empty history, rerun stability, and rollback on write failure.
- [x] **Step 3 - Derive club identities.** Read all loaded `silver.clubs` seasons for the selected competition. Produce one row per `(competition_code, club_code)`, taking latest-season `name`, `crest_url`, `country_code`, and `country_name`, plus first/last season and a distinct season count. Use stable selection if source rows collide and fail quality on conflicting identity keys. Replace the selected competition's rows transactionally, including an empty result. *Done when:* tests cover renamed clubs, missing optional fields, distinct season counting, deterministic selection, empty history, rerun stability, and rollback on write failure.
- [x] **Step 4 - Wire Gold commands and equality checks.** Include both tables in default `all`, `-tb`, `--list-tables`, `--dry-run`, and `--quality-only`. Each selected identity table rebuilds once per invocation from all loaded seasons for the selected competition, regardless of `-sc`; the CLI explains that scope. Dry run and quality-only remain read-only. Compare persisted keys and every field, including ordered player-club JSON, with fresh Silver derivation. *Done when:* CLI and quality tests cover selection, complete-history scope, count and value drift, missing tables, and no writes in read-only modes; the Gold test suite passes.
- [x] **Step 5 - Document and verify local data.** Update `gold_etl/README.md`, `docs/DATA_DICTIONARY.md`, and relevant status and commands in `README.md` and `AGENTS.md`. Build both identities from every locally loaded Silver season, run Gold quality-only checks, and inspect representative multi-season players and renamed clubs against read-only Silver queries. *Done when:* documentation matches schema and commands; local builds and quality checks pass, with observed row counts and commands recorded for review. If the local database is unavailable, report the blocker and leave this step incomplete.

## Files / areas

- `gold_etl/schema.py`, `gold_etl/main.py`, `gold_etl/loader.py`, `gold_etl/quality.py`
- New identity derivation module beside `gold_etl/records.py`; focused tests in `gold_etl/tests/`
- `gold_etl/README.md`, `docs/DATA_DICTIONARY.md`, `README.md`, `AGENTS.md`

## Data / contracts

- `app_players` key: `(competition_code, person_code)`, where `person_code` is a non-null stable code from `silver.people` matched through `person_key`. Include only people with at least one `role_code = 'J'` registration. A missing person/code is an integrity error, not an inferred ID. `name`, `country_code`, `country_name`, `height_cm`, `weight_kg`, `birth_at`, `birth_country_code`, `birth_country_name`, `position`, and `position_name` are latest known values from the maximum player season, with stable within-season tie-breaks. `first_season_code`, `last_season_code`, and `seasons_played INTEGER NOT NULL` use distinct player-registration seasons. `clubs JSONB NOT NULL` is an ordered array of `{seasonCode, clubCode, clubName}`, one entry per distinct player season and club.
- `app_club_identities` key: `(competition_code, club_code)` with non-null club code. `name`, `crest_url`, `country_code`, and `country_name` come from the latest loaded `silver.clubs` season for that code; unavailable values remain null. `first_season_code` and `last_season_code` are non-null source season codes, and `seasons_played INTEGER NOT NULL` counts distinct seasons in `silver.clubs`. The table has no JSON season history. Name changes do not create a second identity.
- Both tables cover all loaded Silver seasons for the selected competition even when `-sc` names one season. A rebuild atomically replaces all rows for that competition; a failed replacement retains the prior committed rows. Empty source history removes stale identities. Read-only commands never mutate Gold. Identifiers come from the registered allowlist, and competition values are SQL parameters.
- The earlier `docs/DATA_DICTIONARY.md` `app_players` description and feature 14 archive define the historical player field names and JSON serialization. Inspect that exact contract before coding. No prior club identity contract exists; the club fields above are the owner's selected 30e contract. Publication mapping belongs to 30f.

## Testing

- Focused unit tests: `python -m unittest discover -s gold_etl/tests`.
- Regression suites before completion: `python -m unittest discover -s postgres_etl/tests`; `cd api_requests && python -m unittest tests.test_scrapper`; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Local database: `python gold_etl/main.py -sc all -tb app_players app_club_identities`, then matching `--quality-only` and `--dry-run`. Check row counts, identity uniqueness, player club ordering, and latest club profiles with read-only Silver queries. No combined Verify command is declared.

## Notes for the AI

- Follow the existing global Gold table pattern for all-season derivation and competition-wide replacement. Keep source projections and season-scoped derivations intact.
- Preserve source `NULL` for unavailable profile values. Do not fill missing fields from unrelated seasons.
- Do not write to Neon or resume pipeline publishing. Keep identity output deterministic across identical Silver inputs.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":7880,"specSha256":"bdcb00a9db8caf7dafe5d7ad1e2b66a1fa2bf6841f5f89c4601342bd4bc992f8","branch":"refs/heads/feature/gold-player-and-club-identity","head":"45832b3dc75935f337e949dd77385f9bd6a8d3b8","baseRef":"refs/heads/main","baseCommit":"e1ab316aaadec0d63a168f20eba0ba592e6fb033","sourceTree":"0bf1194a9aba1b50c6ce731cdcaec5044ff0bcc7","absentOptional":[]} -->

## Independent review

# Independent Review

**Status:** passed
**Target commit:** 45832b3dc75935f337e949dd77385f9bd6a8d3b8
**Base commit:** e1ab316aaadec0d63a168f20eba0ba592e6fb033
**Base ref:** refs/heads/main
**Spec hash:** bdcb00a9db8caf7dafe5d7ad1e2b66a1fa2bf6841f5f89c4601342bd4bc992f8
**Prepared by:** codex
**Builder model:** unknown (runtime did not expose exact model)
**Requested reviewer:** codex
**Requested model:** gpt-6-sol
**Requested execution:** automatic
**Requested at:** 2026-09-28T20:04:15Z
**Workflow:** regular
**Check required:** no
**Reviewer adapter:** codex
**Reviewer model:** gpt-6-sol
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-09-28T20:06:36.394Z
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Commands

- `git diff --check e1ab316aaadec0d63a168f20eba0ba592e6fb033 45832b3dc75935f337e949dd77385f9bd6a8d3b8`: pass
- `python -m unittest discover -s gold_etl/tests`: pass (70 tests)
- `python -m unittest discover -s postgres_etl/tests`: pass (49 tests)
- `cd api_requests && python -m unittest tests.test_scrapper`: pass
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass (19 tests)
- `python gold_etl/main.py -sc all -tb app_players app_club_identities --dry-run`: pass
- `python gold_etl/main.py -sc all -tb app_players app_club_identities --quality-only`: pass

## Evidence

- Reviewed the complete commit delta from `e1ab316aaadec0d63a168f20eba0ba592e6fb033` through `45832b3dc75935f337e949dd77385f9bd6a8d3b8` across `AGENTS.md`, `README.md`, `blueprint/context/current-feature.md`, `docs/DATA_DICTIONARY.md`, `gold_etl/README.md`, `gold_etl/identity.py`, `gold_etl/loader.py`, `gold_etl/main.py`, `gold_etl/quality.py`, `gold_etl/schema.py`, and `gold_etl/tests/test_identity.py`; checked nearby Silver schema, transform, and Gold test helpers.
- Live read-only derivation found 3,749 player rows and 89 club identity rows across E2000-E2026; Gold equality checks passed.
- Verified registered SQL identifiers, parameterized competition values, transaction-scoped replacement, deterministic grouping and ordering, and read-only CLI paths. No skipped or focused Gold tests found.
- Generated, third-party, and cache paths were excluded; this current-scope review covered all changed paths.

## Findings

- None

## Remaining risk

- None identified

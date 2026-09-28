# Feature: Publish Gold to Neon

**From build-plan:** feature 30f
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/publish-gold-to-neon`

## Goal

Publish the current app-facing local `gold` tables into Neon's `public.app_*` tables with guarded, atomic replacement, then restore publishing to the one-command refresh. The owner chose an in-place Neon cutover; the separate web app must be coordinated with the clean table and column names.

## In scope

- Publish the 16 Gold source projections and ten current Gold derivations. The source targets use `public.app_<gold_source_name>`; derived `gold.app_*` names stay `public.app_*`. In particular, `gold.clubs` maps to season-scoped `public.app_clubs`, while `gold.app_club_identities` maps to its own cross-season table.
- Reuse the retained Neon transaction, row-count shrink guard, per-game play-by-play/shots diff, CSV streaming, and secret-redaction patterns, now reading `gold` and its schema registry.
- Publish one selected EuroLeague season and the selected competition-wide records and identity tables atomically; expose an honest read-only dry run.
- Restore `pipeline.py` as fetch Ã¢â€ â€™ Silver load Ã¢â€ â€™ Gold build and quality Ã¢â€ â€™ guarded Neon publish, with retry state retained until publish commits.
- A reviewed schema preflight and migration plan for existing Neon `app_*` tables whose names, columns, or constraints differ from Gold; focused tests and documentation.

## Out of scope

- Historical bulk publishing (feature 15), EuroCup publishing (feature 18), scheduled refresh (feature 20), and the planned advanced-stat tables (25-29).
- Changes in the separate web-app repository, compatibility views, or a second permanent set of Neon tables.
- Automatic dropping of Neon tables or columns, silent weakening of existing constraints, and writes to Silver or Bronze.
- A live Neon cutover without the owner's separate approval after the exact preflight and dry-run results are reviewable.

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; no step commits are required. `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Register the Gold-to-Neon contract and preflight.** Define the fixed allowlist of the 16 `gold_etl.schema.SOURCE_NAMES` plus ten current `DERIVED_NAMES`, each Gold source and `public.app_*` target, its columns/key from `GOLD_TABLES`, and whether it is season-scoped or competition-wide. Inspect the current Neon schema read-only before writing migration code. Produce and review the exact table/column rename or additive changes needed for the owner's in-place cutover; reject unknown or incompatible existing constraints before any publish. Keep one-time migration separate from normal recurring refresh; never infer target identifiers from user text. *Done when:* tests prove all 26 mappings and scopes, `--list-tables` works without connections, and a read-only preflight reports missing/compatible/incompatible targets without DDL or data writes.
- [x] **Step 2 - Adapt guarded publishing to Gold.** Read only registered `gold` columns from one consistent local snapshot. For season tables, preserve one Neon transaction for all selected tables of the selected competition and season, with before/after row-count verification and the existing 90% shrink guard. Preserve per-game checksums and changed-game copying for `play_by_play` and `shots`; compare using the Gold columns and target schema. For the three record tables and two identity tables, replace the selected competition's full table scope once per invocation inside that same transaction, with the same shrink guard and post-copy counts. A failed schema check, shrink check, copy, or count check rolls back the entire selected publish; `--allow-shrink` overrides only the row-count guard when explicitly supplied. *Done when:* fake-connection tests cover first publish, rerun, changed games, removed games, empty/large shrink, global scope, failures after partial COPY, rollback, and no Silver reads or Neon writes in dry run.
- [x] **Step 3 - Restore the standalone publisher CLI.** Replace the paused `neon_publish/main.py` with `-sc current|YYYY|EYYYY` (one EuroLeague season, current by default), `-tb` from the registered allowlist, `--list-tables`, `--dry-run`, and `--allow-shrink`. Require the local Gold quality check for selected tables and scope before a real publish. The dry run reports local and Neon counts, proposed per-game changes, schema problems, and any shrink refusal without DDL or data changes. Use the direct non-pooled `NEON_DATABASE_URL` from the existing environment/.env path; never print it or credentials. Fail clearly on missing configuration, invalid selection, absent Gold tables, incompatible Neon schema, and database errors. *Done when:* CLI tests cover flags, season/global routing, quality failures, missing URL, redacted error output, and dry-run read-only behavior; the Neon test suite passes.
- [x] **Step 4 - Restore the refresh pipeline.** After a successful Silver load, build and quality-check the selected season in Gold, then resolve the Neon URL safely and publish. Preserve the existing no-change short circuit. Keep `publish_pending` true after changed fetches, failed Silver/Gold/Neon stages, and `--dry-run-publish`; clear it only after a committed publish. A retry with no newly changed fetch must still complete pending work. `--allow-shrink` reaches only the publisher when explicitly supplied. The final summary distinguishes skipped, dry-run, failed, and committed publish and names the failed stage without exposing the URL. *Done when:* fake-stage tests cover changed/unchanged fetches, load/Gold/quality/Neon failures and retries, dry run, forced refresh, prompt timing, redaction, pending-state transitions, and successful summary; no fetch or live Neon call occurs in unit tests.
- [x] **Step 5 - Document and verify the cutover.** Update `neon_publish/README.md`, `README.md`, `AGENTS.md`, and `docs/DATA_DICTIONARY.md` with the exact target list, global-versus-season scope, in-place migration, app coordination, dry run, rollback/retry behavior, and live-publish approval boundary. Run all declared test suites. Check local Gold quality and run a read-only Neon schema/count preflight and `--dry-run` for the current season; compare representative source, derived, global, and per-game rows. Present the exact proposed remote migration and publish counts for separate owner approval, then perform the approved live cutover and read-only post-publish checks. *Done when:* docs match behavior; tests and preflight pass; after explicit live approval, Neon has the expected selected-season and competition-wide counts and the refresh command can complete without leaving a pending state. If credentials or approval are unavailable, report the blocker and leave this step incomplete.

## Files / areas

- `neon_publish/main.py`, `neon_publish/publish.py`, `neon_publish/tests/test_publish.py`
- `gold_etl/schema.py` for the existing Gold registry; `gold_etl/main.py` and quality functions for readiness checks
- `pipeline.py` and focused pipeline tests beside the existing refresh tests
- `neon_publish/README.md`, `README.md`, `AGENTS.md`, `docs/DATA_DICTIONARY.md`

## Data / contracts

- The publish allowlist is today's 26 Gold tables: 16 season-scoped source projections, `app_standings`, three team/coverage tables, `app_postseason_series`, three competition-wide record tables, and two competition-wide identity tables. Season tables publish only the requested season; global tables publish all locally built Gold rows for the selected competition. No implicit historical-season bulk publish.
- Source table physical names are `public.app_<Gold source name>`; existing derived `app_*` names remain unchanged. Columns, PostgreSQL types, and natural keys come from `gold_etl.schema.GOLD_TABLES`. A target that already exists must pass a compatibility preflight before mutation. The one-time in-place rename plan is explicit and reviewed; the recurring pipeline never guesses, drops, or silently rewrites legacy schema.
- A normal publish is one Neon transaction for all selected tables and scopes. The local export uses a consistent snapshot. The prior Neon rows remain visible until commit; a failure rolls back all selected changes. Count checks require exact agreement with the local snapshot. The shrink guard refuses a target scope below 90% of its existing Neon count unless `--allow-shrink` is explicitly passed; dry run reports the refusal without changing data.
- `play_by_play` and `shots` use deterministic per-game row checksums; only changed games are copied, and games absent locally are removed within the transaction. The five global tables use a full competition replacement once per invocation. A no-change rerun is safe and does not append duplicates.
- Neon connection details remain in memory, from `NEON_DATABASE_URL` or the existing `.env` reader; logs and subprocess output redact credentials. The web app reads Neon and is maintained in another repository. This in-place schema cutover may change columns it expects; the owner will coordinate that update. No compatibility views are added.

## Testing

- Focused unit tests: `python -m unittest neon_publish.tests.test_publish`, with fake local/Neon connections and pipeline stage runners.
- Regression suites: `python -m unittest discover -s gold_etl/tests`; `python -m unittest discover -s postgres_etl/tests`; `cd api_requests && python -m unittest tests.test_scrapper`; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Read-only checks before live approval: `python gold_etl/main.py -sc EYYYY --quality-only` and `python neon_publish/main.py -sc EYYYY --dry-run`, plus Neon schema and count queries. After approved publish, compare counts and representative rows on Neon. No combined Verify command is declared.

## Notes for the AI

- Approved during 30f implementation: the latest cached E2026 scoring `all/accumulated` feed was empty while the API smoke check returned 226 players. Refresh only that Bronze resource through `EuroScrapas.fetch_to_cache`, reload local Silver and Gold, and rerun the Neon preview before the approved in-place cutover. Do not bypass the shrink guard.

- Start with the actual Neon schema inspection: the old publisher still uses `postgres_etl.flat_schema`, where `PUBLISHED_TABLES` is empty and the local search path is `silver`. Explicitly qualify both Gold source and Neon target schema.
- The Gold-derived global tables cannot use the old season-only DELETE/filter path. Keep their competition replacement and the selected season in the same Neon transaction.
- The refresh currently clears `publish_pending` immediately after Silver load. Move that transition after a confirmed Neon commit; this is needed for retries after a Gold or Neon failure.
- The source names and some columns differ from the historical Neon schema. Treat an incompatible preflight as a blocker and bring the exact migration to the owner for review before any remote write. Do not run a live publish or migration on the strength of this spec alone.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":11320,"specSha256":"2852374fe8fdfc0e0faf870504567748ba7947d0837d5d4d38e9baba37d2060d","branch":"refs/heads/feature/publish-gold-to-neon","head":"12490d0ece7a11b70f5b31c3b4770f66ea6cbda1","baseRef":"refs/heads/main","baseCommit":"d6445c9b3028bf058e2596b8aed12e524f181b66","sourceTree":"52315eb0d2878c97260ecf6b8554e76fe3d16b25","absentOptional":[]} -->

## Findings

### 30f/F-06 [P2] closed - Refresh regression tests were removed during the publish pause

**File:** neon_publish/tests/test_publish.py:23
**Found:** 2026-09-27 by independent /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** The former `RefreshCommandTests` covered load failure and retry state, fetch no-op, summary parsing, and reporting stats feeds kept from an earlier fetch. The replacement has one successful `--skip-fetch` test. A regression in the normal fetch path or the pending-load state can now pass all configured suites while `python pipeline.py` skips or misreports a needed load.
**Suggested fix:** Restore focused fake-stage tests for a changed fetch, unchanged fetch, load failure and retry, and the kept-feed summary, using the paused publishing contract.
**Resolution:** Independent 30f review re-examined `neon_publish/tests/test_publish.py`: changed and unchanged fetches, load/Gold/Neon failures, pending retries, and kept-feed summary reporting are covered. The focused suite passes (28 tests, including CSV tests). Closed.

## Independent review

# Independent Review

**Status:** passed
**Target commit:** 12490d0ece7a11b70f5b31c3b4770f66ea6cbda1
**Base commit:** d6445c9b3028bf058e2596b8aed12e524f181b66
**Base ref:** refs/heads/main
**Spec hash:** 2852374fe8fdfc0e0faf870504567748ba7947d0837d5d4d38e9baba37d2060d
**Prepared by:** codex
**Builder model:** unknown (runtime did not expose exact model)
**Requested reviewer:** codex
**Requested model:** gpt-6-sol
**Requested execution:** automatic
**Requested at:** 2026-09-28T21:14:52Z
**Workflow:** regular
**Check required:** no

**Reviewer adapter:** codex
**Reviewer model:** gpt-6-sol
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-09-28T21:17:05Z
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Commands

- `git status --porcelain=v1 -uall`, `git rev-parse HEAD`, and `git merge-base refs/heads/main HEAD`: pass; only review and findings evidence differs from target.
- `Get-FileHash blueprint/context/current-feature.md -Algorithm SHA256`: pass; exact spec hash matches request.
- `git diff --check d6445c9b3028bf058e2596b8aed12e524f181b66 12490d0ece7a11b70f5b31c3b4770f66ea6cbda1`: pass.
- `python neon_publish/main.py --list-tables`: pass; 26 fixed mappings.
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass; 28 tests.
- `python -m unittest discover -s gold_etl/tests`: pass; 70 tests.
- `python -m unittest discover -s postgres_etl/tests`: pass; 49 tests.
- `cd api_requests; python -m unittest tests.test_scrapper`: pass.
- `python neon_publish/main.py -sc E2026 --dry-run`: unavailable; reviewer task prohibits Neon access.

## Evidence

- Reviewed the full committed `d6445c9b3028bf058e2596b8aed12e524f181b66..12490d0ece7a11b70f5b31c3b4770f66ea6cbda1` delta: publisher contract, CLI, transaction and refresh paths, migration, tests, spec, and affected documentation. Followed Gold schema and stage callers for the table and scope contracts.
- Source and Neon identifiers are registry derived; values use parameters. Local export uses a repeatable-read snapshot, and all selected Neon scopes share one transaction with rollback on failure. No credential value was included in review evidence.
- Focused tests exercise scope mapping, shrink refusal, rollback, dry-run mode, pipeline retries, and output redaction. No skipped or placeholder tests were found in the changed test file.
- Closed F-06 after reviewing the restored refresh coverage and passing tests. F-07 and F-08 record non-blocking preflight defects.

## Findings

- F-06 closed.
- F-07 [P2] open: preflight misses stricter target nullability.
- F-08 [P2] open: preview can fail while reading incompatible target columns.

## Remaining risk

- `python neon_publish/main.py -sc E2026 --dry-run` was unavailable under the reviewer's no-Neon-access boundary; live remote schema and count behavior was not rechecked in this review. Check was not required by the request.
- There is no declared lint, typecheck, build, security scan, or performance benchmark command for this repository.

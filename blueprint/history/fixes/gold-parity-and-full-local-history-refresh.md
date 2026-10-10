# Fix: Gold parity and full local history refresh

**Type:** Fix
**Status:** verified
**Branch:** fix/full-local-history-refresh-cli

## The problem

Local Gold needed the same app-prefixed physical table names as Neon public,
with every historical row and existing index preserved. This completion covers
the Gold naming work and its full-history refresh follow-up as one local change.

Refreshing all local history currently requires four manual commands. The owner
requests one command including API fetching and one rebuilding Silver and Gold
from existing Bronze files. Prior Gold naming work is verified at checkpoint
8a111ec; its spec is preserved in Git and its independent receipt is in
logs/gold_name_alignment/review_checkout/blueprint/context/review.md.

## The fix

Add pipeline.py --all for local full-history fetching, Silver load, Gold build
and Gold quality checks. Add --all --skip-fetch for the same local stages using
cached Bronze only. Reuse existing stage runners, logs, summaries and native ETL
commands. Select API years from 2000 through the current season dynamically;
select all cached/loaded seasons for Silver and Gold. Preserve the existing
current-season publishing path. Reject conflicting season/publishing options
before any stage runs. Neither full-history mode may access Neon or ask for its
URL. Mark the normal current-season publish pending after local work starts so
a later current-season pipeline run can publish rebuilt data even if the API
returns no new resources. Leave database names, schemas and data rules intact.
No full-history API fetch, database rebuild, commit, merge or publish is requested
during implementation; verify orchestration with fake stages and existing suites.
Preserve unrelated README edits and prior review evidence.

## Build steps

- [x] Align all 47 local Gold physical names with Neon, migrate the 36 legacy
  names transactionally, preserve historical data and existing indexes, ensure
  all 51 Neon-equivalent indexes, and update every Gold reader/writer and the
  publisher. Done when table inventories and all 39 app table column contracts
  match, and the E2026 refresh and authorized live publish pass. These live
  criteria were verified on 2026-10-10 before the CLI follow-up.
- [x] Implement local full-history CLI routing, ordered stages, failure stops,
  pending-state behavior and summaries. Done when both commands select all
  local seasons, skip mode makes no API call, and neither path can publish.
- [x] Document the two commands and add VS Code tasks. Done when commands are
  visible through help, README and tasks, and all configured tests pass.

## Verify

Test stage order; unchanged fetch still rebuilds; dynamic year rollover; no Neon
URL resolution or remote subprocess; stop on each failed stage; retained pending
state; conflicting flag rejection; CLI main dispatch and log summaries.
Run all four existing unittest commands. No live full-history rebuild is needed
for this wrapper, whose underlying ETL stages were already verified.

## Evidence

- All 594 configured tests passed: API 46, Silver 199, Gold 277,
  publisher/CSV 72. Seven new orchestration tests cover the full-history paths.
- CLI help lists --all; both new VS Code tasks are present with unique labels.
- Read-only local catalog check: Gold has exactly 47 app-prefixed tables and
  no remaining legacy Gold names. Silver games, clubs and people still exist.
- git diff --check passed. Full-history API/download/load was not executed;
  commands and failure paths were exercised with injected stage runners.
- Regular audit/check/try-guide gates remain manual. This combined completion
  includes the persisted-data naming migration and therefore selects a fresh
  independent review of the complete main-to-checkpoint delta.
- Prior Gold naming review remains preserved at its approved checkpoint's
  clean review worktree. This fix is uncommitted; no merge or publish performed.

## Completion authorization

The owner explicitly approved final commits, local squash merge and deletion
of the work branch in this chat. The earlier README rewrite is kept out of this
pipeline checkpoint and will be committed separately after the local merge.
No push or additional live database operation is authorized.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":4352,"specSha256":"d8fae305af53f8d39aa4f2b489918ffffd93b759567ebda0f6f285bb29bcda43","branch":"refs/heads/fix/full-local-history-refresh-cli","head":"40981e4b3f51fe394016036a96d6133b053d9fe5","baseRef":"refs/heads/main","baseCommit":"bbb6a12cff9a0011ace582ffd0329d7a4adb9f20","sourceTree":"016bb4d9a5b85f62790083f69b231d49a14a28de","absentOptional":[]} -->

## Independent review

# Independent Review

**Status:** passed
**Target commit:** 40981e4b3f51fe394016036a96d6133b053d9fe5
**Base commit:** bbb6a12cff9a0011ace582ffd0329d7a4adb9f20
**Base ref:** main
**Spec hash:** d8fae305af53f8d39aa4f2b489918ffffd93b759567ebda0f6f285bb29bcda43
**Prepared by:** codex
**Builder model:** unknown (runtime did not expose exact model)
**Requested reviewer:** codex
**Requested model:** gpt-6-astra
**Requested execution:** automatic
**Requested at:** 2026-10-10T14:48:53Z
**Workflow:** regular
**Check required:** no

**Reviewer adapter:** codex
**Reviewer model:** gpt-6-astra
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-10-10T14:53:47Z
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Handoff

Review the verified combined Gold parity and full-history refresh spec and the
complete main merge-base-to-target delta in a fresh isolated subagent.
Read the project-local Audit skill and independent-review reference first.
Cover quality, security, performance and tests across all changed files.
The original README rewrite is backed up locally and restored to HEAD for this
checkpoint; it will be committed separately after completion.
Prior live database evidence is readable under logs/gold_name_alignment and
logs/refresh and is described in the committed Gold verification report.
Do not execute API fetches, database loads, migrations or live publication.
Do not edit source, tests, config or spec, commit, merge or accept findings.
Only findings.md and review.md may be written, besides generated audit activity.

## Commands

- `git status --short`, `git branch --show-current`, `git rev-parse HEAD`, `git merge-base main HEAD`, and raw SHA-256 of the active spec: passed before review and rechecked before receipt. The spec is tracked; only permitted review metadata differs from the target.
- `cd api_requests; python -m unittest tests.test_scrapper`: passed, 46 tests.
- `python -m unittest discover -s postgres_etl/tests`: passed, 199 tests.
- `python -m unittest discover -s gold_etl/tests`: passed, 277 tests.
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: passed, 72 tests.
- `python pipeline.py --help`: passed; full-history option present.
- `python gold_etl/main.py --list-tables` and `python neon_publish/main.py --list-tables`: passed; 47 physical Gold names match Neon names.
- `python gold_etl/migrate_names.py --help`: passed without a database connection.
- `python neon_publish/main.py --print-migration 30g`, `30h`, `30i`, and `30j`: passed; 12, 2, 4, and 3 app table definitions respectively, without database operations.
- `git diff --check main...HEAD` and `git diff --check`: passed.
- Read-only Python assertions over saved catalog/count/value JSON, the 972-row column CSV, and VS Code task JSON: passed.
- Targeted source/test searches: no unresolved legacy Gold relation references or skipped/focused/placeholder tests found in the reviewed changes.

## Evidence

- Reviewed the complete `bbb6a12cff9a0011ace582ffd0329d7a4adb9f20..40981e4b3f51fe394016036a96d6133b053d9fe5` delta, all 36 changed paths, against the verified combined spec and project standards. Included pipeline orchestration, Gold migration/schema/loaders/quality/PER readers, publisher contract/copy paths, changed tests, tasks and documentation. Followed adjacent API/Silver season selection, Gold dispatch, shared season helpers, publisher CLI and CSV catalog discovery. Unrelated source, retired code, caches and the prior review checkout were excluded; saved logs were evidence only.
- All 594 configured tests passed. Seven new history tests cover dynamic year bounds, cached mode, unchanged fetches, forwarding, each failed stage, pending state, dispatch and conflicting flags. Naming tests cover 47 mappings, 36 renames, collisions, missing/unexpected tables, idempotence, preview, transaction exception propagation and index creation. Publisher tests retain scope, shrink, quality-gate, rollback and redaction coverage.
- Quality/security: registered selectors determine physical Gold names; Silver names remain unchanged. Migration identifiers use psycopg2 Identifier, and all renames/index creation share a transaction. Publisher checks, season/global scopes, shrink guard and transactional replacement remain intact. Full-history routing cannot reach URL resolution or the publisher and marks current-season publishing pending before local loads.
- Performance: renames retain table storage and indexes; four secondary indexes are ensured alongside 47 primary keys. History stages run sequentially and reuse native loaders, per-season derivations and API cache/rate behavior. No new dependency or concurrent work was introduced.
- Compared builder-produced `logs/gold_name_alignment/local_before.json`, `local_renamed.json` and `local_after.json`: all 47 expected names, original OIDs/storage identities/columns/per-season counts and original index OIDs are preserved. Final local and Neon snapshots have matching column contracts and all 51 index definitions. `neon_before.json` equals `neon_after.json`.
- Builder-produced `published_scope_values.json` records matching typed values for 47 scopes and 71,952 rows. The committed CSV contains 972 matching columns across 39 requested app tables. This review checked the saved evidence's consistency, not live database state.
- Inspected builder-produced `logs/refresh/refresh_20261010_161154.log` and `refresh_20261010_161548.log`: successful preview and prior authorized E2026 publish, 38,361 source rows loaded, zero quality errors, Gold quality passed and one missing-attendance warning. These runs predate the history CLI follow-up.
- No reviewer API calls, database connections, migrations, loads or publishing. No source, tests, configuration or spec edited.

## Findings

- None added, closed or accepted. No P0/P1 blockers found. Existing F-05 remains P3 unverified and unchanged; its unchanged API-feed correction hypothesis did not define the review scope.

## Remaining risk

- Live migration preview/apply, database quality/catalog checks, E2026 refresh/publish, and `python pipeline.py --all` / `--all --skip-fetch` execution were unavailable under this handoff's no-API/no-database boundary. Saved builder evidence supports the prior Gold integration; history orchestration has fake-stage coverage, without a live all-history run or performance measurement.
- No build, lint, typecheck, combined Verify, security scanner or performance benchmark is configured. None was invented or claimed to pass. Browser checks do not apply; Check was explicitly not required.
- The root README rewrite was excluded from this checkpoint as requested and must be handled separately. This receipt covers only the exact target above.

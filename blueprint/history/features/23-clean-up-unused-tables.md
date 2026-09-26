# Feature: Clean up unused tables

**From build-plan:** feature 23
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/clean-up-unused-tables`

## Goal

Remove tables nothing uses, so the database holds only what the web app reads
or later features build on. This clears the ground before the schema split
(feature 16). Locally, stop loading and then drop the 9 `etl_flat_live_*`
tables (E2025 only, not fetched by default) and `etl_source_payloads` (a
300 MB copy of the bronze JSON). In Neon, drop the old `etl_flat_*` views and
stop publishing, then drop, the 7 `app_standings_*` feed tables that the web
app no longer reads. Bronze files are not touched.

## In scope

- Remove the 9 live tables and `source_payloads` from the loader: table
  definitions, transforms, loader batch special case, quality check, CSV export
  (automatic, since it iterates `TABLES`), and their tests.
- Stop publishing the 7 standings feed tables (`standings_basicstandings`,
  `standings_calendarstandings`, `standings_streaks`, `standings_aheadbehind`,
  `standings_margins`, `standings_calendar_streaks`, `standings_basic_form`)
  while still loading them locally under their current `app_standings_*` names.
  They feed `app_standings` checks and the coverage item `officialStandings`.
- A `--drop-retired` option (with `--dry-run`) in `postgres_etl/main.py` for
  the 10 retired local tables and in `neon_publish/main.py` for the 7 retired
  Neon feed tables.
- Keep `--drop-old-names` dropping all 23 old `etl_flat_*` views, including the
  7 standings-feed views, after the published list shrinks.
- Docs: `docs/DATA_DICTIONARY.md`, `README.md`, `postgres_etl/README.md`,
  `neon_publish/README.md`, the Commands section of `AGENTS.md`, and the
  fetcher's `-ds` help text for the optional live datasets.
- Running the drops locally and in Neon, each only after the owner's explicit
  go-ahead in chat.

## Out of scope

- `etl_flat_game_stat_gaps`: still needed. It moves to `core` in feature 16.
- The fetcher's optional `-ds live_boxscores|live_evolution|live_comparison|live_scoring`
  datasets: they keep archiving into bronze on request but are no longer loaded.
- Deleting any bronze file.
- Schemas, renames of kept tables, and new tables (features 16, 24+).
- Any change in `jmp-euroleague2`. Its backend reads none of the removed
  tables (checked in `backend/src` on 2026-09-26).

## Build loop

`workflow.stepReview` is `feature`: build all steps, then one review packet.
Checkpoint commits are disabled; `/complete` makes the feature commit. Step
4's Neon and local drops are live, destructive actions: pause and ask the owner
before each dry run against Neon and before each real drop.

## Build steps

- [x] **Step 1 - Stop loading the live tables and `source_payloads`** - remove
  `live_boxscores`, `live_boxscore_players`, `live_boxscore_teams`,
  `live_boxscore_period_scores`, `live_evolution`, `live_evolution_minutes`,
  `live_evolution_largest_differences`, `live_comparison`, `live_scoring` and
  `source_payloads` from `flat_schema.TABLES` (and `LIVE_PLAYER_STATS`, the
  `source_payloads` case in `physical_name`). Also remove their branches in
  `raw_transform.py` (`files`, `rows`, module docstring) and `flat_transform.py`,
  the batch-size special case in `flat_loader.py`, and `live_boxscore_players`
  from the person-reference checks in `quality.py`. Keep
  `resolve_live_person` and `LIVE_TEAM_MARKER(S)`, which play-by-play and shots
  use. Update `postgres_etl/tests`. *Done when:* `python postgres_etl/main.py
  --list-tables` lists none of the 9 live tables or `source_payloads`;
  `python postgres_etl/main.py -sc 2025 --dry-run` finishes without error;
  `python -m unittest discover -s postgres_etl/tests` passes.
- [x] **Step 2 - Stop publishing the standings feeds, keep their local names** -
  in `flat_schema.py`, define `RENAMED_TABLES` explicitly as the 23 tables
  feature 22 renamed (today's value). Remove the 7 feeds from
  `PUBLISHED_TABLES` (32 -> 25). Make `rename_local_tables` and
  `publish.drop_old_names` iterate `RENAMED_TABLES` instead of the published
  list. *Done when:* `physical_name("standings_basicstandings")` is still
  `app_standings_basicstandings`; `python neon_publish/main.py --list-tables`
  shows 25 tables without the feeds; `drop_old_names` still plans all 23
  `etl_flat_*` views (tested); `python -m unittest
  neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export` and the
  postgres tests pass.
- [x] **Step 3 - `--drop-retired` for local and Neon** - add
  `RETIRED_LOCAL_TABLES` (the 9 `etl_flat_live_*` physical names plus
  `etl_source_payloads`) and `RETIRED_NEON_TABLES` (the 7 `app_standings_*` feed
  physical names) to `flat_schema.py`. Add one function for both that, in a
  single transaction:
  - looks up each name with `relation_kinds`
  - drops each existing **table** with `DROP TABLE` (no `CASCADE`)
  - reports names that are missing ("already gone") or not a table (left alone)
  - in `--dry-run`, lists what would be dropped with row counts and changes
    nothing

  Wire it to `python postgres_etl/main.py --drop-retired [--dry-run]` and
  `python neon_publish/main.py --drop-retired [--dry-run]`. It is refused when
  combined with `-tb`, `-sc`, `--quality-only`, `--skip-quality-check` or
  `--drop-old-names`, like `--drop-old-names` today. A failure (for example an
  old `etl_flat_standings_*` view still depending on a feed table) rolls
  everything back and says to run `--drop-old-names` first. *Done when:* unit
  tests with a fake cursor cover drop, dry run, missing, non-table and
  refused-combination cases and pass; the local dry run lists exactly the 10
  local tables with row counts, and a second real run would report nothing left.
- [x] **Step 4 - Docs, then run the cleanup with the owner** - update the docs
  named in scope:
  - remove the live tables and the Source archive section from the data
    dictionary
  - say the standings feeds are local only
  - document `--drop-retired`
  - record that the old views are gone once dropped
  - add the fetcher help note that optional live datasets are archived in
    bronze only

  Then, each after an explicit yes:
  1. local `--drop-retired --dry-run`, then the real run
  2. Neon `--drop-old-names --dry-run`, then the real run
  3. Neon `--drop-retired --dry-run`, then the real run
  4. `python pipeline.py --dry-run-publish`

  *Done when:* a grep of the docs finds none of the removed tables described as
  current; local PostgreSQL has no `etl_flat_live_*` or `etl_source_payloads`;
  Neon has no `etl_flat_*` views and none of the 7 feed tables (as reported by
  the commands); the pipeline dry run publishes 25 tables with no errors.

## Files / areas

- `postgres_etl/flat_schema.py`, `raw_transform.py`, `flat_transform.py`,
  `flat_loader.py`, `quality.py`, `main.py`, `postgres_etl/tests/`
- `neon_publish/publish.py`, `neon_publish/main.py`, `neon_publish/tests/test_publish.py`
- `api_requests/utils.py` (help text only)
- `docs/DATA_DICTIONARY.md`, `README.md`, `postgres_etl/README.md`,
  `neon_publish/README.md`, `AGENTS.md` (Commands)

## Data / contracts

- **Local tables removed** (physical names): `etl_flat_live_boxscores`,
  `etl_flat_live_boxscore_players`, `etl_flat_live_boxscore_teams`,
  `etl_flat_live_boxscore_period_scores`, `etl_flat_live_evolution`,
  `etl_flat_live_evolution_minutes`, `etl_flat_live_evolution_largest_differences`,
  `etl_flat_live_comparison`, `etl_flat_live_scoring`, `etl_source_payloads`.
- **Local tables kept unchanged**: every `app_*` table (including the 7
  `app_standings_*` feeds) and `etl_flat_game_stat_gaps`.
- **Neon after the feature**: 25 published `app_*` tables; no `etl_flat_*`
  views; no `app_standings_*` feed tables. `app_standings` and every table in
  `backend/src/db/season-schema.ts` remain.
- **Drop contract**: only names in the two explicit lists, never derived from
  "whatever is not in `TABLES`". One transaction, all or nothing, no `CASCADE`.
  Re-runnable: a second run reports nothing left and succeeds. Neon access
  follows the existing `NEON_DATABASE_URL` handling; no URL is printed.
- A dropped feed table can be restored by re-adding it to `PUBLISHED_TABLES`
  and publishing, since the local copies stay.

## Testing

- Commands: `python -m unittest discover -s postgres_etl/tests`,
  `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`,
  `cd api_requests && python -m unittest tests.test_scrapper` (help text only; must stay green).
- Logic that needs tests: the retired-table drop planning and execution (fake
  cursor), CLI refusals, `RENAMED_TABLES` vs `PUBLISHED_TABLES` names and
  `drop_old_names` covering all 23 views.
- Remove tests that only exercised the removed tables; keep play-by-play and
  shots person-matching tests.
- No combined Verify command exists (build-plan item 17). Neon evidence comes
  only from the owner-approved runs in step 4.

## Notes for the AI

- `physical_name()` and `legacy_name()` currently derive from
  `PUBLISHED_TABLES`. Shrinking that list without the explicit `RENAMED_TABLES`
  would silently turn the feeds' local names into `etl_flat_standings_*` and hide
  their old Neon views from `--drop-old-names`. Step 2 exists to prevent that.
- Drop order in Neon matters: old views first (`--drop-old-names`), then the
  feed tables, because `etl_flat_standings_*` views depend on them.
- Keep comments and wording in the style of the surrounding code; no new
  dependencies.
- Never touch Neon, and never run a real drop, without the owner's yes in the
  current chat.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":9819,"specSha256":"fa19dd78b5b46dea64ed546981fc421ef0a93eb30d0b5c346797cd3ef57cb89d","branch":"refs/heads/feature/clean-up-unused-tables","head":"4c33eafb7bb98a5eee9d18de776515a128e37567","baseRef":"refs/heads/main","baseCommit":"e656afdce6218ab160f50be992f17aab260f08bb","sourceTree":"62800872882c2e929ef4612dabbdc4c9bf27c9da","absentOptional":[]} -->

## Independent review

# Independent Review

**Status:** passed
**Target commit:** 4c33eafb7bb98a5eee9d18de776515a128e37567
**Base commit:** e656afdce6218ab160f50be992f17aab260f08bb
**Base ref:** refs/heads/main
**Spec hash:** fa19dd78b5b46dea64ed546981fc421ef0a93eb30d0b5c346797cd3ef57cb89d
**Prepared by:** claude
**Builder model:** claude-opus-5-5
**Requested reviewer:** claude
**Requested model:** claude-opus-5-5
**Requested execution:** automatic
**Requested at:** 2026-09-26T22:41:20Z
**Workflow:** regular
**Check required:** no
**Reviewer adapter:** claude
**Reviewer model:** claude-opus-5-5
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-09-26T22:47:00Z
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Commands

- `git rev-parse HEAD`, `git merge-base refs/heads/main HEAD`, `sha256sum blueprint/context/current-feature.md`, `git status --porcelain --untracked-files=all`: pass (HEAD = target, merge base = base, spec hash matches, only `blueprint/context/review.md` modified)
- `git diff e656afd..4c33eaf` (all 23 files, code and docs): reviewed
- `cd api_requests && python -m unittest tests.test_scrapper`: pass (16 tests)
- `python -m unittest discover -s postgres_etl/tests`: pass (103 tests)
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass (54 tests)
- `python postgres_etl/main.py --list-tables`: pass (33 tables; none of the 9 live tables or `source_payloads`)
- `python neon_publish/main.py --list-tables`: pass (25 tables, no standings feeds)
- `python postgres_etl/main.py -sc 2025 --dry-run` (no database): pass (exit 0)

## Evidence

- `RENAMED_TABLES` is built from `PUBLISHED_TABLES + STANDINGS_FEED_TABLES` (23 names, tested), so `physical_name`/`legacy_name` keep `app_standings_*` locally and `drop_old_names`/`rename_local_tables` still cover the 7 feed views and tables.
- `RETIRED_LOCAL_TABLES` (10) and `RETIRED_NEON_TABLES` (7) are explicit physical-name lists, not derived from `TABLES`; a test asserts they are disjoint from loaded/published names and that the Neon feeds are still loaded locally.
- `drop_retired_tables`: one `with connection` transaction, `relation_kinds` scoped to `current_schema()`, `DROP TABLE` via `sql.Identifier` with no `CASCADE`, views/other kinds left alone, dry run issues no DDL; Neon wrapper catches `DependentObjectsStillExist` and tells the user to run `--drop-old-names` first. No Neon URL is printed.
- CLI refusals: loader refuses `-tb`, `-sc`, `--quality-only`, `--skip-quality-check`; publisher refuses `-tb`, `-sc`, `--drop-old-names`; both tested.
- No remaining code reference to the removed tables outside `old/` and the fetcher's optional bronze datasets (grep of tracked `.py`/`.md`/`.json`); `hashlib`, `json`, `read_bytes` still used in `raw_transform.py`; quality person checks now cover only play-by-play and shots.
- Owner-run Neon logs (`logs/neon_publish/logfile_20260927_0022*`/`0023*`) match the docs: 21 old views dropped, 7 feed tables dropped, reruns report nothing left, pipeline dry run publishes 25 tables.
- Docs (data dictionary, READMEs, AGENTS Commands, fetcher help) no longer describe removed tables as current.

## Findings

- F-02 [P3] open - `--drop-retired` does not report individual missing names (spec says "already gone")
- F-03 [P3] open - loader `--dry-run`/`--config` help says no database connection, but `--drop-retired --dry-run` connects
- No P0 or P1 findings.

## Remaining risk

- Check not required and not run; the local and Neon drops were not re-executed by the reviewer (no database was touched). Their outcome is taken from the owner-run Neon logs; no log exists for the local `--drop-retired` run, so the local database state is unverified here.
- The Neon `DependentObjectsStillExist` refusal path and both `run_drop_retired` wrappers are not unit-tested (the fake database does not simulate dependencies or rollback).
- No combined Verify command, lint, or typecheck exists (build-plan item 17).

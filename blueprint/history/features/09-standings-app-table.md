# Feature: Standings app table

**From build-plan:** feature 9
**Build attempt:** 1
**Status:** verified
**Branch:** feature/standings-app-table

## Goal

Build one page-shaped standings table, `app_standings`, that holds
everything the web app's standings endpoint returns for a season, phase and
round in one row per club. Publish it to Neon next to the current tables, so
the app can later replace its 7-table join (plus 2 list queries) with a single
read. The app-side switch happens in the web-app repo, from the contract below.

## In scope

- A new derived table `app_standings` with clean names (table and columns),
  built by the loader from the
  bronze standings feeds and the season's clubs, one row per
  (competition, season, phase, round, club) of basicstandings.
- Per-feed columns that reproduce the app's `StandingEntry` exactly: `basic`,
  `calendar`, `streaks`, `aheadBehind`, `margins` objects, club identity, crest,
  group, and the `form` and `streakHistory` lists (JSONB).
- Loader support for JSONB columns other than `payload`.
- A quality check (ERROR) that the table has exactly one row per basicstandings row.
- Publishing the table with the existing web-app tables (`APP_TABLES`).
- A contract note for the web-app repo describing how to read the table.

## Out of scope

- Any change in the web-app repo (`D:/jmp-project/jmp-euroleague2`). That is a
  separate `/feature` there, using the contract below.
- Removing the 7 old standings tables from publishing or dropping them in Neon.
  Both happen only after the app has switched (migration path: keep
  `etl_flat_*` working until nothing reads it).
- Renaming the other `etl_flat_*` tables, a separate Neon `app` schema and a
  read-only role (feature 16), and publishing older seasons to Neon (feature 15).
  `app_standings` lives in Neon `public` next to the current tables.
- Any real publish to Neon without the owner's explicit yes in the chat.

## Build loop

- `workflow.stepReview` is `feature`: build all steps, then one review packet
  for the whole feature, followed by the optional code walkthrough.
- `workflow.checkpointCommits` is `disabled`: no step commits. `/complete`
  creates the feature commit (no AI attribution).
- Tests are a gate: all three test commands in `AGENTS.md` must be green before
  review and before `/complete`.

## Build steps

- [x] 1. **JSONB columns in the loader.** In `postgres_etl/flat_loader.py`, wrap
  values with `psycopg2.extras.Json` for every field whose kind starts with
  `JSONB`, not only the column named `payload`. Add a test using the existing
  fake-psycopg2 pattern in `test_raw_etl.py`.
  Done when: the new test passes and `etl_source_payloads` still loads in the
  existing dry-run test.

- [x] 2. **Transform and schema.** Add source `standings_page` in
  `postgres_etl/raw_transform.py`: group the season's `v3/standings/*` files by
  (phase, round), take each basicstandings team as the row driver, merge the
  other four feeds by club code, attach `form` from basicstandings
  `last5Form` and `streak_history` from calendarstandings `streaks`, and
  `crest_url` from the season's `v2/clubs` (`images.crest`). Add the table to
  `postgres_etl/flat_schema.py` as logical and physical name `app_standings`
  (extend `physical_name` so `app_*` tables are not prefixed with `etl_flat_`),
  generating the per-feed columns from the existing standings field
  definitions with a feed prefix and a clean-name map (see Data / contracts). Unit tests cover: merge of all feeds, a missing feed giving all
  NULL columns for that feed, list order and JSON shape, the ISO date format,
  crest lookup, a club present only in a non-basic feed producing no row, and
  `NaN%` staying NULL.
  Done when: tests pass and `python postgres_etl/main.py -sc all -tb app_standings --dry-run` succeeds for all 27 seasons.

- [x] 3. **Quality check and local load.** In `postgres_etl/quality.py`, add an
  ERROR check that `app_standings` and
  `etl_flat_standings_basicstandings` have the same (phase, round, club) keys
  for the season (count of keys present in one but not the other). Add a test.
  Load all seasons: `python postgres_etl/main.py -sc all -tb standings_basicstandings standings_calendarstandings standings_streaks standings_aheadbehind standings_margins standings_calendar_streaks standings_basic_form clubs app_standings`.
  Done when: tests pass and the quality report shows 0 errors for all seasons.

- [x] 4. **Equivalence with the app's current query.** With read-only SQL on
  local PostgreSQL, rebuild the app's current result (basicstandings left
  joined to clubs and the other 4 feeds on phase, round and club, plus the
  ordered streak and form lists) and compare it field by field with
  `app_standings` for every season, phase and round.
  Done when: 0 differences across all seasons, with the row counts reported.

- [x] 5. **Publish wiring and docs.** Add `app_standings` to `APP_TABLES` in
  `neon_publish/publish.py` (keep the 7 old tables) and update its test
  (21 -> 22 tables). Update `docs/DATA_DICTIONARY.md`, `neon_publish/README.md`
  and the table counts in `README.md`; add the contract note for the app repo
  (see Notes). Run `python neon_publish/main.py -sc 2025 2026 --dry-run` only if
  the owner provides `NEON_DATABASE_URL` for it; a real publish needs the
  owner's explicit yes.
  Done when: tests pass, docs describe the table, and (if run) the dry run
  lists `app_standings: missing would become N rows`.

## Files / areas

- `postgres_etl/flat_loader.py` - JSONB wrapping (step 1)
- `postgres_etl/raw_transform.py` - `standings_page` source rows (step 2)
- `postgres_etl/flat_schema.py` - table definition and `physical_name` (step 2)
- `postgres_etl/quality.py` - key parity check (step 3)
- `postgres_etl/tests/test_raw_etl.py`, `test_quality.py` - tests
- `neon_publish/publish.py`, `neon_publish/tests/test_publish.py` - `APP_TABLES`
- `docs/DATA_DICTIONARY.md`, `neon_publish/README.md`, `README.md` - docs
- Read-only reference: `D:/jmp-project/jmp-euroleague2/backend/src/db/season-standings.ts`
  (`getStandings`, `getLatestStandingsRound`) and `routes/seasons.ts` (standings route)

## Data / contracts

Table `app_standings` (local PostgreSQL and Neon `public`):

- Primary key: `competition_code`, `season_code`, `phase_code` (text),
  `round_number` (integer), `club_code` (text).
- Club and group: `club_name`, `club_tv_code` (from basicstandings `club`),
  `crest_url` (v2 clubs `images.crest`, NULL when the club is missing there),
  `group_name`.
- Per-feed columns, prefixed `basic_`, `calendar_`, `streaks_`,
  `ahead_behind_`, `margins_` (the app's `basic`, `calendar`, `streaks`,
  `aheadBehind`, `margins` objects). Each feed has the 6 shared fields
  (`position`, `position_change`, `games_played`, `games_won`, `games_lost`,
  `qualified`) plus its own metrics, with the same types as the existing
  `etl_flat_standings_<feed>` columns.
- Clean column names: each column is the snake_case of the app's
  `StandingEntry` field, not the source spelling. Where they differ:

  | Source-style column | `app_standings` column |
  | --- | --- |
  | `streaks_longest_wins_streak_current_season` | `streaks_longest_win_streak_current_season` |
  | `streaks_longest_loses_streak_current_season` | `streaks_longest_lose_streak_current_season` |
  | `streaks_longest_wins_streak_any_season` | `streaks_longest_win_streak_any_season` |
  | `streaks_longest_loses_streak_any_season` | `streaks_longest_lose_streak_any_season` |
  | `ahead_behind_quater1_ahead` / `_behind` / `_tied` | `ahead_behind_quarter1_ahead` / `_behind` / `_tied` |
  | `ahead_behind_quater3_ahead` / `_behind` / `_tied` | `ahead_behind_quarter3_ahead` / `_behind` / `_tied` |
  | `margins_point_difference1to5` | `margins_point_difference_1_to_5` |
  | `margins_point_difference6to10` | `margins_point_difference_6_to_10` |
  | `margins_point_difference11to15` | `margins_point_difference_11_to_15` |
  | `margins_point_difference_more_than15` | `margins_point_difference_more_than_15` |

  All other columns keep their existing names with the feed prefix (for example
  `basic_win_percentage`, `streaks_last10`, `ahead_behind_half1_ahead`).
- All columns of a feed are NULL when that feed has no row for the club, which
  the app maps to a `null` feed object, as its left join does today.
- `form` JSONB: `[{"resultOrdinal": 0, "result": "W"}, ...]` in source order,
  `[]` when empty.
- `streak_history` JSONB: `[{"streakOrdinal": 0, "startAt":
  "2025-09-01T00:00:00.000Z", "endAt": "2025-09-30T00:00:00.000Z",
  "winLossRecord": "1-0"}, ...]` in source order, `[]` when empty. Dates are
  the source value treated as UTC, formatted like JavaScript `toISOString()`,
  or `null` when missing, matching today's API output.
- Rows exist only for clubs in basicstandings for that phase and round (the
  app's row driver). Standings exist for group-phase rounds only.
- Latest round for a season and phase is `max(round_number)`, as today. No
  rows means the API keeps returning `{ round: null, standings: [] }`.
- Row order is not stored; the app orders by `group_name`, `basic_position`,
  `club_code`.
- NUMERIC stays NUMERIC so node-postgres keeps returning strings (for example
  `winPercentage: "45.5"`).

## Testing

- Test command gate: the three commands in `AGENTS.md`.
- Unit tests (steps 1-3, 5): loader JSONB wrapping, standings merge and lists,
  date format, crest, missing feeds, key parity check selection, `APP_TABLES`.
- Data evidence (steps 2-4): all-season dry run, local load with 0 quality
  errors, and the field-by-field equivalence query. No test claims live Neon
  behaviour; a Neon dry run happens only if the owner runs it.

## Notes for the AI

- Build the per-feed fields from `STANDINGS_IDENTITY` and `STANDINGS_METRICS`
  in `flat_schema.py` rather than retyping about 70 columns.
- The standings filename pattern is `<phase>_<round>_<feed>`; reuse the
  existing parsing in `raw_transform.py`.
- Clean names apply to `app_standings` only; the source tables keep their
  source spellings until feature 16.
- The rule is mechanical: column = feed prefix + snake_case of the app's field
  name (`aheadBehind.quarter1Ahead` -> `ahead_behind_quarter1_ahead`). Keep the
  rename map small and explicit next to the table definition.
- Contract note for the app repo (step 5): add a short section to
  `docs/DATA_DICTIONARY.md` stating that rule, the lists (`streakHistory` ->
  `streak_history`, `form` -> `form`), the crest and club fields, and the
  all-NULL-feed rule.
- Never publish to Neon or call the EuroLeague API in this feature.

## Open questions

- Per-feed shared fields: the default keeps `position`, `games_played` and the
  other shared fields once per feed, because the app returns them per feed
  today. If the app will show one set only, they could be stored once. Not
  blocking: the default preserves current behaviour.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":11125,"specSha256":"828c529e34776d8d3ac14b3236c05df44dbf80aacf2b8496571254848c2efc56","branch":"refs/heads/feature/standings-app-table","head":"081178a7239d3b5e20ca215458a2583b5b671bc0","baseRef":"refs/heads/main","baseCommit":"58b18b25f365e17a200d16bce936e7b09cfb668f","sourceTree":"fd86d560c85fc87ab23e6c2e739811de22ec1cb4","absentOptional":[]} -->

## Independent review

# Independent Review

**Status:** passed
**Target commit:** 081178a7239d3b5e20ca215458a2583b5b671bc0
**Base commit:** 58b18b25f365e17a200d16bce936e7b09cfb668f
**Base ref:** main
**Spec hash:** 828c529e34776d8d3ac14b3236c05df44dbf80aacf2b8496571254848c2efc56
**Prepared by:** claude
**Builder model:** claude-opus-5-5
**Requested reviewer:** claude
**Requested model:** claude-opus-5-5
**Requested execution:** automatic
**Requested at:** 2026-09-24T16:32:40+00:00
**Workflow:** regular
**Check required:** no
**Reviewer adapter:** claude
**Reviewer model:** claude-opus-5-5
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-09-24T16:35:58+00:00
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Commands

- `git rev-parse HEAD`, `git merge-base main HEAD`, `sha256sum blueprint/context/current-feature.md`, `git status --porcelain --untracked-files=all`: pass (target, base and spec hash match; only `blueprint/context/review.md` differed)
- `cd api_requests && python -m unittest tests.test_scrapper`: pass (16 tests)
- `python -m unittest discover -s postgres_etl/tests`: pass (36 tests)
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass (12 tests)
- Read-only SQL on local PostgreSQL (session `readonly`, scratchpad script outside the repo): pass

## Evidence

- Reviewed the full `58b18b2..081178a` delta (14 files): `flat_loader.py` JSONB wrapping, `raw_transform.py` `standings_page` source and `js_iso`, `flat_schema.py` `app_standings` definition and `physical_name`, `quality.py` key-parity check, `publish.py` `APP_TABLES`, tests and docs, plus callers (`flat_transform.py`, `publish.py` COPY path, `tables_to_csv/utils.py`, `pipeline.py`).
- Local data: `app_standings` 12,325 rows over 26 seasons = `etl_flat_standings_basicstandings` 12,325 rows; FULL JOIN key mismatches 0.
- Field-by-field: 0 rows differ across 72 scalar columns (all 5 feeds with the clean-name map, club name/tv code/group, crest vs `etl_flat_clubs`), and 0 `streak_history` / 0 `form` differences against the child tables formatted like `toISOString()`.
- Rename map and column set checked against the app's `StandingEntry` types in `season-standings.ts` (read-only); Drizzle maps zone-less TIMESTAMP as UTC, matching `js_iso`.
- Neon publish copies via `COPY ... FORMAT CSV`, which round-trips JSONB as text; `pipeline.py` loads all tables, so `app_standings` and its parity check run with every refresh.
- Security: identifiers come only from schema-registered names, values are parameterized, no new input or secret handling. Performance: per-season in-memory grouping and a full join over about 12k rows; no concern.
- No em dashes, en dashes or ellipsis characters in added lines.

## Findings

- F-01 [P3] open: `js_iso` re-parses streak dates separately from the TIMESTAMP cast (latent divergence, context-less errors, untested branches)
- F-02 [P3] open: `js_iso` wedged into the module constants block (PEP 8 E305)

## Remaining risk

- `python postgres_etl/main.py -sc all -tb app_standings --dry-run` was not rerun by the reviewer (it writes run logs); the local data checked was loaded before this review and was not reloaded from bronze at the target commit.
- `python neon_publish/main.py --dry-run` unavailable: Neon was out of scope for this review; no Neon behaviour was verified.
- The web-app switch to `app_standings` is not built or tested; the contract was checked only against the app's current query source.

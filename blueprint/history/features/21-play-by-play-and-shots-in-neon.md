# Feature: Play-by-play and shots in Neon

**From build-plan:** feature 21
**Build attempt:** 1
**Status:** verified
**Branch:** feature/play-by-play-and-shots-in-neon

## Goal

The web app can show game play-by-play and shot charts: play-by-play and shots
are published to Neon as `app_play_by_play` and `app_shots` for E2025 and
E2026. Because these tables are large (E2025 alone is about 223,000
play-by-play and 64,000 shot rows, about 130 MB with indexes), a refresh
replaces only the games that are new or changed instead of the whole season,
so Neon stays close to the real data size and a refresh after a round uploads
a few games, not the season.

Owner decisions (2026-09-25): publish only changed games (per-game checksum);
E2025 and E2026 only; clean `app_*` table names (feature 22 rule).

## In scope

- `play_by_play` and `shots` join the published tables (24 in total). Their
  physical name becomes `app_play_by_play` / `app_shots` locally and in Neon;
  the local tables are renamed in place on the next load or publish, as
  feature 22 does. Columns are unchanged. In Neon they are created fresh (no
  old-name views, since Neon never had them).
- Per-game publish for these two tables inside the existing season transaction:
  compare a checksum per game between local and Neon, then delete and copy only
  games that are new or differ, and delete games Neon has but local does not.
  The other 22 tables keep the whole-season replace.
- The shrink guard and the after-copy count check keep working on season
  totals for all 24 tables.
- Dry run (`--dry-run`, `pipeline.py --dry-run-publish`) reports how many games
  would be replaced per table and changes nothing.
- `pipeline.py` publishes the two tables for the current season as part of the
  normal refresh; E2025 is published once by the owner with
  `python neon_publish/main.py -sc 2025` (or `-tb play_by_play shots`).
- Docs: web-app contract for the two tables and the first-run steps.

## Out of scope

- Seasons before E2025 in Neon (feature 15 decides how historical seasons and
  these large tables fit the Neon plan). Nothing here blocks `-sc` for older
  seasons; the docs say not to.
- Column renames, new derived columns, possessions or shot features
  (feature 19, local only).
- Changing any web-app code (the app repo reads the new tables).
- Per-game publish for the other 22 tables.
- The season-stats API problem (finding F-01, deferred by the owner).
- Running anything against Neon; the owner does the real publish.

## Build loop

`workflow.stepReview` is `feature` and `workflow.checkpointCommits` is
`disabled`: build all steps with each step's focused check, then one review
packet. This changes how shared persisted data is deleted and written in Neon,
so the `when-sensitive` gate selects an independent review before `/complete`.
`/complete` makes the single feature commit.

## Build steps

- [x] 1. **Publish the two tables under clean names.** Add `play_by_play` and
  `shots` to `PUBLISHED_TABLES` in `postgres_etl/flat_schema.py` (so
  `physical_name` gives `app_*`, `legacy_name` gives `etl_flat_*`, and
  `rename_local_tables` moves them). Update tests that count or list published
  tables (`neon_publish/tests/test_publish.py`,
  `postgres_etl/tests/test_flat_etl.py`) and any quality test fake that names
  them. Done when: the three test commands in `AGENTS.md` pass, and a real local
  `python postgres_etl/main.py -sc 2026` renames exactly these two tables,
  their per-season row counts for all seasons are unchanged, quality has 0
  errors, and a second run renames nothing.

- [x] 2. **Per-game publish for play-by-play and shots.** In
  `neon_publish/publish.py`, a tuple `GAME_DIFF_TABLES = ("play_by_play",
  "shots")`. For those tables:
  - A checksum query per game: `game_code`, `count(*)` and
    `md5(string_agg(ROW(<columns in TABLES order>)::text, E'\n' ORDER BY <key>))`
    for the season, run with `SET LOCAL TimeZone = 'UTC'` and
    `SET LOCAL DateStyle = 'ISO'` so both databases print values the same way.
  - Neon checksums are read with the before-counts (a missing table means every
    game is new). Local checksums are read in the same `REPEATABLE READ`
    snapshot as the export, and only the rows of new or changed games are
    exported (`WHERE game_code = ANY(...)`).
  - In the season transaction: `DELETE` the rows of changed games and of games
    Neon has but local does not, then `COPY` the exported rows. The existing
    check that Neon's season count equals the local count stays.
  - Log per table `  app_play_by_play: 12 of 408 game(s) replaced` (dry run:
    `would be replaced`), on a line the refresh summary's row regex does not
    match; the `table: before -> after rows` lines are unchanged.
  Tests with the fake database in `neon_publish/tests/test_publish.py`: first
  publish copies every game; unchanged games copy nothing; one changed game
  deletes and copies only that game; a game missing locally is deleted in Neon;
  dry run executes no DELETE/COPY and logs the counts; the other 22 tables still
  use the whole-season replace. Done when: the three test commands pass. No
  Neon connection is made.

- [x] 3. **Check it against a real PostgreSQL.** Create a scratch database on
  the local PostgreSQL server (for example `euroleague_publish_scratch`) and
  run `neon_publish/main.py` against it through `NEON_DATABASE_URL` set only in
  that command's environment (built from `postgres_etl/config_connection.json`,
  never written to a file or printed). Done when all of these are observed and
  the scratch database is dropped afterwards:
  - `-sc 2025 -tb play_by_play shots`: all 402 games replaced per table, counts
    equal local;
  - the same command again: 0 games replaced;
  - after deleting one game's rows and changing one value of another game in
    the scratch copy: exactly those 2 games replaced, and the checksums of all
    games then equal local;
  - a `--dry-run` reports the counts and leaves the scratch database unchanged.
  No code change unless this finds a defect (then fix it in step 2's code and
  tests).

- [x] 4. **Docs.** `docs/DATA_DICTIONARY.md`: the two new names in the Table
  names list, and a web-app contract for `app_play_by_play` and `app_shots`
  (keys, ordering within a game, `points_a`/`points_b` are the source's A/B
  sides so join to the game, `person_code` for players, shot coordinates are the
  source's system, seasons available: E2025 and E2026). `neon_publish/README.md`:
  per-game publish, the first run for E2025, and that older seasons must not be
  published for these tables. Update `README.md`, `postgres_etl/README.md`,
  `tables_to_csv/README.md` names and the `AGENTS.md` Commands where they list
  published tables. Done when: the docs name the tables consistently (grep for
  `etl_flat_play_by_play`/`etl_flat_shots` finds only the old-name list and
  history) and the three test commands pass.

- [x] 5. **Repair F-02: correct play-by-play order in the contract.** In
  `docs/DATA_DICTIONARY.md` (the web-app contract and the `play_by_play` row of
  the live table), say that a game is ordered by the period in play order
  (`FirstQuarter`, `SecondQuarter`, `ThirdQuarter`, `ForthQuarter` (source
  spelling), `ExtraTime`) and then `event_ordinal`, which restarts at 0 in each
  period; `period` is text, so it must not be sorted directly; `play_number` is
  unique within a season and game but not chronological. Mark F-02 `fixed`. Done when:
  the order is checked against local E2025 and E2026 data (the game minute
  never goes backwards in that order) and the three test commands pass.

- [x] 6. **Repair F-03: incomplete Neon table still removes vanished games.**
  In `remote_counts`, when the Neon table exists but lacks a column, return
  Neon's games with their row counts and no checksum (a query that needs no new
  column), so every local game is replaced and every Neon-only game is removed.
  Tests: the missing-column path returns Neon's games; a publish against a Neon
  table with a missing column and one extra game deletes that game, adds the
  column and passes the count check. Mark F-03 `fixed`. Done when: the three
  test commands pass.

- [x] 7. **Repair F-04: correct the `play_number` sentence.** The step 5
  wording said `play_number` is not unique within a game; that count grouped by
  `game_code` across two seasons, whose game codes repeat. Per season and game
  it is unique (0 duplicates, 0 NULLs in E2025/E2026) and links each shot to its
  event, but ordering by it puts the minute backwards 1,152 times. Say so in
  `docs/DATA_DICTIONARY.md` and in step 5. Mark F-04 `fixed`. Done when: the
  sentence matches those counts and the three test commands pass.

## Files / areas

- `postgres_etl/flat_schema.py` (`PUBLISHED_TABLES`)
- `neon_publish/publish.py` (`GAME_DIFF_TABLES`, checksums, per-game export,
  delete and copy, logging), `neon_publish/main.py` only if output needs it
- Tests: `neon_publish/tests/test_publish.py`, `postgres_etl/tests/test_flat_etl.py`,
  `postgres_etl/tests/test_quality.py` if a fake names the tables
- Docs listed in step 4

## Data / contracts

- Names: `app_play_by_play` (key `competition_code, season_code, game_code,
  period, event_ordinal`) and `app_shots` (key `competition_code, season_code,
  game_code, shot_ordinal`); columns exactly as the local tables
  (`postgres_etl/flat_schema.py`).
- Per-game identity: a game's rows are equal in local and Neon when row count
  and checksum match. The checksum covers every column in `TABLES` order,
  ordered by the key, printed with UTC time zone and ISO dates.
- Atomicity: the per-game deletes and copies are inside the season's single
  Neon transaction with the other tables; any error rolls the whole season back.
- Idempotency: a second publish with no local change replaces 0 games.
- Shrink guard: unchanged, on season totals; a local load that lost games still
  refuses the publish unless `--allow-shrink`.
- Size: about 130 MB with indexes for E2025 now; E2026 grows to about the same
  by season end. The 22 other tables hold about 9.5 MB of row data.

## Testing

- `cd api_requests && python -m unittest tests.test_scrapper`
- `python -m unittest discover -s postgres_etl/tests`
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`
- Step 1's local load with before/after counts; step 3's scratch-database runs.
- Not run here: Neon. After `/complete` the owner checks Neon's free storage,
  runs `python neon_publish/main.py -sc 2025 -tb play_by_play shots --dry-run`,
  then without `--dry-run`, and the normal refresh adds E2026.

## Notes for the AI

- Reuse the season transaction, `export_season` snapshot, `_count`,
  `remote_counts`, the shrink guard and the fake database from feature 22; add
  only what per-game replace needs. No new dependency or configuration.
- Build every identifier with `psycopg2.sql.Identifier` and pass game codes as
  parameters, never formatted into SQL text.
- Check the column kinds of both tables before relying on text output: if any
  column is a floating-point type, set `extra_float_digits` for the checksum
  too.
- The scratch database in step 3 is the only extra local write; drop it at the
  end. Never touch Neon or the EuroLeague API.
- Finding F-01 (season stats) is open and unrelated; do not change it.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":11583,"specSha256":"f36b010c2249e72bd5e2aed8792e87912d1ac026833d785bd22bb4fd7ecc0b0a","branch":"refs/heads/feature/play-by-play-and-shots-in-neon","head":"3c4c9ee44a892e00f1ccd5d96305863bd2fcc4c6","baseRef":"refs/heads/main","baseCommit":"5451f7539154839ecaf99b7099e78eb99727b0ac","sourceTree":"2530672ecd9bb2f3505a0c87b5c31ef76c3c7185","absentOptional":[]} -->

## Findings

### 21/F-02 [P1] closed - Web-app contract orders play-by-play alphabetically by period

**File:** docs/DATA_DICTIONARY.md:175
**Found:** 2026-09-25 by /audit independent (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** The new web-app contract says "Order a game by `period`,
then `event_ordinal`". `period` is TEXT with the values `ExtraTime`,
`FirstQuarter`, `ForthQuarter`, `SecondQuarter`, `ThirdQuarter`, and
`event_ordinal` restarts at 0 in every period (checked read-only in local
PostgreSQL: 5,046 games have repeated ordinals; in E2025/E2026, 409 games order
differently by `period, event_ordinal` than chronologically). An app that
follows the contract shows extra time first and the 4th quarter before the
2nd. The spec made "ordering within a game" part of this contract, so the
delivered contract is wrong. The older live-table row at line 159 has the same
ambiguous wording.
**Suggested fix:** Document the real chronological order: `play_number`
(non-null and unique per game for every E2025/E2026 game, rising across
periods), or `period` mapped FirstQuarter, SecondQuarter, ThirdQuarter,
ForthQuarter, ExtraTime, then `event_ordinal`. Fix line 159 the same way. Docs
only; no code change.
**Resolution:** fixed in `feature/play-by-play-and-shots-in-neon` (step 5): the contract and the `play_by_play` live-table row now say to order a game by the period in play order (`FirstQuarter`, `SecondQuarter`, `ThirdQuarter`, `ForthQuarter`, `ExtraTime`) and then `event_ordinal`, never by the `period` text. The suggested `play_number` order was checked and rejected: local E2025/E2026 have 3,372 duplicate (game, play_number) pairs, and ordering by it puts the game minute backwards 3,835 times. In the documented order, per season and game, the minute never goes backwards (0 of 227,057 rows). Awaiting re-review. Re-review 2026-09-25 (independent, fresh subagent, target f858e1f): the original defect is gone. Read-only on local E2025/E2026 (227,057 rows): every `period` maps to the documented order, `event_ordinal` starts at 0 in every period with no gaps, and the minute never goes backwards in that order (0 steps). Left `fixed`, not closed, because the repair added a false statement: `play_number` IS unique within a season and game (0 duplicates in all 20 local seasons, 0 NULLs). The 3,372 duplicates above come from grouping by `game_code` across E2025 and E2026, whose game codes repeat. Tracked as F-04; close F-02 together with F-04.

Re-review 2026-09-25 (independent, fresh subagent, target `3c4c9ee`): closed.
The complete feature delta was reviewed again. Both the live-table row and
the web-app contract explicitly use period play order followed by
`event_ordinal`. Read-only queries on E2025/E2026 found 0 unknown periods
and 0 backward minute steps across 227,057 events in that order. The related
incorrect uniqueness sentence is now corrected and F-04 is closed below.
The earlier cross-season duplicate count is superseded by the correctly
scoped evidence below; no new defect was found in either documentation repair.

### 21/F-03 [P3] closed - Neon table missing a column cannot drop Neon-only games, so every publish fails

**File:** neon_publish/publish.py:211
**Found:** 2026-09-25 by /audit independent (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** When the Neon play-by-play or shots table exists but lacks
a column (a later schema addition), `remote_counts` returns no checksums, so
`changed_games` puts every local game in `replace` and nothing in `remove`.
The per-game DELETE then removes only games local still has; a game Neon has
and local no longer has survives, the after-copy count check raises, and the
whole season (all 24 tables) rolls back. The rollback also undoes the
`ADD COLUMN`, so every later publish repeats the failure until someone
intervenes by hand, and `--allow-shrink` does not help. It fails safe (no data
loss) and needs a schema change plus a vanished game, hence P3. No test covers
the publish outcome of this path (the existing test checks only the empty
checksums).
**Suggested fix:** When the Neon table exists but is incomplete, delete the
whole season for that table (the normal whole-season path) instead of per
game, or list Neon's game codes there (`SELECT DISTINCT game_code`) so they
land in `remove`. Add a fake-database test for Neon with an extra game and a
missing column.
**Resolution:** fixed in `feature/play-by-play-and-shots-in-neon` (step 6): when the Neon table exists but lacks a column, `remote_counts` now returns Neon's games with row counts and no checksum (`game_rows`, which needs no new column), so every local game is replaced and every Neon-only game is removed; `_ensure_table` adds the column in the same transaction. Tests: `test_missing_table_or_column_in_neon_means_every_game_is_new` and `test_missing_column_still_removes_games_only_neon_has`; `game_rows` also ran read-only on local E2025 (402 games, counts equal the checksum query). Awaiting re-review. Re-review 2026-09-25 (independent, fresh subagent, target f858e1f): closed. `remote_counts` (neon_publish/publish.py:222-229) now returns `(rows, None)` per Neon game when a column is missing; `changed_games` puts every local game in `replace` (no local value has a None digest) and every Neon-only game in `remove`; the publish transaction adds the column (`_ensure_table`), deletes `replace + remove` and copies the local rows, so the season count check passes. `game_rows` needs only `game_code`, a key column. `test_missing_column_still_removes_games_only_neon_has` covers the publish outcome. No new defect found in the repair.

### 21/F-04 [P3] closed - Web-app contract says play_number is not unique within a game

**File:** docs/DATA_DICTIONARY.md:180
**Found:** 2026-09-25 by /audit independent (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** The contract (added by the F-02 repair, step 5) says "`play_number` is
neither unique within a game nor chronological". The first half is false: read-only
on local PostgreSQL, (competition, season, game_code, play_number) has 0 duplicates
and 0 NULLs in all 20 seasons, E2025/E2026 included. The builder's 3,372 duplicates
come from grouping by `game_code` across two seasons, whose game codes repeat. The
same contract says "Every shot has a play-by-play event with the same `play_number`"
(true: 0 of 65,275 E2025/E2026 shots without one), so the two statements contradict
each other and an app developer may avoid the correct shot-to-event join. The
"not chronological" half is true (1,152 backward minute steps when ordered by
`play_number` within a season and game). The spec's step 5 and F-02's Resolution
repeat the wrong claim.
**Suggested fix:** Docs only: say `play_number` is unique within a game (it links a
shot to its play-by-play event) but is not in play order, so order by period and
`event_ordinal`. Correct the wording in the spec's step 5. No code change.
**Resolution:** fixed in `feature/play-by-play-and-shots-in-neon` (step 7): `docs/DATA_DICTIONARY.md` now says `play_number` is unique within a season and game (it links each shot to its event) but is not chronological, so do not order by it; spec step 5 says the same. Rechecked per season and game on local E2025/E2026: 0 duplicate and 0 NULL `play_number`, and ordering by it puts the minute backwards 1,152 times. The earlier 3,372 duplicates in F-02's Resolution came from grouping by `game_code` across both seasons (game codes repeat each season); that figure is wrong, the rejection of `play_number` ordering still holds. Awaiting re-review.

Re-review 2026-09-25 (independent, fresh subagent, target `3c4c9ee`): closed.
The corrected sentence and spec step 5 agree with fresh read-only local
queries: E2025 has 222,976 events, E2026 has 4,081, and each season has
0 NULL and 0 duplicate `(game_code, play_number)` values. All 65,275 shots
join to an event using competition, season, game and play number. Ordering
by play number produces 1,135 backward minute steps in E2025 and 17 in
E2026, confirming that it is a join key but not chronological. No new defect
was found in the repair; all three test suites pass (106 tests).

## Independent review

# Independent Review

**Status:** passed
**Target commit:** 3c4c9ee44a892e00f1ccd5d96305863bd2fcc4c6
**Base commit:** 5451f7539154839ecaf99b7099e78eb99727b0ac
**Base ref:** main
**Spec hash:** f36b010c2249e72bd5e2aed8792e87912d1ac026833d785bd22bb4fd7ecc0b0a
**Prepared by:** codex
**Builder model:** claude-opus-5-5
**Requested reviewer:** codex
**Requested model:** gpt-6-astra
**Requested execution:** automatic
**Requested at:** 2026-09-24T23:31:44Z
**Workflow:** regular
**Check required:** no
**Reviewer adapter:** codex
**Reviewer model:** gpt-6-astra
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-09-24T23:34:32Z
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Handoff

Review the active spec and the complete `5451f7539154839ecaf99b7099e78eb99727b0ac..3c4c9ee44a892e00f1ccd5d96305863bd2fcc4c6` delta in a fresh
session or isolated subagent without the builder conversation. Run all Audit lenses from scratch.
Run Check when required above. Do not edit product code, accept findings, or
reuse the existing findings as the review scope.

## Commands

- `git status --short`, `git rev-parse HEAD`, `git merge-base main HEAD`, and `Get-FileHash blueprint/context/current-feature.md -Algorithm SHA256`: pass; target, base, tracked spec hash and allowed evidence-only working changes match the request.
- `git diff --check main...HEAD`: pass.
- `cd api_requests; python -m unittest tests.test_scrapper`: pass, 16 tests.
- `python -m unittest discover -s postgres_etl/tests`: pass, 43 tests.
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass, 47 tests.
- Read-only local PostgreSQL queries through `common.db.connect`, with `readonly=True` and rollback: pass; checked E2025/E2026 chronology, play-number uniqueness, shot-to-event joins, and executed `game_checksums` and `game_rows` for both tables and seasons.

## Evidence

- Reviewed the complete 11-file delta from `5451f7539154839ecaf99b7099e78eb99727b0ac` to `3c4c9ee44a892e00f1ccd5d96305863bd2fcc4c6`: the active spec, `AGENTS.md`, root and stage READMEs, `docs/DATA_DICTIONARY.md`, `neon_publish/publish.py`, its tests, `postgres_etl/flat_schema.py`, and its changed tests. Followed nearby CLI, rename, transformation, connection and refresh-summary code. Review/findings files were evidence only; generated data, logs, caches, retired code and unrelated source were excluded.
- Checked repository standards for scoped season writes, transaction atomicity, shrink protection, safe SQL identifiers and values, credential handling, schema additions, bounded CSV spooling, and existing unittest conventions. No new dependency or configuration was added; no floating-point column requires checksum formatting settings.
- Checksum planning covers every declared column in key order, uses UTC and ISO rendering, and shares the repeatable-read local export snapshot. Changed/new games and vanished remote games are handled separately; the season transaction keeps schema changes, deletes, copies and count verification together. Existing 22-table whole-season behavior remains covered.
- Local data confirms 227,057 events with 0 NULL or duplicate play numbers within season/game, 0 backward minute steps in the documented order, and 1,152 backward steps in play-number order. All 65,275 shots have a matching event. Checksum and fallback row queries agree for 402 E2025 games and 7 E2026 games in each table.
- Missing-column fallback and vanished-game removal were re-examined fresh and remain correct; F-03 stays closed. Existing tests cover the complete fallback publish result. No skipped, focused or placeholder tests were found in the changed test scope.

## Findings

- No new findings across quality, security, performance or tests.
- F-02 [P1] closed after reviewing the corrected chronology contract against local data.
- F-04 [P3] closed after verifying uniqueness and shot joins with correctly scoped queries.
- F-03 [P3] remains closed; the complete repair was re-examined.
- F-01 [P2] remains open and unchanged, outside this feature's scope. No P0/P1 finding is open or fixed.

## Remaining risk

- Neon and the EuroLeague API were not contacted. This pass used unit tests and read-only local PostgreSQL evidence; it did not repeat a scratch-database publish or test Neon storage capacity. The owner still performs the first Neon dry run and publish as the spec requires.
- No build, lint, typecheck, security scanner or performance benchmark is configured. Runtime behavior on Neon is therefore not independently measured here; Check was not required by the request.
- The unrelated season-stats source issue remains recorded as F-01.

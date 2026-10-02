# Feature: Publish on-court, stints and stat gaps

**From build-plan:** feature 30j
**Build attempt:** 1
**Branch:** feature/publish-on-court-stints-and-stat-gaps
**Status:** verified

## Goal

Copy the last three per-game Silver tables into local Gold unchanged and publish them to
Neon for E2025 and E2026 as `app_game_player_on_court`, `app_game_team_lineup_stints` and
`app_game_stat_gaps`, so a game page can show who was on court when, five-man stints with
possessions and points, and which measures a game lacks. No new formulas. Same structure
as 30i.

## In scope

- Three Gold tables named like their Silver sources, with exactly the Silver columns minus
  `load_id`/`loaded_at`, same keys, types and nullability, copied per competition and
  season by the existing `replace_scope`/`check_scope` (delete then `INSERT ... SELECT`,
  row-count and one-way `EXCEPT` equality with Silver).
- Publisher registration (47 targets) and the reviewed migration
  `30j_game_on_court_and_gaps.sql`, selectable with `--print-migration 30j`.
- Tests, `DATA_DICTIONARY.md`, README and `AGENTS.md` updates, and a Neon dry-run.

## Out of scope

- Applying any migration to Neon and any live publish (separate owner approval).
- New columns or derivations, other seasons in Neon, indexes beyond the primary keys,
  splitting the comma-separated `players`/`opponent_players` text into rows, and web-app work.
- Changing how Silver builds these tables (`on_court.py`, `lineups.py`, the box-score loader).

## Build loop

`workflow.stepReview` is `feature`: implement all steps, then present one review
packet. `checkpointCommits` is disabled; `/complete` makes the single commit.

## Build steps

- [x] 1. **Gold schema and copy.** In `gold_etl/schema.py` add `GAME_COURT_NAMES =
  ("game_player_on_court", "game_team_lineup_stints", "game_stat_gaps")` and
  `GAME_COURT_TABLES = {name: ALL_TABLES[name] ...}` (`ALL_TABLES` from
  `postgres_etl.flat_schema`; `game_stat_gaps` is a loaded Silver table, the other two
  are derived), add them to `COPIED_TABLES` and `GOLD_TABLES`, and to `BUILD_NAMES` in
  `gold_etl/main.py`. `TABLES`/`SOURCE_NAMES` stay at 16; the loader and quality code
  already accept `COPIED_TABLES`.
  *Done when:* `python gold_etl/main.py -sc E2025 E2026 -tb game_player_on_court
  game_team_lineup_stints game_stat_gaps` loads with counts equal to Silver (29,325 and
  1,642 on-court rows; 29,522 and 1,550 stint rows; 0 stat-gap rows for both seasons), and
  the same command with `--quality-only` prints "Gold quality: passed".
- [x] 2. **Publisher.** In `neon_publish/contract.py` add `GAME_COURT_TABLES`, extend
  `APP_TABLES` (47) and `MIGRATIONS` with `"30j"`; generate
  `neon_publish/migrations/30j_game_on_court_and_gaps.sql` (primary keys per source table,
  no GRANT). Confirm by test that a scope with zero rows (stat gaps) publishes cleanly:
  replace deletes the old rows, copies nothing and passes the post-copy count check.
  *Done when:* `--list-tables` shows 47 mappings, and `python neon_publish/main.py -sc
  E2026 --dry-run -tb game_player_on_court game_team_lineup_stints game_stat_gaps` reports
  "missing table" for the three targets and 1,642 / 1,550 / 0 rows.
- [x] 3. **Tests.** `gold_etl/tests/test_game_court.py` (columns equal Silver fields minus
  provenance, keys, registration, copy statements, rollback on failure, unknown names
  rejected); update `neon_publish/tests/test_publish.py` (47 targets, 30j migration equals
  generated DDL, `--print-migration 30j`, zero-row replace) and `gold_etl/tests/test_gold.py`
  (build list). *Done when:* the four test commands in `AGENTS.md` pass.
- [x] 4. **Documentation.** `docs/DATA_DICTIONARY.md` (published-to-Neon sentences for the
  three tables, 47 targets, season-scoped count 42), `neon_publish/README.md`, `README.md`
  (all Silver-derived per-game tables are now published; fix the "stay local" sentence) and
  `AGENTS.md` (counts, `--print-migration 30j`, Gold build command). *Done when:* a search
  for 44-target counts and "stay local"/"not in Gold or Neon" finds no stale statement
  about these tables.

## Files / areas

- New: `gold_etl/tests/test_game_court.py`,
  `neon_publish/migrations/30j_game_on_court_and_gaps.sql`.
- Edit: `gold_etl/schema.py`, `gold_etl/main.py`, `neon_publish/contract.py`,
  `neon_publish/tests/test_publish.py`, `gold_etl/tests/test_gold.py`,
  `docs/DATA_DICTIONARY.md`, `neon_publish/README.md`, `README.md`, `AGENTS.md`.
- Reused, not changed: `gold_etl/loader.py`, `gold_etl/quality.py`,
  `postgres_etl/flat_schema.py`.

## Data / contracts

| Table | Key (after `competition_code`, `season_code`) | Columns |
| --- | --- | --- |
| `game_player_on_court` | `game_code`, `side`, `person_key`, `interval_ordinal` | `club_code`, `start_seconds`, `end_seconds` |
| `game_team_lineup_stints` | `game_code`, `side`, `stint_ordinal` | `club_code`, `opponent_club_code`, `start_seconds`, `end_seconds`, `players`, `opponent_players` (comma-separated `person_key`s), `possessions_for`, `possessions_against`, `points_for`, `points_against` |
| `game_stat_gaps` | `game_code`, `stat_name` | `reason` |

- Values are Silver's; NULL keeps its Silver meaning and nothing becomes 0. Seconds are
  elapsed game seconds as in the dictionary. `game_stat_gaps` is empty for E2025 and E2026
  today (its 2,566 rows are older seasons), so the Neon table will hold no rows until a
  season has a gap; `stat_name` `*` means no box score (forfeit).
- Neon names are `app_` plus the Gold name. Publish is replaced per competition and season
  in one transaction with the existing guards (preflight, 90% shrink guard).
- Size: about 31,000 rows each for the first two tables in E2025 and E2026, roughly 25 MB
  in Neon on top of the current 153 MB (free-tier limit 512 MB; observed 2026-10-02 before
  the 30h/30i tables were published).

## Testing

Unit tests only (the four commands in `AGENTS.md`). Live evidence is local: the load and
`--quality-only` on E2025 and E2026 and the Silver count comparison. Neon-side checks wait
for the owner-approved migration and publish.

## Notes for the AI

- No Verify command exists; run the four documented test commands.
- Registering the tables makes `python pipeline.py` and the publisher preflight fail with
  "missing table" until the owner applies the 30h, 30i and 30j migrations; say so and do
  not apply them.
- Follow the 30i structure (`MIGRATIONS`, one constant per feature in `contract.py`).
- Do not change Silver or existing Gold formulas. Do not commit `GAME_ADVANCED_TABLES.md`.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":6560,"specSha256":"1d7d8057cb29ce9fa6e8191af0b6c83e27cc80282cfb01565c33c4bd9f147406","branch":"refs/heads/feature/publish-on-court-stints-and-stat-gaps","head":"10331c6b59f5257b56b450c2369a4639fcf097a1","baseRef":"refs/heads/main","baseCommit":"10331c6b59f5257b56b450c2369a4639fcf097a1","sourceTree":"ae06abfc9c5fa5f65dca1faff8f6ec1914b80f23","absentOptional":[]} -->

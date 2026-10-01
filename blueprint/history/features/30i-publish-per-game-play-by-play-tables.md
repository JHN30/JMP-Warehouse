# Feature: Publish per-game play-by-play tables

**From build-plan:** feature 30i
**Build attempt:** 1
**Branch:** feature/publish-per-game-play-by-play-tables
**Status:** verified

## Goal

Copy the four per-game Silver tables of item 19 into local Gold unchanged and publish
them to Neon for E2025 and E2026 as `app_game_team_possessions`,
`app_game_team_score_flow`, `app_game_team_shot_splits` and `app_game_team_shot_zones`,
so Game Detail can read counted possessions, score flow, fast-break/second-chance/
points-off-turnover splits and shot zones per team and game. No new formulas.

## In scope

- Four Gold tables named like their Silver sources (`gold.game_team_possessions`, ...),
  with exactly the Silver columns minus `load_id`/`loaded_at`, same keys (shot zones adds
  `zone`), same nullability and types. Copy semantics are those of the 16 source
  projections (`replace_scope`, `check_scope`): per competition and season delete, then
  `INSERT ... SELECT`; quality = row count and one-way `EXCEPT` equality with Silver.
- Publisher registration (44 targets) and a reviewed migration
  `30i_game_play_by_play.sql`, selectable with `--print-migration 30i`.
- Tests, `DATA_DICTIONARY.md`, README and `AGENTS.md` updates.
- A dry-run of the Neon publish for review.

## Out of scope

- Applying the migration to Neon and any live publish (separate owner approval).
- 30j tables (on-court, stints, stat gaps), any new column or derivation, seasons other
  than E2025/E2026 in Neon, indexes beyond the primary keys, and any web-app work.
- Changing how Silver builds these tables (`possessions.py`, `score_flow.py`,
  `shot_splits.py`, `shot_zones.py`). `postgres_etl/main.py` already runs them after a
  load, before the Gold build in `pipeline.py`.

## Build loop

`workflow.stepReview` is `feature`: implement all steps, then present one review
packet. `checkpointCommits` is disabled; `/complete` makes the single commit.

## Build steps

- [x] 1. **Gold schema and copy.** In `gold_etl/schema.py` add `GAME_PBP_NAMES` (the four
  names) and `GAME_PBP_TABLES = {name: ADVANCED_TABLES[name]}` imported from
  `postgres_etl.flat_schema`; register them in `GOLD_TABLES` and append them to
  `BUILD_NAMES` in `gold_etl/main.py`. Leave `TABLES`/`SOURCE_NAMES` at 16. In
  `gold_etl/loader.py` and `gold_etl/quality.py` accept `GAME_PBP_NAMES` wherever
  `replace_scope`/`check_scope` now require `name in TABLES` (a shared
  `COPIED_TABLES = {**TABLES, **GAME_PBP_TABLES}`), and route the new names through the
  existing "source table" branch of `main.py` (dry-run count, quality, load).
  *Done when:* `python gold_etl/main.py -sc E2025 E2026 -tb game_team_possessions
  game_team_score_flow game_team_shot_splits game_team_shot_zones` loads and prints row counts
  equal to Silver (804, 804, 804, 6,907 for E2025; 40, 40, 40, 344 for E2026), and the same
  command with `--quality-only` prints "Gold quality: passed".
- [x] 2. **Publisher.** In `neon_publish/contract.py` add `GAME_PBP_TABLES =
  GAME_PBP_NAMES`, extend `APP_TABLES` (now 44) and `MIGRATIONS` with `"30i"`; generate
  `neon_publish/migrations/30i_game_play_by_play.sql` with `--print-migration 30i`
  (primary keys per source table, no GRANT, as in 30h).
  *Done when:* `--list-tables` shows 44 mappings, each of the four scoped to a season, and
  `python neon_publish/main.py -sc E2026 --dry-run -tb game_team_possessions
  game_team_score_flow game_team_shot_splits game_team_shot_zones` reports "missing table"
  for the four targets and the expected row counts.
- [x] 3. **Tests.** `gold_etl/tests/test_game_pbp.py`: columns equal the Silver fields
  minus provenance, keys (including `zone`), the four names registered once, `check_scope`
  and `replace_scope` accept them and reject unknown names, scoped atomic replace with
  rollback. Update `neon_publish/tests/test_publish.py` (44 targets, 30i migration file
  equals generated DDL, `--print-migration 30i`) and `gold_etl/tests/test_gold.py` (build
  list). *Done when:* the four test commands in `AGENTS.md` pass.
- [x] 4. **Documentation.** `docs/DATA_DICTIONARY.md`: replace "not in Gold or Neon" in the
  four sections with "Published to Neon as `public.app_<name>` (E2025 and E2026)" and the
  Gold build command; update the Neon contract counts (44 targets, season-scoped tables).
  Update `neon_publish/README.md`, `README.md` and `AGENTS.md` (counts 40 to 44,
  `--print-migration 30i`, Gold build command). *Done when:* a search for "40 " target
  counts and "not in Gold or Neon" finds no stale statement about these four tables.

## Files / areas

- New: `gold_etl/tests/test_game_pbp.py`,
  `neon_publish/migrations/30i_game_play_by_play.sql`.
- Edit: `gold_etl/schema.py`, `gold_etl/loader.py`, `gold_etl/quality.py`,
  `gold_etl/main.py`, `neon_publish/contract.py`, `neon_publish/tests/test_publish.py`,
  `gold_etl/tests/test_gold.py`, `docs/DATA_DICTIONARY.md`, `neon_publish/README.md`,
  `README.md`, `AGENTS.md`.
- Reused, not changed: `postgres_etl/flat_schema.py` (`ADVANCED_TABLES`).

## Data / contracts

| Table | Key (after `competition_code`, `season_code`) | Columns |
| --- | --- | --- |
| `game_team_possessions` | `game_code`, `side` | `club_code`, `opponent_club_code`, `counted_possessions`, `possession_seconds`, `avg_possession_seconds`, `estimated_possessions` |
| `game_team_score_flow` | `game_code`, `side` | `club_code`, `opponent_club_code`, `points_for`, `points_against`, `lead_changes`, `ties`, `time_leading_seconds`, `time_trailing_seconds`, `time_tied_seconds`, `largest_lead`, `longest_run`, `runs_6_plus`, `clutch_seconds`, `clutch_points_for`, `clutch_points_against` |
| `game_team_shot_splits` | `game_code`, `side` | `club_code`, `opponent_club_code`, `fast_break_points`, `second_chance_points`, `points_off_turnover_points`, `field_goals_made`, `assisted_field_goals`, `assisted_fg_pct` |
| `game_team_shot_zones` | `game_code`, `side`, `zone` | `club_code`, `attempts`, `made`, `points` |

- Values are Silver's, so NULL means what the dictionary says (for example the shot-split
  points are NULL when a shot flag is missing; clock-based columns are NULL for games with
  unusable clocks). Nothing is converted to 0. Zone rows exist only for zones a team shot from.
- Neon names are `app_` plus the Gold name; the web app maps the snake_case columns. Games
  before E2007 have no rows and are not in scope anyway.
- Publish: replaced per competition and season in one transaction with the existing guards
  (preflight refuses missing or incompatible targets, 90% shrink guard).

## Testing

Unit tests only (the four commands in `AGENTS.md`). Live evidence is local: the load and
`--quality-only` run on E2025 and E2026 and the Silver count comparison. Neon-side checks
are not run until the owner approves the migration and publish.

## Notes for the AI

- No Verify command exists; run the four documented test commands.
- Registering the tables makes `python pipeline.py` and the publisher preflight fail with
  "missing table" until the owner applies the 30i migration; say so in the handoff and do
  not apply it.
- Follow the 30h structure (`MIGRATIONS` dict, `GAME_TABLES`-style constant in
  `contract.py`) rather than inventing a new selector.
- Do not change Silver or any existing Gold formula. Do not commit
  `GAME_ADVANCED_TABLES.md`.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":7347,"specSha256":"a0277ab88d9e9c5fe8c75cbf281c7567fb1e3de68b87faca0d73eb94eefa1a35","branch":"refs/heads/feature/publish-per-game-play-by-play-tables","head":"0919c8f8ba2da94a69666bfc930bb80dd07e2f86","baseRef":"refs/heads/main","baseCommit":"0919c8f8ba2da94a69666bfc930bb80dd07e2f86","sourceTree":"ca4a8cb82d81572b91bf2a54006b0c9691bde793","absentOptional":[]} -->

# Feature: Records tables

**From build-plan:** feature 11
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/records-tables`

## Goal

Precompute three all-time EuroLeague leaderboards — player-season, single-game,
and team-season records — as local PostgreSQL tables and publish them to Neon
as `app_*` tables, so the web app's Express API (`jmp-euroleague2/backend`) can
read a ready-made top-50 list instead of running the aggregation queries itself
on every request.

## In scope

- Three new tables, computed from this pipeline's already-loaded local data
  (full history, `E2000`-`E2026`, competition `E` only — EuroCup stays
  deferred), each holding the top 50 rows per metric:
  - `app_records_player_seasons` - one season-long player total per row.
    Metrics: `points_scored`, `total_rebounds`, `assists`, `pir` (same four the
    Express `/records/player-seasons` route exposes today), sourced from
    `season_stats_traditional` (`phase_code = 'all'`, `mode = 'accumulated'`).
  - `app_records_single_games` - one player's box score in one game per row.
    Metrics: `points`, `valuation`, `total_rebounds`, `assistances` (matching
    Express `/records/single-games`), sourced from `game_player_stats` joined
    to `games` where `played = TRUE`.
  - `app_records_team_seasons` - one team's season total per row. Metrics:
    `points`, `valuation`, `total_rebounds`, `assistances` (matching Express
    `/records/team-seasons`), sourced from `game_team_stats`
    (`stats_kind = 'total'`) summed per season and club, joined to `games`
    where `played = TRUE`.
- A local computation step that (re)builds all three tables in one transaction
  each, from the already-loaded flat tables (not from bronze), independent of
  any single `-sc` season selection.
- Read-only quality checks for the three tables (rank sequence, non-null/
  non-negative values, row-count ceiling).
- Neon publish support for the three tables: a whole-table replace (not the
  existing per-season `DELETE ... WHERE season_code = %s` path), reusing the
  existing shrink guard's row-count comparison.
- `docs/DATA_DICTIONARY.md` entries for the three tables.
- Unit tests for the new ranking/tie-break/forfeit-exclusion logic.

## Out of scope

- Changing `jmp-euroleague2` (the Express backend) to read from these tables
  instead of computing records itself. That cutover is coordinated with the
  web-app repo later, the same way `app_standings` (feature 9) and the
  `app_play_by_play` / `app_shots` tables (feature 21) were.
- EuroCup records (`competition_code = 'U'`); EuroCup as a whole is deferred
  (build-plan item 18).
- Record types beyond the three Express already exposes (for example
  multi-metric composites like "40-point games", or career/cross-season
  aggregates outside `person_key`-scoped totals) — feature 14 (player
  careers) is the planned home for cross-season player identity work.
- Automatic/scheduled refresh of these tables (feature 20).
- Publishing older seasons' other tables (`games`, standings, etc.) to Neon —
  unaffected; feature 15 still owns that. Records rows are self-contained
  (player/club names are denormalized onto the row), so they don't depend on
  those other tables being in Neon.

## Build loop

Build one small step at a time. Per `blueprint/config.json`
(`workflow.stepReview: "feature"`), this produces one review packet after all
steps, not a pause after each one. Checkpoint commits are disabled
(`workflow.checkpointCommits: "disabled"`). `/complete` makes the final feature
commit.

## Build steps

- [x] **Step 1 - Schema for the three tables** - Add
  `app_records_player_seasons`, `app_records_single_games`, and
  `app_records_team_seasons` to `postgres_etl/flat_schema.py`, keyed by
  `(competition_code, metric, rank_ordinal)` rather than the usual
  `(competition_code, season_code, ...)` — these tables are cross-season by
  design, so `season_code` is a data column on each row (the season that
  record happened in), not part of the key. Add the three names to
  `PUBLISHED_TABLES` (they already start with `app_`, so `physical_name`
  needs no new mapping). *Done when:* `python postgres_etl/main.py
  --list-tables` lists the three new names.
- [x] **Step 2 - Local ranking computation** - Add `postgres_etl/records.py`
  with one function per table that runs the ranking SQL against the local
  database (reading `season_stats_traditional`, `game_player_stats`,
  `game_team_stats`, `games` for `competition_code = 'E'` across every season
  already loaded locally) and replaces each table's full contents inside one
  transaction (`TRUNCATE` + insert, not per-season delete). Rank 1-50 per
  metric; a metric with fewer than 50 qualifying rows keeps however many
  exist. Tie-break order, replicated from the Express routes: player-seasons
  by value desc then `season_code` asc (add `person_key` asc as a final
  deterministic tiebreak, since JS `Array.sort` gives Express no such
  guarantee); single-games by value desc, `season_code` asc, `game_code` asc,
  `person_key` asc; team-seasons by value desc, `season_code` asc, `club_code`
  asc. Forfeits are excluded via the `games.played = TRUE` join for the two
  game-level tables; `season_stats_traditional` is already a season aggregate
  from the source API, so no separate forfeit filter applies there. *Done
  when:* running the new module against the local dev database populates all
  three tables with at most 50 rows per metric, and a manual spot-check query
  (for example the single highest `points_scored` row) matches the computed
  table.
- [x] **Step 3 - Wire into the loader** - In `postgres_etl/main.py` /
  `postgres_etl/flat_loader.py`, route these three table names to the Step 2
  computation instead of the normal bronze-driven per-season load, so they
  run once per invocation (ignoring which specific `-sc` seasons were
  requested) whenever selected via `-tb`, and still respect `--dry-run` (skip
  writes, report what would change) and `--quality-only`. *Done when:*
  `python postgres_etl/main.py -sc current -tb app_records_player_seasons
  app_records_single_games app_records_team_seasons` refreshes only those
  three tables from full local history, and other `-tb` selections are
  unaffected.
- [x] **Step 4 - Quality checks** - In `postgres_etl/quality.py`, add checks
  gated on the three table names (same pattern as the existing
  `app_standings_key_mismatch` check): `rank_ordinal` is a dense `1..N`
  sequence per metric with no gaps or duplicates, `value` is non-null and
  non-negative, and no metric exceeds 50 rows. *Done when:* `python
  postgres_etl/main.py --quality-only -tb app_records_player_seasons
  app_records_single_games app_records_team_seasons` reports 0 errors after a
  fresh Step 2/3 run.
- [x] **Step 5 - Neon publish (whole-table replace)** - In
  `neon_publish/publish.py`, add a whole-table publish path for these three
  tables — one transaction per table doing a full replace, not the existing
  per-season `DELETE WHERE season_code = %s` — reusing the existing
  `shrink_problems` row-count comparison as the safety check. Triggered
  whenever the tables are included in `-tb`, regardless of the requested
  `-sc`. *Done when:* `python neon_publish/main.py --dry-run -tb
  app_records_player_seasons app_records_single_games app_records_team_seasons`
  reports the planned whole-table replace and touches no other table.
- [x] **Step 6 - Data dictionary** - Document the three tables in
  `docs/DATA_DICTIONARY.md`: columns, the four metrics per table, the
  tie-break rule, the forfeit-exclusion note, and the all-time (`E2000`-
  current) scope. *Done when:* the doc lists all three tables consistently
  with the Step 1 schema.
- [x] **Step 7 - Tests** - Add unit tests under `postgres_etl/tests/` for the
  Step 2 ranking logic: correct top-50 ordering, the documented tie-break
  order per table, forfeit exclusion, and the "fewer than 50 qualifying rows"
  case. *Done when:* `python -m unittest discover -s postgres_etl/tests`
  passes, including the new tests.

## Files / areas

- `postgres_etl/flat_schema.py` - three new table definitions, `PUBLISHED_TABLES`.
- `postgres_etl/records.py` (new) - ranking SQL and whole-table replace logic.
- `postgres_etl/main.py`, `postgres_etl/flat_loader.py` - route the three
  table names to the new non-season-scoped computation.
- `postgres_etl/quality.py` - new checks for the three tables.
- `postgres_etl/tests/` - new test module for `records.py`.
- `neon_publish/publish.py` - whole-table replace path for these tables.
- `docs/DATA_DICTIONARY.md` - new table documentation.

## Data / contracts

- All three tables: key `(competition_code, metric, rank_ordinal)`;
  `competition_code` is always `'E'` for now. `season_code` is a plain column
  (which season that record row belongs to), not part of the key, since a
  table's content spans every season loaded locally.
- `app_records_player_seasons` columns: `competition_code`, `metric`,
  `rank_ordinal`, `season_code`, `person_key`, `player_name`, `club_code`,
  `club_name`, `value` (NUMERIC). `metric` in
  `{points_scored, total_rebounds, assists, pir}`.
- `app_records_single_games` columns: `competition_code`, `metric`,
  `rank_ordinal`, `season_code`, `game_code`, `scheduled_at`, `person_key`,
  `player_name`, `club_code`, `club_name`, `value`. `metric` in
  `{points, valuation, total_rebounds, assistances}`.
- `app_records_team_seasons` columns: `competition_code`, `metric`,
  `rank_ordinal`, `season_code`, `club_code`, `club_name`, `value`. `metric`
  in `{points, valuation, total_rebounds, assistances}`.
- Rows are self-contained (player/club names denormalized onto the row) so
  the app never needs to join back to `games`/`people` to render a record.
- Rebuild is idempotent and full-replace: every run recomputes all rows for
  all three tables from current local data and replaces prior contents in one
  transaction per table. Local build and Neon publish are not `-sc`-scoped;
  they always reflect every season currently loaded (locally) or already
  published as source tables (in Neon, for the publish step's own source
  data — Neon just receives whatever the local tables currently hold).
- At most 50 rows per `metric` per table; fewer when a metric has fewer than
  50 qualifying rows (never an error).
- Forfeits: excluded from the two game-level tables via `games.played = TRUE`
  (a forfeit has no box-score rows to rank in the first place, per
  `docs/DATA_DICTIONARY.md`'s existing forfeit note); not applicable to
  `app_records_player_seasons`, which reads a season-level source aggregate.

## Testing

- `python -m unittest discover -s postgres_etl/tests` covers the new ranking/
  tie-break/forfeit-exclusion logic (Step 7).
- Manual verification per step's *Done when* above: `--list-tables`,
  `--quality-only`, and `neon_publish/main.py --dry-run` output.
- No UI to test; this is a data pipeline change only.

## Notes for the AI

- Every other table in this pipeline is season-scoped and loaded per-season
  straight from bronze files. These three tables are the first exception:
  they're computed from already-loaded local PostgreSQL data across all
  seasons, and republished as a whole-table replace, not a per-season delete.
  Don't force them through the existing `table()` SCOPE helper (which
  prepends `competition_code, season_code` to the key) — that helper assumes
  season-scoping these tables don't have.
- Match the Express route logic in `D:\jmp-project\jmp-euroleague2\backend\
  src\routes\seasons.ts` (`/records/player-seasons`, `/records/single-games`,
  `/records/team-seasons`) exactly for metric names, source filters, and
  ordering — that's the existing contract being replicated, not redesigned.
  That file lives in a separate repo and is not part of this feature's
  in-scope changes; it's read-only reference here.
- Never leave Neon with a half-replaced records table: wrap each table's
  `TRUNCATE` + insert in one transaction, same safety bar as the existing
  per-season publish.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":12092,"specSha256":"fe9ec48877c0fbf35d6b307844a97f1009911b706e176ece37fb402d73448723","branch":"refs/heads/feature/records-tables","head":"129ed24bdccfec5a3c22b1ffe05edc02e4f3b4e9","baseRef":"refs/heads/main","baseCommit":"129ed24bdccfec5a3c22b1ffe05edc02e4f3b4e9","sourceTree":"e5ea41b6b0ec398060e511ea4acd52d4941e4e65","absentOptional":[]} -->

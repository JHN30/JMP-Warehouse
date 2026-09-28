# Feature: Standings Stats App Table

**From build-plan:** feature 28
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/standings-stats-app-table`

## Goal

Build `gold.app_standings_stats`: for every season, scope, round and club, one page-shaped row with the team advanced stats the standings page needs, taken from the three per-round team tables (26a cumulative, 26b ratings, 26c splits). It is the team counterpart to `app_standings` (feature 9) for advanced stats: one wide row per club and round that a page can read with a single filter. It is built and checked locally now; publishing to Neon is feature 30g.

## In scope

- One new local Gold table, `app_standings_stats`, registered in `ROUND_NAMES` (outside `DERIVED_NAMES` and the Neon allowlist, which stays 26 tables until 30g), with the same row set as `team_round_stats`: scopes `all`, each phase and `PS`, every round each club has played through.
- A derivation module `gold_etl/standings_stats.py` that joins the pure derivations of `team_rounds`, `team_ratings` and `team_splits` in memory on (`scope`, `round_number`, `club_code`), from one shared Silver read. It reads no Gold table, so it does not depend on build order.
- The column set below (a projection of the three source tables, no new formulas).
- `gold_etl/main.py` support: `-tb app_standings_stats` (part of `-tb all`), `--list-tables`, `--dry-run`, `--quality-only` (fresh-derivation equality plus a row-set and value tie to the three source tables).
- Documentation and a local backfill of every loaded EuroLeague season.

## Out of scope

- Neon publishing, allowlist and cutover changes (30g); any change to `app_standings`, `app_team_season_stats`, the three source round tables, Silver or Bronze.
- Replacing `app_team_season_stats` (feature 12). Both stay for now; the overview leaves that choice to this spec, and the smaller reversible design is to keep both and decide when publishing in 30g (see Open questions).
- Raw own/opponent totals (`own_*`, `opp_*`), which `app_team_season_stats` and `team_round_stats` already carry; player tables (27); lineups (29).
- New formulas, ranks or per-page ordering (`app_standings` already carries positions).

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Register the table; derive the join.** Add `app_standings_stats` to `gold_etl/schema.py` (`ROUND_NAMES`, merged into `GOLD_TABLES`, columns below). In `gold_etl/standings_stats.py`, call the three `derive_rows` functions on the same Silver tables and merge them by key into one row per club, scope and round, keeping the source values exactly.
  *Done when:* tests show the merged row equals the corresponding source rows column by column for a small multi-round, multi-scope example (including a club that starts later, a postseason phase and its `PS` scope), that the row set equals `team_round_stats`, and that no `own_*`, `opp_*`, `game_minutes` or `pythagorean_exponent` column exists; `python -m unittest gold_etl.tests.test_standings_stats` passes.
- [x] **Step 2 - Storage, CLI and quality.** Reuse the round-table loader and quality pattern: atomic season-slice replace, dry run, `--quality-only` fresh-derivation equality, and a tie check that every row's shared columns equal the stored `team_round_stats`, `team_round_ratings` and `team_round_splits` rows when those exist, reported as errors on mismatch.
  *Done when:* fake-connection tests show scoped delete, insert, rollback on failure, dry-run read-only behavior, mismatch detection and the tie check catching a changed value and a missing source row; `python gold_etl/main.py -sc E2025 -tb app_standings_stats --dry-run` prints a row count; the neon_publish allowlist test still shows 26 tables.
- [x] **Step 3 - Document, backfill, verify.** Update `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`. Run all declared test suites, build every loaded EuroLeague season, run `--quality-only`, report row counts and build time, and compare the group-phase rows with `app_standings` (games, wins, losses for the same club, phase and round), recording any differences in the data dictionary as findings rather than adding a gate.
  *Done when:* docs match behavior, tests pass, the table exists for every season, quality reports no error, and the `app_standings` comparison result is written down.

## Files / areas

- `gold_etl/schema.py`, `gold_etl/standings_stats.py` (new), `gold_etl/loader.py`, `gold_etl/quality.py`, `gold_etl/main.py`
- `gold_etl/tests/test_standings_stats.py` (new), small updates to `gold_etl/tests/test_gold.py` list-tables expectations through `ROUND_NAMES` if needed
- `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`

## Data / contracts

- Name: `app_standings_stats` (final Neon name; publishing later adds it to the allowlist). Key: `competition_code`, `season_code`, `scope`, `round_number`, `club_code`, matching the three source tables. To join with `app_standings` on a group phase, use `scope = phase_code`; `scope` also takes `all` and `PS`, which `app_standings` has no rows for.
- Columns (values identical to the source tables, `NUMERIC` unless noted): from `team_round_stats` - `club_name`, `games_played` and `wins`, `losses` (`INTEGER`), `points_for`, `points_against`, `possessions`, `mov`, `pythagorean_win_pct`, `pythagorean_wins`, `pace`, `offensive_rating`, `defensive_rating`, `net_rating`, `efg_pct`, `tov_pct`, `orb_pct`, `drb_pct`, `ft_rate`, `opp_efg_pct`, `opp_tov_pct`, `opp_ft_rate`, `true_shooting_pct`, `assist_ratio`; from `team_round_ratings` - `connected` (`BOOLEAN`), `league_offensive_rating`, `league_pace`, `relative_offensive_rating`, `relative_defensive_rating`, `relative_pace`, `srs`, `sos`, `sov`, `adj_offensive_rating`, `adj_defensive_rating`, `adj_net_rating`; from `team_round_splits` - for each of `home`, `away`, `last5`, `last10`: `<group>_games`, `<group>_wins` (`INTEGER`), `<group>_mov`, `<group>_offensive_rating`, `<group>_defensive_rating`, `<group>_net_rating`, `<group>_pace`.
- Rates and percentages stay fractions as in the source tables; NULL stays NULL. The season slice is replaced atomically; a rerun gives identical rows. Reads Silver only; no Neon, no network.

## Testing

- Focused: `python -m unittest gold_etl.tests.test_standings_stats`, with in-memory games (reuse the fixtures of `test_team_rounds`, `test_team_ratings` and `test_team_splits`) and fake cursors.
- Regression suites: `python -m unittest discover -s gold_etl/tests`; `python -m unittest discover -s postgres_etl/tests`; `cd api_requests && python -m unittest tests.test_scrapper`; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Local checks: `python gold_etl/main.py -sc all -tb app_standings_stats`, then `--quality-only`. No combined Verify command is declared; no Neon call is made.

## Notes for the AI

- Follow `gold_etl/team_splits.py` and `player_ratings.py` for the module shape and the `ROUND_NAMES` dispatch in loader, quality and `main.py`. The `read_rows` cursor is reused by `read_tables`; call it once and pass its tables to the three derivations, and if any extra query is added, fetch its rows before the next `execute` (27b hit this).
- Merge by key with dictionaries, and take column names from the schema so the table and the derivation cannot drift. Derive each source table once per season; do not recompute per club.
- The name starts with `app_`, so check that nothing that lists `app_*` tables (`neon_publish/contract.py`, docs tables, tests) treats it as published; it must stay out of `DERIVED_NAMES`.

## Open questions

Non-blocking; the defaults above apply unless changed at review.

- Keep `app_team_season_stats` alongside the new table (default, recommended) or replace it when publishing in 30g. Keeping both means two team-stats owners until 30g decides; `app_team_season_stats` has season totals per phase, this table has cumulative per-round advanced stats.
- Column selection: only advanced stats and splits are exposed, not raw totals. The web app can request more columns before 30g without changing the derivations.
- The web app is local-only and in development, so a later rename of the table is cheap.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":8438,"specSha256":"aad9f19c727395a4a54241ed7bdffeea69f997ac1e78d4a410d9f4be51a5f2c5","branch":"refs/heads/feature/standings-stats-app-table","head":"facfabe450b46eff00715b205e4f0cecb9c92d82","baseRef":"refs/heads/main","baseCommit":"facfabe450b46eff00715b205e4f0cecb9c92d82","sourceTree":"4e30a4111284c55ed606036565b87758be78d0ca","absentOptional":[]} -->

# Feature: Play-by-Play Aggregates

**From build-plan:** feature 19d
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/play-by-play-aggregates`

## Goal

Build two local Gold tables that aggregate the per-game play-by-play tables of 19a-19c per team, season and scope: `gold.team_pbp_stats` (counted possessions, possession length, score flow, clutch, fast-break, second-chance and off-turnover points, assisted field goals) and `gold.team_shot_zone_stats` (attempts, makes, points and attempt share per shot zone). They finish feature 19 and follow the round-table pattern (scopes `all`, each phase and `PS`, local only, outside the Neon allowlist).

## In scope

- Two new local Gold tables registered in `ROUND_NAMES` (outside `DERIVED_NAMES`, so the Neon allowlist stays 26 tables): `team_pbp_stats` and `team_shot_zone_stats`.
- Derivation modules `gold_etl/team_pbp.py` and `gold_etl/team_shot_zones.py` (pure `derive_rows`, `read_rows`) reading Silver only: `games` (phase), `game_team_possessions`, `game_team_score_flow`, `game_team_shot_splits`, `game_team_shot_zones`. A clear error names the missing Silver table and the command that builds it.
- `gold_etl/main.py` support for both: `-tb <name>` (part of `-tb all`), `--list-tables`, `--dry-run`, `--quality-only` (fresh-derivation equality plus a partition check that the `all` scope equals the sum of the phase scopes).
- Documentation and a local backfill of every loaded EuroLeague season with play-by-play.

## Out of scope

- Player-level aggregates: none of the 19a-19c inputs is per player.
- Any change to the Silver tables of 19a-19c, to the round tables, or to which possessions the ratings use (`team_round_*` keep the box-score estimate; the counted values are only aggregated here).
- Per-round (cumulative) versions, opponent columns, ranks, and Neon publishing (30g).

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - `team_pbp_stats` derivation (pure).** Register the table in `gold_etl/schema.py` (`ROUND_NAMES`, merged into `GOLD_TABLES`) and write `gold_etl/team_pbp.py`'s `derive_rows` over the four per-game rows lists and `games`.
  *Done when:* tests check every column against a hand-worked example with two clubs, two phases and a postseason scope: sums, possession-weighted average length, per-game averages, maxima, counts of clutch and flagged games, NULL handling (a game with NULL time or NULL point splits is left out of that column's sums and its game count), and that `all` equals the sum of the phase scopes for additive columns; `python -m unittest gold_etl.tests.test_team_pbp` passes.
- [x] **Step 2 - `team_shot_zone_stats` derivation (pure).** Register the table and write `gold_etl/team_shot_zones.py`'s `derive_rows`.
  *Done when:* tests check attempts, makes, points, `fg_pct` and `attempt_share` per club, scope and zone (shares sum to 1 per club and scope), scopes, and that zones a club never shot from have no row; its tests pass.
- [x] **Step 3 - Storage, CLI, quality.** Reuse the round-table loader and quality pattern for both tables: atomic season-slice replace, dry run, `--quality-only` fresh-derivation equality, the partition check, and the missing-Silver-table error.
  *Done when:* fake-connection tests show scoped delete, insert, rollback on failure, dry-run read-only behavior, mismatch detection, the partition check catching a wrong `all` row, and the missing-table message; `python gold_etl/main.py -sc E2025 -tb team_pbp_stats team_shot_zone_stats --dry-run` prints row counts; the neon_publish allowlist test still shows 26 tables.
- [x] **Step 4 - Document, backfill, verify.** Update `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`. Run all declared suites, build every loaded season, run `--quality-only`, report row counts, and hand-check one club's season against its per-game rows.
  *Done when:* docs match behavior, tests pass, both tables exist for every season E2007-E2026, quality reports no error, and the hand check is written down.

## Files / areas

- `gold_etl/schema.py`, `gold_etl/team_pbp.py` (new), `gold_etl/team_shot_zones.py` (new), `gold_etl/loader.py`, `gold_etl/quality.py`, `gold_etl/main.py`
- `gold_etl/tests/test_team_pbp.py` (new, covers both tables), list-tables expectations in `gold_etl/tests/test_gold.py` only through `ROUND_NAMES`
- `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`

## Data / contracts

- `gold.team_pbp_stats`: key `competition_code`, `season_code`, `scope`, `club_code`; `scope` is `all`, each phase in the season, or `PS` (postseason phases together), as in the round tables (`_scopes` and the phase per game from `silver.games`). Columns (all `NUMERIC` unless noted): `games` (`INTEGER`, games with a possessions row), from 19a `counted_possessions`, `estimated_possessions`, `possession_seconds` (sums) and `avg_possession_seconds` (mean of the per-game averages weighted by counted possessions, games with a NULL average left out); from 19b `lead_changes_per_game`, `ties_per_game` (means over games), `timed_games` (`INTEGER`, games with time data), `time_leading_seconds`, `time_trailing_seconds`, `time_tied_seconds` (sums over timed games), `largest_lead`, `longest_run` (maxima), `runs_6_plus` (`INTEGER` sum), `clutch_games` (`INTEGER`, games with clutch seconds above 0), `clutch_seconds`, `clutch_points_for`, `clutch_points_against` (sums over timed games for seconds, over all games for points); from 19c `flagged_games` (`INTEGER`, games with point splits), `fast_break_points`, `second_chance_points`, `points_off_turnover_points` (sums over flagged games), `field_goals_made`, `assisted_field_goals` (sums) and `assisted_fg_pct` (sum over sum). NULL when the scope has no usable game for that column.
- `gold.team_shot_zone_stats`: key `competition_code`, `season_code`, `scope`, `club_code`, `zone`; columns `attempts`, `made`, `points` (`INTEGER` sums), `fg_pct` (`made / attempts`), `attempt_share` (`attempts` over the club's attempts in the scope).
- Fractions are `NUMERIC` with 6 places, NULL on a zero denominator. The season slice is replaced atomically; a rerun gives identical rows. Reads Silver only; no Neon, no network.

## Testing

- Focused: `python -m unittest gold_etl.tests.test_team_pbp gold_etl.tests.test_team_shot_zones`, with in-memory rows and fake cursors.
- Regression suites: `python -m unittest discover -s gold_etl/tests`; `python -m unittest discover -s postgres_etl/tests`; `cd api_requests && python -m unittest tests.test_scrapper`; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Local checks: `python gold_etl/main.py -sc 2007-2026 -tb team_pbp_stats team_shot_zone_stats`, then `--quality-only`. No combined Verify command is declared; no Neon call is made. Run every command from the project root.

## Notes for the AI

- Follow `gold_etl/team_splits.py` and `player_ratings.py` for module shape and the `ROUND_NAMES` dispatch in `loader.py`, `quality.py` and `main.py` (`read_aggregate_rows`, `check_aggregate_scope`, `replace_aggregate_scope`). The Silver 19a-19c tables are read with plain queries, one `execute` then `_dict_rows` each, before the next query.
- Group games by (club, scope) using the phase of each game from `silver.games`; a game counts in `all`, its phase, and `PS` when the phase is a postseason phase (`gold_etl/team_rounds._scopes`).
- Keep the per-game rows lists independent: 19a-19c rows should share the same (game, side) set, but do not assume it; join by (game_code, side) and let a missing row leave that game out of that table's columns only.
- Existing Gold main-wiring and list-tables tests must keep passing; adjust their expectations through `ROUND_NAMES` only.
- The partition check compares additive columns of `all` with the sum of the phase scopes for each club, so it holds by construction and catches a wrong scope grouping.

## Open questions

Non-blocking; the defaults above apply unless changed at review.

- The column set is the natural aggregation of 19a-19c, without derived ratings from counted possessions; a counted offensive rating can be added later once the possessions question (which value the ratings use) is decided.
- Two tables (per-club totals and a long per-zone table), matching the two long and wide Silver shapes.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":8539,"specSha256":"329a65266219878ff3616f1969f193c6d21d3fbd5a158c17776747e9db955d9e","branch":"refs/heads/feature/play-by-play-aggregates","head":"0b215cbeafbd71df8aff93dadbd321cd921aedd2","baseRef":"refs/heads/main","baseCommit":"0b215cbeafbd71df8aff93dadbd321cd921aedd2","sourceTree":"43ba27ff1d441117bbf02b1e133989cd3e0f746b","absentOptional":[]} -->

# Feature: Per-Game Advanced Stats

**From build-plan:** feature 25
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/per-game-advanced-stats`

## Goal

Add per-record enrichment to `silver`: one advanced-stats row per game and club, and one per game and player, computed only from the game's own box score (possessions, pace, ratings, four factors, player rates, Game Score). Features 26-29 build their per-round Gold tables on these rows.

## In scope

- Two new Silver tables, `silver.game_team_advanced` and `silver.game_player_advanced`, defined beside the existing tables and carrying the same provenance columns (`load_id`, `loaded_at`) and load-log entries.
- A pure derivation module `postgres_etl/advanced.py` (formulas below) that reads `silver.games`, `silver.game_period_scores`, `silver.game_team_stats` (`total` rows) and `silver.game_player_stats` for one season and returns rows. Reading and writing are separate from the formulas so tests need no database.
- A season-scoped, transactional replace (delete the season slice, insert, commit together; a failure keeps the old rows), like the existing Gold replace.
- CLI `python postgres_etl/advanced.py -sc <seasons>` with `--dry-run` (derive and count, no writes) and `--quality-only` (read-only checks), plus an automatic run after a Silver load in `postgres_etl/main.py` for the loaded seasons (skipped on `--dry-run` and when no game stat table was loaded). `pipeline.py` already calls the Silver load, so it needs no change.
- Quality checks and documentation (`docs/DATA_DICTIONARY.md`, `postgres_etl/README.md`, `README.md`, `AGENTS.md` commands and table counts).
- A local backfill of all cached EuroLeague seasons once the checks pass.

## Out of scope

- Per-round or cumulative stats, league averages, relative/adjusted ratings, SRS/SOS (features 26-28), PER, Win Shares and PIE (27), play-by-play possessions and clutch stats (19), lineups (29).
- Any Gold table, Neon publishing, or web-app change (30g publishes later); changes to the 28 bronze-sourced Silver tables or to Bronze.
- Comparing to the API's season feeds (a check in 26/27).

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; no step commits are required. `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Team derivation.** Register `game_team_advanced` in the Silver schema (key `game_code`, `side`; `club_code`, `opponent_club_code`, `phase_code`, `round_number`, `game_minutes`, `possessions`, `own_possessions_estimate`, `pace`, `offensive_rating`, `defensive_rating`, `net_rating`, `efg_pct`, `tov_pct`, `orb_pct`, `drb_pct`, `ft_rate`, `opp_efg_pct`, `opp_tov_pct`, `opp_ft_rate`, `true_shooting_pct`, `assist_ratio`). Implement the pure function in `postgres_etl/advanced.py` per the formulas. *Done when:* unit tests with worked box scores check every formula, regulation and overtime minutes, a missing measure giving NULL, zero denominators giving NULL, and skipped forfeit/no-box-score/unplayed games; `python -m unittest discover -s postgres_etl/tests` passes.
- [x] **Step 2 - Player derivation.** Register `game_player_advanced` (key `game_code`, `side`, `person_key`; `club_code`, `seconds_played`, `game_score`, `true_shooting_pct`, `efg_pct`, `usage_pct`, `assist_pct`, `orb_pct`, `drb_pct`, `trb_pct`, `steal_pct`, `block_pct`, `tov_pct`) using the team `total` row and the player's minutes. *Done when:* tests cover Game Score, each rate with a hand-worked example, a player with zero minutes (row kept, rates NULL, Game Score still computed), and a team total that disagrees with its player sum (rates still use the official team total).
- [x] **Step 3 - Storage and CLI.** Add the season replace, the `advanced.py` CLI (`-sc`, `--dry-run`, `--quality-only`), load-log entries, and the automatic call from `postgres_etl/main.py`. *Done when:* fake-connection tests show DDL, scope-limited delete, insert, rollback on failure, load-log rows, a dry run touching no database, and `main.py` running it only after a real load of game tables; `python postgres_etl/advanced.py --dry-run -sc E2025` prints row counts.
- [x] **Step 4 - Quality checks.** Add read-only checks: every played game with a `total` box score for both sides has two team rows and each `game_player_stats` row has a player row; both sides of a game share the same `possessions`; implausible pace or rating values (outside 30-150 pace, 20-250 rating) are reported as warnings. Failures print in the existing quality report format. *Done when:* tests cover pass and fail cases and `--quality-only` runs against local Silver.
- [x] **Step 5 - Document, backfill, verify.** Update the docs listed above. Run all declared test suites, then the enrichment for `-sc 2000-2026`, then `--quality-only`; report row counts and hand-check one game. *Done when:* docs match behavior, tests pass, local Silver holds the new tables for every cached season, and quality reports no unexplained failure.

## Files / areas

- `postgres_etl/flat_schema.py` (new table definitions), `postgres_etl/advanced.py` (new), `postgres_etl/main.py`, `postgres_etl/quality.py`
- `postgres_etl/tests/test_advanced.py` (new) and existing `postgres_etl/tests/`
- `docs/DATA_DICTIONARY.md`, `postgres_etl/README.md`, `README.md`, `AGENTS.md`

## Data / contracts

- Keys start with `competition_code`, `season_code`. Ratios are `NUMERIC` fractions (0.512, not 51.2); ratings and pace are per 100 possessions and per 40 minutes. NULL means not computable; never 0 for a missing input.
- Only played games with a `total` team row for both sides produce rows. A game listed in `game_stat_gaps` with `*` produces none. A missing measure gives NULL for the outputs that need it.
- Formulas are box-score estimates. Feature 19 keeps counted possessions alongside them, never silently replacing them.
  - `game_minutes` = 40 + 5 per overtime period in `game_period_scores` (periods above 4); team minutes = 5 x `game_minutes`.
  - Own estimate = FGA + 0.44 x FTA - OREB + TOV. Game `possessions` = average of the two teams' estimates, identical on both rows; `own_possessions_estimate` keeps each side's value.
  - `pace` = 40 x `possessions` / `game_minutes`. `offensive_rating` = 100 x points / `possessions`; `defensive_rating` is the opponent's; `net_rating` is the difference.
  - Four factors: `efg_pct` = (FGM + 0.5 x 3PM) / FGA; `tov_pct` = TOV / (FGA + 0.44 x FTA + TOV); `orb_pct` = OREB / (OREB + opponent DREB); `drb_pct` = DREB / (DREB + opponent OREB); `ft_rate` = FTM / FGA. `opp_*` columns are the opponent's own values. `true_shooting_pct` = points / (2 x (FGA + 0.44 x FTA)); `assist_ratio` = AST / FGM.
  - Game Score (Hollinger) = PTS + 0.4 FGM - 0.7 FGA - 0.4 (FTA - FTM) + 0.7 OREB + 0.3 DREB + STL + 0.7 AST + 0.7 BLK - 0.4 PF - TOV, with PF = `fouls_committed`.
  - Player rates use `seconds_played` and the team `total` row (Basketball-Reference forms): `usage_pct` = (FGA + 0.44 FTA + TOV) x team minutes / (player minutes x the team's same sum); `assist_pct` = AST / ((player minutes / team minutes) x team FGM - FGM); `trb_pct`, `orb_pct`, `drb_pct` = rebounds x team minutes / (player minutes x (team + opponent rebounds of that type)); `steal_pct` = STL x team minutes / (player minutes x opponent possessions); `block_pct` = BLK x team minutes / (player minutes x opponent two-point attempts); `tov_pct` as for teams. Zero minutes or a zero denominator gives NULL.
- Each season slice is replaced in one transaction; a rerun gives identical rows apart from provenance. Derived only from Silver; nothing reads Gold or Neon.

## Testing

- Focused unit tests: `python -m unittest postgres_etl.tests.test_advanced`, with fake cursors and in-memory box scores.
- Regression suites: `python -m unittest discover -s postgres_etl/tests`; `python -m unittest discover -s gold_etl/tests`; `cd api_requests && python -m unittest tests.test_scrapper`; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Read-only local check after the backfill: `python postgres_etl/advanced.py -sc 2000-2026 --quality-only`. No combined Verify command is declared; no Neon call is made.

## Notes for the AI

- Follow the Gold derivation style: a pure `derive_rows` plus a `read_rows` that queries `silver` with `competition_code`/`season_code` parameters and returns dicts.
- Reuse the Silver table machinery (`create_table_sql`, provenance columns, load log) instead of new DDL code; check how the load log names tables before adding entries.
- Use Silver names (`assists`, `fouls_committed`, `two_pointers_made`, `seconds_played`), not the API's. `points` in `game_team_stats` and `game_player_stats` is the scoring source.
- Older seasons may lack minutes or some measures; produce NULLs, never guess.

## Open questions

Non-blocking; the defaults above apply unless changed at review.

- Formula conventions (Oliver possessions with 0.44 x FTA, Hollinger Game Score, Basketball-Reference rate forms, `ft_rate` as FTM/FGA). Say so if the JMP rating model expects different ones.
- The tables live in `silver` as the plan says and run automatically after each Silver load; the standalone CLI stays available.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":9318,"specSha256":"60fe7fe3d653c9a9b0b63f00205fc07e24bfb84cb76f09c6ef64a3677c7b3d50","branch":"refs/heads/feature/per-game-advanced-stats","head":"df1a880a3803db11ffeeefa0fcbfe73e34259dce","baseRef":"refs/heads/main","baseCommit":"df1a880a3803db11ffeeefa0fcbfe73e34259dce","sourceTree":"6152b1e3590e5a345796874ee03a8f4b59fa819e","absentOptional":[]} -->

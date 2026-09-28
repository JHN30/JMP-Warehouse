# Feature: Cumulative Player-Round Stats

**From build-plan:** feature 27a
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/cumulative-player-round-stats`

## Goal

Build `gold.player_round_stats`: for every season, scope and round, one row per player with cumulative totals, minutes, shooting efficiency, usage, assist, rebound, steal, block and turnover rates, per-100 stats, Game Score and PIE through that round. It is the player counterpart of `team_round_stats` (26a) and the base for PER (27b) and Win Shares (27c). Final rows are checked against the API player season feeds.

## In scope

- One new local Gold table, `player_round_stats`, registered with the other round tables (`ROUND_NAMES`) and outside the Neon allowlist.
- A derivation module `gold_etl/player_rounds.py` reading only Silver: `games`, `game_team_stats` (`total` rows), `game_team_advanced`, `game_player_stats`, `game_player_advanced`. Counted games and scopes come from 26a's helpers.
- Scopes `all`, each phase, and `PS`, as for the team tables.
- `gold_etl/main.py` support: `-tb player_round_stats` (part of `-tb all`), `--list-tables`, `--dry-run`, and `--quality-only` (fresh derivation equality, plus API warnings).
- A cross-check of each scope's final-round row against `season_player_stats_traditional` and `_advanced` (mode `accumulated`), reported as warnings with a tolerance found from the data.
- Documentation and a local backfill of every loaded EuroLeague season.

## Out of scope

- PER (27b) and Win Shares (27c); team ratings and standings tables (26, 28); lineups and on/off (29); play-by-play possessions (19).
- Per-36 and per-game averages beyond Game Score, percentile ranks, qualification thresholds (consumers filter on minutes), and career or cross-season totals.
- Neon publishing and allowlist changes (30g); any change to Silver, Bronze, or existing Gold tables.

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; no step commits are required. `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Register the table; appearances and cumulative totals.** Add `player_round_stats` to `gold_etl/schema.py` (`ROUND_NAMES`, merged into `GOLD_TABLES`, not in `DERIVED_NAMES`). In `gold_etl/player_rounds.py`, join each counted team game to its player rows (side from the entry's `home` flag), keep appearances with `seconds_played > 0`, and build per scope the rows from a player's first appearance on, with carried-forward idle rounds, latest club and name, games, starts, seconds and cumulative box-score totals. *Done when:* tests cover the `all`, phase and `PS` scopes, DNP rows (`seconds_played` 0) not counted, idle rounds carried, a player who changes club (club is the latest, totals span both), missing values propagating to NULL, uncounted games skipped, and `python -m unittest discover -s gold_etl/tests` passes.
- [x] **Step 2 - Rates, per-100, Game Score and PIE.** Add the rate, per-100, possession, Game Score and PIE columns as ratios of sums over the player's appearances (formulas below). *Done when:* tests check every formula against a hand-worked two-game example (one with a different team and opponent per game), NULL on missing inputs and zero denominators, that a one-game row equals feature 25's per-game value for the columns that do not depend on the minutes share (TS%, eFG%, TOV%, Game Score; see Notes), and that PIE across all players of one game sums to 1.
- [x] **Step 3 - Storage, CLI and quality.** Reuse the aggregate loader/quality pattern for `player_round_stats`: atomic season-slice replace, dry run, and `--quality-only` fresh-derivation equality. *Done when:* fake-connection tests show scoped delete, insert, rollback on failure, dry-run read-only behavior and mismatch detection; `python gold_etl/main.py -sc E2025 -tb player_round_stats --dry-run` prints a row count; the neon_publish allowlist test still shows 26 tables.
- [x] **Step 4 - API cross-check.** First inspect the API `accumulated` player feeds against our final rows (which phases `all` covers, how `games_played` and minutes are counted, percent versus fraction, which rates match and which use other definitions), then record the findings in the data dictionary. Implement the comparison with the tolerance the data supports, as warnings printed by `--quality-only`. *Done when:* tests cover match, mismatch beyond tolerance, missing API row and a scope without a feed; `python gold_etl/main.py -sc all -tb player_round_stats --quality-only` runs and reports the remaining differences by season, scope and metric.
- [x] **Step 5 - Document, backfill, verify.** Update `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`. Run all declared test suites, build every loaded EuroLeague season, run `--quality-only`, report row counts and build time, and hand-check one player's rows in one season. *Done when:* docs match behavior, tests pass, the table exists for every season, and quality reports no error.

## Files / areas

- `gold_etl/schema.py`, `gold_etl/player_rounds.py` (new), `gold_etl/team_rounds.py` (small reuse if needed), `gold_etl/loader.py`, `gold_etl/quality.py`, `gold_etl/main.py`
- `gold_etl/tests/test_player_rounds.py` (new)
- `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`

## Data / contracts

- Key: `competition_code`, `season_code`, `scope`, `round_number`, `person_key`. A player has a row for every scope round from their first appearance on; rounds they did not play carry the previous cumulative values. `club_code` and `player_name` are the values from the player's latest appearance in the scope through that round. Transfers do not split rows.
- An appearance is a `game_player_stats` row in a counted game (26a's definition: played, full team box score for both sides) with `seconds_played > 0`; `games_played` counts appearances and `games_started` counts appearances with `started` true. Step 4 confirms this against the API's `games_played` and records the result.
- Stored cumulative totals: `seconds_played`, `points`, `field_goals_made`, `field_goals_attempted`, `three_pointers_made`, `three_pointers_attempted`, `free_throws_made`, `free_throws_attempted`, `offensive_rebounds`, `defensive_rebounds`, `total_rebounds`, `assists`, `steals`, `turnovers`, `blocks`, `fouls_committed`, `pir`. One missing value in a game makes that total (and every rate that uses it) NULL from then on.
- Per game `g`, with `s` = the player's seconds, `T` = game seconds (`game_minutes` x 60, a team's minutes divided by 5, so `s/T` is the fraction of the game the player was on court), team and opponent totals and the game's `possessions`, rates are ratios of sums over appearances (fractions, `NUMERIC`, 6 places, NULL on zero denominator):
  - `ts_pct` = PTS / (2 x (FGA + 0.44 FTA)); `efg_pct` = (FGM + 0.5 x 3PM) / FGA.
  - `usg_pct` = sum(used_g x T_g) / sum(s_g x team_used_g), `used` = FGA + 0.44 FTA + TOV.
  - `ast_pct` = sum(AST) / sum(s/T x team FGM - FGM).
  - `orb_pct`, `drb_pct`, `trb_pct` = sum(rebounds) / sum(s/T x (team + opponent rebounds of that type, the opponent's other type for ORB/DRB as in feature 25)).
  - `stl_pct` = sum(STL) / sum(s/T x possessions); `blk_pct` = sum(BLK) / sum(s/T x opponent two-point attempts); `tov_pct` = sum(TOV) / sum(used).
  - `possessions_played` = sum(s/T x possessions); `*_per_100` (`points`, `rebounds`, `assists`, `steals`, `blocks`, `turnovers`) = 100 x sum(stat) / `possessions_played`.
  - `game_score_total` = sum of `silver.game_player_advanced.game_score` over appearances; `game_score_average` = total / games.
  - `pie` = sum(player numerator) / sum(game numerator), numerator = PTS + FGM + FTM - FGA - FTA + DREB + OREB/2 + AST + STL + BLK/2 - PF - TOV, game numerator = the sum of both teams' `total` rows in that game.
- The season slice is replaced atomically; a rerun gives identical rows. Reads Silver only; no Neon, no network.

## Testing

- Focused unit tests: `python -m unittest gold_etl.tests.test_player_rounds`, with in-memory games and fake cursors.
- Regression suites: `python -m unittest discover -s gold_etl/tests`; `python -m unittest discover -s postgres_etl/tests`; `cd api_requests && python -m unittest tests.test_scrapper`; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Local checks: `python gold_etl/main.py -sc all -tb player_round_stats`, then `--quality-only`. No combined Verify command is declared; no Neon call is made.

## Notes for the AI

- Follow `gold_etl/team_rounds.py`, `team_ratings.py` and `team_splits.py`, including the shared `read_tables` reader (extend it or add a player reader, but keep one place) and the `ROUND_NAMES` dispatch in the loader, quality and `main.py`; keep the table out of `DERIVED_NAMES`.
- Build each player's rows by walking their sorted appearances once per scope, not by rescanning all games per round. Accumulate numerators and denominators, and divide when emitting each row.
- Reuse feature 25's formulas (`postgres_etl/advanced.py`); restate constants locally with a test tying the one-game row to the per-game value, as 26a did.
- Feature 25's player rates that use the minutes share (`usage_pct`, `assist_pct`, `orb_pct`, `drb_pct`, `trb_pct`, `steal_pct`, `block_pct` in `silver.game_player_advanced`) use `seconds / game seconds` where the standard forms use `5 x seconds / team seconds`, so they are wrong (usage is 5x too large). 27a computes them correctly (its rebound rates agree with the API); the Silver columns need a separate `/fix`.
- Season row volume is about 30k rows in a full season; measure the build time in Step 5 and index nothing extra unless it is slow.
- Update `gold_etl/tests/test_gold.py` list-tables expectations only through `ROUND_NAMES`.

## Open questions

Non-blocking; the defaults above apply unless changed at review.

- One row per player per scope-round, keyed by `person_key` with the latest club as an attribute (approved by the owner at the 27 split).
- Rates are ratios of sums, so a transferred player's rates blend both teams' contexts.
- `per-100` uses estimated player possessions (minutes share of the team's game possessions), not counted possessions; feature 19 may add counted values later.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":10390,"specSha256":"5c5cfe1d20672c7cd2c9ae9ce1aced86f35c7e45dddbe8b582a705bce1bf8c1d","branch":"refs/heads/feature/cumulative-player-round-stats","head":"5bfe62ef2314b37a86eefed9ea0fa3528a6b374c","baseRef":"refs/heads/main","baseCommit":"5bfe62ef2314b37a86eefed9ea0fa3528a6b374c","sourceTree":"7727daf5a9272e9c4e7de92df4df37e6459421b7","absentOptional":[]} -->

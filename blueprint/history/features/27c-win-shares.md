# Feature: Win Shares

**From build-plan:** feature 27c
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/win-shares`

## Goal

Build `gold.player_round_win_shares`: for every season, scope and round, one row per player with offensive, defensive and total Win Shares and Win Shares per 48 minutes, cumulative through that round, using Basketball-Reference's marginal offense and marginal defense method. It completes feature 27 next to `player_round_stats` (27a) and `player_round_ratings` (27b) and follows their one-table-per-enrichment pattern.

## In scope

- One new local Gold table, `player_round_win_shares`, registered in `ROUND_NAMES` (outside `DERIVED_NAMES`, so the Neon allowlist stays 26 tables).
- A derivation module `gold_etl/player_win_shares.py` reading only Silver through the shared readers (`read_tables`, `_counted_games`, `_scopes`) and `silver.game_player_stats`. Scopes `all`, each phase, `PS`, as in 27a and 27b.
- `gold_etl/main.py` support: `-tb player_round_win_shares` (part of `-tb all`), `--list-tables`, `--dry-run`, `--quality-only` (fresh-derivation equality plus a league-total check that reports warnings).
- Documentation and a local backfill of every loaded EuroLeague season.

## Out of scope

- Any change to `player_round_stats`, `player_round_ratings`, Silver or Bronze; Neon publishing and the allowlist (30g).
- An API cross-check (the API player feeds have no Win Shares), per-game or per-36 values, career values, and qualification thresholds.
- Season-level BBRef features that do not exist in the data (for example minutes-based bonuses); only the standard OWS/DWS method below.

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Register the table; accumulate context; offensive Win Shares.** Add `player_round_win_shares` to `gold_etl/schema.py` (`ROUND_NAMES`, merged into `GOLD_TABLES`). In `gold_etl/player_win_shares.py`, walk each player's counted appearances (seconds > 0) per scope as 27a and 27b do, accumulating the player's totals plus the own-club and opponent totals, possessions and minutes of the games the player played, and compute league sums per scope round. Implement `off_win_shares` (formulas below).
  *Done when:* tests check every intermediate (`qAST`, `FG_Part`, `AST_Part`, `FT_Part`, `ScPoss`, `TotPoss`, `PProd`) and `off_win_shares` against a float hand-worked example with two teams and at least three players, plus NULL on a missing input and the documented zero-denominator cases; `python -m unittest gold_etl.tests.test_player_win_shares` passes.
- [x] **Step 2 - Defensive and total Win Shares.** Add `def_win_shares` (stops, Stop%, defensive rating, marginal defense), `win_shares` and `win_shares_per_48`.
  *Done when:* tests check `Stops1`, `Stops2`, `Stop%`, `DRtg`, `def_win_shares`, the sum, and WS/48 against the hand-worked example, including a mid-scope transfer, an idle round that carries values but uses that round's league constants, and a zero-minute-share edge; the gold suite passes.
- [x] **Step 3 - Storage, CLI and quality.** Reuse the round-table loader and quality pattern: atomic season-slice replace, dry run, `--quality-only` fresh-derivation equality, and league-total warnings: per scope round, the sum of `win_shares` over all players against the number of counted games (each game has one win), reported as `WARN` when they differ by more than a tolerance found from the data and recorded in the data dictionary.
  *Done when:* fake-connection tests show scoped delete, insert, rollback on failure, dry-run read-only behavior, mismatch detection and both branches of the league-total warning; `python gold_etl/main.py -sc E2025 -tb player_round_win_shares --dry-run` prints a row count; the neon_publish allowlist test still shows 26 tables.
- [x] **Step 4 - Document, backfill, verify.** Update `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`. Run all declared test suites, build every loaded EuroLeague season, run `--quality-only`, report row counts, build time and how closely league Win Shares total the games, and hand-check one player's final row in one season (a star's WS/48 should be about 0.2 or more, a typical rotation player about 0.1).
  *Done when:* docs match behavior, tests pass, the table exists for every season and quality reports no error.

## Files / areas

- `gold_etl/schema.py`, `gold_etl/player_win_shares.py` (new), `gold_etl/loader.py`, `gold_etl/quality.py`, `gold_etl/main.py`
- `gold_etl/tests/test_player_win_shares.py` (new), small updates to `gold_etl/tests/test_gold.py` list-tables expectations through `ROUND_NAMES` if needed
- `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`

## Data / contracts

- Key: `competition_code`, `season_code`, `scope`, `round_number`, `person_key`; same row set as `player_round_stats`. Columns: `club_code`, `player_name` (latest appearance), `games_played`, `seconds_played`, `off_win_shares`, `def_win_shares`, `win_shares`, `win_shares_per_48` (`NUMERIC`, 6 places, NULL when an input is missing or a denominator is zero).
- Inputs are cumulative through the round. Player totals: MP (minutes = seconds / 60), PTS, FG, FGA, 3P, FT, FTA, ORB, DRB, AST, STL, BLK, TOV, PF. Summed over the games the player played, each with that game's own club: club totals `Tm*` (same names, plus `Tm MP` = 5 x game minutes, `Tm Poss` = game possessions) and opponent totals `Opp*`. League: `lgPTS` (both clubs of every counted game), `lgPoss`, `lgPace` (as in 27b, 40 x possessions / minutes over club rows) and `lgG` (club rows, that is two per game). `Tm Pace` = 40 x sum(Tm Poss) / sum(game minutes) over the player's games.
- Zero-denominator rule: a ratio inside a bracketed term whose numerator or multiplier is a zero count (`FT/FTA` and `(PTS - FT) / (2 x FGA)` for a player with no attempts, `(Tm FG - FG)` and `(Tm FGA - FGA)` when the player had every team attempt, `Tm FT/Tm FTA`, `Opp FT/Opp FTA` when there are none) contributes 0. Any other zero denominator, and any missing input, gives NULL.
- Offense (Basketball-Reference): `qAST = (MP / (Tm MP / 5)) x (1.14 x (Tm AST - AST) / Tm FG) + (((Tm AST / Tm MP) x MP x 5 - AST) / ((Tm FG / Tm MP) x MP x 5 - FG)) x (1 - MP / (Tm MP / 5))`; `FG_Part = FG x (1 - 0.5 x ((PTS - FT) / (2 x FGA)) x qAST)`; `AST_Part = 0.5 x (((Tm PTS - Tm FT) - (PTS - FT)) / (2 x (Tm FGA - FGA))) x AST`; `FT_Part = (1 - (1 - FT/FTA)^2) x 0.4 x FTA`; `Team_Scoring_Poss = Tm FG + (1 - (1 - Tm FT/Tm FTA)^2) x Tm FTA x 0.4`; `Team_ORB% = Tm ORB / (Tm ORB + (Opp TRB - Opp ORB))`; `Team_Play% = Team_Scoring_Poss / (Tm FGA + Tm FTA x 0.4 + Tm TOV)`; `Team_ORB_Weight = ((1 - Team_ORB%) x Team_Play%) / ((1 - Team_ORB%) x Team_Play% + Team_ORB% x (1 - Team_Play%))`; `ORB_Part = ORB x Team_ORB_Weight x Team_Play%`; `ScPoss = (FG_Part + AST_Part + FT_Part) x (1 - (Tm ORB / Team_Scoring_Poss) x Team_ORB_Weight x Team_Play%) + ORB_Part`; `FGxPoss = (FGA - FG) x (1 - 1.07 x Team_ORB%)`; `FTxPoss = (1 - FT/FTA)^2 x 0.4 x FTA`; `TotPoss = ScPoss + FGxPoss + FTxPoss + TOV`; `PProd_FG_Part = 2 x (FG + 0.5 x 3P) x (1 - 0.5 x ((PTS - FT) / (2 x FGA)) x qAST)`; `PProd_AST_Part = 2 x ((Tm FG - FG + 0.5 x (Tm 3P - 3P)) / (Tm FG - FG)) x 0.5 x (((Tm PTS - Tm FT) - (PTS - FT)) / (2 x (Tm FGA - FGA))) x AST`; `PProd_ORB_Part = ORB x Team_ORB_Weight x Team_Play% x (Tm PTS / (Tm FG + (1 - (1 - Tm FT/Tm FTA)^2) x 0.4 x Tm FTA))`; `PProd = (PProd_FG_Part + PProd_AST_Part + FT) x (1 - (Tm ORB / Team_Scoring_Poss) x Team_ORB_Weight x Team_Play%) + PProd_ORB_Part`; `marginal_offense = PProd - 0.92 x (lgPTS / lgPoss) x TotPoss`; `marginal_ppw = 0.32 x (lgPTS / lgG) x (Tm Pace / lgPace)`; `off_win_shares = marginal_offense / marginal_ppw`.
- Defense: `DOR% = Opp ORB / (Opp ORB + Tm DRB)`; `DFG% = Opp FG / Opp FGA`; `FMwt = (DFG% x (1 - DOR%)) / (DFG% x (1 - DOR%) + (1 - DFG%) x DOR%)`; `Stops1 = STL + BLK x FMwt x (1 - 1.07 x DOR%) + DRB x (1 - FMwt)`; `Stops2 = (((Opp FGA - Opp FG - Tm BLK) / Tm MP) x FMwt x (1 - 1.07 x DOR%) + (Opp TOV - Tm STL) / Tm MP) x MP + (PF / Tm PF) x 0.4 x Opp FTA x (1 - Opp FT/Opp FTA)^2`; `Stops = Stops1 + Stops2`; `Stop% = Stops x Tm MP / (Tm Poss x MP)`; `Team_DRtg = 100 x Opp PTS / Tm Poss`; `D_Pts_per_ScPoss = Opp PTS / (Opp FG + (1 - (1 - Opp FT/Opp FTA)^2) x Opp FTA x 0.4)`; `DRtg = Team_DRtg + 0.2 x (100 x D_Pts_per_ScPoss x (1 - Stop%) - Team_DRtg)`; `marginal_defense = (MP / Tm MP) x Tm Poss x (1.08 x (lgPTS / lgPoss) - DRtg / 100)`; `def_win_shares = marginal_defense / marginal_ppw`.
- `win_shares = off_win_shares + def_win_shares`; `win_shares_per_48 = win_shares x 48 / MP`.
- The season slice is replaced atomically; a rerun gives identical rows. Reads Silver only; no Neon, no network.

## Testing

- Focused: `python -m unittest gold_etl.tests.test_player_win_shares`, with in-memory games and fake cursors; the expected values are written out separately from the implementation (float arithmetic in the test).
- Regression suites: `python -m unittest discover -s gold_etl/tests`; `python -m unittest discover -s postgres_etl/tests`; `cd api_requests && python -m unittest tests.test_scrapper`; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Local checks: `python gold_etl/main.py -sc all -tb player_round_win_shares`, then `--quality-only`. No combined Verify command is declared; no Neon call is made.

## Notes for the AI

- Follow `gold_etl/player_ratings.py` closely (27b): the appearance walk, additive sums per appearance, league sums by prefix over rounds, and the fetch-player-rows-before-`read_tables` ordering in `read_rows` (the shared cursor is reused, so fetching after `read_tables` returns the wrong result set; 27b hit exactly this). Reuse its helpers where sharing is cheap.
- Use `Decimal` for stored values as the other round tables do; the formulas are long, so build them from small named intermediates that tests can check one by one.
- Early rounds have few games, so constants and Win Shares are noisy; expected and documented, not filtered. Win Shares can be negative.
- `PLAYER_TOTALS` names match the club `total` rows used by 26a; reuse them.

## Open questions

Non-blocking; the defaults above apply unless changed at review.

- Team and opponent context comes from the games the player played, not the club's full-season totals (as in 27b), so values differ slightly from Basketball-Reference for players who missed games.
- Zero-denominator terms inside brackets contribute 0 (see the rule above); this keeps players with no free throws or field goal attempts from being NULL.
- There is no API reference for Win Shares. Correctness rests on the hand-worked tests and the league-total warning, whose tolerance is set from the data in Step 4 (set to 15% for rounds with at least 30 games; E2000-E2026 range 0.90-1.07 of the games, median 1.03).


<!-- blueprint:completion {"schemaVersion":1,"specBytes":11061,"specSha256":"06f094f5ffabfbbc7d32c249a98b648e2aef6b82166f067db2c6c3f9d400e5c5","branch":"refs/heads/feature/win-shares","head":"fd87736e792f1ca98a955c83adef13f500786e05","baseRef":"refs/heads/main","baseCommit":"fd87736e792f1ca98a955c83adef13f500786e05","sourceTree":"69eae7d40d0a01e93b0a1b1424b4acd979e6a5ad","absentOptional":[]} -->

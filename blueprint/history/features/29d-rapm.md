# Feature: RAPM

**From build-plan:** feature 29d
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/rapm`

## Goal

Build `gold.player_rapm`: regularized adjusted plus-minus per player and season (E2007 onward), with separate offensive and defensive coefficients, from the lineup stints of 29b. It is the last item of feature 29.

## In scope

- One local Gold table `player_rapm`, key `(competition_code, season_code, scope, person_key)`; `scope` is `all` (every game of the season). Columns: `player_name`, `seconds` (on-court seconds in stored stints), `possessions_offense`, `possessions_defense` (counted possessions the player was on court for), `penalty` (the ridge penalty chosen for the season), `offense`, `defense`, `rapm` (= offense + defense), in points per 100 possessions relative to an average player. A positive `defense` means fewer points allowed.
- Model: every stint row with possessions is one observation, `points_for / possessions_for * 100`, weighted by `possessions_for`, explained by an intercept, +1 for each of the five offensive players' offense coefficient and -1 for each of the five defenders' defense coefficient. Ridge penalty on all coefficients (not the intercept) with the penalty chosen per season by 5-fold cross-validation over a fixed grid, folds made of whole games; the strongest penalty within 0.01% of the no-player error of the best one is taken, because stint outcomes are noisy and the errors are nearly flat. Small samples are kept: the penalty shrinks them toward zero and their possessions are stored.
- The linear algebra uses numpy, imported inside the solver so nothing else in Gold depends on it; a missing numpy stops only this table with a clear message. numpy is already installed in the local environment; it is not added to any install step because the project declares none.
- Built by `gold_etl/rapm.py` (`derive_rows`, `read_rows`), registered in `ROUND_NAMES`, the loader dispatch and the CLI; local only, outside the Neon allowlist until 30g.
- Documentation and a local backfill of E2007-E2026.

## Out of scope

- Per-phase or per-round RAPM, multi-season priors, box-score priors, confidence intervals, and Neon publishing.
- A `possessions >= N` filter or ranking columns.

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Solver and derivation.** `gold_etl/rapm.py` with a ridge solver (normal equations built from the sparse ten-entry rows, eigendecomposition per fold), season derivation, schema entry, loader dispatch.
  *Done when:* unit tests on synthetic seasons with planted effects cover: recovery of a planted offensive and a planted defensive effect with the right signs, shrinkage growing with the penalty, the penalty chosen from the grid and stored, whole-game folds, empty and zero-possession input, ordering, registration, storage and the missing-numpy message; `python -m unittest discover -s gold_etl/tests` passes.
- [x] **Step 2 - Validate on real data, document, backfill.** Backfill E2007-E2026, compare with on/off, run `--quality-only`, write the method and observed results in the data dictionary and docs.
  *Done when:* the table exists for every loaded season, `--quality-only` passes, the chosen penalties, run time and the correlation of RAPM with `net_rating_diff` are recorded, and all declared suites pass.

## Files / areas

- `gold_etl/rapm.py` (new), `gold_etl/schema.py`, `gold_etl/loader.py`, `gold_etl/tests/test_rapm.py` (new).
- `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`.

## Data / contracts

- Input: `silver.game_team_lineup_stints`, `silver.game_player_stats` (names), `silver.games` (played games).
- Output: one season slice replaced atomically per run. Values are rounded to four decimals so a rerun reproduces them.

## Testing

- Unit tests on synthetic data with a seeded generator; fake-connection storage tests; real-data validation in step 2. No live Neon calls.

## Notes for the AI

- Reuse `gold_etl/team_pbp.read_silver` and the loader pattern of `player_on_off`. The web app is local-only, so schema changes are acceptable.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":4306,"specSha256":"df453dd5cf641d6875c2529e75d5b3bd3d708644c6053cc41dbed16d98c5765f","branch":"refs/heads/feature/rapm","head":"97fbeeffc3164e44983ca82ee4f82678a503a3da","baseRef":"refs/heads/main","baseCommit":"97fbeeffc3164e44983ca82ee4f82678a503a3da","sourceTree":"f8f2f97f96e7fca27fa1afa415598e1fafa8fd19","absentOptional":[]} -->

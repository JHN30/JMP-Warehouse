# Feature: Strength-Adjusted Team Ratings

**From build-plan:** feature 26b
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/strength-adjusted-team-ratings`

## Goal

Add `gold.team_round_ratings`: for every season, scope and round, one row per club with its league-relative ratings, SRS, SOS, SOV and opponent-adjusted offensive, defensive and net ratings, all cumulative through that round. It uses the same key and rows as feature 26a's `team_round_stats` and is the base for the standings stats page (28).

## In scope

- One new local Gold table, `team_round_ratings`, registered beside `team_round_stats` (`ROUND_NAMES`), outside the Neon allowlist.
- A derivation module `gold_etl/team_ratings.py` reading the same Silver inputs as 26a (`games`, `game_team_stats` totals, `game_team_advanced`), reusing 26a's counted-game and scope logic.
- League averages and relative ratings per scope and round; SRS, SOS and SOV; adjusted offensive, defensive and net ratings (definitions below), all through one small pure-Python linear solver (no new dependency).
- `gold_etl/main.py` support: `-tb team_round_ratings` (part of `-tb all`), `--list-tables`, `--dry-run`, and `--quality-only` (fresh derivation equality plus invariant checks).
- Documentation and a local backfill of every loaded EuroLeague season.

## Out of scope

- Home/away splits and rolling windows (26c); player stats (27); the standings stats page table (28); Neon publishing and allowlist changes (30g).
- Home-court adjustment, margin caps, regression to the mean, and any fitted model (BPM, win probability).
- Any change to Silver, Bronze, `team_round_stats`, or existing Gold tables.

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; no step commits are required. `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Register the table; graph, league and relative ratings.** Add `team_round_ratings` to `gold_etl/schema.py` (`ROUND_NAMES`, merged into `GOLD_TABLES`, not in `DERIVED_NAMES`). In `gold_etl/team_ratings.py`, build for every scope and round the cumulative game list (both sides, opponent, points, possessions, minutes), the club set, and league offensive rating, league pace, `relative_offensive_rating`, `relative_defensive_rating`, `relative_pace`. *Done when:* tests with fake seasons cover key/row parity with `team_round_stats` for the same input, league values from a hand-worked example, carry-forward rounds, and the `all`, phase and `PS` scopes; `python -m unittest discover -s gold_etl/tests` passes.
- [x] **Step 2 - SRS, SOS, SOV.** Add a Gaussian-elimination solver and solve, per scope and round, `(L + 11ᵀ/N) r = m` (definitions below). NULL for every club of a scope-round whose game graph is not connected. *Done when:* tests check a hand-solved three-club example, `sum(srs) = 0`, `sos = srs - mov`, `sov` NULL for a club without wins, and NULL results for a disconnected graph (two separate pairs), and ±margin/2 for a single game between two clubs.
- [x] **Step 3 - Adjusted ratings.** Add possession-weighted `adj_offensive_rating`, `adj_defensive_rating`, `adj_net_rating` from the linear systems below. *Done when:* tests check `adj_offensive_rating - adj_defensive_rating = adj_net_rating`, possession-weighted mean adjusted net 0 and possession-weighted mean adjusted offense and defense equal to the league rating, hand-computed values for the three-club example, NULL offense/defense (net still defined) for a bipartite graph such as a single game, and NULL for a disconnected graph.
- [x] **Step 4 - Storage, CLI and quality.** Reuse the aggregate loader/quality pattern for `team_round_ratings`: replace the season slice atomically, dry run, and `--quality-only` that compares a fresh derivation with stored rows and also reports as errors any connected scope-round whose `srs` sum or possession-weighted `adj_net_rating` mean differs from 0 by more than 1e-4. *Done when:* fake-connection tests show scoped delete, insert, rollback on failure, dry-run read-only behavior, mismatch and invariant detection; `python gold_etl/main.py -sc E2025 -tb team_round_ratings --dry-run` prints a row count; the neon_publish allowlist test still shows 26 tables.
- [x] **Step 5 - Document, backfill, verify.** Update `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`. Run all declared test suites, build every loaded EuroLeague season, run `--quality-only`, report build time, and hand-check one club's SRS in one season (for example the final RS round). *Done when:* docs match behavior, tests pass, the table exists for every season, and quality reports no error.

## Files / areas

- `gold_etl/schema.py`, `gold_etl/team_ratings.py` (new), `gold_etl/team_rounds.py` (small reuse), `gold_etl/loader.py`, `gold_etl/quality.py`, `gold_etl/main.py`
- `gold_etl/tests/test_team_ratings.py` (new)
- `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`

## Data / contracts

- Key: `competition_code`, `season_code`, `scope`, `round_number`, `club_code`; same rows as `team_round_stats` (a club from its first counted game on, earlier rounds carried forward). Counted games as in 26a (played, full box score for both sides).
- Per scope-round, with N clubs that have played: `n_i` = club i's games; `n_ij` = games between i and j; `m_i` = sum of i's game margins; `P_ij` = sum of shared possessions of games between i and j.
- League values (columns `league_offensive_rating`, `league_pace`): `100 x total points / total possessions` and `40 x total possessions / total minutes`, both counting each game once per side. `relative_*` = club value minus league value; relative net equals net rating, so it is not stored.
- `srs`: solve `(L + 11ᵀ/N) r = m`, where `L_ii = n_i`, `L_ij = -n_ij`; equivalent to `r_i = MOV_i + mean of opponents' r` with `sum(r) = 0`. `sos` = mean over i's games of the opponent's `srs` (= `srs - mov`). `sov` = mean opponent `srs` over games i won, NULL without wins.
- Adjusted ratings (possession-weighted, per 100 possessions), with net `d_i = 100 x (PF_i - PA_i) / P_i` and `T_i = 100 x (PF_i + PA_i) / P_i` cumulative for club i, weights `w_ij = P_ij / sum_j P_ij` and league rating `L`: `adj_net` solves `a_i = d_i + sum_j w_ij a_j` with the possession-weighted mean of `a` equal to 0 (weights `P_i / sum P`); the total `t_i = adj_offensive + adj_defensive` solves `t_i + sum_j w_ij t_j = T_i + 2L`; then `adj_offensive_rating = (t + a) / 2`, `adj_defensive_rating = (t - a) / 2`. When the game graph is bipartite (for example after one round) the second system is singular: offense and defense cannot be separated, so those two columns are NULL while `adj_net_rating` stays defined.
- Graph not connected (some club cannot reach another through played games) or fewer than 2 clubs: `srs`, `sos`, `sov` and the three adjusted columns are NULL for that scope-round; `connected BOOLEAN NOT NULL` records which. Relative and league columns never depend on connectivity. Values are `NUMERIC` rounded to 6 places; NULL when an input is missing.
- The season slice is replaced atomically; a rerun gives identical rows. Reads Silver only; no Neon, no network.

## Testing

- Focused unit tests: `python -m unittest gold_etl.tests.test_team_ratings`, with in-memory games and fake cursors.
- Regression suites: `python -m unittest discover -s gold_etl/tests`; `python -m unittest discover -s postgres_etl/tests`; `cd api_requests && python -m unittest tests.test_scrapper`; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Local checks: `python gold_etl/main.py -sc all -tb team_round_ratings`, then `--quality-only`. No combined Verify command is declared; no Neon call is made.

## Notes for the AI

- Follow `gold_etl/team_rounds.py` and its tests, storage, and quality wiring; extend the same dispatch points (`ROUND_NAMES`, `read_aggregate_rows`) rather than adding new branches to `main.py` where the aggregate branch already covers it.
- Keep the table out of `DERIVED_NAMES`. Update `gold_etl/tests/test_gold.py` `--list-tables` expectations only through `ROUND_NAMES`.
- Use floats inside the solver and quantize to Decimal at the end; sort clubs by code so a rerun is deterministic.
- Do not introduce numpy or another dependency; the systems are at most about 25 x 25.
- Measure build time in Step 5; if a season takes more than a few minutes, cache the per-scope game list instead of rebuilding it per round.

## Open questions

Non-blocking; the defaults above apply unless changed at review.

- SRS method: plain per-game margin, no home-court or margin cap, solved exactly rather than by iteration.
- Adjusted ratings are possession-weighted least-squares (no ridge), NULL when the graph is disconnected. Playoff-only scopes (`PI`, `PO`, `FF`, `PS`) are mostly disconnected and will mostly be NULL; `all` and `RS` carry the ratings.
- Adjusted offense and defense are NULL in bipartite scope-rounds (RS rounds 1-2), adjusted net is not; SRS needs only connectivity.
- A separate table rather than new columns on `team_round_stats`, because Gold tables have no add-column migration.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":9285,"specSha256":"6d32cb3a9ba2413c01139f0624e17b4950701c25ad409610a4d0bc9d1faa297b","branch":"refs/heads/feature/strength-adjusted-team-ratings","head":"95b478b90b7a7b59da5577021fa8d51a0a2316bd","baseRef":"refs/heads/main","baseCommit":"95b478b90b7a7b59da5577021fa8d51a0a2316bd","sourceTree":"3015b4c10077d1471879f3de8fb5ac50999eb65b","absentOptional":[]} -->

# Feature: Lineup Ratings

**From build-plan:** feature 29c
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/lineup-ratings`

## Goal

Build `gold.lineup_ratings`: for every club and scope, the 2-man, 3-man and 5-man combinations of players that shared the floor, with their time, possessions, points and ratings, from the lineup stints of 29b. Possessions are stored instead of filtering small samples; consumers filter, as with PER.

## In scope

- One local Gold table `lineup_ratings`, key `(competition_code, season_code, scope, club_code, lineup_size, lineup)`, scopes `all`, each phase and `PS` (as `player_on_off`). `lineup` is the sorted `person_key`s joined by commas; `lineup_names` the player names in the same order joined by `; `. Columns: `games` (games in which the group played together), `seconds`, `possessions_for`, `possessions_against`, `points_for`, `points_against` (sums over the stints where all of the group's players were on court), `ortg`, `drtg`, `net_rating` (points per 100 possessions, NULL without possessions).
- Built by `gold_etl/lineup_ratings.py` (`derive_rows` pure, `read_rows`) from `silver.game_team_lineup_stints` and `game_player_stats` (names), registered in `ROUND_NAMES`, the loader dispatch and the CLI; local only, outside the Neon allowlist until 30g.
- A quality invariant: per club and scope, the 5-man rows add up to the club's stint totals and the 2-man and 3-man rows each add up to ten times the 5-man totals for every summed column (each stint holds ten pairs and ten triples).
- Documentation and a local backfill of E2007-E2026.

## Out of scope

- Opponent-adjusted lineup ratings and RAPM (29d); 4-man lineups; a minimum-possessions filter; per-round ratings; Neon publishing.

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Derive, register and store.** `gold_etl/lineup_ratings.py`, the schema entry, loader dispatch, the invariant check and CLI dispatch.
  *Done when:* unit tests cover pair, triple and five-player rows from hand-built stints, sums over stints, games counted once per game, ratings and NULLs, phase and `PS` scopes, separate clubs, ordering and registration, storage, the missing-table message and the invariant check; `python -m unittest discover -s gold_etl.tests` passes.
- [x] **Step 2 - Validate on real data, document, backfill.** Backfill E2007-E2026, run the quality check, hand-check one lineup, update the docs.
  *Done when:* the table exists for every loaded season, `--quality-only` passes, the row counts and one hand check are written in the data dictionary, and all declared suites pass.

## Files / areas

- `gold_etl/lineup_ratings.py` (new), `gold_etl/schema.py`, `gold_etl/loader.py`, `gold_etl/quality.py`, `gold_etl/main.py`, `gold_etl/tests/test_lineup_ratings.py` (new).
- `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`.

## Data / contracts

- Input: `silver.game_team_lineup_stints` (`players` comma-joined, both teams complete), `silver.game_player_stats` (names), `silver.games` (phase).
- Output: one season slice replaced atomically per run.

## Testing

- Unit tests on hand-built stints; fake-connection storage tests; real-data validation in step 2. No live Neon calls.

## Notes for the AI

- Reuse `gold_etl/player_on_off.py` rating helpers and `gold_etl/team_pbp.read_silver`. The web app is local-only, so schema changes are acceptable.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":3608,"specSha256":"873fc6ba0c2d5fe440a248396dfe811729cb4770fc39edd8bcbda5e75cc6e69d","branch":"refs/heads/feature/lineup-ratings","head":"647d841fc0b065ca35ea027ffb7d653cfa76fcfa","baseRef":"refs/heads/main","baseCommit":"647d841fc0b065ca35ea027ffb7d653cfa76fcfa","sourceTree":"92be00c6aba6d5d5e855e1dd271be40847c06e87","absentOptional":[]} -->

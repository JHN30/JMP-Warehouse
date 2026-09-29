# Feature: Lineup Stints and On/Off

**From build-plan:** feature 29b
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/lineup-stints-and-on-off`

## Goal

Build `silver.game_team_lineup_stints` (five-man stints with time, possessions and points for every played game with play-by-play, E2007 onward) and `gold.player_on_off` (per-player on and off ratings per season and scope). It builds on the on-court reconstruction of 29a and is the base of the lineup ratings (29c) and RAPM (29d).

## In scope

- Silver: a derived table `game_team_lineup_stints`, key `(game_code, side, stint_ordinal)`, two rows (one per team) per stint with `players` and `opponent_players` (sorted `person_key`s joined by commas), `start_seconds`, `end_seconds`, `possessions_for`, `possessions_against`, `points_for`, `points_against`. Built by `postgres_etl/lineups.py` with the same substitution walk as 29a; run after Silver loads of `games`, `game_player_stats` or `play_by_play`.
- Only stints in which both teams have exactly five players are stored. Possessions come from 19a's counted possession state machine (each counted possession is attributed to the stint on court at its closing event); points come from the running score. Events are attributed by event order, not by clock, so a substitution between two free throws at one clock time is handled.
- A quality check: fresh-derivation equality (ERROR) and a WARN for team-games whose stored stints cover less than 95% of the game's minutes.
- Gold: `gold.player_on_off` (`gold_etl/player_on_off.py`), key `(competition_code, season_code, scope, club_code, person_key)`, scopes `all`, each phase and `PS`. On sums (seconds, possessions for and against, points for and against), off sums (the club's other stints in the scope), on and off ratings per 100 possessions, and on-minus-off differences. Local only, outside the Neon allowlist until 30g.
- A Gold quality invariant: per club and scope every player's on plus off is the same team total and the players' on-court seconds are five times the team's.
- Documentation and a local backfill of E2007-E2026.

## Out of scope

- Lineup, 2/3-man ratings (29c) and RAPM (29d); per-round on/off; Neon publishing.
- Repairing incomplete lineups: their stints are left out and counted in the WARN.

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Stint walk and Silver storage.** `postgres_etl/lineups.py`, a `_count(..., ends=None)` hook in `possessions.py` that reports the event closing each possession, the table in `flat_schema.py`, the `main.py` hook and the quality check.
  *Done when:* unit tests cover a game without substitutions, a swap, mirrored rows, IN before OUT at one instant, a lineup returning to the same five, period carry and overtime, an incomplete lineup left out, a dropped zero-length stint, storage, checks and hook wiring; `python -m unittest discover -s postgres_etl/tests` passes and the load tests never touch the database.
- [x] **Step 2 - Gold on/off.** `gold_etl/player_on_off.py`, the schema entry, loader dispatch, `check_on_off_totals` and the `main.py` quality dispatch.
  *Done when:* unit tests cover on and off sums, ratings, a player always on court, phase and `PS` scopes, clubs, the invariants, storage and a missing-table message; `python -m unittest discover -s gold_etl/tests` passes.
- [x] **Step 3 - Validate on real data, document, backfill.** Backfill E2007-E2026 for both tables, compare with the box score, hand-check, update the docs.
  *Done when:* both tables exist for every loaded season, `--quality-only` passes for both with warnings only for the documented gaps, the observed agreement is written in the data dictionary, and all declared suites pass.

## Files / areas

- `postgres_etl/lineups.py` (new), `postgres_etl/possessions.py`, `postgres_etl/flat_schema.py`, `postgres_etl/main.py`, `gold_etl/player_on_off.py` (new), `gold_etl/schema.py`, `gold_etl/loader.py`, `gold_etl/quality.py`, `gold_etl/main.py`, `gold_etl/team_pbp.py` (source list), tests under `postgres_etl/tests/` and `gold_etl/tests/`.
- `docs/DATA_DICTIONARY.md`, `README.md`, `postgres_etl/README.md`, `gold_etl/README.md`, `AGENTS.md`.

## Data / contracts

- Input: `silver.games`, `silver.game_player_stats` (`started`), `silver.play_by_play`; Gold reads `game_team_lineup_stints` and `game_player_stats` (name).
- Output: see In scope. Ratings are points per 100 possessions, rounded to six decimals; a rating with no possessions is NULL, and the off ratings and differences of a player who never sat are NULL.

## Testing

- Unit tests on hand-built events and rows; fake-connection storage tests; real-data validation in step 3. No live Neon calls.

## Notes for the AI

- Fetch rows before reusing a cursor. The web app is local-only, so schema changes are acceptable. This spec was written while building, so its steps are already checked.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":5090,"specSha256":"e19396ff74179a48d0a5d2dcb44212486bf317f7088fea3dffa179a05c919c10","branch":"refs/heads/feature/lineup-stints-and-on-off","head":"74a4df278e56b7d821eb8be4903c99e2c685226b","baseRef":"refs/heads/main","baseCommit":"74a4df278e56b7d821eb8be4903c99e2c685226b","sourceTree":"dd4606607f719d7953927dd89088de00e02f2b2e","absentOptional":[]} -->

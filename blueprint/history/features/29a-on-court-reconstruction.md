# Feature: On-Court Reconstruction

**From build-plan:** feature 29a
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/on-court-reconstruction`

## Goal

Build `silver.game_player_on_court`: for every played game with play-by-play (E2007 onward), one row per player and continuous stretch on the floor, rebuilt from the box-score starters and the `IN`/`OUT` substitution events. It is the base for the lineup stints, on/off ratings, lineup ratings and RAPM of 29b-29d, and follows the per-game derived Silver pattern of feature 19 (`possessions.py` runner).

## In scope

- One derived Silver table `game_player_on_court`, key `(game_code, side, person_key, interval_ordinal)`, columns `club_code`, `start_seconds`, `end_seconds` (elapsed game seconds, integers), registered in `ADVANCED_TABLES`, built by a new module `postgres_etl/on_court.py` (pure `derive_rows`, `read_rows`, season replace, quality check, `run_seasons`, CLI) that reuses the shared runner of `possessions.py`. Run after Silver loads of `games`, `game_player_stats` or `play_by_play`.
- Reconstruction rules: a side starts with the players whose `started` flag is true; `IN` adds and `OUT` removes a player, in event order (period rank, overtime number, `event_ordinal`); players carry across periods; everyone still on court closes at the game end (2400 s plus 300 s per overtime). A substitution whose clock is missing or outside the period (older seasons log period-start substitutions at times such as `11:00`) is placed at the period start. An `IN` for a player already on court and an `OUT` for one who is not are ignored and counted.
- Validation against the box score: on-court seconds per player against `game_player_stats.seconds_played`, reported by the quality check as `WARN` when they differ by more than 120 seconds (older box scores have minute precision), with the observed distribution recorded in the data dictionary.
- Documentation and a local backfill of every loaded EuroLeague season with play-by-play.

## Out of scope

- Lineup stints, on/off, possessions and points (29b), lineup ratings (29c), RAPM (29d), Gold, and Neon.
- Repairing games whose substitution log is incomplete; they are flagged, not fixed. 29b decides how to treat them.
- Seasons before E2007 (no play-by-play).

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Pure reconstruction and table registration.** In `postgres_etl/on_court.py`, build `derive_rows(games, players, events)` with the rules above and register the table in `flat_schema.py`.
  *Done when:* unit tests over hand-built games cover: starters only, a simple swap, a same-instant `IN` before `OUT`, carry-over across a period, an overtime end, a period-start substitution with an out-of-range clock, a duplicate `IN`, an `OUT` for a player not on court, an unplayed game and a game without play-by-play; `python -m unittest postgres_etl.tests.test_on_court` passes.
- [x] **Step 2 - Storage, CLI, hook and quality check.** Reuse `possessions.py`'s season replace, runner and CLI; read `games`, `game_player_stats` and `play_by_play`; hook `run_on_court` into `postgres_etl/main.py` after the other derived tables; the check compares stored rows with a fresh derivation (ERROR) and reports players off the box-score seconds by more than 120 s (WARN).
  *Done when:* fake-connection tests show scoped delete, insert, rollback, dry-run read-only behavior and mismatch detection; `python postgres_etl/on_court.py -sc E2025 --dry-run` prints a row count; the load tests never touch the real database; the existing `postgres_etl` suite passes.
- [x] **Step 3 - Validate on real data, document, backfill.** Backfill E2007-E2026, record per-season agreement with `seconds_played` and the count of games with a player beyond 120 s, hand-check one game, and update `docs/DATA_DICTIONARY.md`, `README.md`, `postgres_etl/README.md` and `AGENTS.md`.
  *Done when:* the table exists for every loaded season E2007-E2026, `--quality-only` passes with warnings only for the documented gaps, all declared suites pass.

## Files / areas

- `postgres_etl/on_court.py` (new), `postgres_etl/flat_schema.py`, `postgres_etl/main.py`, `postgres_etl/tests/test_on_court.py` (new), `postgres_etl/tests/` load tests that patch the post-load hooks.
- `docs/DATA_DICTIONARY.md`, `README.md`, `postgres_etl/README.md`, `AGENTS.md`.

## Data / contracts

- Input: `silver.games` (`played`, club codes), `silver.game_player_stats` (`side`, `person_key`, `club_code`, `started`, `seconds_played`), `silver.play_by_play` (`IN`/`OUT` events; `person_code` equals `person_key`).
- Output: `silver.game_player_on_court`, one season slice replaced atomically per run; `interval_ordinal` counts a player's stretches from 1 in time order; intervals of zero length are dropped.
- Prototype on E2007-E2026 (119,331 player-games): mean absolute difference from `seconds_played` 7.1 s; within 120 s for 98-100% per season (E2007-E2010 have minute-precision box scores); 245 of 5,049 games have a player beyond 120 s.

## Testing

- Unit tests on hand-built events; fake-connection storage tests; real-data validation in step 3. No live Neon calls.

## Notes for the AI

- Fetch rows before reusing a cursor (`read_tables` gotcha). Do not change the existing derived tables. The web app is local-only, so schema changes are acceptable.
- Found while validating: every game's play-by-play ends with `EG`/`EP` events with no clock and a minute past the last overtime, so counting overtimes from all extra-time events overstated the game end by 300 seconds in 236 overtime games. `possessions._game_end` counts overtimes from events with a clock; `on_court.py` and `score_flow.py` (feature 19b, which had this defect) use it, and the score-flow season slices and `gold.team_pbp_stats` were rebuilt. Regression tests cover both modules.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":6043,"specSha256":"34a7f18bb104f13102763d6e174184d5eaa6d53cacf66ff98df692cf52dd53e4","branch":"refs/heads/feature/on-court-reconstruction","head":"b5a1ad6993d126088afb5afd9f56a2c2725467f6","baseRef":"refs/heads/main","baseCommit":"b5a1ad6993d126088afb5afd9f56a2c2725467f6","sourceTree":"f69156d1e7447ed4cff15169e03e1deab5ce7223","absentOptional":[]} -->

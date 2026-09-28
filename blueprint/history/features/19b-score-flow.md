# Feature: Score Flow

**From build-plan:** feature 19b
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/score-flow`

## Goal

Build `silver.game_team_score_flow`: for every played game with play-by-play (E2007 onward), one row per team with lead changes, ties, time leading, trailing and tied, largest lead, scoring runs and clutch results derived from the running score in the event stream. It is the second of four play-by-play items and reuses 19a's event ordering, clock and storage pattern.

## In scope

- One new derived Silver table, `game_team_score_flow`, registered beside `game_team_possessions` in `postgres_etl/flat_schema.py` and built by a new module `postgres_etl/score_flow.py` (pure `derive_rows`, `read_rows`, quality check, CLI) run after Silver loads next to `possessions.py`.
- Small generalizations in `postgres_etl/possessions.py` so both modules share one replace, stored-row check and season runner instead of copying them (the table name and the row, replace and check functions become parameters; behavior and names used by 19a's tests stay).
- The score flow rules below, over the running score in `play_by_play` and 19a's ordering and clock helpers.
- Quality: stored rows equal a fresh derivation; a warning when a game's event-derived final score differs from `games.local_score` and `road_score`.
- Documentation and a local backfill of every loaded EuroLeague season with play-by-play.

## Out of scope

- Possessions (19a, unchanged apart from the shared-runner refactor); shot-based splits (19c); Gold aggregates (19d); lineups (29).
- Player-level score flow, momentum models, win probability, and Neon publishing.
- Games or seasons without play-by-play (before E2007) get no rows.

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Share the runner; register the table.** Generalize `possessions.py`'s `replace_season`, stored-row comparison and `run_seasons`/`main` so a table name and its `read_rows`, `replace` and `check` functions are parameters, keeping every existing name and default so 19a behaves the same; register `game_team_score_flow` in `flat_schema.py`.
  *Done when:* the existing `test_possessions` and the whole `postgres_etl` suite pass unchanged, and `postgres_etl/possessions.py -sc E2025 --dry-run` still prints the same row count as before.
- [x] **Step 2 - Score flow derivation (pure).** In `postgres_etl/score_flow.py`, walk each game's ordered events, keep the running score, and compute the columns below per side.
  *Done when:* unit tests over hand-built score sequences cover: lead changes (through a tie and directly), ties, time leading/trailing/tied summing to the game length (including overtime), largest lead, longest run and the count of runs of 6 or more points (a run broken by an opponent score, a run across a period boundary), clutch seconds and clutch points (a game within five at five minutes left, one that is not, and overtime), a missing clock making the time columns NULL while counts stay, a `None` running-score value carried forward, and a game with no scoring events; `python -m unittest postgres_etl.tests.test_score_flow` passes.
- [x] **Step 3 - Storage, CLI, quality, hook.** Wire `score_flow.py` to the shared runner: season replace, `--dry-run`, `--quality-only` (fresh derivation equality plus the final-score warning), and the post-load hook in `postgres_etl/main.py` after `run_possessions`.
  *Done when:* tests show scoped delete, insert, rollback, dry-run read-only behavior, mismatch detection and the hook (run after a load of `games` or `play_by_play`, skipped for dry run, quality-only and unrelated tables); `python postgres_etl/score_flow.py -sc E2025 --dry-run` prints a row count.
- [x] **Step 4 - Validate on real data, document, backfill.** Backfill E2007-E2026, compare event-derived final scores with `games`, check that leading + trailing + tied time equals the game length, inspect any large disagreement and refine a rule only for a systematic cause, and hand-check one game. Update `docs/DATA_DICTIONARY.md`, `README.md`, `postgres_etl/README.md`, `AGENTS.md`.
  *Done when:* the table exists for every loaded season E2007-E2026, `--quality-only` passes with only recorded warnings, the observed agreement and the final rules are in the data dictionary, all declared suites pass, and one game is hand-checked against its events.

## Files / areas

- `postgres_etl/score_flow.py` (new), `postgres_etl/possessions.py`, `postgres_etl/flat_schema.py`, `postgres_etl/main.py`
- `postgres_etl/tests/test_score_flow.py` (new), `postgres_etl/tests/test_possessions.py` (only if the refactor needs it)
- `docs/DATA_DICTIONARY.md`, `README.md`, `postgres_etl/README.md`, `AGENTS.md`

## Data / contracts

- Table `silver.game_team_score_flow`: key `competition_code`, `season_code`, `game_code`, `side`; columns `club_code`, `opponent_club_code`, `points_for`, `points_against` (final event-derived score, `INTEGER`), `lead_changes`, `ties` (`INTEGER`, the same on both rows), `time_leading_seconds`, `time_trailing_seconds`, `time_tied_seconds` (`NUMERIC`), `largest_lead`, `longest_run`, `runs_6_plus` (`INTEGER`), `clutch_seconds` (`NUMERIC`, the same on both rows), `clutch_points_for`, `clutch_points_against` (`INTEGER`), plus `load_id` and `loaded_at`. NULL time columns mean a scoring event had no usable clock; counts and points never depend on the clock.
- Score: `play_by_play.points_a` is the local team's running score and `points_b` the road team's, present on scoring events; a `None` value keeps the previous value (the first score of a game shows `None` for the team that has not scored). Events are ordered as in 19a (period rank, overtime number, `event_ordinal`); elapsed seconds come from 19a's clock helper. Every event with a non-`None` score field updates the score.
- Lead change: the leading team differs from the last team that led (a tie in between does not count as a change by itself). A tie: the score becomes level at a non-zero score. Time is measured between consecutive score changes, from 0 to the game length (2400 plus 300 per overtime seen in the events); the margin is constant between them. Largest lead: the biggest own margin over the game (0 when never ahead). A run: consecutive points by one team with no opponent score; `longest_run` is the largest such total for the team and `runs_6_plus` counts runs of at least 6 (`RUN_MINIMUM`). An event that changes both scores is treated as a break in every run.
- Clutch: the last five minutes of regulation and all of overtime (elapsed at or after 2100 seconds) while the margin before the event or interval is at most 5 points (`CLUTCH_MARGIN`); `clutch_seconds` counts those intervals, and clutch points are the points each team scores during them.
- The season slice is replaced atomically; a rerun gives identical rows. Reads Silver only; no Neon, no network.

## Testing

- Focused: `python -m unittest discover -s postgres_etl/tests -p test_score_flow.py`, with in-memory event lists and fake cursors.
- Regression suites: `python -m unittest discover -s postgres_etl/tests`; `python -m unittest discover -s gold_etl/tests`; `cd api_requests && python -m unittest tests.test_scrapper`; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Local checks: `python postgres_etl/score_flow.py -sc 2007-2026`, then `--quality-only`. No combined Verify command is declared; no Neon call is made.

## Notes for the AI

- Import ordering, clock and period helpers from `postgres_etl/possessions.py` rather than copying them; the storage, check and CLI code becomes shared in Step 1, so `score_flow.py` stays small.
- Use the running score fields, not a tally of made shots: they cover every event type. Validate against `games.local_score` and `road_score`.
- Keep the walk a pure function over sorted event dicts for tests. Do not add configuration or dependencies.
- Step 4 is an inspection step: print distributions and the largest disagreements; change a rule only for a systematic, explainable cause, and record final rules and observed agreement in the data dictionary.

## Open questions

Non-blocking; the defaults above apply unless changed at review.

- Clutch uses the common definition (last five minutes, margin within five) applied to 40-minute games; the constants are named so they can change.
- A "run" is any unanswered scoring streak, not limited by clock time; runs of 6 or more are counted (`RUN_MINIMUM`).
- Games whose feed lacks a running score, or whose event-derived final score differs from `games`, are kept and flagged by the warning, not repaired.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":8839,"specSha256":"95aca0b3b0e064e735ce50a0e4af751a02160d21960cd31d17f4d59af422c20a","branch":"refs/heads/feature/score-flow","head":"f8865f86a482162e26d044dc8a5badffe2d207c4","baseRef":"refs/heads/main","baseCommit":"f8865f86a482162e26d044dc8a5badffe2d207c4","sourceTree":"c0727e3a78993df58465791735aafa584ce78565","absentOptional":[]} -->

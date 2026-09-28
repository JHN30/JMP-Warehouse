# Feature: Home/Away and Rolling Team Stats

**From build-plan:** feature 26c
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/home-away-and-rolling-team-stats`

## Goal

Add `gold.team_round_splits`: for every season, scope and round, one row per club with its home and away splits and its last-5 and last-10 game windows, all through that round. It shares the key and rows of `team_round_stats` (26a) and `team_round_ratings` (26b) and completes feature 26.

## In scope

- One new local Gold table, `team_round_splits`, registered beside the other round tables (`ROUND_NAMES`), outside the Neon allowlist.
- A derivation module `gold_etl/team_splits.py` reading the same Silver inputs and counted games as 26a, reusing its scope and round logic.
- Four groups of measures per row: `home` (games where the club was the `local` side), `away` (`road`), `last5` and `last10` (the club's most recent 5 and 10 counted games in the scope through the round).
- Per group: games, wins, MOV, offensive, defensive and net rating, pace.
- `gold_etl/main.py` support: `-tb team_round_splits` (part of `-tb all`), `--list-tables`, `--dry-run`, `--quality-only` (fresh derivation equality plus consistency checks against `team_round_stats`).
- Documentation and a local backfill of every loaded EuroLeague season.

## Out of scope

- Other split dimensions (by phase inside `all`, opponent quality, rest days, margin), other window sizes, and per-group four factors.
- Opponent-adjusted or league-relative split ratings (26b covers adjusted ratings on the cumulative table).
- Neon publishing and allowlist changes (30g); the standings stats page table (28); player stats (27).
- Any change to Silver, Bronze, or the two existing round tables' columns.

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; no step commits are required. `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Register the table and derive home/away splits.** Add `team_round_splits` to `gold_etl/schema.py` (`ROUND_NAMES`, merged into `GOLD_TABLES`, not in `DERIVED_NAMES`). Extend 26a's counted-game entries with `home` and `game_code` (a small change in `gold_etl/team_rounds.py`). Implement `gold_etl/team_splits.py` producing the key, carry-forward rows and the `home_*` and `away_*` groups. *Done when:* tests cover key/row parity with `team_round_stats` for the same input, a club with no home game yet (games 0, wins 0, other measures NULL), venue assignment from the `local`/`road` side, the `all`, phase and `PS` scopes, and hand-worked values; `python -m unittest discover -s gold_etl/tests` passes, including the existing 26a tests.
- [x] **Step 2 - Rolling windows.** Add `last5_*` and `last10_*` groups from the club's most recent counted games in the scope, ordered by `round_number` then `game_code`, with the actual game count stored. *Done when:* tests cover a club with fewer games than the window (all its games, count shown), exactly N games, more than N (oldest dropped, hand-checked totals), two games in one round, carried-forward idle rounds (window unchanged), and NULL propagation when an input is missing.
- [x] **Step 3 - Storage, CLI and quality.** Reuse the aggregate loader/quality pattern for `team_round_splits`. `--quality-only` compares a fresh derivation with stored rows and reports as errors: `home_games + away_games` not equal to `team_round_stats.games_played`, home plus away wins not equal to `wins`, and a `last10_*` or `last5_*` value that differs from the cumulative `team_round_stats` value while the club has no more games than the window. *Done when:* fake-connection tests show scoped delete, insert, rollback on failure, dry-run read-only behavior, mismatch and consistency detection; `python gold_etl/main.py -sc E2025 -tb team_round_splits --dry-run` prints a row count; the neon_publish allowlist test still shows 26 tables.
- [x] **Step 4 - Document, backfill, verify.** Update `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`. Run all declared test suites, build every loaded EuroLeague season, run `--quality-only`, and hand-check one club's home/away and last-5 rows in one season. *Done when:* docs match behavior, tests pass, the table exists for every season, and quality reports no error. `/complete` then checks 26c and, with 26a-b already done, its parent line 26.

## Files / areas

- `gold_etl/schema.py`, `gold_etl/team_splits.py` (new), `gold_etl/team_rounds.py` (entry fields), `gold_etl/loader.py`, `gold_etl/quality.py`, `gold_etl/main.py`
- `gold_etl/tests/test_team_splits.py` (new)
- `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`

## Data / contracts

- Key: `competition_code`, `season_code`, `scope`, `round_number`, `club_code`; identical rows to `team_round_stats` (a club from its first counted game on; idle rounds carry the previous values). Counted games as in 26a.
- Venue: `home` is the game's `local` side, `away` the `road` side, as stored in `silver.games`. Neutral-site games (for example the Final Four) keep the source designation; the data dictionary says so.
- Window order: a club's counted games in the scope with `round_number` up to the current round, sorted by `round_number` then `game_code`; the last N of them. `last5_games` and `last10_games` hold the actual count (fewer than N early in a scope).
- For each group `g` in `home`, `away`, `last5`, `last10`: `g_games` (INTEGER NOT NULL), `g_wins` (INTEGER NOT NULL), `g_mov` = (points for - against) / games, `g_offensive_rating` = 100 x points for / possessions, `g_defensive_rating` = 100 x points against / possessions, `g_net_rating` = difference, `g_pace` = 40 x possessions / minutes (possessions and minutes from `game_team_advanced`). `NUMERIC`, 6 places, NULL when the group has no games or an input is missing. Wins use `silver.games.match_winner_club_code`.
- The season slice is replaced atomically; a rerun gives identical rows. Reads Silver only; no Neon, no network.

## Testing

- Focused unit tests: `python -m unittest gold_etl.tests.test_team_splits`, with in-memory games and fake cursors.
- Regression suites: `python -m unittest discover -s gold_etl/tests`; `python -m unittest discover -s postgres_etl/tests`; `cd api_requests && python -m unittest tests.test_scrapper`; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Local checks: `python gold_etl/main.py -sc all -tb team_round_splits`, then `--quality-only`. No combined Verify command is declared; no Neon call is made.

## Notes for the AI

- Follow `gold_etl/team_ratings.py` and `gold_etl/team_rounds.py`, including the shared `read_tables` reader and the `ROUND_NAMES` dispatch in the loader, quality and `main.py`; keep the table out of `DERIVED_NAMES`.
- Keep the window sizes as named constants (`WINDOWS = (5, 10)`) so column names and code stay in step; do not add configuration.
- Compute per club by walking its sorted games once per scope, not by rescanning all games per round.
- Update `gold_etl/tests/test_gold.py` list-tables expectations only through `ROUND_NAMES`.

## Open questions

Non-blocking; the defaults above apply unless changed at review.

- Window sizes 5 and 10 games.
- Whether Final Four games should count as home/away; the default keeps the source's local/road designation.
- A separate table rather than new columns, for the same reason as 26b (no Gold add-column migration).


<!-- blueprint:completion {"schemaVersion":1,"specBytes":7571,"specSha256":"584ed1937629637ed90cc5567680ea973a63f2b904ee3f9349441fd38b7d5bb9","branch":"refs/heads/feature/home-away-and-rolling-team-stats","head":"e999db9900c3eb432dddd893dba83808391beb1f","baseRef":"refs/heads/main","baseCommit":"e999db9900c3eb432dddd893dba83808391beb1f","sourceTree":"53759d2d6b3ded0f887e5ab73181bb678157c65e","absentOptional":[]} -->

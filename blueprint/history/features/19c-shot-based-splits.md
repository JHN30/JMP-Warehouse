# Feature: Shot-Based Splits

**From build-plan:** feature 19c
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/shot-based-splits`

## Goal

Build two derived Silver tables from the shots and play-by-play feeds (E2007 onward): `game_team_shot_splits`, one row per team and game with fast-break, second-chance and off-turnover points and assisted field goals, and `game_team_shot_zones`, one row per team, game and shot zone with attempts, makes and points. They are the third of four play-by-play items, follow 19a and 19b's pattern and share their storage runner.

## In scope

- `game_team_shot_splits` and `game_team_shot_zones`, registered beside the other derived tables in `postgres_etl/flat_schema.py`, built by two small modules `postgres_etl/shot_splits.py` and `postgres_etl/shot_zones.py` (pure `derive_rows`, `read_rows`, quality check, CLI) that reuse `possessions.py`'s shared replace, stored-row comparison and season runner and its event ordering helpers, and run after Silver loads next to the other derived tables.
- The rules below over `silver.shots` (flags, points, zone, action code) and `silver.play_by_play` (assists, made field goals).
- Quality: stored rows equal a fresh derivation; warnings where assisted field goals exceed made field goals or where points in the shots table differ from `games` scores.
- Documentation, including what the shot-zone codes look like in the data, and a local backfill of every loaded EuroLeague season.

## Out of scope

- Possessions (19a) and score flow (19b), unchanged; Gold aggregates (19d); lineups (29).
- Player-level splits, shot charts, shot quality models, and inventing names for the zone codes (only observed properties are documented).
- Neon publishing; seasons before E2007 (no shots or play-by-play).

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Shot splits and assisted field goals (pure).** Register `game_team_shot_splits` and write `postgres_etl/shot_splits.py`'s `derive_rows` over shots and play-by-play events.
  *Done when:* unit tests cover: the three point splits summing the points of flagged made shots including free throws, a shot with several flags counted in each, NULL point splits for a game where any shot has a NULL flag (older seasons) while assisted counts stay, assists counted whatever their clock or order (the feed logs assists at other clock times than their shots), assists capped at the made field goals and kept per club, layup and dunk made types counting as field goals, and `assisted_fg_pct` NULL with no made shots; `python -m unittest discover -s postgres_etl/tests -p test_shot_splits.py` passes.
- [x] **Step 2 - Shot zones (pure).** Register `game_team_shot_zones` and write `postgres_etl/shot_zones.py`'s `derive_rows`.
  *Done when:* unit tests cover attempts, makes and points per zone for both teams, free throws and empty or NULL zones excluded, a zone with only misses, both sides' rows for a zone one of them never shot from being absent (no zero rows), and stable ordering; its tests pass.
- [x] **Step 3 - Storage, CLI, quality, hooks.** Wire both modules to the shared runner (season replace, `--dry-run`, `--quality-only` with fresh-derivation equality and the warnings above) and hook them into `postgres_etl/main.py` after `run_score_flow`; keep the load tests isolated from the hooks.
  *Done when:* tests show scoped delete, insert, rollback, dry-run read-only behavior, mismatch detection and the hooks (run after a load of `games`, `play_by_play` or `shots`, skipped for dry run, quality-only and unrelated tables) for both tables; `python postgres_etl/shot_splits.py -sc E2025 --dry-run` and `python postgres_etl/shot_zones.py -sc E2025 --dry-run` print row counts.
- [x] **Step 4 - Validate on real data, document, backfill.** Backfill E2007-E2026, compare the flagged points and assisted counts with the box score and `games`, check which seasons have flags, describe each zone code by its observed coordinates and three-point share, hand-check one game, and update `docs/DATA_DICTIONARY.md`, `README.md`, `postgres_etl/README.md` and `AGENTS.md`.
  *Done when:* both tables exist for every loaded season E2007-E2026, `--quality-only` passes with only recorded warnings, the season coverage of the flags, the observed agreement and the zone descriptions are in the data dictionary, all declared suites pass, and one game is hand-checked against its events.

## Files / areas

- `postgres_etl/shot_splits.py` (new), `postgres_etl/shot_zones.py` (new), `postgres_etl/flat_schema.py`, `postgres_etl/main.py`
- `postgres_etl/tests/test_shot_splits.py` (new), `postgres_etl/tests/test_shot_zones.py` (new), plus the hook isolation in the existing main-wiring tests
- `docs/DATA_DICTIONARY.md`, `README.md`, `postgres_etl/README.md`, `AGENTS.md`

## Data / contracts

- `silver.game_team_shot_splits`: key `competition_code`, `season_code`, `game_code`, `side`; columns `club_code`, `opponent_club_code`, `fast_break_points`, `second_chance_points`, `points_off_turnover_points` (`INTEGER`), `field_goals_made`, `assisted_field_goals` (`INTEGER`, from play-by-play), `assisted_fg_pct` (`NUMERIC`, `assisted_field_goals / field_goals_made`), plus `load_id` and `loaded_at`. The point splits are NULL for a game in which any shot has a NULL `fastbreak`, `second_chance` or `points_off_turnover` flag (all of E2016 onward have flags; older seasons mostly do not).
- Point splits: for each team, the sum of `points` over its made shots (`points > 0`, free throws included, since the flags also mark free throws) whose flag is true; a shot with several flags counts in each split. The shots table has one row per made shot and per missed field goal; `club_code` gives the team and the game's local/road clubs give the side.
- Assisted field goals: made field goals are `2FGM`, `3FGM`, `LAYUPMD` and `DUNK` play-by-play events (19a's `MADE`); assists are `AS` events. The assisted count per team is the number of its `AS` events, capped at its made field goals. Pairing an assist with its shot by period and clock was tried first and undercounted badly (assists are logged at other clock times than their shots, sometimes much later); the `AS` count equals the box score's assists in 99.5% of team games (Step 4).
- `silver.game_team_shot_zones`: key `competition_code`, `season_code`, `game_code`, `side`, `zone`; columns `club_code`, `attempts`, `made`, `points` (`INTEGER`), plus `load_id` and `loaded_at`. Field goals only (`2FGM`, `3FGM`, `LAYUPMD`, `DUNK` made and `2FGA`, `3FGA`, `LAYUPATT`, `2FGAB`, `3FGAB` missed, the same shot types as 19a; E2008-E2014 use the layup, dunk and blocked types); attempts count made and missed. Rows with an empty or NULL `zone` (free throws and unlabeled shots) are left out, and a team gets a row only for zones it shot from.
- The season slices are replaced atomically; a rerun gives identical rows. Reads Silver only; no Neon, no network.

## Testing

- Focused: `python -m unittest discover -s postgres_etl/tests -p test_shot_splits.py` and `-p test_shot_zones.py`, with in-memory rows and fake cursors.
- Regression suites: `python -m unittest discover -s postgres_etl/tests`; `python -m unittest discover -s gold_etl/tests`; `cd api_requests && python -m unittest tests.test_scrapper`; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Local checks: `python postgres_etl/shot_splits.py -sc 2007-2026` and `python postgres_etl/shot_zones.py -sc 2007-2026`, then `--quality-only` for each. No combined Verify command is declared; no Neon call is made.

## Notes for the AI

- Follow `postgres_etl/score_flow.py` exactly for the module shape: it imports the shared replace, run, main and stored-row helpers from `possessions.py`. The shared `differences_from_derivation` keys rows by `(game_code, side)`; the zones table has a third key part, so either extend that helper to take the key columns (keeping the default) or add the zone to its key argument. Do not copy the runner.
- Run every command from the project root; the test commands use `discover -s postgres_etl/tests` so the tests can import each other.
- Existing main-wiring tests patch the derived-table hooks (`run_advanced`, `run_possessions`, `run_score_flow`) so a load test never touches the database; patch the two new hooks in the same places (`test_advanced.py`, `test_possessions.py`, `test_score_flow.py`, `test_quality.py`).
- Do not name or interpret zone codes beyond what the data shows (mean court coordinates and three-point share per code, computed in Step 4).
- Step 4 is an inspection step: print distributions and the largest disagreements, and change a rule only for a systematic, explainable cause; record final rules and observed agreement in the data dictionary.

## Open questions

Non-blocking; the defaults above apply unless changed at review.

- Two tables (a wide per-game table and a long per-zone table) rather than one wide table with a column per zone; the zone codes are the feed's own letters.
- Point splits include free throws because the feed flags them; "points off turnovers" therefore includes the free throws that follow.
- Older seasons' NULL flags give NULL splits rather than estimates.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":9433,"specSha256":"6f2edf4d993dbfd0f597455e3771ab47272d4fe846e6a1e7637564dc572c966f","branch":"refs/heads/feature/shot-based-splits","head":"703e9e0c33b8e7469b2d04bbac02591d9867bb2f","baseRef":"refs/heads/main","baseCommit":"703e9e0c33b8e7469b2d04bbac02591d9867bb2f","sourceTree":"6599ce5f941c7dfa5c758def88776d16c57abd44","absentOptional":[]} -->

# Feature: Counted Possessions

**From build-plan:** feature 19a
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/counted-possessions`

## Goal

Build `silver.game_team_possessions`: for every played game with play-by-play (E2007 onward), one row per team with its counted possessions and possession lengths derived from the event stream, kept next to the box-score estimate from `game_team_advanced` and never replacing it. It is the first of four play-by-play items (19a possessions, 19b score flow, 19c shot-based splits, 19d Gold aggregates) and follows feature 25's pattern for per-game derived Silver tables.

## In scope

- One new derived Silver table, `game_team_possessions`, registered beside `ADVANCED_TABLES` in `postgres_etl/flat_schema.py`, built by a new module `postgres_etl/possessions.py` (pure `derive_rows`, `read_rows`, atomic season replace, quality check, `run_seasons`, CLI) and run after Silver loads like `advanced.py` (`python postgres_etl/possessions.py -sc <seasons>`, `--dry-run`, `--quality-only`).
- A possession state machine over `silver.play_by_play` (rules below), the ordering and game-clock conversion it needs, and per-team counts and lengths.
- Comparison with the box-score estimate: a stored `estimated_possessions` copy and quality warnings, with a tolerance found from the data.
- Documentation and a local backfill of every loaded EuroLeague season with play-by-play.

## Out of scope

- Any change to `game_team_advanced` or its estimate, or to Gold; the ratings keep using the estimate.
- Lead changes, runs, clutch (19b); shot-based splits (19c); Gold aggregates (19d); lineups (29).
- Player-level possession counts, and Neon publishing.
- Games or seasons without play-by-play (before E2007) get no rows; nothing is estimated for them.

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Ordering, clock and the possession state machine (pure).** In `postgres_etl/possessions.py`, order a game's events and convert them to an elapsed game clock, then count possessions and lengths per side with the rules below. Register the table in `flat_schema.py` (`ADVANCED_TABLES`, so `ALL_TABLES` and the create/index SQL include it).
  *Done when:* unit tests over hand-built event streams cover: a made field goal, a miss with a defensive rebound, a miss with an offensive rebound (same possession continues), a turnover, an and-one, a two-shot trip ending on a made last shot, a trip whose last shot misses and is rebounded (both rebound types), a technical foul shot that does not end a possession, a period end that closes an open possession, an overtime clock, and missing clock values giving NULL lengths; `python -m unittest postgres_etl.tests.test_possessions` passes.
- [x] **Step 2 - Storage, CLI and quality wiring.** Reuse `advanced.py`'s season replace, `run_seasons` and CLI shape: read `play_by_play`, `games` and `game_team_advanced`, delete and insert the season slice atomically, hook `run_possessions` after `run_advanced` in `postgres_etl/main.py`, and add the stored-row check (fresh derivation equality).
  *Done when:* fake-connection tests show scoped delete, insert, rollback on failure, dry-run read-only behavior and mismatch detection; `python postgres_etl/possessions.py -sc E2025 --dry-run` prints a row count; the existing `postgres_etl` suite still passes.
- [x] **Step 3 - Validate on real data, refine, document, backfill.** Backfill E2007-E2026, compare counted possessions with `own_possessions_estimate` and the event counts with the box score (turnovers, made field goals and free throws), inspect the largest disagreements and refine the rules where the data shows a systematic cause, then set the quality-warning tolerance from the observed distribution. Update `docs/DATA_DICTIONARY.md`, `README.md`, `postgres_etl/README.md` and `AGENTS.md`.
  *Done when:* the table exists for every loaded season E2007-E2026, `--quality-only` passes with warnings only beyond the recorded tolerance, the observed agreement (mean and spread of counted minus estimated possessions, share of games within 3%) and the final rules are written in the data dictionary, all declared suites pass, and one game's possessions are hand-checked against its event stream.

## Files / areas

- `postgres_etl/possessions.py` (new), `postgres_etl/flat_schema.py`, `postgres_etl/main.py`
- `postgres_etl/tests/test_possessions.py` (new)
- `docs/DATA_DICTIONARY.md`, `README.md`, `postgres_etl/README.md`, `AGENTS.md`

## Data / contracts

- Table `silver.game_team_possessions`: key `competition_code`, `season_code`, `game_code`, `side` (`local` or `road`); columns `club_code`, `opponent_club_code`, `counted_possessions` (`INTEGER`), `possession_seconds` (`NUMERIC`, sum of counted possession lengths in game seconds), `avg_possession_seconds` (`NUMERIC`, `possession_seconds` over the possessions with a measurable length), `estimated_possessions` (`NUMERIC`, copied from `game_team_advanced.possessions`), plus the standard provenance columns `load_id`, `loaded_at` like feature 25's tables. NULL means an input was missing or a denominator was zero. Rows exist only for played games that have play-by-play events and a `game_team_advanced` row.
- Event order: by period rank then `event_ordinal` (which restarts each period). Period labels are `FirstQuarter`, `SecondQuarter`, `ThirdQuarter`, `ForthQuarter` (sic) and `ExtraTime`, which holds every overtime; the overtime number comes from `minute` (41-45 is the first overtime, then 46-50, and so on). `play_number` is not used for order (late corrections carry high numbers). `marker_time` is the time left in the period (`MM:SS`; 10:00 per quarter, 5:00 per overtime), converted to elapsed game seconds.
- Possession rules (defaults to refine in Step 3 from the data): a possession ends, and counts for the team that had it, on a made field goal, a turnover, a defensive rebound after a miss, the last made free throw of a trip, and the end of a period when one is still open. A missed field goal or last free throw followed by an offensive rebound continues the same possession. Free throws form a trip as consecutive free-throw events for one club ignoring substitutions, timeouts and fouls between them; technical free throws (after a technical or disqualifying foul event) neither end nor start a possession. An and-one (a free throw after a made field goal by the same club at the same clock) does not add a possession. Length is the elapsed time from the possession start (the previous possession's end, or the period start) to its end; missing clock values give a NULL length for that possession and are left out of the sum.
- The season slice is replaced atomically; a rerun gives identical rows. Reads Silver only; no Neon, no network.

## Testing

- Focused: `python -m unittest postgres_etl.tests.test_possessions`, with in-memory event lists and fake cursors.
- Regression suites: `python -m unittest discover -s postgres_etl/tests`; `python -m unittest discover -s gold_etl/tests`; `cd api_requests && python -m unittest tests.test_scrapper`; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Local checks: `python postgres_etl/possessions.py -sc 2007-2026`, then `--quality-only`. No combined Verify command is declared; no Neon call is made.

## Notes for the AI

- Follow `postgres_etl/advanced.py` for the module layout, the atomic replace, the derived-table registration, provenance columns and the `run_*` hook in `postgres_etl/main.py` (a table set that triggers it after a Silver load).
- Play-by-play events of one period are only ordered by `event_ordinal`, so sort explicitly; the raw row order is not chronological (period rows interleave). `club_code` on an event is the team credited with it; team rebounds may have no player.
- Keep the state machine a small pure function over sorted events so tests can feed it plain dicts. Do not add configuration or dependencies.
- Step 3 is an inspection step: print distributions, look at the worst games, and change a rule only for a systematic, explainable cause; record every final rule and the observed agreement in the data dictionary. Do not tune the rules until the numbers merely agree.
- The overview says counted possessions are kept next to the box-score estimate, never replacing it silently; do not touch `game_team_advanced`.

## Open questions

Non-blocking; the defaults above apply unless changed at review.

- The possession definition (above) is the common play-by-play convention; Step 3 may refine it from the data.
- Which possessions value the Gold ratings use once counted possessions exist stays a later decision (19d or a follow-up); 19a only stores the counted values.
- Games without a clock or with truncated event streams get partial counts; the quality warnings show them and they are not repaired.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":9070,"specSha256":"0efaae9c3a7f8b3460a106b8dd6e7001975f1942324465d853a97b4e368b4d2e","branch":"refs/heads/feature/counted-possessions","head":"48d774986d9954e6db32ae5970fb86a8475f27b2","baseRef":"refs/heads/main","baseCommit":"48d774986d9954e6db32ae5970fb86a8475f27b2","sourceTree":"364d46f382a4c900d8bdcc1908cdd83f385f6b6b","absentOptional":[]} -->

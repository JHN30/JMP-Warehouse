# Feature: Player Efficiency Rating

**From build-plan:** feature 27b
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/player-efficiency-rating`

## Goal

Build `gold.player_round_ratings`: for every season, scope and round, one row per player with Hollinger's PER (unadjusted, pace-adjusted and normalized to a league average of 15) cumulative through that round. League constants are computed per scope and round from the same counted games. It sits beside `player_round_stats` (27a) and follows the team `team_round_ratings` (26b) pattern of one table per enrichment.

## In scope

- One new local Gold table, `player_round_ratings`, registered in `ROUND_NAMES` (outside `DERIVED_NAMES`, so the Neon allowlist stays 26 tables).
- A derivation module `gold_etl/player_ratings.py` reading only Silver through the existing shared readers: counted games and scopes from `gold_etl/team_rounds.py`, players from `game_player_stats`. Same scopes as 27a: `all`, each phase, `PS`.
- `gold_etl/main.py` support: `-tb player_round_ratings` (part of `-tb all`), `--list-tables`, `--dry-run`, `--quality-only` (fresh-derivation equality plus a normalization invariant).
- Documentation and a local backfill of every loaded EuroLeague season.

## Out of scope

- Win Shares (27c); any change to `player_round_stats` (27a), Silver or Bronze; Neon publishing and allowlist changes (30g).
- An API cross-check: the API player feeds have no PER column, so PER is checked by construction and hand-worked tests only.
- Per-36 or per-game PER, qualification thresholds (consumers filter on minutes), and career or cross-season values.

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Register the table and derive PER.** Add `player_round_ratings` to `gold_etl/schema.py` (`ROUND_NAMES`, merged into `GOLD_TABLES`). In `gold_etl/player_ratings.py`, walk each player's counted appearances (seconds > 0) per scope as 27a does, accumulating player totals and the additive team-context sums of the games they played, and per scope and round compute the league constants, `uper`, `aper`, `per` (formulas below).
  *Done when:* tests check every constant and column against a hand-worked example with two teams and at least three players, including a mid-scope transfer, an idle round that carries values, NULL on a missing input or zero denominator, and that the minutes-weighted mean of `per` over a scope round is 15 within 0.0001 (the stored `per` is rounded to 6 places); `python -m unittest gold_etl.tests.test_player_ratings` passes.
- [x] **Step 2 - Storage, CLI and quality.** Reuse the round-table loader and quality pattern: atomic season-slice replace, dry run, `--quality-only` fresh-derivation equality, and an invariant check that for each scope and round the seconds-weighted mean of `per` is 15 (within 0.0001). Negative PER is legitimate for players with a few minutes, so it is not flagged (corrected during implementation).
  *Done when:* fake-connection tests show scoped delete, insert, rollback on failure, dry-run read-only behavior, mismatch detection and the invariant check catching a bad row; `python gold_etl/main.py -sc E2025 -tb player_round_ratings --dry-run` prints a row count; the neon_publish allowlist test still shows 26 tables.
- [x] **Step 3 - Document, backfill, verify.** Update `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`. Run the declared test suites, build every loaded EuroLeague season, run `--quality-only`, report row counts and build time, and hand-check one player's final row in one season (top PER values should be plausible for a star player and near 15 for a typical rotation player).
  *Done when:* docs match behavior, tests pass, the table exists for every season and quality reports no error.

## Files / areas

- `gold_etl/schema.py`, `gold_etl/player_ratings.py` (new), `gold_etl/loader.py`, `gold_etl/quality.py`, `gold_etl/main.py`
- `gold_etl/tests/test_player_ratings.py` (new), small updates to `gold_etl/tests/test_gold.py` list-tables expectations through `ROUND_NAMES`
- `docs/DATA_DICTIONARY.md`, `README.md`, `gold_etl/README.md`, `AGENTS.md`

## Data / contracts

- Key: `competition_code`, `season_code`, `scope`, `round_number`, `person_key`; same row set as `player_round_stats` (a row for every scope round from the player's first appearance on, idle rounds carry the previous appearances but use that round's league constants). Columns: `club_code`, `player_name` (latest appearance), `games_played`, `seconds_played`, `uper`, `aper`, `per` (`NUMERIC`, 6 places, NULL when an input is missing or a denominator is zero).
- League constants for a scope through round `r`, from the counted games' team `total` rows summed over both clubs of every game (`lg*`): `factor = 2/3 - (0.5 x lgAST/lgFGM) / (2 x lgFGM/lgFTM)`; `VOP = lgPTS / (lgFGA - lgORB + lgTOV + 0.44 x lgFTA)`; `DRB% = (lgTRB - lgORB) / lgTRB`; `lgPace = 40 x sum(game possessions over club rows) / sum(game minutes over club rows)`, the same pace definition as `team_round_stats`.
- Player context: over the games the player appeared in, each with that game's own club, `tmAST` and `tmFGM` are the summed club totals and `tmPace` is 40 x possessions / minutes over those games. This keeps a transferred player consistent and avoids a per-club lookup; it differs slightly from Basketball-Reference, which uses the club's full-season totals.
- `uper = (1/MP) x [3PM + (2/3) AST + (2 - factor x tmAST/tmFGM) FGM + 0.5 FTM (2 - (1/3) tmAST/tmFGM) - VOP TOV - VOP DRB% (FGA - FGM) - VOP 0.44 (0.44 + 0.56 DRB%) (FTA - FTM) + VOP (1 - DRB%) (TRB - ORB) + VOP DRB% ORB + VOP STL + VOP DRB% BLK - PF (lgFTM/lgPF - 0.44 (lgFTA/lgPF) VOP)]`, `MP` = cumulative minutes (seconds / 60), player totals cumulative through `r`.
- `aper = uper x lgPace / tmPace`. `per = aper x 15 / lgaPER`, where `lgaPER` is the seconds-weighted mean of `aper` over the scope's players with a non-NULL `aper` through round `r` (all players with at least one appearance, no minutes cutoff). If `lgaPER` is zero or undefined, `per` is NULL.
- The season slice is replaced atomically; a rerun gives identical rows. Reads Silver only; no Neon, no network.

## Testing

- Focused: `python -m unittest gold_etl.tests.test_player_ratings`, with in-memory games and fake cursors.
- Regression suites: `python -m unittest discover -s gold_etl/tests`; `python -m unittest discover -s postgres_etl/tests`; `cd api_requests && python -m unittest tests.test_scrapper`; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Local checks: `python gold_etl/main.py -sc all -tb player_round_ratings`, then `--quality-only`. No combined Verify command is declared; no Neon call is made.

## Notes for the AI

- Follow `gold_etl/player_rounds.py`, `team_ratings.py` and `team_splits.py`: the shared `read_tables` reader, the `ROUND_NAMES` dispatch in loader, quality and `main.py`, and `_dict_rows`. Reuse 27a's appearance walk and helpers if that can be shared without duplicating logic; otherwise keep the walk local and small.
- Accumulate additive player and team-context sums per appearance and divide when emitting each row. League constants change every round, so compute them once per scope round from prefix sums over rounds, not by rescanning games per player.
- `PLAYER_TOTALS` names (`fouls_committed`, `total_rebounds`, ...) match the team `total` rows used by 26a; reuse them.
- Use `Decimal` for stored values as the existing round tables do; the small league-constant algebra can use `Decimal` too so the 15 normalization is exact to 6 places.
- Early rounds have few games, so constants and PER are noisy; this is expected and documented, not filtered.

## Open questions

Non-blocking; the defaults above apply unless changed at review.

- Team context uses the club totals of the games the player played, not the club's full-season totals (differs slightly from Basketball-Reference).
- `per` uses all appearances, with no minutes threshold, in the league average, so garbage-time appearances pull `lgaPER` slightly; BBRef does the same over all players.
- There is no API reference for PER, so correctness rests on the hand-worked tests and the normalization invariant.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":8445,"specSha256":"7e868f4466843a8c88c7a8fc198c11c9434e913ff87362bf36a97ba5e16d7794","branch":"refs/heads/feature/player-efficiency-rating","head":"e29d116870c727c6fa27fba8eca1fb408e50064b","baseRef":"refs/heads/main","baseCommit":"e29d116870c727c6fa27fba8eca1fb408e50064b","sourceTree":"aec1d0841bdbc18bfdca63e51cb6eb216f133a8f","absentOptional":[]} -->

# Feature: Cumulative Team-Round Stats

**From build-plan:** feature 26a
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/cumulative-team-round-stats`

## Goal

Build `gold.team_round_stats`: for every season, scope and round, one row per club with its cumulative own and opponent totals, record, MOV, Pythagorean wins, possessions, pace, ratings and four factors through that round. It is the base for 26b (SRS/SOS/adjusted), 26c (home/away, rolling), 27-28 and the standings stats page. The final round of each scope is checked against the API team season feeds.

## In scope

- One new local Gold table, `team_round_stats`, registered in `gold_etl/schema.py` outside the Neon allowlist (not in `SOURCE_NAMES` or `DERIVED_NAMES`; publishing waits for 28/30g).
- A pure derivation module `gold_etl/team_rounds.py` reading only Silver: `games`, `game_team_stats` (`total` rows) and `game_team_advanced` (feature 25).
- Scopes `all` (every phase), each phase present in the season (`RS`, `PI`, `PO`, `FF`, ...), and `PS` (`PI`+`PO`+`FF`, the existing postseason definition).
- `gold_etl/main.py` support: `-tb team_round_stats` (also part of `-tb all`, so the refresh builds it), `--list-tables`, `--dry-run`, and `--quality-only` (fresh derivation compared with stored rows, like the other derived tables).
- A cross-check of each scope's final-round row against the API feeds `season_team_stats_advanced` and `_traditional` (mode `accumulated`), reported as warnings with a tolerance found from the data.
- Documentation and a local backfill of every loaded EuroLeague season.

## Out of scope

- SRS, SOS, SOV, adjusted and relative ratings (26b); home/away splits and rolling windows (26c); player stats (27); the page-shaped standings stats table (28).
- Neon publishing, publisher allowlist changes, web-app contracts (30g).
- Any change to Silver, Bronze, or existing Gold tables.

## Build loop

Follow `workflow.stepReview: "feature"`: finish the small steps, then present one review packet. `workflow.checkpointCommits: "disabled"`; no step commits are required. `/complete` creates the work commit after verification and approval.

## Build steps

- [x] **Step 1 - Register the table and derive cumulative totals.** Add `team_round_stats` to `gold_etl/schema.py` (`ROUND_NAMES`, merged into `GOLD_TABLES`, excluded from `DERIVED_NAMES`) and implement `derive_rows` in `gold_etl/team_rounds.py` for scopes, round sets, carry-forward rows and cumulative own/opponent totals, games, wins, losses, points for/against. *Done when:* unit tests with small fake seasons cover the `all`, per-phase and `PS` scopes, non-continuous round numbers, a club idle in a round (row carried forward), a club first appearing in a later round (no earlier rows), forfeit/unplayed games skipped, and `python -m unittest discover -s gold_etl/tests` passes.
- [x] **Step 2 - Cumulative rates and models.** Add `mov`, `pythagorean_win_pct`, `pythagorean_wins`, `possessions`, `game_minutes`, `pace`, ratings, four factors and the club and opponent rate columns, computed from the cumulative totals. *Done when:* tests check every formula against a hand-worked two-game example, NULL on missing inputs or zero denominators, and that the final-round cumulative possessions equal the sum of the per-game `game_team_advanced` values.
- [x] **Step 3 - Storage and CLI.** Add the season-slice replace (delete then insert in one transaction), read/derive wiring, and the `gold_etl/main.py` branches for build, dry run and quality-only, reusing the aggregate-loader pattern. *Done when:* fake-connection tests show scoped delete, insert, rollback on failure, dry-run read-only behavior and quality mismatch detection; `python gold_etl/main.py -sc E2025 -tb team_round_stats --dry-run` prints a row count; a neon_publish test still shows exactly the 26 mappings.
- [x] **Step 4 - API cross-check.** First inspect the API `accumulated` team feed scopes against our final rows (which phases `all` covers, percent versus fraction, which metrics match), then record the findings in the data dictionary. Implement the comparison with the tolerance the data supports, as warnings. *Done when:* tests cover match, mismatch beyond tolerance, and a scope with no API feed; `python gold_etl/main.py -sc all -tb team_round_stats --quality-only` runs and reports remaining differences with their season and scope.
- [x] **Step 5 - Document, backfill, verify.** Update `docs/DATA_DICTIONARY.md`, `README.md` and `AGENTS.md`. Run all declared test suites, then build every loaded EuroLeague season and run `--quality-only`; hand-check one club's rows in one season. *Done when:* docs match behavior, tests pass, the table exists for every season, and quality has no unexplained error.

## Files / areas

- `gold_etl/schema.py`, `gold_etl/team_rounds.py` (new), `gold_etl/loader.py`, `gold_etl/quality.py`, `gold_etl/main.py`
- `gold_etl/tests/test_team_rounds.py` (new), and one assertion in `neon_publish/tests/test_publish.py` that the allowlist is unchanged
- `docs/DATA_DICTIONARY.md`, `README.md`, `AGENTS.md`

## Data / contracts

- Key: `competition_code`, `season_code`, `scope`, `round_number`, `club_code`. `scope` is `all`, a phase code, or `PS`. `round_number` is the game round already stored in `silver.games` (continuous across phases within a season).
- A scope's rounds are the distinct `round_number` values with at least one counted game in that scope. A club has a row for every scope round from its first counted game onward; rounds it did not play carry its previous cumulative values forward. Rows include the club name and `games_played`.
- Counted games: `played IS TRUE` with a `game_team_advanced` row for both sides (a full box score). Forfeits and games without box scores are not counted; the data dictionary says so.
- Stored cumulative measures, `own_` and `opp_` prefixed: field goals made and attempted, three-pointers made, free throws made and attempted, offensive and defensive rebounds, turnovers, assists, points. Plus `wins`, `losses`, `points_for`, `points_against`, `game_minutes`, `possessions`.
- Derived (fractions, `NUMERIC`, NULL when an input is missing or a denominator is zero): `mov` = (points for - against) / games; `pythagorean_win_pct` = PF^e / (PF^e + PA^e) with e = 10.25, also stored as `pythagorean_exponent` so the value is visible; `pythagorean_wins` = win pct x games; `pace` = 40 x possessions / game_minutes; `offensive_rating`, `defensive_rating`, `net_rating` = 100 x points / possessions; four factors, `true_shooting_pct` and `assist_ratio` for the club and `opp_*` for the opponent, using feature 25's formulas on the cumulative totals (not averages of per-game rates).
- The season slice is replaced atomically; a rerun gives identical rows. Reads Silver only; no Neon, no network.

## Testing

- Focused unit tests: `python -m unittest gold_etl.tests.test_team_rounds`, with in-memory games and fake cursors.
- Regression suites: `python -m unittest discover -s gold_etl/tests`; `python -m unittest discover -s postgres_etl/tests`; `cd api_requests && python -m unittest tests.test_scrapper`; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Local checks: `python gold_etl/main.py -sc all -tb team_round_stats`, then `--quality-only`. No combined Verify command is declared; no Neon call is made.

## Notes for the AI

- Follow `gold_etl/team_season.py` (pure `derive_rows` plus `read_rows`) and the aggregate loader and quality patterns; do not refactor the existing `main.py` branches, add one.
- Keep the table out of `DERIVED_NAMES`: `neon_publish/contract.py` builds its 26-table allowlist from it.
- Reuse feature 25's box-score names and formulas (`postgres_etl/advanced.py`) instead of new conventions; import constants only if a clean import path exists, otherwise restate them with a test tying the two together.
- The API `all` scope may not equal our `all`; find out in Step 4 instead of assuming.
- Take `PS` membership from the existing definition in `gold_etl/postseason.py`.

## Open questions

Non-blocking; the defaults above apply unless changed at review.

- Pythagorean exponent 10.25 (approximate EuroLeague fit). Change it if the JMP model uses another; it is stored per row.
- Table name `team_round_stats` and its exclusion from the Neon allowlist until 28/30g decides the published shape.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":8404,"specSha256":"50f0745e4014ff164137c677209bde46823272b1f058244efb832b71b7ea058d","branch":"refs/heads/feature/cumulative-team-round-stats","head":"d304190d4d95643b889f51afa2eda9baa5d11ff5","baseRef":"refs/heads/main","baseCommit":"d304190d4d95643b889f51afa2eda9baa5d11ff5","sourceTree":"e189948532bdeb7b9057c770db1c79d76ed30f25","absentOptional":[]} -->

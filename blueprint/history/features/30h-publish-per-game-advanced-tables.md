# Feature: Publish per-game advanced tables

**From build-plan:** feature 30h
**Build attempt:** 1
**Branch:** feature/publish-per-game-advanced-tables
**Status:** verified

Source brief: `GAME_ADVANCED_TABLES.md` (untracked, repository root). Its table specs,
column names and section 6 checks are the contract; this spec adds the how.

## Goal

Build `app_game_player_advanced` and `app_game_team_advanced` in local Gold from the
item 25 Silver tables, add single-game PER (`game_uper`, `game_aper`, `game_per`), and
register both in the Neon publisher for E2025 and E2026. The web app's Game Detail
page (steps 23d and 23e) reads them; it never recomputes them.

## In scope

- Two Gold tables, named `game_player_advanced` and `game_team_advanced` in `gold`
  (publisher target `public.app_game_player_advanced` / `app_game_team_advanced`, the
  same `app_` prefixing as the 30g tables). Columns, order, types and keys exactly as
  brief sections 3.1 and 3.2.
- Game PER from the existing PER code (`gold_etl/player_ratings.py`), no new formula.
- Quality checks in `gold_etl/main.py --quality-only` (brief checks 2, 4, 5, plus
  the round-1 ties of check 3 against the stored Gold round tables).
- Publisher registration, reviewed migration SQL, tests, `DATA_DICTIONARY.md`, README
  and `AGENTS.md` command/count updates.
- A **dry-run** of the Neon publish and printed migration for review.

## Out of scope

- Applying the migration to Neon and any live publish: each needs
  separate owner approval in the chat. Section 6 checks 1 and the API spot checks that
  need Neon are run only after that approval.
- The other per-game Silver tables (30i, 30j), seasons other than E2025/E2026 in Neon,
  any change to existing `app_*` tables, and any web-app work.

## Build loop

`workflow.stepReview` is `feature`: implement all steps, then present one review
packet. `checkpointCommits` is disabled; `/complete` makes the single commit.

## Build steps

- [x] 1. **Schema and projection.** In `gold_etl/schema.py` add `GAME_ADVANCED_NAMES =
  ("game_player_advanced", "game_team_advanced")`, the two `Table` definitions (keys per
  brief; `game_code` INTEGER, measures NUMERIC, text codes NOT NULL as the brief marks
  them) and register them in `GOLD_TABLES`, `SEASON_DERIVED_NAMES` and
  `BUILD_NAMES` (not `DERIVED_NAMES`, matching how 26-29 were added). New
  `gold_etl/game_advanced.py` projects `silver.game_team_advanced` and
  `silver.game_player_advanced` into those columns with NULL game PER columns for now;
  `read_aggregate_rows` returns the rows for either name.
  *Done when:* `python gold_etl/main.py -sc E2026 -tb game_team_advanced game_player_advanced`
  loads, and counts equal Silver for E2025 and E2026 (`--dry-run` and a count query).
- [x] 2. **Game PER.** In `game_advanced.py`, per game row with seconds > 0: league
  constants from `_league_states`/`_constants` of the game's own phase scope, taken
  **through the game's round**; the player's single-game line with that game's team
  assists, field goals, possessions and minutes (reuse `_uper`); `game_aper` per the
  existing function; `game_per = game_aper x 15 / seconds-weighted mean game_aper of the
  games of the same scope and round`. Quantize to 6 places like `player_round_ratings`.
  NULL when seconds are 0 or missing, an input is missing or a denominator is zero.
  *Done when:* unit tests pass (step 5) and E2026 game 2, Dubai, `person_key` `011286`
  gives `seconds_played` 1744, `usage_pct` 0.258519, `game_per` 27.804814.
- [x] 3. **Quality checks.** In `gold_etl/quality.py` plus `main.py` wiring: (a) team
  table has exactly two rows per counted game with identical `possessions`; (b) player
  keys equal the `game_player_stats` keys of counted games; (c) percent columns not
  negative or above 2, and rates and `game_per` NULL for zero-minute rows; (d) mean of
  `game_per` weighted by `seconds_played` is 15 within 1e-4 for every scope and round;
  (e) round-1 ties: `usage_pct`, `efg_pct`, `true_shooting_pct`, `game_score` vs
  `gold.player_round_stats`, `game_per` vs `gold.player_round_ratings` (scope `RS`),
  and team `possessions`, `pace`, ratings vs `gold.team_round_stats` for rows whose
  first counted game is round 1. 6-decimal tolerance.
  *Done when:* `python gold_etl/main.py -sc E2025 E2026 -tb game_team_advanced
  game_player_advanced --quality-only` prints "Gold quality: passed".
- [x] 4. **Publisher.** In `neon_publish/contract.py` add `GAME_TABLES =
  GAME_ADVANCED_NAMES`, extend `APP_TABLES` (now 40) and keep `NEW_TABLES`
  as the 30g set; `--print-migration` gains the smallest selector needed to print the 30h
  DDL only (`migrations/30h_game_advanced.sql`, generated, with `BEGIN`/`COMMIT`, primary
  keys per brief and an index only if the primary key does not already serve lookups by
  `(competition_code, season_code, game_code)`, which it does as the leading prefix).
  No `GRANT` is written: Neon has only `neondb_owner` (checked read-only on 2026-10-01) and no existing `app_*` table grants anything to another role.
  *Done when:* `python neon_publish/main.py --list-tables` shows 40 mappings and the
  printed migration creates exactly the two tables; `python neon_publish/main.py -sc
  E2026 --dry-run` runs (it reports the two targets as missing until the owner applies the
  migration, which is expected).
- [x] 5. **Tests.** `gold_etl/tests/test_game_advanced.py`: projection columns and keys,
  PER on a small fixture against the round-ratings function for a single-game round,
  zero-minute NULLs, missing-input NULLs, league-mean 15 per scope and round, overtime
  `game_minutes`. Update `neon_publish/tests/test_publish.py` for 40 targets and the 30h
  migration; extend `tables_to_csv` tests only if they enumerate Gold tables.
  *Done when:* the four test commands in `AGENTS.md` pass.
- [x] 6. **Documentation.** `docs/DATA_DICTIONARY.md`: remove "not part of Gold or Neon"
  from the per-game advanced section, document both tables, the final game PER
  definition and the "Published to Neon as ... (E2025 and E2026)" sentence, and update
  the Neon contract paragraph counts. Update `neon_publish/README.md`, `AGENTS.md`
  (table counts 38 to 40, new Gold build command) and `postgres_etl/README.md` if it
  says Silver-only. *Done when:* a search for "38" and "not part of Gold or Neon" finds
  no stale statement about these tables.

## Files / areas

- New: `gold_etl/game_advanced.py`, `gold_etl/tests/test_game_advanced.py`,
  `neon_publish/migrations/30h_game_advanced.sql`.
- Edit: `gold_etl/schema.py`, `gold_etl/loader.py`, `gold_etl/quality.py`,
  `gold_etl/main.py`, `neon_publish/contract.py`, `neon_publish/main.py`,
  `neon_publish/tests/test_publish.py`, `docs/DATA_DICTIONARY.md`,
  `neon_publish/README.md`, `AGENTS.md`.
- Reused, not changed: `gold_etl/player_ratings.py` (`_league_states`, `_constants`,
  `_uper`), `gold_etl/team_rounds.py` (`_counted_games`, `_scopes`).

## Data / contracts

- Column names, types, order and primary keys: brief 3.1 and 3.2. `side` is `local` or
  `road`; ratios are fractions; NULL, never 0, for missing data.
- `game_team_advanced` drops Silver's `opponent_club_code`, `phase_code`, `round_number`;
  `club_code` stays. `game_player_advanced` takes `club_code` and `seconds_played` from
  Silver.
- Game PER definition (final, to be written into the dictionary): constants (factor, VOP,
  DRB%, league pace) are sums over every counted game of the game's phase scope through
  its round, exactly as `player_round_ratings`; the player's line and team context are
  that single game; normalisation divides by the seconds-weighted mean `game_aper` over
  the games of the same scope **and round**, so the mean is 15 per scope and round.
  Scopes are the game's own phase code, not `all` or `PS`.
- Publish: replaced per competition and season in one transaction with the existing
  guards (preflight refuses a missing or incompatible target, 90% shrink guard).

## Testing

Unit tests only (`python -m unittest discover -s gold_etl/tests`, and the
`neon_publish` and `tables_to_csv` commands). Live evidence is local: the `--quality-only`
run on E2025 and E2026 and the Bacon game 2 spot check. Neon-side checks (brief 6.1, the
API role, game 13 reference) are not run until the owner approves the migration and
publish.

## Notes for the AI

- No Verify command exists; run the four documented test commands.
- Registering the tables in `APP_TABLES` makes `python pipeline.py` and
  `neon_publish` preflight fail with "missing table" until the owner applies the 30h
  migration. Say so in the review handoff; do not apply it.
- Zero-minute players: Silver stores `game_score` for them (16,661 rows have
  `seconds_played` 0 and a non-null score). Keep Silver's value; rates and PER are NULL.
  Mention the difference from the brief's "measures are NULL" in the handoff.
- Do not touch `silver.*` or existing Gold formulas. numpy/pandas are allowed but not
  needed.
- Game PER normalisation is per scope and round (decided; round 1 ties to the season table
  either way). A season PER is not derived from game PER: it is `app_player_round_ratings`.
- Do not commit `GAME_ADVANCED_TABLES.md` unless the owner says so.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":9229,"specSha256":"0990aa9bab527a09a4938829d780dd20e508e6cacdbc37e9c8adda5ff00fee9d","branch":"refs/heads/feature/publish-per-game-advanced-tables","head":"8657b9ab28f84bb753aa05c2191b63466afbf4c1","baseRef":"refs/heads/main","baseCommit":"8657b9ab28f84bb753aa05c2191b63466afbf4c1","sourceTree":"449ce62c4b327df83472d688ae9eae88ea6e8ea3","absentOptional":[]} -->

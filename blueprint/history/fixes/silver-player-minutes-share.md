# Fix: Silver player minutes share is 5x too small

**Type:** Fix
**Status:** verified
**Branch:** fix/silver-player-minutes-share

## The problem

`postgres_etl/advanced.py` `derive_rows` passes `minutes * 5 * 60` (the team's total player-seconds) as `team_seconds` to `_player_row`, so `share = seconds / team_seconds` is one fifth of the fraction of the game the player was on court. The standard forms (usage, assist, rebound, steal and block rates) use the player's minutes over the team's minutes divided by 5, that is over game seconds. Every rate in `silver.game_player_advanced` that divides by `share` is therefore about 5 times too large (usage about 245% against the API's ~49%; ORB% 15 vs API ~3). Found while verifying feature 27a; feature 25's own test encodes the same wrong share (`1200 / 12000`).

Affected columns: `usage_pct`, `assist_pct`, `orb_pct`, `drb_pct`, `trb_pct`, `steal_pct`, `block_pct`. Unaffected: `true_shooting_pct`, `efg_pct`, `tov_pct`, `game_score`, and all team columns. Gold `player_round_stats` already uses game seconds and reads only `game_score` from this table, so it needs no change.

## The fix

- In `derive_rows`, pass `minutes * 60` (game seconds) as the share denominator, and rename the `_player_row` parameter to `game_seconds` so the name matches. No other logic changes.
- Correct the feature 25 test to expect `share = 1200 / 2400` and assert plausible ranges (usage of a starter well under 100%).
- Update the `docs/DATA_DICTIONARY.md` note that documents the known bug, and any comment or README line that describes the old denominator.
- Re-backfill the stored rows: `python postgres_etl/advanced.py -sc 2000-2026`, then `--quality-only`. This is a local Silver rewrite only; Neon is untouched (these tables are not published).
- Must not break: Silver table shape, the team rows, the Gold round tables, or the Neon allowlist.

## Build steps

- [x] 1. Repair the denominator in `postgres_etl/advanced.py`, correct the tests in `postgres_etl/tests/test_advanced.py`, and update the docs note.
  **Done when:** the corrected test fails against the old code and passes with the fix, and `python -m unittest discover -s postgres_etl/tests` passes.
- [x] 2. Re-backfill Silver for E2000-E2026 and compare against the API feeds.
  **Done when:** `python postgres_etl/advanced.py -sc 2000-2026` and `--quality-only` succeed, and a spot check of one full E2025 player (season accumulated ORB%/usage from Silver rows vs `season_player_stats_*`) is within rounding of the API's advanced figures; `python gold_etl/main.py -sc 2000-2026 --quality-only` still passes.

## Verify

- `python -m unittest discover -s postgres_etl/tests` and `python -m unittest discover -s gold_etl/tests`.
- Read-only SQL: the E2025 mean `usage_pct` is about 0.19 (five times larger before the fix, by construction) and mean `orb_pct` about 0.055. A player with very few seconds can still show a large single-game rate, which is inherent to the formula, so no upper bound is asserted in SQL. The step 2 API spot check was replaced by these league-level figures, because the per-game Silver rows have no direct API counterpart (Gold `player_round_stats`, which computes its own share, already matches the API).
- No Neon call.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":3255,"specSha256":"17f46468efb880a055357e6bd5bd3105bae331bf7a05fbb54e500a488c55b425","branch":"refs/heads/fix/silver-player-minutes-share","head":"ea054542a67b806ae45b3d68b7fa4a0c65273a96","baseRef":"refs/heads/main","baseCommit":"ea054542a67b806ae45b3d68b7fa4a0c65273a96","sourceTree":"a1b14cace4383df06f55b053a7d6f78fa0af4188","absentOptional":[]} -->

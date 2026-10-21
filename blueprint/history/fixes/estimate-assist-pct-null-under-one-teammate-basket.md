# Fix: Estimate assist % NULL under one teammate basket

**Type:** Fix
**Status:** verified
**Branch:** fix/estimate-assist-pct-null-under-one-teammate-basket

## The problem

The Gold quality check warns `rows have assist_pct below 0 or above 2` for E2000,
E2001, E2004 and E2005. All four rows are box-score estimates
(`rate_source = 'estimate'`). Play-by-play starts at E2007, so the on-court form
from feature 32 and the free-throw-trip fix (`blueprint/history/fixes/assist-pct-counts-free-throw-trips.md`)
cannot apply.

The estimate in `postgres_etl/advanced.py` `_player_row` is the Basketball-Reference
form: `AS / (share * team FGM - player FGM)`, where share = seconds / game seconds.
When a player scores more baskets than his minutes share of the team's baskets, the
estimated teammate baskets drop below 1 or go negative, so the value means nothing:

| Season | Game | Player | Seconds | AS | FGM | assist_pct |
|---|---|---|---|---|---|---|
| E2000 | 4 | Jennings (PET) | 600 | 2 | 6 | -8.00 |
| E2001 | 151 | Lutcke (FRA) | 192 | 1 | 3 | -5.00 |
| E2004 | 52 | Morovic (CIB) | 195 | 1 | 2 | 2.81 |
| E2005 | 136 | Mendy (STR) | 375 | 1 | 2 | 2.91 |

Across the 29,046 estimate rows, 2 are negative and 16 are above 1; on-court rows
have 0 negative and 1 above 1.

## The fix

Owner decision (2026-10-21): in the estimate path only, `assist_pct` is NULL when the
estimated teammate baskets while on court (`share * team FGM - player FGM`) is below 1.
This follows the existing rule that estimates are NULL below 180 seconds: the formula
has too little to measure. NULL means unavailable, never 0.

- `postgres_etl/advanced.py` `_player_row`: apply the rule to the estimate
  `assist_pct` only.
- Unchanged: on-court `assist_pct` (E2007+ with play-by-play), every other rate, the
  team rows, the Gold round tables (27a keep the cumulative form), the Gold quality
  range check, and the Neon schema. Gold `app_game_player_advanced` picks up the new
  values when rebuilt.
- `docs/DATA_DICTIONARY.md`: note the rule on the player rate row (line ~173).

## Build steps

1. [x] **Rule and tests.** Add the threshold to the estimate `assist_pct`, with unit
   tests in `postgres_etl/tests/test_advanced.py`: a negative denominator (Jennings
   shape) is NULL, a denominator between 0 and 1 (Morovic shape) is NULL, exactly 1 and
   above keep the value, and on-court rows are unaffected. Update the dictionary row.
   **Done when:** `python -m unittest discover -s postgres_etl/tests` passes.
2. [x] **Rebuild.** `python postgres_etl/advanced.py -sc all`, then
   `python gold_etl/main.py -sc all -tb game_player_advanced`, then `--quality-only` for
   both.
   **Done when:** Silver quality has no ERROR, Gold quality passes with no
   `assist_pct below 0 or above 2` warning, and the evidence records how many estimate
   rows became NULL (expected about 18).

## Verify

- All four configured test suites pass.
- Read-only SQL: no `silver.game_player_advanced` or `gold.app_game_player_advanced`
  row with `assist_pct < 0 OR assist_pct > 2`; the four rows above have NULL
  `assist_pct` and unchanged `usage_pct`.
- Local only. Seasons already on Neon (E2023-E2026) are all on-court rows, so their
  values do not change. No Neon call.

## Evidence

- Rebuilt with `python postgres_etl/advanced.py -sc all` and
  `python gold_etl/main.py -sc all -tb game_player_advanced`; Silver `--quality-only`
  reports 0 errors in every season and Gold `--quality-only` passes with no `assist_pct`
  warning.
- Estimate rows with NULL `assist_pct` went from 5,602 to 5,650 of 34,648: 48 rows, not
  the 18 estimated. 5 had assists (the 4 rows above plus one more); 43 had 0 assists and
  a stored 0% over less than one teammate basket, which the same rule makes NULL.
- No Silver or Gold row has `assist_pct < 0 OR assist_pct > 2`; the four rows above
  are NULL in Gold with `usage_pct` kept.
- All four configured test suites pass (46, 214, 283, 72 tests).


<!-- blueprint:completion {"schemaVersion":1,"specBytes":4039,"specSha256":"3c799da277f2a986f1a184ebf0124e186deba7eff248e47e011f37dc2d55d7b7","branch":"refs/heads/fix/estimate-assist-pct-null-under-one-teammate-basket","head":"7adc4a04a7dc98146f7d360499ceba5dbcbc4fd3","baseRef":"refs/heads/main","baseCommit":"7adc4a04a7dc98146f7d360499ceba5dbcbc4fd3","sourceTree":"99b83635d796f14989613221793f3f899642a086","absentOptional":[]} -->

# Feature: EuroCup Gold tables and records

**From build-plan:** feature 18a
**Build attempt:** 1
**Type:** Feature
**Status:** verified
**Branch:** feature/eurocup-gold-tables-and-records

## Goal

Build every local Gold table for EuroCup (competition `U`, U2002-U2026) from
Silver, with Gold quality passing, and enable EuroCup all-time records. Local only:
nothing EuroCup reaches Neon.

## In scope

- Remove the EuroCup records guards: `read_rows` in
  [gold_etl/records.py:78-80](../../gold_etl/records.py#L78-L80) and the
  `parser.error` in [gold_etl/main.py:81-82](../../gold_etl/main.py#L81-L82). The
  records query already filters by `competition_code`; EuroCup records use every
  loaded EuroCup season, as EuroLeague's do.
- Build all 40 Gold tables for EuroCup:
  `python gold_etl/main.py -cp eurocup -sc all`.
- Run `python gold_etl/main.py -cp eurocup -sc all --quality-only` and make it
  pass with 0 errors. Each error is triaged as one of:
  - a real Gold defect, fixed in competition-neutral code with a test;
  - a EuroCup format difference (group stages such as `RS`, `TS`, `L16`, `L32`;
    drawn two-leg legs with no winner in U2004-U2015; no `PI`/`PO`/`FF`, so no
    postseason rows), where the check or builder is made correct for both
    competitions with a test;
  - a known source gap, kept visible as a `WARN` (not an error) with its reason.
- EuroLeague Gold must be unchanged: rebuild and quality-check it after the code
  changes.
- Docs that say records cover EuroLeague only, or that EuroCup is deferred, updated
  to say EuroCup Gold (with records) is built locally and not published.

## Out of scope

- EuroCup postseason outputs: `PS` season stats, the `PS` scope of the round
  tables, qualification thresholds for postseason, and `app_postseason_series`.
  They stay empty for EuroCup until 18c, because the postseason phases
  (`PI`, `PO`, `FF`) are hard-coded and EuroCup's format differs by era.
- The daily EuroCup refresh and a skip-publish option (18b).
- Any Neon change, migration or publish, and the web app.
- Silver changes, except a Silver defect found here, which stops for a separate
  `/fix`.

## Build loop

`workflow.stepReview` is `feature` and checkpoint commits are disabled: build all
steps, then present one review packet. `/complete` makes the feature commit.

## Build steps

- [x] 1. **Enable EuroCup records.** Remove the two guards; replace
  `test_series_scopes_and_eurocup_records_rejected`
  ([gold_etl/tests/test_gold.py:284-305](../../gold_etl/tests/test_gold.py#L284-L305))
  so it keeps its series-scope assertions and asserts that a EuroCup records
  selection is accepted and reads with competition `U`. **Done when:** Gold tests
  pass.
- [x] 2. **Build EuroCup Gold and record the quality baseline.** Run the full
  EuroCup build and `--quality-only`. Record each error and warning code with its
  seasons and counts in this spec, under Notes, before changing any code for
  them. **Done when:** every table is built for U2002-U2026 (or the build failure
  is recorded) and the baseline is written down.
- [x] 3. **Make EuroCup Gold quality pass.** Fix each recorded error as triaged
  above, one focused test per fix. If a fix needs a product decision (for example,
  what a postseason phase means, or how a draw counts in standings), stop and
  revise this spec instead of choosing. **Done when:** EuroCup `--quality-only`
  has 0 errors, and every remaining warning is explained in Notes.
- [x] 4. **Check EuroLeague is unchanged and update the docs.** Rebuild and
  quality-check EuroLeague Gold, and update the docs that describe records or
  EuroCup scope (AGENTS.md:357, docs/GOLD_TABLE_REFERENCE.md:861, and any other
  current doc found by search). **Done when:** EuroLeague `--quality-only` still
  has 0 errors and all test suites pass.

## Files / areas

- `gold_etl/records.py`, `gold_etl/main.py`, `gold_etl/tests/test_gold.py`
- Gold builders and `gold_etl/quality.py`, only where step 3 finds a defect
- `AGENTS.md`, `README.md`, `gold_etl/README.md`, `docs/GOLD_TABLE_REFERENCE.md`,
  `docs/DATA_DICTIONARY.md` (docs only where wording is affected)

## Data / contracts

- No new tables or columns. EuroCup rows go into the same 40 local Gold tables,
  keyed by `competition_code = 'U'` like every other row.
- Neon is not affected. Publishing is scoped by competition
  ([neon_publish/contract.py:31-38](../../neon_publish/contract.py#L31-L38)): season
  tables by competition and season, competition-wide tables (records, identities)
  by competition. The EuroLeague publish selects only `E` rows, and the publisher
  refuses any other competition
  ([neon_publish/publish.py:179](../../neon_publish/publish.py#L179)).
- Draws in two-leg legs (8 games, U2004-U2015) have a NULL `match_winner_club_code`
  in Silver; Gold must not invent a winner for them.

## Testing

- Gold unit tests: `python -m unittest discover -s gold_etl/tests`.
- All declared suites at the end (API, Silver, Gold, publisher/CSV).
- Data checks: EuroCup and EuroLeague Gold `--quality-only`.
- Observed before this spec: `python gold_etl/main.py -cp eurocup -sc all
  --dry-run` (all tables except records) exits 0 and reads every Silver source for
  U2002-U2026, including 6,056 players and 188 club identities.

## Notes for the AI

- Gold quality limits were tuned on EuroLeague (for example
  `WIN_SHARE_TOLERANCE` around E2000-E2026's 0.90-1.07 wins per game,
  `API_RATE_TOLERANCE`). Do not widen a limit just to pass EuroCup; change it only
  with evidence that EuroCup's data, not Gold, differs, and keep EuroLeague's
  behavior.
- Known Silver warnings that may echo in Gold: `on_court_rate_out_of_range` (1 row
  each in U2008, U2009) and `standings_played_not_won_plus_lost` (U2011, U2025).
- Quality baseline (step 2, 2026-10-26): `python gold_etl/main.py -cp eurocup -sc all`
  built all 40 tables (exit 0, about 4 min), and `--quality-only` passed with
  **0 errors** and 185 warnings, so step 3 needed no code change. Warnings:
  - `feed perGame row(s) below min_games` (180, U2002-U2025 in `8F`, `4F`, `2F`,
    `Final`): the API perGame feed lists players under the phase threshold
    (`rounds // 2 + 1`, which is 2 for a two-round knockout phase). EuroLeague
    avoids this for `FF` via `UNFILTERED_PHASES`; EuroCup postseason qualification
    belongs to 18c. EuroLeague has 16 warnings of the same type.
  - `efg_pct` / `drb_pct differs from the API feed` (17, U2002-U2007, 1-3 players
    or clubs each): small differences between our box-score totals and the API's
    early-season feeds; EuroLeague has 6 of the same type.
  - `true_shooting_pct below 0 or above 2` (1, U2005 game 4, KSK row): the source
    box score has 11 points from 2 field-goal attempts and 0 free throws, which is
    impossible; a source error, kept visible.
- Results: EuroCup Gold holds U2002-U2026 (for example `app_standings` 8,820 rows,
  `app_player_round_stats` 304,826, records 200 per table, `app_player_rapm` 8,393
  for U2007+), with group-stage scopes `L16`, `L32`, `TS` in `app_standings_stats`.
  `app_postseason_series` and `PS` rows are empty for EuroCup, as planned for 18c.
  EuroLeague Gold rebuilt with `-sc all` and still passes quality (0 errors,
  22 warnings of the two types above).


<!-- blueprint:completion {"schemaVersion":1,"specBytes":7418,"specSha256":"656d77139d020cdaaff7e9997aa7d9634ca471d69247042be37f814aeeb1cf48","branch":"refs/heads/feature/eurocup-gold-tables-and-records","head":"3e0552eca8f8836ec7f3bbaf4813b9118a52e981","baseRef":"refs/heads/main","baseCommit":"3e0552eca8f8836ec7f3bbaf4813b9118a52e981","sourceTree":"a8d0784cad4ed1e52925722ee21745c2e17a6377","absentOptional":[]} -->

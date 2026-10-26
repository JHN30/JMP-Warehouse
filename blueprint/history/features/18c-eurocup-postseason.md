# Feature: EuroCup postseason

**From build-plan:** feature 18c
**Build attempt:** 1
**Type:** Feature
**Status:** verified
**Branch:** feature/eurocup-postseason

## Goal

Give EuroCup the postseason outputs EuroLeague already has: the derived `PS`
season player stats, the `PS` scope of the per-round tables, postseason
qualification thresholds, and `app_postseason_series`, using EuroCup's own
knockout format per season and round. Local only. EuroLeague output stays exactly
the same.

## Format by season (owner-confirmed 2026-10-26)

Checked by the owner against historical sources and matched to Silver games
(phase codes in brackets). Season codes are start years: U2023 = 2023-24.

| Seasons | Knockout format |
|---|---|
| U2002 | Round of 16 (`8F`), quarterfinals (`4F`), semifinals (`2F`), final (`Final`): two-leg aggregate |
| U2003-U2006 | `8F`, `4F`, `2F` two-leg aggregate; `Final` single game |
| U2007 | `L32`, `L16` two-leg aggregate knockouts; then a Final Eight: `4F`, `2F` single games, `Final` = final and third-place game, single games |
| U2008 | `L16` is a group stage; Final Eight: `4F`, `2F`, `Final` single games |
| U2009-U2011 | `4F` two-leg aggregate; Final Four in `Final`: semifinals, final and third-place game, single games |
| U2012 | `4F`, `2F` two-leg aggregate; `Final` single game |
| U2013-U2015 | `L32` group stage; `8F`, `4F`, `2F`, `Final` two-leg aggregate |
| U2016-U2018, U2020 | `TS` group stage; `4F`, `2F`, `Final` best-of-three |
| U2019 | cancelled before the playoffs: 12 `4F` games exist in Silver, all `status = cancelled`, `played = false`; no postseason, no champion |
| U2021-U2022 | `8F`, `4F`, `2F`, `Final` single games |
| U2023-U2025 | `8F`, `4F` single games (top two per group get a quarterfinal bye, so `8F` has 4 ties); `2F`, `Final` best-of-three |
| U2026 | in progress; `8F`, `4F`, `2F`, `Final` all best-of-three (no knockout games in Silver yet) |

Data checks behind it (read-only, Silver U2002-U2026): in every phase marked
two-leg above, each tie has exactly 2 games with home and away reversed; every
2-game tie from U2016 on is a 2-0 sweep; draws and 1-1 splits occur only in
two-leg phases.

API labels that need normalization in Gold (Silver keeps the source values):
- U2007 `L32` and `L16` have `phase_is_group = true` but were knockouts.
- `Final` is not only the championship game: U2007 holds the final and the
  third-place game (both round 17), and U2009-U2011 hold a Final Four (semifinals
  in round 15, final and third place in round 16).

## Decisions (approving this spec approves them)

1. **Postseason phases for EuroCup:** `8F`, `4F`, `2F`, `Final` in every season,
   plus `L32` and `L16` in U2007 only. `RS`, `TS` and every other `L32`/`L16` are
   group stages.
2. **Two-leg aggregate ties are an explicit season and phase table** (the
   two-leg rows above), never inferred from game counts. A two-leg tie is won by
   the higher combined points over both legs, regardless of game wins; with a leg
   unplayed, or level combined points, it has no winner. Every other tie is won by
   the club with more game wins, as today (single games, best-of-three including
   2-0 and 2-1).
3. **EuroCup knockout qualification** uses `ceil(rounds / 2)` minimum games: the
   API perGame feed lists every player in 1- and 2-round knockout phases (minimum
   1 game in U2004 and U2015 `8F`/`4F`/`2F`/`Final`, U2018 `2F`, U2024 `Final`)
   and players with 2+ games in 3-round phases (U2018 `4F`/`Final`, U2024 `2F`).
   This removes 18a's 180 `below min_games` warnings. `PS` (derived) keeps the
   existing rule.
4. **Cancelled games are not postseason results:** games with
   `status = 'cancelled'` are left out of series, so U2019 has no series rows and
   no winner. EuroLeague has no cancelled postseason games today, so its output
   does not change.
5. **Third-place and Final Four ties stay separate rows** in
   `app_postseason_series`, each with its own pairing, as EuroLeague's Final Four
   rows already are; the championship tie is the `Final` tie won by the season
   champion. No column marks it: a new column would change the published table's
   shape and need a Neon migration (a later decision).

## In scope

- One competition-aware definition in `gold_etl/qualification.py`: postseason
  phases (EuroLeague `PI`, `PO`, `FF`; EuroCup per decision 1), the EuroCup
  group-stage phases, and the two-leg table (decision 2), each an explicit
  constant with a comment pointing at the table above. Used everywhere the
  hard-coded `PI`/`PO`/`FF` set is today:
  - `gold_etl/qualification.py` (`scope_rounds`, `min_games` / `scope_min_games`);
  - `gold_etl/postseason.py` (`derive_rows` and both SQL filters, lines 147 and
    160);
  - `gold_etl/team_rounds.py` `_scopes` (games rows carry `competition_code` and
    `season_code`);
  - `gold_etl/series.py` (`PHASES` and the SQL filter, line 73).
- EuroCup knockout qualification (decision 3) in `min_games`/`scope_min_games` and
  their callers (`gold_etl/per_game_rows.py`, `gold_etl/quality.py`).
- Series (decisions 2, 4, 5) in `series.derive_rows`/`read_rows`. No new columns:
  `club_a_wins`/`club_b_wins` stay game wins (a two-leg tie can read 1-1 with a
  winner), and the `games` JSON already holds both legs' scores.
- A Gold quality `WARN` for EuroCup played games in a phase code that is neither a
  known group stage nor a postseason phase, so a new API phase code (for example in
  U2026) is seen instead of silently left out of `PS` and series.
- Rebuild EuroCup Gold and check it; rebuild EuroLeague Gold and prove it is
  unchanged.
- Docs that say EuroCup postseason outputs are empty or planned.

## Out of scope

- New Gold columns or a changed `app_postseason_series` shape, including a
  championship or third-place flag (decision 5).
- Changing Silver's source `phase_is_group` values.
- Any Neon change or EuroCup publish, the scheduled refresh, and the web app.

## Build loop

`workflow.stepReview` is `feature` and checkpoint commits are disabled: build all
steps, then present one review packet. `/complete` makes the feature commit.

## Build steps

- [x] 1. **Record the EuroLeague baseline.** Before any code change, save row
  counts and an order-independent checksum (for example `md5` of sorted row text,
  leaving out build-time or load-time columns such as `loaded_at`, which change on
  every rebuild) per EuroLeague (`E`) Gold table this feature touches:
  `app_postseason_series`, `app_season_player_stats_*`, `app_standings_stats`,
  `app_player_round_*`, `app_game_player_advanced`, `app_game_team_advanced`.
  **Done when:** the baseline is saved in the scratchpad and summarized in Notes.
- [x] 2. **Competition-aware phases and qualification.** The constants and helpers
  (decisions 1-3), every caller pointed at them, and the unknown-phase `WARN`.
  Unit tests: EuroLeague phases and thresholds unchanged; EuroCup U2007 includes
  `L32`/`L16` as postseason and two-leg, U2008 `L16` and U2013 `L32` are group
  stages; EuroCup knockout thresholds 1, 1, 2 for 1, 2, 3 rounds; `PS` scope
  rounds and team `_scopes` include EuroCup knockout phases. **Done when:** Gold
  tests pass.
- [x] 3. **Series rules.** Aggregate winner for two-leg ties, game wins otherwise,
  cancelled games left out (decisions 2 and 4). Unit tests: a 1-1 two-leg tie won
  on aggregate; a two-leg tie lost on wins but won on aggregate (draw plus a win
  each way); a two-leg 2-0 tie; level aggregate and an unplayed leg give no
  winner; best-of-three 2-0 and 2-1 by wins; a 2-game tie in a non-two-leg phase
  by wins; a cancelled game is not a game of the series; EuroLeague series
  unchanged. **Done when:** Gold tests pass.
- [x] 4. **Rebuild and check both competitions.** Rebuild EuroCup Gold
  (`-cp eurocup -sc all`) and run `--quality-only`; rebuild EuroLeague Gold
  (`-sc all`) and run `--quality-only`. **Done when:**
  - EuroCup quality has 0 errors, no unknown-phase warning, and no knockout
    `below min_games` warning (or each remaining one is explained in Notes);
  - EuroCup has `PS` rows and series in every season with played knockout games,
    U2019 has none, and in every season with a champion in `silver.seasons` the
    champion wins a `Final` tie in the last `Final` round;
  - every EuroLeague table from step 1 has the same row count and checksum;
  - all four test suites pass.
- [x] 5. **Docs.** Update AGENTS.md, README.md, `gold_etl/README.md` and
  `docs/GOLD_TABLE_REFERENCE.md` where they call EuroCup postseason empty or
  planned; describe the EuroCup postseason phases, the two-leg aggregate rule,
  the cancelled-game rule and how to find the championship tie. **Done when:** a
  search finds no doc calling EuroCup postseason empty or planned.

## Files / areas

- `gold_etl/qualification.py`, `gold_etl/postseason.py`, `gold_etl/team_rounds.py`,
  `gold_etl/series.py`, `gold_etl/per_game_rows.py`, `gold_etl/quality.py`
- `gold_etl/tests/` (`test_series.py`, `test_qualification.py`,
  `test_team_rounds.py` and the PS tests in `test_gold.py`)
- `AGENTS.md`, `README.md`, `gold_etl/README.md`, `docs/GOLD_TABLE_REFERENCE.md`

## Data / contracts

- No new tables or columns. EuroCup gains rows in existing tables: `PS` rows in
  `app_season_player_stats_traditional` and `_misc`, `PS` scope rows in the round
  tables, and `app_postseason_series` rows with EuroCup phase codes (`L32`, `L16`
  for U2007, `8F`, `4F`, `2F`, `Final`).
- EuroLeague rows must be unchanged (step 1 baseline): same phase sets, thresholds
  and series winners.
- Neon is unaffected: publishing is scoped by competition and refuses EuroCup.

## Testing

- `python -m unittest discover -s gold_etl/tests`, then all declared suites.
- Data checks in step 4: both competitions' `--quality-only`, the champion check,
  U2019, and the EuroLeague checksum comparison.

## Notes for the AI

- Keep the definitions in one place; no per-module copies of phase sets.
- U2026's best-of-three `8F` needs no special case: it is not in the two-leg
  table, so it is decided on game wins once its games exist.
- EuroLeague baseline (step 1, 2026-10-26): row count and `md5` of sorted row text for
  14 `E` Gold tables (series 202 rows, season player stats 46,928-51,734 per table,
  `app_standings_stats` 31,716, player round tables 425,922 each,
  `app_game_player_advanced` 155,417, `app_game_team_advanced` 13,342,
  `app_team_pbp_stats` 1,346, `app_player_on_off` 18,770, `app_lineup_ratings`
  623,752). Gold has no build-time columns, so whole rows were hashed.
- Results (step 4):
  - EuroCup `-cp eurocup -sc all` rebuilt (exit 0); `--quality-only` passed with 0
    errors and 21 warnings (was 185): no `below min_games` and no unknown-phase
    warning left. The 21 are API-feed differences: the 17 known U2002-U2007 ones,
    the U2005 true shooting source error, and 4 new U2026 lines (`pir` and
    `turnovers` 1 off for 2 players) from games fetched by today's 18b refresh.
  - Series and `PS` rows in every season with knockout games, every series has a
    winner, U2019 and U2026 have none, and every champion in `silver.seasons` wins
    the last-round `Final` tie (0 mismatches). The 8 drawn-leg ties go to the
    aggregate winner (PAM, ZGO, GAL, BES, TRE, KSK, MUN, STR).
  - EuroLeague `-sc all` rebuilt (exit 0); `--quality-only` passed (22 warnings, as
    before); all 14 tables identical to the baseline (count and checksum).
  - Tests: API 45, Silver 202, Gold 272 (10 new), publisher/CSV 76.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":11698,"specSha256":"a9c6c28ff3fcd0c9c37619c6f2e8ce9797dc8c5b4d26a81a280573425a9bb476","branch":"refs/heads/feature/eurocup-postseason","head":"f29e88b9de19cc2b0beca3f5647addea070caa2e","baseRef":"refs/heads/main","baseCommit":"f29e88b9de19cc2b0beca3f5647addea070caa2e","sourceTree":"4413cb79eb1cd2a6950331382c42f61a0fd149d7","absentOptional":[]} -->

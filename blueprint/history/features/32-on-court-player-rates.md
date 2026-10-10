# Feature: On-court player rates

**From build-plan:** feature 32
**Build attempt:** 1
**Type:** Feature
**Status:** verified
**Branch:** feature/on-court-player-rates

## Goal

Per-game player usage, assist, rebound, steal and block percentages in
`silver.game_player_advanced` (and its Gold copy `gold.app_game_player_advanced`)
use the team and opponent events that actually happened while the player was on
court, counted from play-by-play, instead of spreading the team's game totals
evenly over the game. A player with one shot in one second gets usage 1.0 (100%), not 27.6.
Where no play-by-play exists (before E2007, or any game without events) the
box-score estimate stays, but these rates and game PER are NULL below 3 minutes.

## In scope

- A pure on-court counting step: for every player line, the team's and the
  opponent's events while that player was on court, plus the player's own events
  in those stretches, from the existing substitution walk and counted possessions.
- New formulas for `usage_pct`, `assist_pct`, `orb_pct`, `drb_pct`, `trb_pct`,
  `steal_pct` and `block_pct` from those counts, for games with play-by-play.
- A 180-second floor for the same seven rates where the estimate is used.
- A Silver-only `rate_source` column (`on_court` or `estimate`).
- Game PER (`game_per`) NULL below 180 seconds in every season.
- Silver and Gold quality checks adjusted to the new rules; docs updated.
- Local rebuild of all loaded seasons and a recorded comparison.

## Out of scope

- Per-round tables (26-29): they keep their cumulative box-score formulas.
  `player_round_stats` reads only `game_score` from this table.
- `game_score`, `true_shooting_pct`, `efg_pct`, `tov_pct`: unchanged; they do not
  depend on playing time.
- Neon schema changes (none needed) and the live E2025/E2026 republish, which
  needs separate owner approval after completion.
- Web-app changes in `jmp-euroleague2`.

## Build loop

Config: `stepReview: feature`, `checkpointCommits: disabled`. Implement all
steps, run their checks, then present one review packet. `/complete` makes the
single feature commit.

## Build steps

- [x] 1. **On-court counts (pure).** Add `postgres_etl/on_court_rates.py` with
  `derive_counts(games, players, events)` returning
  `{(game_code, side, person_key): counts}`. Reuse `lineups._walk` (event-order
  stint attribution, any lineup size) and `possessions._count` (closing events);
  no new walk. Before writing formulas, confirm the assist, steal and block event
  codes with a read-only query that compares per-game event totals with the box
  score for one season (`AS`, `ST`, `FV` expected) and record the result.
  Done when unit tests cover: a mid-period substitution, a substitution between
  two free throws, a team rebound without a person, `2FGAB`/`3FGAB` attempts, a
  player event while the walk has him off court (excluded from his own counts but
  kept in team counts), and a game without events (no entry).
- [x] 2. **Silver rates.** In `postgres_etl/advanced.py`, read `play_by_play` with
  the other sources, use the counts for the seven rates when the player's game has
  an entry (`rate_source = 'on_court'`), else the current estimate with NULL for the
  seven rates below 180 seconds (`rate_source = 'estimate'`). Add `play_by_play`
  to the advanced trigger tables so a play-by-play load re-derives them. Add
  `rate_source` (TEXT) to the Silver schema via the existing add-column path.
  Silver checks: ERROR for estimate rows under 180 seconds with any of the seven
  rates; WARN for on-court rows with a rate outside 0-1.
  Done when unit tests prove the Kharchenkov-shaped case (1 s, one shot) gives
  usage 1.0, the floor nulls estimate rates at 179 s but not 180 s, tov/eFG/TS
  and Game Score are unchanged, and a play-by-play-only load triggers the step.
- [x] 3. **Gold.** In `gold_etl/game_advanced.py`, set `game_per` NULL below 180
  seconds; keep the league scaling over all players (so the round-1 PER tie holds)
  and keep `game_uper`/`game_aper`. In `gold_etl/quality.py`, replace the
  "mean game_per is 15" check with: per phase and round, `game_per = game_aper *
  15 / A` for non-null rows, where `A` is the seconds-weighted mean `game_aper`
  of all rows; limit the round-1 `usage_pct` tie to rows whose Silver
  `rate_source` is `estimate`.
  Done when Gold tests cover the PER floor and both changed checks.
- [x] 4. **Rebuild, validate, document.** Run `python postgres_etl/advanced.py
  -sc all` and `python gold_etl/main.py -sc all -tb game_player_advanced` locally,
  then both quality commands. Update `docs/DATA_DICTIONARY.md` (player rate
  formulas, `rate_source`, the floor, game PER), `postgres_etl/README.md` and the
  AGENTS.md advanced-stats trigger line.
  Done when Silver quality has no ERROR, Gold quality has no failure that the
  pre-feature run (`logs/refresh/refresh_20261010_164437.log`) did not have
  (owner decision 2026-10-10: its 11 E2000-E2007 failures go to a separate
  `/fix`), the eight range WARN rows from
  E2023-E2025 are gone, and the evidence records: rows per `rate_source` per
  season, and the median and 90th-percentile difference between on-court and
  estimate usage for players with at least 10 minutes in E2025.

## Files / areas

- New: `postgres_etl/on_court_rates.py`, `postgres_etl/tests/test_on_court_rates.py`
- `postgres_etl/advanced.py`, `postgres_etl/flat_schema.py`, `postgres_etl/main.py`
  (trigger tables come from `advanced.SOURCE_TABLES`), `postgres_etl/tests/test_advanced.py`
- `gold_etl/game_advanced.py`, `gold_etl/quality.py`, matching Gold tests
- `docs/DATA_DICTIONARY.md`, `postgres_etl/README.md`, `AGENTS.md`

## Data / contracts

On-court counts per player line (events attributed to the stint on court at the
event, as `game_team_lineup_stints` does; a player is on court for an event when
he is in his side's lineup of that stint):

| Count | Events |
| --- | --- |
| plays | `2FGM 3FGM LAYUPMD DUNK 2FGA 3FGA LAYUPATT 2FGAB 3FGAB` + 0.44 x (`FTM FTA`) + `TO` |
| fgm | `2FGM 3FGM LAYUPMD DUNK` |
| two_pa (opponent) | `2FGM LAYUPMD DUNK 2FGA LAYUPATT 2FGAB` |
| oreb / dreb | `O` / `D`, including team rebounds without a person |
| possessions (opponent) | closing events from `possessions._count` |

Formulas for `rate_source = 'on_court'` (player counts are his own events while on court):

- `usage_pct` = player plays / team plays
- `assist_pct` = player `AS` / (team fgm - player fgm)
- `orb_pct` = player `O` / (team `O` + opponent `D`); `drb_pct` and `trb_pct` likewise
- `steal_pct` = player `ST` / opponent possessions
- `block_pct` = player `FV` / opponent two_pa

All are fractions rounded to 6 places as today; a zero or missing denominator
gives NULL. A player in the box score with no on-court counts in a game that has
events gets NULL for the seven rates with `rate_source = 'on_court'`.

`rate_source`: TEXT, `on_court` when the game has play-by-play events and the
player's side has starters, else `estimate`. Silver only; Gold and Neon columns
are unchanged, so no migration.

Floor: 180 seconds (`seconds_played < 180` gives NULL) for the seven estimate
rates and for `game_per` in every season.

## Testing

- `python -m unittest discover -s postgres_etl/tests`
- `python -m unittest discover -s gold_etl/tests`
- All four configured suites before review (594 passed at the start of this
  session; no combined Verify command exists).
- Local database evidence from step 4 only; no Neon access.

## Notes for the AI

- Keep `derive_counts` pure, like the other per-game modules; the database
  read stays in `advanced.read_rows`.
- Do not change `lineups._walk` or `possessions._count` behavior; existing stint
  and possession tests must pass unchanged.
- `NULL` means not meaningful, never 0.
- Game PER below 180 seconds keeps `game_uper` and `game_aper` (unscaled
  intermediates) so the scaling stays checkable from stored rows.

## Evidence

- Event codes (step 1, read-only): `AS`, `ST`, `FV`, `TO`, `O`, `D` equal the box
  score's assists, steals, blocks, turnovers and rebounds for all 9,540 E2025
  player-games and 99.7-99.9% of E2007 and E2015 player-games.
- Tests: API 46, Silver 209, Gold 280, publisher/CSV 72 (607) pass; 7 new
  on-court count tests, 3 new Silver tests, 3 new Gold tests.
- Local rebuild: `python postgres_etl/advanced.py -sc all` (E2000-E2026, 0 errors)
  and `python gold_etl/main.py -sc all -tb game_player_advanced`.
- `rate_source`: `estimate` for every row of E2000-E2006 and the 24 rows of
  E2018 game 21 (no play-by-play); `on_court` for every other row of E2007-E2026.
- Silver warnings: 16 on-court rows outside 0-1 over E2007-E2026, all
  `assist_pct`. EuroLeague credits assists that lead to free throws (577 of
  8,596 `AS` in E2015 and 1,307 of 15,150 in E2025 directly precede the club's
  free throws), so assists can exceed the stint's made field goals.
- The eight reported rows (E2023 games 24, 51, 168, 277; E2024 games 10, 177,
  197; E2025 game 223) are now on-court values between 0 and 1 with NULL
  `game_per`; Kharchenkov's usage is 1.0 (was 27.6).
- E2025 players with at least 10 minutes (7,307): on-court usage differs from
  the box-score estimate by 0.0061 at the median and 0.0199 at the 90th
  percentile.
- Gold quality `-sc all`: 13 failure lines versus 17 in the pre-feature run
  `logs/refresh/refresh_20261010_164437.log`; none new. Removed: E2007
  zero-minute `assist_pct` and the E2009, E2011, E2014 round-1 usage ties.
  Remaining 11 (E2000-E2007 zero-minute `tov_pct`/`efg_pct`/TS values and one
  E2002 `game_score` tie) go to a separate `/fix` by owner decision.
- Not run: Neon access, live publish, a full `pipeline.py` run.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":9693,"specSha256":"89964eb61bba11529d055c98309ff1b1aa4d5fbf43f70dca047c8881a062c943","branch":"refs/heads/feature/on-court-player-rates","head":"109e1027262a520ee0320de0c80ae2355a569318","baseRef":"refs/heads/main","baseCommit":"109e1027262a520ee0320de0c80ae2355a569318","sourceTree":"22ffe2ef04e601e8086f1e8488e980f4c629258e","absentOptional":[]} -->

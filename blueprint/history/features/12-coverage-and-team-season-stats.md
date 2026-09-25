# Feature: Coverage and team season stats

**From build-plan:** feature 12
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/coverage-and-team-season-stats`

## Goal

Precompute three tables the jmp-euroleague2 Express API currently computes on
every request: team-season stat totals (own and opponent), season-wide data
coverage counts, and per-game data coverage — so the app can eventually read
ready-made rows instead of aggregating live (that cutover happens in the
web-app repo later, same as records).

## In scope

- `app_team_season_stats` - one row per `(season, phase, club)`: games played,
  and 20 summed box-score measures for the club ("own") and the same 20 for
  its opponents in the same games, from played games only, `stats_kind =
  'total'`. Matches Express `/teams/:clubCode/team-stats?phase=` exactly:
  `points`, `fieldGoalsMade2/Attempted2`, `fieldGoalsMade3/Attempted3`,
  `freeThrowsMade/Attempted`, `fieldGoalsMadeTotal/AttemptedTotal`,
  `totalRebounds`, `defensiveRebounds`, `offensiveRebounds`, `assistances`,
  `steals`, `turnovers`, `blocksFavour`, `blocksAgainst`, `foulsCommited`,
  `foulsReceived`, `valuation`. One row per phase actually present in that
  season's games (`RS`, `PI`, `PO`, `FF`, or older `TS`) — no synthetic "all
  phases" row, matching Express (it has none either).
- `app_coverage_seasons` - one row per season: 8 data-coverage items (box
  scores, period scores, official standings, rosters, player photos, season
  statistics, shot locations, play-by-play), each with a status
  (`available`/`partial`/`incomplete`/`unavailable`/`notYetApplicable`) and
  its available/applicable counts, replicating Express `getCoverage`'s exact
  per-item counting and status logic (see Data/contracts) with one approved
  change: `shotLocations` and `playByPlay` are computed from this pipeline's
  own `app_shots`/`app_play_by_play` data instead of Express's current
  hardcoded `unavailable` (approved 2026-09-25 — Express hasn't been updated
  for feature 21 yet; this is a known, separate fix on that side, not part of
  this feature).
- `app_coverage_games` - one row per game: the same 8 items, scoped the same
  way Express's per-game `/coverage?gameCode=` call scopes them today: box
  scores, period scores, player photos, shot locations, and play-by-play
  narrow to that one game; official standings, rosters, and season statistics
  stay season-wide (same value as the season row) — replicating Express's
  existing behavior exactly, including that quirk.
- Wiring these three into the local load, quality checks, and Neon publish.
  Unlike feature 11's records tables, all three ARE season-scoped (one
  season's rows depend only on that season's already-loaded data), so they
  fit the existing per-season `-sc` load and per-season Neon publish
  (`DELETE ... WHERE season_code = %s`, shrink guard) — no whole-table-replace
  path needed this time.
- `docs/DATA_DICTIONARY.md` entries and tests, same pattern as feature 11.

## Out of scope

- Changing `jmp-euroleague2` to read from these tables instead of computing
  them itself, including the separate Express-side fix to stop hardcoding
  `shotLocations`/`playByPlay` as `unavailable` — coordinated later, like
  every other app-facing table so far.
- Any other coverage item beyond Express's current 8 (no new coverage
  categories invented).
- EuroCup (`competition_code = 'U'`) — still deferred project-wide.
- A synthetic "all phases" row for team-season stats (Express has none).

## Build loop

Per `blueprint/config.json` (`workflow.stepReview: "feature"`), one review
packet after all steps; checkpoint commits disabled. `/complete` makes the
final commit.

## Build steps

- [x] **Step 1 - Schema for the three tables** - Add `app_team_season_stats`
  (key `competition_code, season_code, phase_code, club_code`),
  `app_coverage_seasons` (key `competition_code, season_code`), and
  `app_coverage_games` (key `competition_code, season_code, game_code`) to
  `postgres_etl/flat_schema.py` using the normal `table()` helper (these ARE
  season-scoped, unlike feature 11's records tables). Coverage tables store
  their 8 items as one `items JSONB NOT NULL` column, each item shaped
  `{key, label, status, availableCount, applicableCount}` — matching the
  `app_standings` precedent of JSONB list columns for page-shaped API output,
  instead of 32 flat columns. Add all three to `PUBLISHED_TABLES`. *Done
  when:* `python postgres_etl/main.py --list-tables` lists the three names.
- [x] **Step 2 - Local aggregation** - Add `postgres_etl/aggregates.py` with
  one function per table that computes rows for a given `(competition_code,
  season_code)` from already-loaded local tables (`app_games`,
  `app_game_team_stats`, `app_game_player_stats`, `app_clubs`,
  `app_registrations`, `app_standings_basicstandings`,
  `app_season_stats_traditional`, `app_play_by_play`, `app_shots`) and
  replaces that season's rows (`DELETE ... WHERE competition_code = %s AND
  season_code = %s`, then insert) inside one transaction, mirroring the exact
  Express counting/status logic named in Data/contracts. *Done when:* running
  it against the local dev database for one season populates all three
  tables with the documented row shape, and a manual spot-check (for example
  `app_coverage_seasons.items` for the current season) matches what
  `GET /seasons/current/coverage` returns today (except the two updated
  items).
- [x] **Step 3 - Wire into the loader** - In `postgres_etl/main.py` /
  `postgres_etl/flat_loader.py`, route these three table names to the Step 2
  aggregation instead of the normal bronze-driven load, once per requested
  season (reusing the existing per-season loop, since these are
  season-scoped), respecting `--dry-run` and `--quality-only`. *Done when:*
  `python postgres_etl/main.py -sc current -tb app_team_season_stats
  app_coverage_seasons app_coverage_games` refreshes only those three tables
  for the requested season(s).
- [x] **Step 4 - Quality checks** - In `postgres_etl/quality.py`, add checks
  gated on the three table names: `app_team_season_stats.games_played` is
  non-negative and no summed measure is negative; each coverage row's `items`
  array has exactly 8 entries with the 8 expected keys and a status value from
  the documented enum; `app_coverage_games` has one row per game in
  `app_games` for that season (key-parity check, same pattern as
  `app_standings_key_mismatch`). *Done when:* `python postgres_etl/main.py
  --quality-only -tb app_team_season_stats app_coverage_seasons
  app_coverage_games` reports 0 errors after a fresh Step 2/3 run.
- [x] **Step 5 - Neon publish** - Add the three table names to the normal
  per-season publish path (`neon_publish/publish.py`'s existing
  `publish_season`); no new whole-table-replace logic needed. *Done when:*
  `python neon_publish/main.py --dry-run -tb app_team_season_stats
  app_coverage_seasons app_coverage_games` reports the planned per-season
  replace.
- [x] **Step 6 - Data dictionary** - Document the three tables in
  `docs/DATA_DICTIONARY.md`: columns, the 20 summed measures, the 8 coverage
  items with their status rules, the per-game scoping quirk, and the
  shots/play-by-play computed-from-real-data note. *Done when:* the doc lists
  all three tables consistently with the Step 1 schema.
- [x] **Step 7 - Tests** - Add unit tests under `postgres_etl/tests/` for the
  Step 2 aggregation logic: own/opponent measure summing, phase grouping,
  each coverage item's status derivation (`available`/`partial`/`incomplete`/
  `unavailable`/`notYetApplicable`), and the per-game scoping quirk
  (season-wide items unchanged, game-scoped items narrowed). *Done when:*
  `python -m unittest discover -s postgres_etl/tests` passes, including the
  new tests.

## Files / areas

- `postgres_etl/flat_schema.py` - three new table definitions, `PUBLISHED_TABLES`.
- `postgres_etl/aggregates.py` (new) - aggregation SQL for all three tables.
- `postgres_etl/main.py`, `postgres_etl/flat_loader.py` - route the three
  table names to the new season-scoped aggregation.
- `postgres_etl/quality.py` - new checks for the three tables.
- `postgres_etl/tests/` - new test module for `aggregates.py`.
- `neon_publish/publish.py` - add the three names to the existing per-season
  publish table list (no new function needed).
- `docs/DATA_DICTIONARY.md` - new table documentation.

## Data / contracts

- `app_team_season_stats`: key `(competition_code, season_code, phase_code,
  club_code)`. Columns: `club_name`, `games_played`, then `own_<measure>` and
  `opp_<measure>` (NUMERIC) for each of the 20 measures listed in In scope
  (snake_case, e.g. `own_field_goals_made_2`, `opp_total_rebounds`). "Own" is
  the club's own `game_team_stats` row for a game; "opponent" is the other
  side's row in the same game. Summed only over `games.played = TRUE` and
  `stats_kind = 'total'`.
- `app_coverage_seasons`: key `(competition_code, season_code)`. `items`
  JSONB: exactly 8 objects, in this order and with these exact
  `(availableCount, applicableCount)` definitions (all counts are within that
  season):
  1. `boxScores` — available = games with a `game_team_stats` `total` row;
     applicable = played games. Status via **gameStatus**.
  2. `periodScores` — available = games with a `game_period_scores` row;
     applicable = played games. **gameStatus**.
  3. `officialStandings` — available = distinct clubs in
     `app_standings_basicstandings`; applicable = distinct clubs in
     `app_clubs`. **rosterStatus**.
  4. `rosters` — available = distinct clubs with a non-null-club-code row in
     `app_registrations`; applicable = distinct clubs in `app_clubs`.
     **rosterStatus**.
  5. `playerPhotos` — available = distinct `person_key` with a non-null
     `headshot_url` in `app_game_player_stats` among played games; applicable
     = played games. **gameStatus**. (Numerator is a player count compared
     against a game count — an existing Express quirk, replicated as-is.)
  6. `seasonStatistics` — available = distinct `person_key` in
     `app_season_stats_traditional`; applicable = distinct clubs in
     `app_clubs`. **rosterStatus**. (Same kind of quirk, replicated as-is.)
  7. `shotLocations` — available = games with an `app_shots` row; applicable
     = played games. **gameStatus**. Computed from real data (approved
     change from Express's current hardcoded `unavailable`).
  8. `playByPlay` — available = games with an `app_play_by_play` row;
     applicable = played games. **gameStatus**. Computed from real data
     (same approved change).
  - **gameStatus**(available, applicable): `applicable = 0` →
    `notYetApplicable`; else `available = 0` → `unavailable`; else
    `available >= applicable` → `available`; else `partial`.
  - **rosterStatus**(available, applicable): same as gameStatus but the
    non-complete case is `incomplete` instead of `partial`.
- `app_coverage_games`: key `(competition_code, season_code, game_code)`.
  Same `items` JSONB shape as `app_coverage_seasons`. Items 1, 2, 5, 7, 8
  narrow every count to that one game (so `applicableCount` becomes 0 or 1);
  items 3, 4, 6 keep the season-wide counts unchanged (identical to that
  season's `app_coverage_seasons` row) — this mismatched scoping is
  Express's existing behavior, replicated exactly, not a new design.
- Rebuild is per-season and idempotent: a season's rows are fully replaced
  (delete then insert) from that season's current local data; unrelated
  seasons are untouched. Fits the existing per-season Neon publish path with
  its shrink guard.

## Testing

- `python -m unittest discover -s postgres_etl/tests` covers the aggregation
  and status-derivation logic (Step 7).
- Manual verification per step's *Done when* above: `--list-tables`,
  `--quality-only`, and `neon_publish/main.py --dry-run` output, plus one
  manual comparison against the live Express `/coverage` response for a
  season (excluding the two intentionally changed items).
- No UI to test; this is a data pipeline change only.

## Notes for the AI

- Match `D:\jmp-project\jmp-euroleague2\backend\src\db\season-coverage.ts`
  (`getCoverage`) and `season-games.ts` (`getTeamStatsSummary`,
  `measureFields`, `MEASURE_KEYS`) exactly for counting logic and status
  rules, except the two approved changes (shots/play-by-play computed from
  real data). That file lives in a separate repo and is read-only reference
  here, not an in-scope change.
- These three tables ARE season-scoped (unlike feature 11's records tables),
  so reuse the normal per-season load/publish shape wherever possible; don't
  carry over feature 11's whole-table-replace machinery here, it isn't needed.
- Never leave Neon with a half-replaced season for these tables: same
  per-season transaction safety bar as every other table.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":12898,"specSha256":"c9d14ba1309820bcf784df38c7cf282df2e6ec0183498a57cfc3196af84343f8","branch":"refs/heads/feature/coverage-and-team-season-stats","head":"eb92708e001adc10256f94f684aae27b3bf9b7bc","baseRef":"refs/heads/main","baseCommit":"eb92708e001adc10256f94f684aae27b3bf9b7bc","sourceTree":"f4373d97e9e2f5fcdb8073b5f343dbcd687eea46","absentOptional":[]} -->

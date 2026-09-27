# Feature: API team stats

**From build-plan:** feature 24
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/api-team-stats`

## Goal

Close the one gap in the bronze download: the v3 team statistics feeds. Fetch
`teams/traditional`, `teams/advanced`, `teams/opponentsTraditional` and
`teams/opponentsAdvanced` for every season, phase and mode. Load them into typed
tables that later features use as reference numbers for our own calculations
(features 26-27). Also document what every API endpoint downloads, and which
endpoints were checked and are deliberately not downloaded, so the API survey of
2026-09-27 never has to be repeated.

## In scope

- Fetch the 4 team feeds with the existing v3 season-stats loop: phases `all`
  plus every phase with played games, modes `perGame` and `accumulated`, same
  refresh rules as the player feeds (current season and hot phases re-fetched).
- 4 local tables, one per feed, loaded from bronze with the normal loader,
  dry run, CSV export and quality checks.
- Quality checks: the missing phase/mode warning for the team tables, and a
  points cross-check against `app_team_season_stats` that proves the meaning of
  own and opponent rows.
- Backfill E2000-E2026 into bronze and local PostgreSQL.
- Docs: an endpoint reference and a "checked, not downloaded" list in
  `api_requests/README.md`; "live API" instead of "legacy live API" wording
  there; the new tables in `docs/DATA_DICTIONARY.md` and `postgres_etl/README.md`.

## Out of scope

- Publishing these tables to Neon (reference data, local only).
- Derived postseason (`PS`) team rows; own calculations and full comparisons
  with our numbers (features 25-27).
- The `core` schema move (feature 16; built after this one, it moves these
  tables with the rest). Until then they are named `etl_flat_season_team_stats_*`.
- Downloading any other endpoint: the survey found the rest duplicate data
  already downloaded (see Data / contracts).

## Build loop

`workflow.stepReview` is `feature`: build all steps, then one review packet.
Checkpoint commits are disabled; `/complete` makes the feature commit. API
requests use the existing rate-limited client (2.5 s apart). Nothing touches
Neon.

## Build steps

- [x] **Step 1 - Fetch the team feeds** - add `teams_traditional`,
  `teams_advanced`, `teams_opponents_traditional` and
  `teams_opponents_advanced` to `EuroScrapas.V3_STATISTIC_SPECS` in
  `api_requests/scrapper.py`. The team endpoints reject the player sort
  parameter (`Statistic=points` returns 400), so send `Statistic` only when a
  spec has one. Bronze resources are
  `v3/season_stats/teams_<feed>_<phase>_<mode>` next to the player files.
  Add scrapper tests: the team calls are made per phase and mode, carry no
  `Statistic` parameter, and follow the same hot-refresh rule. *Done when:*
  `cd api_requests && python -m unittest tests.test_scrapper` passes, and
  `python api_requests/main.py -sc 2025 -ds game_lists season_stats` stores 40
  team files for E2025 (4 feeds x 2 modes x `all`, RS, PI, PO, FF) while the
  existing player files stay `[cached]`.
- [x] **Step 2 - Load them into 4 tables** - in `postgres_etl/raw_transform.py`,
  narrow the player source to `v3/season_stats/players_*` and add a
  `season_team_stats` source for `teams_*` files, which fails on an unexpected
  filename as the player one does. In `flat_schema.py`, add
  `season_team_stats_traditional`, `season_team_stats_advanced`,
  `season_team_stats_opponents_traditional` and
  `season_team_stats_opponents_advanced` (contract below). Add loader tests from
  small fixture files: rows per feed, percentage strings as numbers, `NaN%` as
  NULL, and the player feeds unaffected. *Done when:* `python postgres_etl/main.py
  --list-tables` lists the 4 tables; `python postgres_etl/main.py -sc 2025
  --dry-run` passes; `python -m unittest discover -s postgres_etl/tests` passes.
- [x] **Step 3 - Quality checks** - in `postgres_etl/quality.py`:
  - run `season_stats_phase_mode_missing` (WARN) for the 4 team tables too
  - add `team_stats_points_mismatch` (WARN) for `accumulated` rows of real
    phases (not `all`) when `app_team_season_stats` is loaded: traditional
    `points_scored` must equal `own_points`, opponents traditional
    `points_scored` must equal `opp_points`, same season, phase and club

  Add tests. *Done when:* the quality tests pass, and `python
  postgres_etl/main.py -sc 2025 --quality-only` after a real E2025 load
  reports no errors. Any mismatch warning is either 0 or explained in the
  data dictionary.
- [x] **Step 4 - Backfill all seasons** - `python api_requests/main.py -sc
  2000-2026 -ds game_lists season_stats` (about 1,000 team requests, roughly 45
  minutes; run in the background), then `python postgres_etl/main.py -sc all -tb
  <the 4 tables> app_team_season_stats`. *Done when:* every season E2000-E2026
  has rows in all 4 tables, or an empty feed is reported by the missing
  phase/mode warning and listed; the quality report has no errors; the counts
  and warnings are recorded in the review packet.
- [x] **Step 5 - Docs** - `api_requests/README.md`:
  - add an **Endpoint reference** table with one row per downloaded endpoint:
    `-ds` dataset, URL and parameters, bronze resource, contents, seasons
    covered, when it is (re-)fetched, and the tables loaded from it
  - add a **Checked, not downloaded** list with the reason for each endpoint
  - replace "legacy live API" wording with "live API"

  `docs/DATA_DICTIONARY.md` gets a "v3 season team statistics" section, and
  `postgres_etl/README.md` gets the new row in the flat-table design table.
  *Done when:* each downloaded endpoint in `scrapper.py` appears exactly once in
  the reference table, and the docs describe the 4 tables.

## Files / areas

- `api_requests/scrapper.py`, `api_requests/tests/test_scrapper.py`, `api_requests/README.md`
- `postgres_etl/raw_transform.py`, `flat_schema.py`, `quality.py`, `postgres_etl/tests/`
- `docs/DATA_DICTIONARY.md`, `postgres_etl/README.md`

## Data / contracts

- **Source:** `GET https://api-live.euroleague.net/v3/competitions/{E|U}/statistics/teams/{traditional|advanced|opponentsTraditional|opponentsAdvanced}`
  with `SeasonMode=Single`, `SeasonCode`, `StatisticMode` (`perGame` or
  `accumulated`), optional `PhaseTypeCode`, and `Limit`. The response is
  `{"total", "teams": [...]}`; each item has `teamRanking`,
  `team {code, tvCodes, name, imageUrl}` and the metrics. Checked 2026-09-27: it
  covers E2000 onward and accepts a phase filter. E2026 `perGame` without a
  phase returned no teams while games were played, like the player feed (F-01).
- **Tables** (local only, physical names `etl_flat_season_team_stats_*`, CSV
  export includes them). Key: scope + `phase_code`, `mode`, `club_code`. A club
  appears at most once per feed.
  - Identity columns on all 4: `club_name`, `club_tv_codes`, `club_image_url`,
    `team_ranking` (feed position from the source).
  - Traditional and opponents traditional (NUMERIC): `games_played`,
    `minutes_played`, `points_scored`, `two_pointers_made`,
    `two_pointers_attempted`, `two_pointers_percentage`, `three_pointers_made`,
    `three_pointers_attempted`, `three_pointers_percentage`,
    `free_throws_made`, `free_throws_attempted`, `free_throws_percentage`,
    `offensive_rebounds`, `defensive_rebounds`, `total_rebounds`, `assists`,
    `steals`, `turnovers`, `blocks`, `blocks_against`, `fouls_commited`,
    `fouls_drawn`, `pir`.
  - Advanced and opponents advanced (NUMERIC): `games_played`,
    `effective_field_goal_percentage`, `true_shooting_percentage`,
    `offensive_rebounds_percentage`, `defensive_rebounds_percentage`,
    `rebounds_percentage`, `assists_to_turnovers_ratio`, `assists_ratio`,
    `turnovers_ratio`, `two_point_rate`, `three_point_rate`,
    `free_throws_rate`, `points_from_two_pointers_percentage`,
    `points_from_three_pointers_percentage`,
    `points_from_free_throws_percentage`.
  - Percentages are percentage points (`51.7` = 51.7%), `NaN%` is NULL. An
    opponents row describes what that club's opponents did against it.
  - If an older season's feed has extra or missing fields, missing ones stay
    NULL. Extra ones are noted in the review packet; they are not silently added.
- **Endpoints checked 2026-09-27 and not downloaded** (for the README): v3
  player and team `leaders`; v2 and v3 club season `stats`; v2 person season
  `stats`; v2 `teamsComparison`; v3 game `stats` (same as v2); v2 single-item
  endpoints; v2 `venues` (already inside games); the v2 `clubs` catalogue;
  v2 `phases`; live `Header`; the v1 XML endpoints. Each duplicates downloaded
  data or can be calculated from it.

## Testing

- Commands: `cd api_requests && python -m unittest tests.test_scrapper`,
  `python -m unittest discover -s postgres_etl/tests`,
  `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Logic that needs tests: the team specs and the conditional `Statistic`
  parameter, the file routing between player and team sources, the team row
  parsing, and the two quality checks.
- Live evidence: the E2025 fetch and load (steps 1-3) and the full backfill
  (step 4). No combined Verify command exists (build-plan item 17).

## Notes for the AI

- Follow the player season-stats code closely; add no new abstraction.
- `teams/scoring` and `teams/misc` do not exist (404), so the team specs stop at
  the 4 feeds.
- Be polite to the API: never lower the 2.5 s interval, and let the backfill run
  in the background.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":9551,"specSha256":"74f357267f454908f5a1c78479f8815c56f068216a709e85745c5d4e3a0c40c7","branch":"refs/heads/feature/api-team-stats","head":"cee3800c9e938e9fb07e57b17420b177289fee25","baseRef":"refs/heads/main","baseCommit":"cee3800c9e938e9fb07e57b17420b177289fee25","sourceTree":"76f914bc7b44ef273619a37e5d2d688d0d2e7e27","absentOptional":[]} -->

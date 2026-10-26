# Fix: Stale shot-zone docs and live-endpoint comment

**Type:** Fix
**Status:** verified
**Branch:** fix/stale-shot-zone-docs-and-live-endpoint-comment
**Fixes:** F-12, F-13

## The problem

Two leftovers from the fix that stopped publishing unused tables (2026-10-26):

- **F-12:** `docs/SILVER_CATALOG.md:125` maps shots to "Silver shot zones/splits -> Gold game
  copies, team zones and team PBP summaries", and `README.md:87` says the pipeline will
  "build shot splits and zones". Neither Silver `game_team_shot_zones` nor Gold
  `app_game_team_shot_zones`/`app_team_shot_zone_stats` is built any more; the web app
  derives its zones from `app_shots`.
- **F-13:** the comment above `LIVE_ENDPOINTS` in `api_requests/utils.py:46` describes the
  removed optional live datasets ("covered by v2 game data … Requested only when named with
  -ds"), but the constant now holds the two default live endpoints, so it says the opposite
  of what the code does.

## The fix

- `docs/SILVER_CATALOG.md`: "Shots + events + fixtures -> Silver shot splits -> Gold game
  copies and team PBP summaries."
- `README.md`: "build shot splits" instead of "build shot splits and zones".
- `api_requests/utils.py`: replace the two comment lines with one that says what the map is:
  the live API endpoint for each live dataset (the same map as `EuroScrapas.LIVE_DATASETS`).
- Wording and comments only: no behavior, schema or table change. Historical records
  (build plan, project overview, archives, `docs/gold-name-alignment-2026-10-10.md`) keep
  their wording.

## Build steps

1. [x] Edit the two doc lines and the comment. Done when no current doc or code comment says
   shot zones are built or that the live endpoints are optional.

## Verify

- `cd api_requests && python -m unittest tests.test_scrapper` passes (the only code file
  touched is a comment, so this confirms the module still imports).
- Searching current docs (excluding history and the build plan) for "zones" finds only
  statements that the zones are no longer built.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":2033,"specSha256":"59ce036c3324864107b59b1002b96477274ee353d0dbd627da842e2e9ceed61e","branch":"refs/heads/fix/stale-shot-zone-docs-and-live-endpoint-comment","head":"f84abac2f647fa2d6a6f8c400076821dbf75139c","baseRef":"refs/heads/main","baseCommit":"f84abac2f647fa2d6a6f8c400076821dbf75139c","sourceTree":"0502ccfc5af31e09fde1811c75ec1ac95181c890","absentOptional":[]} -->

## Findings

### stale-shot-zone-docs-and-live-endpoint-comment/F-12 [P3] closed - Two current docs still describe shot zones as built

**File:** docs/SILVER_CATALOG.md:125
**Found:** 2026-10-26 by /audit independent (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the spec's Build step 2 is done "when no current doc lists the
seven tables as built or published". `docs/SILVER_CATALOG.md:125` still maps shots to
"Silver shot zones/splits -> Gold game copies, team zones and team PBP summaries", and
`README.md:87` still says the pipeline will "build shot splits and zones". Silver
`game_team_shot_zones`, Gold `app_game_team_shot_zones` and `app_team_shot_zone_stats`
are no longer built (`postgres_etl/shot_zones.py` and `gold_etl/team_shot_zones.py`
removed; local tables dropped). Every other current doc was updated. Nothing breaks at
runtime; a reader would expect tables that do not exist.
**Suggested fix:** change the SILVER_CATALOG row to "Silver shot splits -> Gold game
copies and team PBP summaries" and the README bullet to "build shot splits". Nothing
needs deleting; no current requirement would be lost.
**Resolution:** fixed 2026-10-26 by fix/stale-shot-zone-docs-and-live-endpoint-comment: SILVER_CATALOG row now reads "Silver shot splits -> Gold game copies and team PBP summaries" and the README bullet says "build shot splits". Closed 2026-10-26 by /audit (scope: current; lenses: quality, security, performance, tests): re-read docs/SILVER_CATALOG.md:125 and README.md:87; neither says zones are built, and a search of current docs and code finds only "no longer built" statements.

### stale-shot-zone-docs-and-live-endpoint-comment/F-13 [P3] closed - Stale comment above LIVE_ENDPOINTS describes the removed optional datasets

**File:** api_requests/utils.py:46
**Found:** 2026-10-26 by /audit independent (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the comment "Live API endpoints whose content is covered by v2 game
data, play-by-play or shots (verified on every E2025 game). Requested only when named
with -ds." described the deleted `OPTIONAL_DATASETS`. It now sits directly above
`LIVE_ENDPOINTS = {"play_by_play": "PlayByPlay", "shooting_charts": "Points"}`, the two
live endpoints that are part of the default `all` set, so it states the opposite of what
the constant does.
**Suggested fix:** replace the two comment lines with one such as "Live API endpoints
called for the selected live datasets (same map as EuroScrapas.LIVE_DATASETS)". No
current requirement would be lost.
**Resolution:** fixed 2026-10-26 by fix/stale-shot-zone-docs-and-live-endpoint-comment: the comment now reads "Live API endpoint for each live dataset (same map as EuroScrapas.LIVE_DATASETS)." Closed 2026-10-26 by /audit (scope: current; lenses: quality, security, performance, tests): re-read api_requests/utils.py:46; the comment matches the constant, and api_requests/tests/test_scrapper.py:254 asserts LIVE_ENDPOINTS equals EuroScrapas.LIVE_DATASETS.

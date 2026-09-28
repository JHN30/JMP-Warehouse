# EuroLeague Data ETL - Project Overview

<!-- blueprint:source-hash a8aaba6b860362916419d89dddb760871bd884cbb1af27d2673f5220edbb55ad -->

> The data pipeline behind the JMP EuroLeague web app: EuroLeague API data into
> exact bronze files, typed tables in local PostgreSQL, advanced statistics, and
> app tables in Neon.

## Problem

The JMP EuroLeague web app (`jmpeuroleague.com`, repo `jmp-euroleague2`) needs
complete, correct and current EuroLeague data. The source APIs are rate-limited,
split over three hosts (v2, v3, legacy live), overlap, and have quirks: 0 for
unrecorded stats and crowds, wrong live player ids, cancelled games still marked
"Confirmed". This pipeline fetches once, keeps the exact responses, builds clean
tables and advanced statistics, makes source problems visible, and publishes
what the app reads.

## Users

- **Owner** (single developer) - runs the pipeline; uses local PostgreSQL and
  MSSQL for private analysis and the JMP rating model.
- **Web app** - reads the published Neon tables, never writes.
- **App visitors** - indirect.

## Usage model

- Single operator on a Windows PC; the app reads Neon read-only.
- A publish must never leave the app with a half-loaded or emptied season.
- `NULL` means unavailable, never 0. Every season row carries
  `competition_code` + `season_code`. Known source problems stay visible.
- One owner per aggregation: a figure is computed here or in the app API, not both.
- EuroLeague only for now; EuroCup deferred. 2.5 s between API requests.

## Features

Shipped: 1-14, 21-24, plus fixes (stale stats feeds kept out, docs).

1. **Bronze fetch** - v2/v3 plus live play-by-play and shots into exact, gzipped, versioned files with a manifest.
2. **Current-season refresh** - recent rounds' standings, stats and rosters re-fetched; season-level data re-checked daily.
3. **Local PostgreSQL load** - typed tables with dry run and quality checks.
4. **Source-problem handling** - unrecorded stats as NULL, forfeits, game status, attendance notes, live player id matching.
5. **Neon publish** - one transaction per season, shrink guard, re-runnable.
6. **One-command refresh** - `pipeline.py`, skipped when nothing changed.
7. **CSV export** - one CSV per season and table.
8. **Full EuroLeague history** - E2000-E2025 loaded locally, 0 quality errors.
9. **Standings app table** - `app_standings`, one page-shaped row per club and round.
10. **Manual refresh command** - `python pipeline.py` end to end with safe Neon URL handling, a summary and a log file.
22. **Clean table names** - published tables renamed to `app_*` in Neon `public`.
21. **Play-by-play and shots in Neon** - `app_play_by_play`, `app_shots` for E2025 and E2026.
11. **Records tables** - player-season, single-game and team-season records.
12. **Coverage and team season stats** - precomputed for the app.
13. **Postseason series** - play-in, playoff and Final Four matchups.
14. **Player careers** - `app_players`, cross-season identity on `person_code`.

Next, in build-plan order (IDs are stable, so order is not numeric):

23. **Clean up unused tables** (shipped) - dropped local `etl_flat_live_*` and `etl_source_payloads`, the old Neon `etl_flat_*` views and the 7 Neon `app_standings_*` feed tables.
16. **Silver layer** (shipped) - `silver` schema with 28 clean source tables and provenance from bronze.
30. **Gold layer** - 30a local source projections; 30b `PS` stats and standings; 30c team season stats and coverage; 30d records and postseason series; 30e player and club identity; 30f guarded Neon publishing from Gold; 30g final publishing of the advanced Gold additions after 25-29.
24. **API team stats** (shipped) - v3 team `traditional`, `advanced`, `opponentsTraditional`, `opponentsAdvanced` into bronze and local tables as reference numbers.
25. **Per-game advanced stats** - team and player per game: possessions, pace, ratings, four factors, rates, Game Score; in `silver`.
26. **Per-round team advanced stats** - every round and scope: advanced stats, MOV, Pythagorean, SRS, SOS/SOV, adjusted/relative, home/away, rolling; checked against API team feeds; in `gold`.
27. **Per-round player advanced stats** - every round and scope: USG%, AST%, rebound/steal/block %, per-100, PER, Win Shares, PIE; checked against API player feeds; build in `gold`, publish in 30g.
28. **Standings stats app table** - per-round team advanced stats in `gold` for the standings page; publish in 30g.
19. **Play-by-play analytics** - actual possessions, clutch, runs, lead changes, time leading, second-chance/fast-break/points off turnovers, assisted FG%, shot zones, possession length (E2007+); local only (per-game in `silver`, aggregates in `gold`).
29. **Lineups and on/off** - lineups from substitutions: on/off, lineup and 2/3/5-man ratings, RAPM (E2007+); build in `gold`, publish in 30g.
30g. **Publish completed Gold tables** - after 25-29, publish their new and updated Gold tables to Neon with coordinated web-app contracts; choose exact targets and storage scope in its feature spec.
15. **Historical seasons in Neon** - when Neon storage allows (about 237 MB for all seasons).
17. **Dependencies and CI** - `requirements.txt` and automatic tests.
18. **EuroCup** - download, load and publish.
20. **Scheduled refresh** - run the refresh command automatically.

Advanced stats scope: everything computable from API data. Out for now:
BPM/OBPM/DBPM, VORP, Estimated Wins Added, win probability, WPA (need a fitted
model), tracking and play-type stats (no tracking data in the API).

## Data model

Every season table's primary key starts with `competition_code` (`E`, `U`) and
`season_code` (`E2025` = 2025-26). Codes are text; `person_code` and
`club_code` are stable across seasons. Schemas are defined in
`postgres_etl/flat_schema.py`; physical names come from `physical_name()`.

### Layers

| Layer | Today | Target |
| --- | --- | --- |
| Bronze | `data/bronze/<competition>/<scope>/<resource>/<fetched_at>_<sha16>.json.gz` + `manifest.jsonl` | unchanged (files, not in the database) |
| Silver (feature 16) | `silver.<name>`: 28 clean source tables with provenance, API data only | Per-game enrichment in 25 |
| Gold (feature 30) | `gold.<name>`: 16 source projections and ten derivations, including player and club identities | Advanced tables added by 26-29 |
| Neon | 26 `public.app_*` tables published from Gold for E2026 and competition-wide records and identities | New Gold outputs published in 30g, after 25-29 |

Rule: Gold is built from Silver, never the reverse. The 30f in-place Neon cutover
and first E2026 publish completed on 2026-09-28; future live runs require owner approval.

### Bronze resource

- `manifest.jsonl` per scope: `resource`, `url`, `params`, `status_code`, `fetched_at_utc`, `sha256`, `bytes`, `stored_as`
- New version only when bytes change; readers use the latest

### seasons / clubs / rounds

- seasons: `name`, `start_year`, `start_at`, `end_at`, `champion_club_code`
- clubs (key `club_code`): `name`, `abbreviated_name`, `crest_url`, `country_code`, `venue_code`
- rounds (key `round_key`): `phase_code`, `round_number`, `name`, `first_game_at`, `last_game_at`

### people / registrations

- people (key `person_key` = v2 person code): `person_code`, `name`, `country_code`, `height_cm`, `birth_at`
- registrations (key `registration_key`): `person_key` -> people, `club_code` -> clubs, `role_code` (`J` player, others staff), `dorsal`, `position`, `start_at`, `end_at`

### games

- Key `game_code` (int): `phase_code` (`RS`, `PI`, `PO`, `FF`; older `TS`), `round_number`, `scheduled_at` (timestamptz), `local_club_code`, `road_club_code` -> clubs
- `played` (bool), `game_status` (source), `status` (derived: `completed`, `scheduled`, `awaiting_result`, `postponed`, `cancelled`), `status_note`
- `local_score`, `road_score`, `match_winner_club_code` (NULL until played); `champion_club_code` is the season champion
- `audience` (NULL when the source says 0), `audience_note`, `venue_code`, `venue_name`

### Game detail

- game_period_scores: key `game_code`, `side` (`local`/`road`), `period_number` (5+ overtime) -> `score`
- game_player_stats: key `game_code`, `side`, `person_key` -> people; `club_code`, `points`, `time_played`, shooting made/attempted (2, 3, FT), rebounds, `assistances`, `steals`, `turnovers`, blocks, fouls, `valuation`, `plus_minus`
- game_team_stats: key `game_code`, `side`, `stats_kind` (`team` or `total`); same measures, `coach_code`
- game_stat_gaps: key `game_code`, `stat_name` (column, or `*` for no box score such as a forfeit), `reason`
- game_officials: key `game_code`, `official_number` -> `official_code`, `name`

### Season stats and standings (v3)

- Player season stats (traditional / advanced / scoring / misc): key `phase_code` (`all`, a phase, or derived `PS`), `mode` (`accumulated`, `perGame`), `entry_ordinal`; `person_key`, `club_code`, category metrics
- Team season stats feeds (feature 24): `traditional`, `advanced`, `opponentsTraditional`, `opponentsAdvanced`, per phase and mode, all seasons; reference numbers for the checks in 26
- Standings feeds: key `phase_code`, `round_number`, `club_code` (group-phase rounds only); `app_standings` combines them per club and round (`basic_*`, `calendar_*`, `streaks_*`, `ahead_behind_*`, `margins_*`, `form`, `streak_history` JSONB); contract in `docs/DATA_DICTIONARY.md`

### Live detail (from E2007)

- play_by_play: key `game_code`, `period`, `event_ordinal`; shots: key `game_code`, `shot_ordinal` with `coord_x`, `coord_y`, `points`, `zone`, `fastbreak`, `second_chance`, `points_off_turnover`
- Both: `player_code` (source id), `person_code` -> people, `person_code_method`
- In Neon for E2025 and E2026 only

### Page-shaped app tables (shipped)

- `app_records_*` (not season-scoped, top 50 per metric), `app_team_season_stats` (own/opp totals per phase and club), `app_coverage_seasons` / `app_coverage_games` (8 items JSONB), `app_postseason_series`, `app_players` (not season-scoped); contracts in `docs/DATA_DICTIONARY.md`

### Advanced stats (features 25-29, planned)

- Per game (25): one row per game and club, one per game and player, with opponent context; possessions (box-score estimate), game minutes including overtime, pace, ratings, four factors, player rates, Game Score
- Per round (26 team, 27 player): cumulative after every round for scopes `all`, each phase and `PS`; league averages for relative stats
- Standings stats (28): the per-round team rows the standings page needs, built in Gold and published in 30g
- Play-by-play (19) and lineups (29): counted possessions kept next to the box-score estimate, never replacing it silently
- 30g publishes the new Gold tables after 25-29; its spec confirms exact targets and Neon storage scope

> The separate web app was coordinated for the 30f in-place Gold table and
> column renames; no compatibility views were added (owner decision 2026-09-27).

## Tech stack

- **Python 3.13** - all stages; `requests` (fetch), `psycopg2-binary` (databases); no dbt, DuckDB or ORM
- **Local PostgreSQL 18** - working database with every table
- **Neon PostgreSQL** - app-facing tables only
- **unittest** - tests per stage; MSSQL separately for private analysis

## Monetization

Not applicable to the pipeline.

## UI/UX

No UI. Command-line stages with progress lines, per-season and total timers,
a short run summary, and a quality report that explains every known source gap.

- `python pipeline.py` - refresh the current season end to end
- `api_requests/main.py` - fetch; `postgres_etl/main.py` - load and quality; `neon_publish/main.py` - publish; `tables_to_csv/main.py` - export

## Deployment

- Runs on the owner's Windows PC; data in `data/bronze`, local PostgreSQL on disk D:.
- Refresh: the owner runs one command manually, typically nightly and after each round. Automatic scheduling is feature 20.
- Env: `NEON_DATABASE_URL` (direct, non-pooled). Local DB via `postgres_etl/config_connection.json` (not committed).
- Neon storage is limited; only app-facing tables go there.

## Open questions

> - Feature 15 depends on the Neon plan's storage limit.
> - Monetization of the web app, if any, is unconfirmed (project-plan TODO).
> - Feature 28 vs `app_team_season_stats` (feature 12): whether the new table
>   replaces it or both are kept, for 28's spec (one owner per aggregation).
> - Which possessions value the ratings use once play-by-play possessions exist
>   (E2007+ only), for 19's spec.
> - Pythagorean exponent and SRS method, for 26's spec.

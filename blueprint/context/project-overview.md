# EuroLeague Data ETL - Project Overview

<!-- blueprint:source-hash 11a4d392061d8c4e660ff4c290c942c43ed925d89efcff2a2b2f31a3592064d9 -->

> The data pipeline behind the JMP EuroLeague web app: EuroLeague API data into
> exact bronze files, typed tables in local PostgreSQL, and app tables in Neon.

## Problem

The JMP EuroLeague web app (`jmpeuroleague.com`, repo `jmp-euroleague2`) needs
complete, correct and current EuroLeague data. The source APIs are rate-limited,
split over three hosts (v2, v3, legacy live), overlap, and have quirks: 0 for
unrecorded stats and crowds, wrong live player ids, cancelled games still marked
"Confirmed". This pipeline fetches once, keeps the exact responses, builds clean
tables, makes source problems visible, and publishes what the app reads.

## Users

- **Owner** (single developer) - runs the pipeline; uses local PostgreSQL and
  MSSQL for private analysis.
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

Shipped (1-10):

1. **Bronze fetch** - v2/v3 plus live play-by-play and shots into exact, gzipped, versioned files with a manifest.
2. **Current-season refresh** - recent rounds' standings, stats and rosters re-fetched; season-level data re-checked daily.
3. **Local PostgreSQL load** - typed `etl_flat_*` tables with dry run and quality checks.
4. **Source-problem handling** - unrecorded stats as NULL, forfeits, game status, attendance notes, live player id matching.
5. **Neon publish** - one transaction per season, shrink guard, re-runnable.
6. **One-command refresh** - `pipeline.py`, skipped when nothing changed.
7. **CSV export** - one CSV per season and table.
8. **Full EuroLeague history** - E2000-E2025 loaded locally, 0 quality errors.
9. **Standings app table** - `app_standings`, one page-shaped row per club and round, published next to the 7 old standings tables until the app switches.

10. **Manual refresh command** - `python pipeline.py` refreshes the current season end to end, with safe Neon URL handling, a summary and a log file.

Next, in build-plan order (IDs are stable, so 22 comes before 21):

22. **Clean table names** (headline next feature) - rename the 21 published `etl_flat_*` tables to clean `app_*` names in Neon `public` (for example `app_games`), switched over together with the web-app repo.
21. **Play-by-play and shots in Neon** - publish `app_play_by_play` and `app_shots` for E2025 and E2026 only, for game play-by-play and shot charts in the app.
11. **Records tables** - player-season, single-game and team-season records, excluding forfeits.
12. **Coverage and team season stats** - precomputed for the app.
13. **Postseason series** - play-in, playoff and Final Four matchups from games.
14. **Player careers** - cross-season player dimension on `person_code`.
15. **Historical seasons in Neon** - when Neon storage allows (about 237 MB for all seasons).
16. **Clean app schema** - move the clean-named app tables (feature 22) into a Neon `app` schema with a read-only role.
17. **Dependencies and CI** - `requirements.txt` and automatic tests.
18. **EuroCup** - download, load and publish.
19. **Analytics layer** - play-by-play and shot features, possessions, reports; local only.
20. **Scheduled refresh** - run the refresh command automatically later (Task Scheduler or GitHub Actions).

## Data model

Layers: bronze files -> local PostgreSQL (`public.etl_flat_*`, 33 tables, plus
`app_standings` and `etl_source_payloads`) -> Neon (`public`, 22 app tables: 21
`etl_flat_*` plus `app_standings`). Every table's primary
key starts with `competition_code` (`E`, `U`) and `season_code` (`E2025` =
2025-26). Codes are text; `person_code` and `club_code` are stable across seasons.
Schemas are defined in `postgres_etl/flat_schema.py`.

### Bronze resource

- Path `data/bronze/<competition>/<scope>/<resource>/<fetched_at>_<sha16>.json.gz`; scope is a season or `_catalog`
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
- `played` (bool), `game_status` (source), `status` (derived: `completed`, `scheduled`, `awaiting_result`, `postponed`, `cancelled`), `status_note` (e.g. "inferred")
- `local_score`, `road_score`, `match_winner_club_code` (NULL until played); `champion_club_code` is the season champion
- `audience` (NULL when the source says 0), `audience_note`, `venue_code`, `venue_name`

### Game detail

- game_period_scores: key `game_code`, `side` (`local`/`road`), `period_number` (5+ overtime) -> `score`
- game_player_stats: key `game_code`, `side`, `person_key` -> people; `club_code`, `points`, `time_played`, shooting made/attempted (2, 3, FT), rebounds, `assistances`, `steals`, `turnovers`, blocks, fouls, `valuation`, `plus_minus` (numeric, source spellings)
- game_team_stats: key `game_code`, `side`, `stats_kind` (`team` or `total`); same measures, `coach_code`
- game_stat_gaps: key `game_code`, `stat_name` (column name, or `*` for no box score such as a forfeit), `reason`
- game_officials: key `game_code`, `official_number` -> `official_code`, `name`

### Season stats and standings (v3)

- season_stats_traditional / advanced / scoring / misc: key `phase_code` (`all` or a phase), `mode` (`accumulated`, `perGame`), `entry_ordinal`; `person_key` -> people, `club_code`, category metrics
- standings_basicstandings / calendarstandings / streaks / aheadbehind / margins: key `phase_code`, `round_number`, `club_code`; `position`, `games_played`, `games_won`, `games_lost`, feed metrics (group-phase rounds only)
- standings_calendar_streaks (`streak_ordinal`), standings_basic_form (`result_ordinal`, `result`)

### Live detail (from E2007; E2025-E2026 go to Neon with feature 21)

- play_by_play: key `game_code`, `period`, `event_ordinal`; shots: key `game_code`, `shot_ordinal` with `coord_x`, `coord_y`, `points`, `zone`
- Both: `player_code` (source id), `person_code` -> people, `person_code_method` (`live_id`, `jersey_number`, `name`, `play_by_play`, `season_roster`, `unmatched`)

### app_standings (web-app table, clean names)

- Key `phase_code`, `round_number`, `club_code`; one row per basicstandings club (ERROR check on key parity)
- `club_name`, `club_tv_code`, `crest_url`, `group_name`
- Per-feed columns `basic_*`, `calendar_*`, `streaks_*`, `ahead_behind_*`, `margins_*`: feed prefix + snake_case of the app's `StandingEntry` field (for example `ahead_behind_quarter1_ahead`); all NULL when the feed has no row
- `form` JSONB (`[{resultOrdinal, result}]`), `streak_history` JSONB (`[{streakOrdinal, startAt, endAt, winLossRecord}]`, ISO `...000Z`)
- Contract for the app repo in `docs/DATA_DICTIONARY.md`

> Locked: the 21 `etl_flat_*` Neon tables keep their names and columns until
> feature 22 renames them to `app_*` in `public`, switched over together with
> the app repo (old names stay until the app no longer reads them). New tables
> use clean `app_*` names from the start. Changes are coordinated with the app repo.

### app_play_by_play / app_shots (feature 21)

- Same rows as local play_by_play and shots, E2025 and E2026 only (about 130 MB
  estimated; all seasons about 1.5 GB, too large for the current Neon plan)
- Derived analytics (possessions, features; feature 19) stay local

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
- Refresh: the owner runs one command manually (feature 10), typically nightly and after each round. Automatic scheduling is feature 20.
- Env: `NEON_DATABASE_URL` (direct, non-pooled). Local DB via `postgres_etl/config_connection.json` (not committed).
- Neon storage is limited; only app-facing tables go there.

## Open questions

> - Order of features 11-15 is a proposal (build-plan TODO).
> - Feature 15 depends on the Neon plan's storage limit.
> - Monetization of the web app, if any, is unconfirmed (project-plan TODO).
> - Project plan section 4 says "22 v2/v3 `etl_flat_*` tables"; it is 21 `etl_flat_*` plus `app_standings`.
> - Project plan section 3 still lists standings as next; features 9 and 10 are shipped.
> - Feature 21 needs the free space left in Neon (about 130 MB estimated for
>   two seasons of play-by-play and shots); not checked, since Neon is only
>   accessed with the owner's go-ahead.
> - Feature 22: whether the local tables are renamed too, and when the old Neon
>   `etl_flat_*` tables are dropped after the app switches, is for its spec.

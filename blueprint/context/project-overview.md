# EuroLeague Data ETL - Project Overview

<!-- blueprint:source-hash 3ed25cd46fba61202ee32b5150e70251a18ce1a5a9b125c754ed4fdcb04c62e3 -->

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

In build-plan order (IDs are stable, so order is not numeric). Completion state
lives in `build-plan.md`; open items are 30 (parent), 32, 15, 17, 18 and 20.

1. **Bronze fetch** - v2/v3 plus live play-by-play and shots into exact, gzipped, versioned files with a manifest.
2. **Current-season refresh** - recent rounds' standings, stats and rosters re-fetched; season-level data re-checked daily.
3. **Local PostgreSQL load** - typed tables with dry run and quality checks.
4. **Source-problem handling** - unrecorded stats as NULL with `game_stat_gaps`, forfeits, game status, attendance notes, live player id matching.
5. **Neon publish** - one transaction per season, shrink guard, re-runnable.
6. **One-command refresh** - `pipeline.py`, skipped when nothing changed.
7. **CSV export** - one CSV per season and table.
8. **Full EuroLeague history** - E2000-E2025 loaded locally, 0 quality errors.
9. **Standings app table** - `app_standings`, one page-shaped row per club and round.
10. **Manual refresh command** - `python pipeline.py` end to end with safe Neon URL handling, a summary and a log file.
22. **Clean table names** - published tables renamed to `app_*` in Neon `public`.
21. **Play-by-play and shots in Neon** - `app_play_by_play`, `app_shots` for E2025 and E2026.
11. **Records tables** - player-season, single-game and team-season records, forfeits excluded.
12. **Coverage and team season stats** - precomputed for the app.
13. **Postseason series** - play-in, playoff and Final Four matchups.
14. **Player careers** - cross-season player identity on `person_code`.
23. **Clean up unused tables** - local `etl_flat_live_*` and `etl_source_payloads`, old Neon `etl_flat_*` views and the 7 `app_standings_*` feed tables dropped.
16. **Silver layer** - 16a `silver` schema with 28 clean source tables and standard column names; 16b load log and per-row provenance.
30. **Gold layer** - 30a source projections; 30b `PS` stats and standings; 30c team season stats and coverage; 30d records and postseason series; 30e player and club identity; 30f guarded Neon publishing from Gold.
24. **API team stats** - v3 team `traditional`, `advanced`, `opponentsTraditional`, `opponentsAdvanced` as reference numbers.
25. **Per-game advanced stats** - team and player per game: possessions, pace, ratings, four factors, player rates, Game Score; in `silver`.
26. **Per-round team advanced stats** - 26a cumulative table; 26b SRS/SOS/SOV, adjusted and relative ratings; 26c home/away and rolling; checked against the API team feeds; `gold`.
27. **Per-round player advanced stats** - 27a cumulative rates, per-100, Game Score, PIE; 27b PER; 27c Win Shares; checked against the API player feeds; `gold`, published in 30g.
28. **Standings stats app table** - per-round team advanced stats for the standings page; published in 30g.
19. **Play-by-play analytics** (E2007+) - 19a counted possessions; 19b score flow; 19c shot-based splits and zones (per game, `silver`); 19d aggregates (`gold`).
29. **Lineups and on/off** (E2007+) - 29a on-court intervals; 29b lineup stints and on/off; 29c 2/3/5-man lineup ratings; 29d RAPM; published in 30g.
31. **CSV export of every table** - one CSV per `silver` and `gold` table for SSMS.
30g. **Publish completed Gold tables** - the new Gold tables of 25-29 to Neon with coordinated web-app contracts.
30h. **Publish per-game advanced tables** - `app_game_player_advanced`, `app_game_team_advanced` with game PER (`game_uper`, `game_aper`, `game_per`) matching round-level PER at round 1; E2025 and E2026.
30i. **Publish per-game play-by-play tables** - `app_game_team_possessions`, `_score_flow`, `_shot_splits`, `_shot_zones`; E2025 and E2026.
30j. **Publish on-court, stints and stat gaps** - `app_game_player_on_court`, `app_game_team_lineup_stints`, `app_game_stat_gaps`; E2025 and E2026. 30h-30j add about 25 MB to Neon.
32. **On-court player rates** - per-game usage, assist, rebound, steal and block % from team and opponent play-by-play events during each player's on-court stretches (E2007+), replacing the box-score estimate in `silver.game_player_advanced` and its Gold copy; before E2007 and for game PER the estimate stays, NULL below 3 minutes; republishing E2025 and E2026 needs owner approval.
15. **Historical seasons in Neon** - when Neon storage allows (about 237 MB for all seasons of the app tables).
17. **Dependencies and CI** - `requirements.txt` and an automatic test run.
18. **EuroCup** - download, load and publish.
20. **Scheduled refresh** - run the refresh command automatically (Task Scheduler or GitHub Actions).

Advanced stats scope: everything computable from API data (box scores,
play-by-play, shots). Out for now: BPM/OBPM/DBPM, VORP, Estimated Wins Added,
win probability, WPA (need a fitted model), tracking and play-type stats (no
tracking data in the API).

## Data model

Every season table's primary key starts with `competition_code` (`E`, `U`) and
`season_code` (`E2025` = 2025-26). Codes are text; `person_code` and
`club_code` are stable across seasons. Contracts live in `docs/DATA_DICTIONARY.md`.

### Layers

| Layer | Contents |
| --- | --- |
| Bronze | `data/bronze/<competition>/<scope>/<resource>/<fetched_at>_<sha16>.json.gz` + `manifest.jsonl`; files, not in the database |
| Silver (16) | `silver.<name>`: 28 clean source tables with provenance, API data only, plus per-game enrichment (25, 19a-19c, 29a-29b, 32) |
| Gold (30) | Built from Silver: source projections, page and aggregate tables, identities, per-round advanced stats (26-29) and per-game copies (30h-30j) |
| Neon | The app-facing subset of Gold in `public.app_*`, season-scoped tables for E2025 and E2026 plus competition-wide records and identities |

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
- game_player_stats: key `game_code`, `side`, `person_key` -> people; `club_code`, `points`, `seconds_played`, shooting made/attempted (2, 3, FT), rebounds, `assists`, `steals`, `turnovers`, blocks, fouls, `pir`, `plus_minus`, `started`
- game_team_stats: same measures per `game_code`, `side`; team and total rows
- game_stat_gaps: key `game_code`, `stat_name` (column, or `*` for no box score such as a forfeit)
- game_officials: key `game_code`, `official_number` -> `official_code`, `name`

### Season stats and standings (v3)

- Player season stats (traditional / advanced / scoring / misc): key `phase_code` (`all`, a phase, or derived `PS`), `mode` (`accumulated`, `perGame`), `entry_ordinal`; `person_key`, `club_code`, category metrics
- Team season stats feeds (24): per phase and mode, all seasons; reference numbers for the checks in 26
- Standings feeds: key `phase_code`, `round_number`, `club_code`; `app_standings` combines them per club and round

### Live detail (from E2007)

- play_by_play: key `game_code`, `period`, `event_ordinal`; shots: key `game_code`, `shot_ordinal` with coordinates, `points`, `zone`, `fastbreak`, `second_chance`, `points_off_turnover`
- Both: `person_code` -> people, with the matching method recorded

### Advanced stats

- Per game (25): one row per game and club, one per game and player, with opponent context; possessions (box-score estimate), game minutes including overtime, pace, ratings, four factors, player rates, Game Score
- Per-game player rates (32): usage, assist, offensive/defensive/total rebound, steal and block % use team and opponent events counted during the player's on-court stretches (E2007+); before E2007 they and game PER keep the box-score estimate, NULL under 3 minutes played
- Play-by-play (19) and lineups (29): counted possessions kept next to the box-score estimate, never replacing it silently; on-court intervals and five-man stints per game
- Per round (26 team, 27 player): cumulative after every round for scopes `all`, each phase and `PS`; league averages for relative stats

## Tech stack

- **Python 3.13** - all stages; `requests` (fetch), `psycopg2-binary` (databases); no framework, dbt, DuckDB or ORM
- **Local PostgreSQL 18** - working database with every table
- **Neon PostgreSQL** - app-facing tables only
- **unittest** - tests per stage; MSSQL separately for private analysis

## Monetization

Not applicable to the pipeline.

## UI/UX

No UI. Command-line stages with progress lines, per-season and total timers,
a short run summary, and a quality report that explains every known source gap.

## Deployment

- Runs on the owner's Windows PC. The owner starts the refresh manually with one command, typically nightly and after each round. Automatic scheduling is feature 20.
- Env: `NEON_DATABASE_URL` (direct, non-pooled). Local DB via `postgres_etl/config_connection.json` (not committed).
- Neon storage is limited; only app-facing tables go there.

## Open questions

> - Feature 15 depends on the Neon plan's storage limit.
> - Monetization of the web app, if any, is unconfirmed (project-plan TODO).

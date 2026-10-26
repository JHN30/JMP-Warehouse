# Build Plan

List the features that make up your project, high level and in rough build order.
Keep each item to one line; the details come later in `/feature`.

Plain bullets are fine. When both planning docs are ready, run `/overview`.
It adds tracking numbers and checkboxes to your feature list before generating
the project overview.

Run `/feature` to spec the next unchecked item, or `/feature 2` to pick one.
Keep completed items checked and append new features as the project grows.
Do not renumber completed features; their archived specs refer to those IDs.

Scaffolding the app and prototyping its look are pre-build steps, not features.
Start with your first real slice of functionality.

## Your features

Items 1-8 were already shipped when the Blueprint was adopted (2026-09-24).

- [x] 1. **Bronze fetch** - rate-limited download of v2/v3 plus live play-by-play and shots into exact, gzipped, versioned files with a request manifest
- [x] 2. **Current-season refresh** - re-fetch recent rounds' standings, stats and rosters automatically; daily re-check of season-level data
- [x] 3. **Local PostgreSQL load** - typed `etl_flat_*` tables from bronze with dry run and post-load quality checks
- [x] 4. **Source-problem handling** - unrecorded stats as NULL with `game_stat_gaps`, forfeits, derived game status, attendance notes, live player id matching
- [x] 5. **Neon publish** - replace a season in one transaction with a shrink guard, re-runnable
- [x] 6. **One-command refresh** - `pipeline.py` fetch, load and publish, skipped when nothing changed
- [x] 7. **CSV export** - local tables to one CSV per season and table
- [x] 8. **Full EuroLeague history** - E2000-E2025 downloaded and loaded locally with 0 quality errors
- [x] 9. **Standings app table** - one page-shaped standings table published to Neon, replacing the 7 standings tables the app reads (coordinated with the web-app repo)
- [x] 10. **Manual refresh command** - one command the owner runs when wanted that refreshes the current season end to end (fetch, load, quality checks, publish), handles the Neon URL safely, and ends with a clear summary and a log file
- [x] 22. **Clean table names** - rename the 21 published `etl_flat_*` tables to clean `app_*` names in Neon's `public` schema (for example `app_games`), switched over together with the web-app repo
- [x] 21. **Play-by-play and shots in Neon** - publish play-by-play and shots as `app_play_by_play` and `app_shots` for E2025 and E2026 so the app can show game play-by-play and shot charts (coordinated with the web-app repo)
- [x] 11. **Records tables** - precomputed player-season, single-game and team-season records, excluding forfeits, instead of computing them in the Express API
- [x] 12. **Coverage and team season stats** - precomputed coverage counts and team season aggregates for the app
- [x] 13. **Postseason series** - play-in, playoff and Final Four matchups derived from games
- [x] 14. **Player careers** - cross-season player dimension on `person_code` for careers, archives and head-to-head
- [x] 23. **Clean up unused tables** - drop the local `etl_flat_live_*` tables (E2025 only, not fetched by default) with their loader code and `etl_source_payloads` (bronze stays the raw archive); in Neon, drop the old `etl_flat_*` views and the 7 unused `app_standings_*` feed tables
- [x] 16. **Silver layer** - `silver` schema in local PostgreSQL with the 28 source tables rebuilt from bronze
  - [x] 16a. **Silver schema and clean names** - the 28 tables in `silver` with clean table names and one standard column name per stat (for example `assists`, `fouls_committed`, `pir`, `seconds_played`); API data only (derived `PS` rows out); today's gold code removed and Neon publishing paused until feature 30; one-time drop/rename commands removed; all local `public` tables dropped and every season rebuilt
  - [x] 16b. **Silver provenance** - a load log per table and season with the bronze file versions used, and load id and load time on every silver row
- [ ] 30. **Gold layer** - `gold` schema rebuilt from silver: page and aggregate tables (standings, records, coverage, postseason series, team season stats, derived `PS` stats), cross-season player and club identity tables, publishing of the current app tables, and a final publish of new Gold outputs after features 25-29
  - [x] 30a. **Gold schema and source projections** - build the 16 app-facing source tables in local `gold` from silver, with clean names and source values; keep publishing paused
  - [x] 30b. **Gold PS stats and standings** - derive postseason `PS` season-player stats and the page-shaped standings table from silver
  - [x] 30c. **Gold team season stats and coverage** - rebuild team-season totals and season/game coverage tables from silver
  - [x] 30d. **Gold records and postseason series** - rebuild all-time records and play-in, playoff and Final Four series from silver
  - [x] 30e. **Gold player and club identity** - build cross-season identity tables from silver registrations, people and clubs
  - [x] 30f. **Publish Gold to Neon** - publish the app-facing Gold tables with guarded season transactions and resume the refresh pipeline
- [x] 24. **API team stats** - fetch the v3 team `traditional`, `advanced`, `opponentsTraditional` and `opponentsAdvanced` feeds (per phase, both modes, all seasons) into bronze and `core` as reference numbers
- [x] 25. **Per-game advanced stats** - per game, team and player (with opponent): possessions, pace, ratings, four factors, player rates and Game Score, in `silver` (enrichment per record)
- [x] 26. **Per-round team advanced stats** - cumulative after every round for scopes `all`, each phase and `PS`: team and opponent advanced stats, MOV, Pythagorean, SRS, SOS/SOV, adjusted and relative ratings, home/away and rolling, checked against the API team feeds, in `gold`
  - [x] 26a. **Cumulative team-round table** - `gold.team_round_stats`: cumulative own and opponent totals, record, MOV, Pythagorean wins, possessions, pace, ratings and four factors after every round for `all`, each phase and `PS`, checked against the API team feeds; local only
  - [x] 26b. **Strength-adjusted team ratings** - SRS, SOS, SOV, adjusted and relative ratings per round, using league averages per scope and round
  - [x] 26c. **Home/away and rolling team stats** - home and away splits and last-N-game rolling windows per round
- [x] 27. **Per-round player advanced stats** - cumulative after every round for the same scopes: USG%, AST%, rebound/steal/block %, per-100 stats, PER, Win Shares and PIE, checked against the API player feeds; build in `gold`, publish in 30g
  - [x] 27a. **Cumulative player-round table** - `gold.player_round_stats`: cumulative totals, minutes, TS%/eFG%, USG%, AST%, rebound/steal/block/turnover %, per-100 stats, Game Score and PIE after every round for `all`, each phase and `PS`, checked against the API player feeds; local only
  - [x] 27b. **Player efficiency rating** - PER per round from league constants computed per scope and round
  - [x] 27c. **Win Shares** - offensive, defensive and total Win Shares and WS/48 per round from marginal offense and defense
- [x] 28. **Standings stats app table** - per-round team advanced stats in `gold` for the standings page, publish in 30g
- [x] 19. **Play-by-play analytics** - actual possessions, clutch, scoring runs, lead changes, time leading, second-chance/fast-break/points off turnovers, assisted FG%, shot zones and possession length (E2007+), local only (per-game in `silver`, aggregates in `gold`)
  - [x] 19a. **Counted possessions** - actual possessions and possession length per team and game from the play-by-play event stream, kept next to the box-score estimate (E2007+); `silver`, local only
  - [x] 19b. **Score flow** - lead changes, time leading, largest lead, scoring runs and clutch results per team and game from play-by-play (E2007+); `silver`, local only
  - [x] 19c. **Shot-based splits** - second-chance, fast-break and points off turnovers, assisted FG% and shot zones per team and game from shots and play-by-play (E2007+); `silver`, local only
  - [x] 19d. **Play-by-play aggregates** - per-season team (and player where it fits) aggregates of 19a-19c by phase; `gold`, local only
- [x] 29. **Lineups and on/off** - on-court lineups rebuilt from play-by-play substitutions: on/off ratings, lineup, 2/3/5-man ratings and RAPM (E2007+), build in `gold`, publish in 30g
  - [x] 29a. **On-court reconstruction** - per-game player on-court intervals rebuilt from starters and play-by-play substitutions, validated against box-score minutes (E2007+); `silver`, local only
  - [x] 29b. **Lineup stints and on/off** - five-man stints with time, possessions and points per team and game, plus per-player on/off ratings per season and scope; `silver` stints, `gold` on/off, local only
  - [x] 29c. **Lineup ratings** - 2, 3 and 5-man lineup ratings per club, season and scope with possessions stored; `gold`, local only
  - [x] 29d. **RAPM** - regularized adjusted plus-minus (ridge, offense and defense, penalty by cross-validation) per player and season; `gold`, local only
- [x] 31. **CSV export of every table** - export every `silver` and `gold` table to one CSV file per table (all seasons) for import into SSMS; `tables_to_csv`, local only
- [x] 30g. **Publish completed Gold tables** - after 25-29, publish their new and updated Gold tables to Neon, update the refresh and quality paths and coordinate their web-app contracts; confirm the exact table list and Neon storage scope in its feature spec
- [x] 30h. **Publish per-game advanced tables** - build `app_game_player_advanced` and `app_game_team_advanced` in `gold` from the item 25 Silver tables, add game PER (`game_uper`, `game_aper`, `game_per`) matching the round-level PER at round 1, and register both in the Neon publisher for E2025 and E2026; live migration and publish need separate owner approval
- [x] 30i. **Publish per-game play-by-play tables** - build and publish `app_game_team_possessions`, `app_game_team_score_flow`, `app_game_team_shot_splits` and `app_game_team_shot_zones` from the item 19 Silver tables for E2025 and E2026 (about 25 MB for all of 30h-30j in Neon)
- [x] 30j. **Publish on-court, stints and stat gaps** - build and publish `app_game_player_on_court`, `app_game_team_lineup_stints` and `app_game_stat_gaps` for E2025 and E2026
- [x] 32. **On-court player rates** - per-game usage, assist, rebound, steal and block % counted from team and opponent play-by-play events during each player's on-court stretches (E2007+), replacing the box-score estimate in `silver.game_player_advanced` and its Gold copy; before E2007, and for game PER, keep the estimate and store NULL below 3 minutes; republishing E2025 and E2026 needs owner approval
- [x] 15. **Historical seasons in Neon** - publish older seasons once Neon storage allows (app tables for all seasons are about 237 MB)
- [ ] 17. **Dependencies and CI** - `requirements.txt` and an automatic test run so the project installs and verifies anywhere
- [ ] 18. **EuroCup** - download, load and publish EuroCup seasons
- [x] 20. **Scheduled refresh** - run the refresh command automatically (Windows Task Scheduler or GitHub Actions), nightly and after each round

> Layers (agreed 2026-09-27): bronze = the downloaded files; `silver` = cleaned,
> standardized per-record tables (plus per-record enrichment); `gold` =
> aggregates, page-shaped and identity tables, and what Neon gets. The web app
> is still in development and is updated afterwards; no compatibility views.
>
> Advanced stats scope (agreed 2026-09-26): everything computable from API data
> (box scores, play-by-play, shots). Left out for now: BPM/OBPM/DBPM, VORP,
> Estimated Wins Added, win probability and WPA (they need a model fitted on
> EuroLeague data, part of the JMP model work), and tracking or play-type
> statistics (the API has no tracking data). The web-app pages (home, overview,
> standings) are updated later in `jmp-euroleague2`.

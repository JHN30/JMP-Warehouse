# Project Plan

> Adopted from the existing codebase on 2026-09-24 (`/adopt`). Sections 3-5
> describe what already exists; the rest comes from the owner's answers. Items
> marked `TODO (confirm)` are inferences to check.

## 1. Problem - What problem are we solving?

The JMP EuroLeague web app (`jmpeuroleague.com`, separate repo `jmp-euroleague2`)
is a public, read-only EuroLeague explorer. It needs complete, correct and
current data, but the EuroLeague APIs are rate-limited, spread over three hosts
(v2, v3 and the legacy live API), overlap, and have quirks: unrecorded stats
stored as 0, wrong player ids in the live feed, cancelled games still marked
"Confirmed", attendance 0 for unknown crowds.

This project is the data pipeline behind the app. It downloads the API data
once, keeps the exact responses, turns them into clean typed tables in a local
PostgreSQL database, makes source problems visible instead of silently fixing
them, and publishes the tables the app needs to Neon, refreshed during the
season.

## 2. Users - Who is this for?

- **The owner** (a single developer): runs and maintains the pipeline, and
  uses the local database (and MSSQL) for private analysis.
- **The JMP EuroLeague web app**: the consumer of the published Neon tables. It
  never writes to the database.
- Indirectly, visitors of the web app.

## 3. Features - What does the MVP need?

Existing (shipped):

- Rate-limited fetch of every needed endpoint into a bronze store of exact,
  gzipped, versioned responses with a request manifest
- Automatic current-season refresh (recent rounds, rosters, standings, stats)
- Local PostgreSQL load into typed `etl_flat_*` tables with quality checks
- Source-problem handling: unrecorded stats as NULL, forfeits, game status,
  attendance notes, live player id matching
- Safe Neon publish: one transaction per season, shrink guard, re-runnable
- One-command refresh (`pipeline.py`) that skips work when nothing changed
- CSV export of local tables

Shipped since adoption: page-shaped web-app tables (standings, records,
coverage, team season stats, postseason series, players), clean `app_*` names,
and play-by-play and shots in Neon.

Next (agreed 2026-09-26): clean up unused tables, split the database into
schemas, then advanced statistics computed from API data (box scores,
play-by-play, shots), stored for every round so they serve the web app's
standings page, the owner's JMP rating model and general analytics. The API's
own team and player season numbers are kept as reference and used to check our
calculations; where we can calculate more exactly than the API (for example
possessions counted from play-by-play), we do, keeping both values. Order and
details are in `build-plan.md`.

## 4. Data - What are we storing?

- **Bronze** (`data/bronze/`): exact API responses per competition, season and
  resource, with `manifest.jsonl`. EuroLeague E2000-E2026, about 174 MB.
- **Local PostgreSQL** (about 2 GB), today all in `public`: the `app_*` tables
  (seasons, clubs, people, registrations, rounds, games with status and
  attendance notes, officials, period scores, player and team box scores, v3
  player season stats in 4 categories, v3 standings feeds, play-by-play and
  shots from E2007, and the page-shaped tables), plus `etl_flat_game_stat_gaps`,
  the unused `etl_flat_live_*` tables and `etl_source_payloads` (a copy of
  bronze), the last two to be dropped.
- **Target layers (medallion, agreed 2026-09-27):**
  - **Bronze** - the downloaded files in `data/bronze/` (not in the database).
  - `silver` schema - one validated, non-aggregated table per source (28
    tables): typed, deduplicated, `NULL` for unrecorded values, source errors
    corrected, clean table names and one standard column name per stat
    (for example `assists`, `fouls_committed`, `pir`), provenance columns (bronze version, load
    time), API data only. Per-record enrichment (per-game advanced stats) also
    lives here.
  - `gold` schema - built from silver: page-shaped and aggregate tables
    (standings, records, coverage, postseason series, team season stats,
    derived `PS` stats, per-round advanced stats), cross-season player and club
    identity tables. Neon gets a subset of gold; some gold tables stay local.
  - Gold may be built from silver, never the reverse. The old `public` tables
    (`app_*`, `etl_flat_*`) are dropped when silver is built.
- **Advanced stats grain:** cumulative after every round, for the scopes `all`,
  each phase (`RS`, `PI`, `PO`, `FF`, older `TS`) and `PS` (all postseason
  phases).
- **Neon:** today the `app_*` tables in `public`, for E2025 and E2026 only (all
  seasons of the app tables would be about 237 MB; play-by-play and shots for
  all seasons about 1.5 GB, too large for the current plan). Target: gold tables
  published with a read-only role (feature 30); the web app is still in
  development and is updated after the rename, so no compatibility views.
  Per-round team advanced stats go to Neon for the standings
  page; per-round player advanced stats stay local because of storage.
- Keys are source natural keys scoped by `competition_code` + `season_code`.
  `person_code` is stable across seasons.

## 5. Tech - What stack are we using?

- Python 3.13 (standard library, `requests`, `psycopg2-binary`), no framework.
- Local PostgreSQL 18 as the working database. Neon PostgreSQL for the app.
- Plain `unittest` tests. No dbt or DuckDB: the owner chose tools they already
  know. MSSQL is used separately for private analysis.
- Windows workstation. The app side is Node/Express with Drizzle.

## 6. Monetize - How will this make money?

Not applicable to the pipeline. > TODO (confirm) whether the web app has any
monetization that affects data needs.

## 7. UI/UX - How should this look and feel?

No UI. Output is terminal and log files: concise progress lines with per-season
and total timers, a short run summary at start, and a quality report whose
warnings explain every known source gap.

## 8. Deployment - Where and how will this ship?

- Runs on the owner's Windows PC. A Windows Task Scheduler task (feature 20)
  runs the refresh daily at 06:00 while the owner is logged on and catches up
  after a missed start; the owner can still run it manually with one command
  (feature 10). GitHub Actions is not used: the pipeline needs the local Bronze
  cache and the local PostgreSQL warehouse.
- Needs `NEON_DATABASE_URL` (direct, non-pooled) in the environment and
  `postgres_etl/config_connection.json` for local PostgreSQL (not committed).
- Neon plan storage is limited; only app-facing tables go there.

## 9. Usage model and constraints (optional)

- Single operator; the app reads Neon read-only.
- Publishing must never leave the app with a half-loaded or emptied season.
- `NULL` means unavailable, never 0. Every season row carries
  `competition_code` + `season_code`. Known source problems stay visible.
- One owner per aggregation: a figure is computed either here or in the API.
- EuroLeague only for now; EuroCup is deferred.
- Be polite to the EuroLeague API (2.5 s between requests).

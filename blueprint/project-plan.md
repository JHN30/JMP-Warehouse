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

Next: page-shaped tables for the web app (standings first), scheduling, then
the items in `build-plan.md`.

## 4. Data - What are we storing?

- **Bronze** (`data/bronze/`): exact API responses per competition, season and
  resource, with `manifest.jsonl`. EuroLeague E2000-E2026, about 174 MB.
- **Local PostgreSQL** (about 2 GB): 33 `etl_flat_*` tables. Seasons, clubs,
  people, registrations, rounds, games (with status and attendance notes),
  officials, period scores, player and team box scores, stat gaps, v3 season
  stats (4 categories), v3 standings (7 feeds), play-by-play and shots (from
  E2007), plus `etl_source_payloads`.
- **Neon** (`public` schema): the 22 v2/v3 `etl_flat_*` tables the app reads,
  currently for E2025 and E2026 only. All seasons would be about 237 MB.
  Feature 22 renames them to clean `app_*` names in `public` (the `app` schema
  and read-only role stay in feature 16). Feature 21 then adds play-by-play
  and shots as `app_play_by_play` and `app_shots`, for E2025 and E2026 only
  (all seasons would be about 1.5 GB, too large for the current plan). Derived
  analytics (feature 19) stay local.
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

- Runs on the owner's Windows PC. For now the owner starts the refresh manually
  with one command (feature 10), typically nightly and after each round.
  Automatic scheduling (Task Scheduler or GitHub Actions) comes later (feature 20).
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

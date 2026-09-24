# Pipeline Handoff: JMP EuroLeague web app → data pipeline

Context carried over from a planning session in the **web app repo** (`jmp-euroleague2`)
into the **data pipeline repo** (where EuroLeague data is downloaded and cleaned).
The web app is the consumer; the pipeline is the producer. Snapshot date: 2026-09-24.

**First task in the pipeline repo:** analyse the existing download/cleaning code,
answer the open questions in section 6 from what the code actually does, then
propose how the current flow maps onto the target architecture in section 5.
Do not start rewriting before that mapping is reviewed with the owner.

---

## 1. The web app (consumer)

- Public, read-only EuroLeague explorer at `jmpeuroleague.com`. No accounts, no user data.
- Frontend: React + Vite + React Router, Tailwind/DaisyUI, Chart.js, TanStack Query.
- Backend: Node.js + Express 5 + strict TypeScript + Drizzle ORM (`pg` driver). Deployed on Render.
- Database: **Neon PostgreSQL**. Backend env var is `DB_URL` (not `DATABASE_URL`).
- The app **never writes** to the database. It only reads pipeline-produced tables.
- Scope: competition `E` (EuroLeague) only; seasons hard-coded as
  `SUPPORTED_SEASONS = ["E2025", "E2026"]` in `backend/src/db/season-catalog.ts`.
  Older seasons, EuroCup, predictions and ratings are deferred, but the site already has
  cross-season features (records, career history, head-to-head), so more seasons are the
  expected next step.
- Most of the planned features (1–17h) are built. The UI is ahead of the data model.

### Rules the app relies on (the pipeline must preserve them)

- **`NULL` means unavailable, never zero.** Do not coalesce missing stats to 0.
- Every season-dependent row carries `competition_code` + `season_code`; the app always
  filters by both. Keep source natural keys (composite), not opaque surrogate IDs.
- Known corrections, gaps and anomalies should be visible, not silently filled or fixed.
- Game status must distinguish scheduled / live-unknown / postponed-cancelled / completed.
- One owner per aggregation: either the pipeline or the API computes a figure, never both.

## 2. Current data contract (what the API reads today)

All tables live in Neon `public`, named `etl_flat_*`. They are produced by an existing
process referred to as `postgres_etl` (`create_v2_v3_tables.sql` in the app repo says:
"Generated from CSV headers and postgres_etl.flat_schema"). Full DDL is in that file.

| Table | Primary key (after `competition_code, season_code`) | Used by |
| --- | --- | --- |
| `etl_flat_seasons` | — | catalog |
| `etl_flat_rounds` | `round_key` (+ `phase_code`, `round_number`) | catalog, phases |
| `etl_flat_games` | `game_code` (int) | fixtures, game detail, records |
| `etl_flat_clubs` | `club_code` | teams, crests |
| `etl_flat_people` | `person_key` (**per-season key**) | players |
| `etl_flat_registrations` | `registration_key` | rosters (role `J` = player, others are staff) |
| `etl_flat_game_period_scores` | `game_code, side, period_number` | game detail |
| `etl_flat_game_team_stats` | `game_code, side, stats_kind` | box scores, team stats, records |
| `etl_flat_game_player_stats` | `game_code, side, person_key` | box scores, game logs, records |
| `etl_flat_standings_basicstandings` | `phase_code, round_number, club_code` | standings |
| `etl_flat_standings_calendarstandings` | same | standings |
| `etl_flat_standings_streaks` | same | standings |
| `etl_flat_standings_aheadbehind` | same | standings |
| `etl_flat_standings_margins` | same | standings |
| `etl_flat_standings_calendar_streaks` | + `streak_ordinal` | standings |
| `etl_flat_standings_basic_form` | + `result_ordinal` | standings form |
| `etl_flat_season_stats_traditional` | `phase_code, mode, entry_ordinal` | leaderboards, player stats, records |
| `etl_flat_season_stats_advanced` | same | leaderboards |
| `etl_flat_season_stats_scoring` | same | leaderboards |
| `etl_flat_season_stats_misc` | same | leaderboards |

Present in the DDL but **not read by the app**: `etl_flat_game_officials`.

### Value conventions the app code depends on

- `competition_code = 'E'`; `season_code` like `E2025`.
- `side` ∈ `local` | `road`; team box score totals use `stats_kind = 'total'`.
- Season stats: `phase_code` ∈ `RS`, `PI`, `PO`, `FF`, `all`; `mode` ∈ `accumulated`, `perGame`.
- Box-score measures are `numeric`. Column names follow the source API, including its
  misspellings (`fouls_commited`, `assistances`, `possesions`, `quater1_ahead`). A clean
  gold layer can fix these, but that requires a coordinated app-side change.
- `games.played` (boolean) marks completed games; `scheduled_at` is timestamptz.

### Aggregations the API currently computes (should move to gold)

These live in `backend/src/routes/seasons.ts` and `backend/src/db/*.ts` and are the
best candidates for precomputed `gold_app` tables:

- **Records** (`/records/player-seasons`, `/single-games`, `/team-seasons`): loops over
  every supported season, fetches top-N per season, merges and sorts in JavaScript.
  Team-season records sum `game_team_stats` per club in SQL at request time.
- **Coverage** (`/coverage`): counts distinct games and players across six tables per request.
- **Team season stats** (`/teams/:clubCode/team-stats`): derived from game team stats.
- **Player identity across seasons**: `person_key` is per season, so career and archive
  views have no clean cross-season player dimension.

### Data the UI wants but no table provides

The app shows honest "unavailable" states for these today:

- Shots / shot locations, play-by-play, venue, attendance (officials exist but aren't wired up).
- Phase table, postseason matchups/series (play-in, playoffs, Final Four brackets),
  team season aggregates, data-quality annotations (target record, flag, public note).

## 3. Scale assumptions

- Data is small: all EuroLeague seasons with play-by-play and shots is likely a few GB
  of raw JSON and a few million rows. Single-node tools are enough.
- Neon has limited storage on small plans, so only app-facing data should live there.
- Refresh schedule, retries and idempotency are undecided. The app plan explicitly says
  not to add a production cron until these are defined.

## 4. Decision taken: no Databricks for now

Databricks (Spark clusters) is built for terabyte-scale distributed compute. Here it would add
cost, cold starts and Spark complexity for no benefit. The medallion pattern is a
convention, not a platform. Parquet in object storage stays portable if Databricks is
ever wanted for learning or a portfolio.

## 5. Target architecture (proposal to validate against the real pipeline code)

```
API ──fetch──▶ BRONZE ──dbt/DuckDB──▶ SILVER ──▶ GOLD
               raw JSON, immutable     typed,      ├─ gold_app       ──publish──▶ Neon schema "app"
               + fetch manifest        deduped,    │    shaped per page             (Express reads only this)
                                       conformed   └─ gold_analytics ──stays──▶ Parquet / DuckDB
                                                        PBP, shots, features       reports, notebooks, ML
```

**Bronze: raw, never edited**
- Store the exact API response, gzipped, e.g.
  `bronze/<endpoint>/season=E2025/game=123/<fetched_at>.json.gz`.
- Manifest per fetch: URL, params, fetched_at, HTTP status, content hash. This allows full
  rebuilds without re-calling the API and lets unchanged payloads be skipped.
- Local disk plus a mirror in Cloudflare R2 (already on Cloudflare; S3-compatible; no egress fees).
- Completed games are immutable: fetch once. Re-fetch only the current season and live games.

**Silver: clean entities that know nothing about the app**
- One table per entity, typed, deduplicated (latest fetch wins), source keys kept.
- Split cross-season identity from season rows: `dim_player` (stable `person_code`) plus
  `player_season`, and the same for clubs. This unlocks careers, archives and head-to-head.
- Data-quality tests: unique and non-null keys, game score equals the sum of the box score,
  NULL preserved rather than zero-filled.

**Gold, split in two**
- `gold_app`: tables shaped per page or API route (standings, player season stats with totals
  and per-game values, leaderboards, game detail, records, coverage, postseason series).
  Express then only filters, paginates and returns rows.
- `gold_analytics`: wide facts (play-by-play, shots, possessions, lineup stints, per-game
  feature tables) kept as Parquet or DuckDB for reports and data science. Never loaded into Neon.

**Tooling for the least work**
- Python pipeline (fits notebooks and data science).
- dbt-core + dbt-duckdb for silver and gold: models are `SELECT`s; dbt provides ordering,
  incremental builds, tests and lineage docs.
- Publish with DuckDB's `postgres` extension: `ATTACH` Neon, write to `app_staging`,
  validate row counts, then swap to `app` in one transaction. The site never sees a
  half-loaded state.
- Neon: the API uses a read-only role on `app`. Drizzle in the app repo must be filtered
  (`schemaFilter`/`tablesFilter`) so it never manages pipeline-owned tables.
- Reports: notebooks on DuckDB first; Evidence.dev or MotherDuck only if shareable
  dashboards are needed.
- Scheduling later: GitHub Actions cron running fetch → `dbt build` → publish.

**Migration path (no big bang)**
- Keep `etl_flat_*` working until nothing in the app reads it.
- Build `app.*` gold tables and move one API group at a time (standings first is a good
  pilot), then drop the old tables.
- Contract changes (renamed columns, new keys) are coordinated with the app repo, where
  each migration step goes through its Blueprint `/feature` workflow.

## 6. Open questions to answer from the pipeline code

1. What language is the download code, and where does raw data land today? Files, CSV, or
   straight into Postgres?
2. What exactly does `postgres_etl` do (JSON → CSV → Postgres?), and which parts become
   silver dbt models rather than being thrown away?
3. Which API endpoints and seasons are fetched? Is play-by-play and shot data included?
   How far back does the history go?
4. Is raw JSON kept today, or only the flattened output?
5. How is `person_key` built, and is there a stable cross-season person identifier
   (`person_code`)?
6. Required freshness: nightly, after each round, or near-live during games?
7. Where do the `etl_flat_*` tables get loaded from, and how: full reload or upsert?

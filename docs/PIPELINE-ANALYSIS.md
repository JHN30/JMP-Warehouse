# Pipeline analysis and plan

Analysis of the existing pipeline against [PIPELINE-HANDOFF.md](PIPELINE-HANDOFF.md),
revised with the owner's decisions of 2026-09-24. Facts are checked against the code
and the local E2025/E2026 cache.

## 0. Owner decisions (2026-09-24)

| # | Decision |
| --- | --- |
| Freshness | Nightly **and** after each round. |
| Tooling | **Python + PostgreSQL** (plus MSSQL for private local analysis). **No dbt, no DuckDB.** |
| E2026 in Neon | Loaded the same way as E2025, via `import-e2025-e2026.psql` (CSV `\copy`, append-only; moved to `old/code/` in the 2026-09-24 cleanup). |
| History | All seasons from 2000. Live endpoints start at E2007 (confirmed). Download only the endpoints that are actually needed. **EuroCup is deferred: EuroLeague only for now** (the code already supports `-cp eurocup`). |
| Existing cache | Can be re-downloaded; a full download is planned after testing. |
| Priority | Web app data first; reports/analysis only need to stay possible. `etl_flat_*` names may change. **Refreshable E2026 and standings are equally important.** |

## 1. How the pipeline works today (short version)

```
api_requests/ ─▶ data/euroleague_json/**.json ─▶ postgres_etl/ ─▶ local Postgres (etl_flat_*)
                                                   ─▶ tables_to_csv/ ─▶ CSV ─▶ psql \copy ─▶ Neon public.etl_flat_*
```

- **Download (Python, `requests`)**: v2 `api-live.euroleague.net`, v3 stats/standings, and
  legacy `live.euroleague.net`. Shared 2.5 s rate limit, retries, and a per-season
  `manifest.json`. Detail for played games is fetched once. The current season's game
  list is re-fetched every run.
- **Transform/load (Python)**: `raw_transform.py` + `flat_transform.py` + `flat_schema.py`
  produce 32 typed tables. Each (table, season) is replaced with DELETE + INSERT in one
  transaction. `quality.py` runs read-only checks. 21 unit tests pass.
- **To Neon**: CSV export, then `psql \copy` of 21 v2/v3 tables. **Append-only**: loading
  a season twice fails on a duplicate key, so there is no refresh.

### Problems that matter for the web app

1. **No refresh path into Neon.** Both import scripts append. This blocks in-season E2026.
2. **E2026 standings have never been published.** At export time no E2026 game was
   played, so the standings and season-stats CSVs were header-only.
3. **Stale-data trap in the downloader.** v3 standings for a round and v3 season stats
   are cached on first fetch and only re-fetched with `--refresh-current`. A standings
   file fetched mid-round never updates.
4. `import-e2025-e2026.psql` runs `\copy` **without column lists**, so it silently
   depends on table column order matching CSV header order.
5. Raw files are re-serialized JSON, not the original bytes, and are overwritten on
   refresh. There is no history and no content hash.
6. Game status: every cached game has `gameStatus = "Confirmed"` plus `played`.
   Live/postponed values have never been observed, so the app's 4 states cannot be
   derived yet.

### Useful facts

- **`person_key` is already a stable cross-season id.** It is the v2 `person.code`: it
  equals `person_code` on 966/966 E2025 rows, and 593 people have the same code in
  E2025 and E2026. Clubs behave the same way (19/20 codes shared).
- Live feeds prefix codes with `P`. **Bug:** `player_code()` strips the `P` only when
  digits follow, so `PKLT`, `PTGB` and `PLCZ` do not join. Their v2 codes are `KLT`,
  `TGB` and `LCZ`, and always stripping the prefix fixes it.
- Fallback keys `"unknown-{ordinal}"` / `"anonymous-…"` never fired in E2025, but they
  break "NULL, not a fake value". They should become NULL plus a quality flag.
- Already in Neon but unused by the app: venue and attendance in `etl_flat_games`
  (402/402 games; 12 have `audience = 0`, which should be flagged, not trusted), and
  `etl_flat_game_officials`.
- Dead code (never imported by `main.py`): `table_loading.py`, `table_schema.py`,
  `table_indexing.py`, `helper_loading.py`, `postgres_etl/utils.py`.

## 2. Endpoint overlap (the download can roughly halve)

Compared on all 402 E2025 games:

| Legacy `live` endpoint | Compared with | Result | Proposal |
| --- | --- | --- | --- |
| **Boxscore** | v2 game stats + v2 game list | Player stats identical except 3 values (2 plus/minus, 1 valuation). Quarter scores, attendance and referees are all in the v2 game list. | **Drop** (keep only as a fallback if v2 game stats turn out to be missing for old seasons) |
| **ShootingGraphic** | sums over Points (shots) flags | Fast-break, second-chance and points-off-turnover match **804/804** team-games | **Drop**, compute from shots |
| **Evolution** | play-by-play running score | Final score matches 402/402; the minute series is a projection of PBP | **Drop**, compute from PBP |
| **Comparison** | v2 box (`startFive`) + PBP | Starter/bench points, assists and steals 804/804. Turnovers differ in 382 (likely team turnovers), max lead in 43 (off by 1–2). | **Drop**; nothing in the app uses it |
| **PlayByPlay** | nothing | Unique | **Keep** |
| **Points** (shots, coordinates) | nothing | Unique | **Keep** |

v2 and v3 endpoints stay: games, clubs, rounds, people (paged), rosters, game stats,
v3 season stats and v3 standings. The app reads all of them.

**Cost**: 7 → 3 requests per played game. E2025 would drop from about 3,070 requests
(~2.1 h) to about 1,460 (~1 h). A rough full-history estimate drops from about 45–50 h
to about 15–20 h.

**Old-season smoke test (2026-09-24, 23 requests, game 1 of each season):**

| Season | v2 games | v2 game stats | v3 standings / stats | live PBP / Points / Boxscore |
| --- | --- | --- | --- | --- |
| E2000 | 158 games (RS, PO); venue, audience, referees, quarters all set | yes | yes (24 teams / 304 players) | **not JSON (no data)** |
| E2006 | – | – | – | **not JSON (no data)** |
| E2007 | 231 games (RS, **TS**, PO, FF); audience set for 212 | yes | yes | yes (545 events, 175 shots) |
| E2015 | 250 games (RS, **TS**, PO, FF) | yes | yes | yes |

Conclusions:
- v2/v3 cover every season from 2000, so **Boxscore can be dropped everywhere**.
- Live data starts at **E2007**, as `LIVE_DATA_START_YEAR = 2007` already assumes.
- **Must fix before the backfill:** older seasons have phase **`TS`** (Top 16). The
  v3 season-stats filename regex in `raw_transform.py` only accepts `RS|PI|PO|FF|all`
  and would crash, and the app's phase list has no `TS` either.
- **NULL vs 0 in old seasons:** unrecorded stats come back as `0` (`plusMinus = 0.0` in
  E2000/E2007; Boxscore attendance `'0'`). Silver needs per-season availability rules
  so these become NULL rather than real zeros.

## 3. Target architecture (Python + PostgreSQL)

The medallion idea stays; only the tools change. Everything below is Python you run,
plus plain `.sql` files for the gold tables.

```
fetch (api_requests, hardened)
  └─▶ BRONZE  data/bronze/<comp>/<season>/<endpoint>/…/<fetched_at>.json.gz + manifest (url, params, status, sha256)
        │     exact bytes, never edited; unchanged payloads are not stored twice
        ▼
silver loader (existing flat_schema / transforms, Python)
  └─▶ local PostgreSQL schema  silver     typed entities, latest fetch wins, source keys,
        │                                  dim_player / dim_club, player_season, quality flags
        ▼
gold builder (Python runs gold/*.sql in order)
  ├─▶ local PostgreSQL schema  gold_app       page-shaped tables for the web app
  └─▶ local PostgreSQL schema  gold_analytics PBP, shots, possessions… (later; copy to MSSQL if wanted)
        ▼
publish (Python, psycopg2 COPY local → Neon)
  └─▶ Neon  app_staging ─(validate row counts)─▶ swap ─▶ app       Express reads only this
```

- **Why local PostgreSQL as the warehouse**: you already know it and run it. It holds
  everything, including PBP and shots. Neon gets only `gold_app`, which keeps Neon small.
- **Publish replaces** `tables_to_csv/`, `neon_csv_import/` and the hand-written `.psql`
  scripts. One Python command copies tables straight between the two databases.
- **Idempotent runs**: if the game list is unchanged and every played game is already in
  bronze, a run makes one request and publishes nothing. The same job can therefore run
  nightly and every couple of hours on game days, which covers "after each round"
  without detecting rounds by hand.
- **Current-season refresh rule** (fixes the stale-data trap): when the number of played
  games changes, re-fetch standings for the affected rounds, the v3 season stats, and
  rosters/people. Completed-season data is never re-fetched.
- **Gold owns every aggregation**: records, coverage, team season stats, postseason
  series and career views move out of `backend/src/routes/seasons.ts` into `gold/*.sql`.

## 4. Milestones

**M1: refreshable E2026 and standings in Neon (no app change).** **Built
2026-09-24; not yet run against the real Neon.**
- Done: automatic hot-round refresh in `api_requests` (`--hot-hours`, changed-resource
  tracking, `--summary-file`); `neon_publish/` (one transaction per season, shrink guard,
  explicit columns, count check); `pipeline.py` (fetch → load → quality → publish,
  "publish pending" state in `data/<comp>_json/<season>/pipeline_state.json`).
- Verified: 11 scraper tests, 6 publish/pipeline tests and 21 ETL tests pass. Publishing
  into a scratch local schema gave byte-identical tables for E2025 and E2026, re-running
  was safe, the shrink guard fired, and a missing column was re-added. A real
  `pipeline.py` run fetched a changed E2026 game list, and the next run correctly did
  nothing.
- First real run against Neon succeeded on 2026-09-24. `neon_csv_import/` and both
  `.psql` scripts were then moved to `old/code/`; `tables_to_csv/` stays (useful for MSSQL analysis).

Original M1 scope:
- Downloader: the automatic current-season refresh rule above; `--refresh-current` is
  no longer needed.
- New `publish` command: local PG → Neon. For each table and season, `DELETE` that
  season's rows and `COPY` the new rows **in one transaction per season**, so the site
  sees the old or new data, never half. Explicit column lists and a row-count check.
  It targets today's `public.etl_flat_*` names, so the app keeps working unchanged.
- One command that runs the lot: `pipeline run --season current` = fetch → load →
  quality → publish.
- Retire `tables_to_csv/`, `neon_csv_import/` and both `.psql` scripts once M1 publish
  has been verified.

**M2: bronze hardening and endpoint trim, then the full download.** **Code done
2026-09-24; the full download is next (owner runs it).**
- Done:
  - [common/bronze.py](../common/bronze.py): exact bytes, gzip, one version per distinct response, and
    a `manifest.jsonl` with url/params/status/sha256/bytes.
  - Downloader and loader both moved to bronze.
  - Default endpoints trimmed to v2/v3 + PlayByPlay + Points.
  - Live tables keep the original `player_code` (`PKLT`) and add a standardized
    `person_code` (`KLT`; NULL for team/coach markers such as `CO_A`) for joins. On
    E2025, all 284,347 player rows link to `people`. Phase codes such as `TS` are parsed.
  - Warnings (not errors) for fallback keys, unmatched live player codes and
    played games with attendance 0.
  - The current season's clubs, people, rosters and rounds are re-checked at least
    every 20 h. Found while testing: pre-season roster changes were never picked up.
- Verified:
  - 51 unit tests pass.
  - Converting the old E2025 cache to bronze and loading it into a scratch schema gave
    29/33 tables identical to the old load. The rest differ only by the intended
    `P`-prefix fix (PKLT/PLCZ/PTGB → KLT/LCZ/TGB) and the removed synthetic
    `season_people.json`. There are 0 unmatched live player codes left.
  - A real E2026 fetch into bronze took 321 KB, against 3.1 MB before.
- Found in real E2026 data: registrations shrink from 1,134 to 918, because the old
  pre-season roster rows were stale. The first real publish therefore needs
  `--allow-shrink` once.
- **Finished 2026-09-24 after the download** (EuroLeague E2000–E2025: 0 failed requests,
  174 MB bronze). All 27 seasons loaded into local PostgreSQL: 3,982,028 rows, 0 quality
  errors. Only local; the web-app tables for all seasons are ~237 MB.
  - Unrecorded stats → NULL, per game: a measure that is 0 for every player is NULL and
    listed in `game_stat_gaps` (plus/minus E2000–E2011, fouls received in 22 early games).
    From E2012 nothing changes.
  - Forfeits (E2001 game 264, 2–0; E2003 game 200, 20–0) have no box score: team stats are
    NULL and they are flagged. They must be excluded from records.
  - `games.status` + `status_note`: completed / scheduled / awaiting_result / postponed /
    cancelled. E2021: 28 cancelled by the source. E2019: 54 COVID games inferred as cancelled
    (the source still says "Confirmed").
  - Live player ids are wrong for some players in the source. They are matched to the v2 box
    score by jersey number or name, with `person_code_method` recording how. 297 rows were
    corrected, and 6 events remain unmatched (Mulalić, E2007).
  - `NaN%` standings values → NULL. 3 source standings rows where played ≠ won + lost are warned.
  - Attendance (owner decision 2026-09-24): the source's 0 becomes NULL. It stands for
    games not played yet, crowds that were not recorded (most of E2004/E2005, clusters
    in E2003/E2007, some recent games such as Final Fours) and closed-door games alike.
    `games.audience_note` says "likely behind closed doors (COVID period)" (260 games,
    March 2020 – June 2022) or "attendance not recorded (or behind closed doors)" (490
    games), so the web app can flag them.

Original M2 scope:
- Exact bytes, gzip, versioned files, and manifest with sha256/params/status.
- Drop Boxscore, Evolution, Comparison and ShootingGraphic (the smoke test confirmed
  v2/v3 back to 2000).
- Fix `player_code()` and replace fallback keys with NULL plus a flag.
- Accept phase `TS` in the season-stats parser, and decide how the app shows it.
- Per-season "stat not recorded" rules (0 → NULL) for old seasons.
- Then the full E2000–E2026 + EuroCup download (estimated 15–20 h).

**M3: silver + gold_app with clean names (coordinated with the app repo).**
- `silver` schema: `dim_player` (on `person_code`), `player_season`, `dim_club`,
  `club_season`, games, boxes, a data-quality flag table.
- `gold_app` → Neon `app`: **standings first** (pilot, one page-shaped table instead of
  7), then records, coverage, team season stats, postseason series and careers. Each
  moves one API group at a time, through the app's `/feature` workflow.
- Drop `public.etl_flat_*` in Neon when nothing reads it.

**M4: scheduling.** Windows Task Scheduler on your machine (simplest; the bronze files
live there), or GitHub Actions, which then needs bronze mirrored to Cloudflare R2.
Nightly, plus every ~2 h on game days.

## 5. Open questions

1. ~~M1 naming~~: **answered**, keep `etl_flat_*` for M1 and rename in M3.
2. ~~Old-season smoke test~~: **done**, see section 2.
3. **Scheduler host** (M4): your PC or GitHub Actions? Not needed until M4.

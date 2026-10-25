# Fix: Stop publishing tables the web app no longer reads

**Type:** Fix
**Status:** verified
**Branch:** fix/stop-publishing-unused-tables

## The problem

The web app no longer reads seven Gold tables, but every refresh rebuilt them locally and
published them to Neon:

- `app_coverage_seasons`, `app_coverage_games` (the app's coverage endpoint was removed)
- `app_team_round_stats`, `app_team_round_ratings`, `app_team_round_splits` (exact
  duplicates of `app_standings_stats` for every shared column)
- `app_game_team_shot_zones`, `app_team_shot_zone_stats` (the app derives its own zones
  from `app_shots`)

## The fix

- Unregister the seven tables in `gold_etl/schema.py`, so Gold no longer builds them and the
  Neon allowlist (derived from the schema) drops from 47 to 40 tables.
- Keep the three team round derivations as in-memory steps of `app_standings_stats`.
- Move the checks that read the stored team round tables onto `gold.app_standings_stats`
  (SRS and adjusted-rating sums, split totals, Win Shares games, round-1 game ties); run the
  API team-feed cross-check on the in-memory team round rows. Remove the tie check that only
  compared `app_standings_stats` with those tables.
- Remove `gold_etl/coverage.py` and `gold_etl/team_shot_zones.py`.
- Stop building Silver `game_team_shot_zones` (`postgres_etl/shot_zones.py` removed); it had
  no consumer left. The local Silver table was dropped (owner-approved).
- Stop fetching and loading club rosters (`v2/rosters/{club}`): in every season E2000-E2026
  each entry is already in the season people pages with identical values. The loader's
  people/registrations rows are unchanged for all 27 seasons (same row fingerprint).
- Docs: Neon holds every locally loaded season (E2000-E2026, E2007+ for event tables).
- Remove dead code: `person_code_from_live` (superseded by `resolve_live_person`), three
  unreferenced constants, the spent one-time `gold_etl/migrate_names.py`, and the optional
  live datasets (live_boxscores, live_evolution, live_comparison, live_scoring, never
  downloaded) with the `-api` option that only duplicated `-ds`.
- Stop fetching the team opponents statistics feeds and the team per-game mode; Silver keeps
  `season_team_stats_traditional`/`_advanced` in accumulated mode for Gold's API cross-check.
  Local Silver reloaded for E and U; the two local opponents tables dropped (owner-approved).
- The v3 player statistics and standings feeds stay: six Neon tables depend on them.
- Kept on purpose for now: `app_players`, `app_club_identities`, `app_records_*`, the
  derivable `app_games` columns and the perGame season-stat feeds.
- Drop the seven local Gold tables (owner-approved).
- Add the reviewed Neon script `neon_publish/migrations/drop_unused_app_tables.sql`; the owner
  applied it in the Neon SQL editor on 2026-10-26, after confirming the app deploy (commits
  04f65f5 and c713d64).
- Must not change any table the app reads or the section-2 tables.

## Build steps

1. Schema, loader, quality and CLI changes with tests. Done when all four test suites pass.
2. Docs. Done when no current doc lists the seven tables as built or published.
3. Local drop. Done when `gold` holds exactly the 40 registered tables and a rebuild does not
   recreate the seven.

## Verify

- All four test suites pass.
- `python gold_etl/main.py -sc E2026 --quality-only` passes after a rebuild.
- `python neon_publish/main.py --list-tables` lists 40 mappings.
- `python neon_publish/main.py -sc E2026 --dry-run` passes the Neon preflight (read-only).
- After the deploy confirmation: apply the drop script (done 2026-10-26); then
  `python pipeline.py --skip-fetch --dry-run-publish` rebuilds Silver and Gold and passes the
  Neon preflight. The first live publish after the drop is the next scheduled refresh.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":3809,"specSha256":"b6490643612aaefe090e116a27ae10d43b6d3e3e7806c1fb87cdbb7915c303cc","branch":"refs/heads/fix/stop-publishing-unused-tables","head":"fda8cc430bb7fe3ca0dbd4a0a8143905b1b2147b","baseRef":"refs/heads/main","baseCommit":"a9c43861d78c21d3f9fa5194e42b4e12a2a7b4db","sourceTree":"dec395b5922b0f6ca3c42d38cac4cbb637be8f06","absentOptional":[]} -->

## Independent review

# Independent Review

**Status:** passed
**Target commit:** fda8cc430bb7fe3ca0dbd4a0a8143905b1b2147b
**Base commit:** a9c43861d78c21d3f9fa5194e42b4e12a2a7b4db
**Base ref:** main
**Spec hash:** b6490643612aaefe090e116a27ae10d43b6d3e3e7806c1fb87cdbb7915c303cc
**Prepared by:** claude
**Builder model:** claude-opus-5-5
**Requested reviewer:** claude
**Requested model:** claude-opus-5-5
**Requested execution:** automatic
**Requested at:** 2026-10-25T23:48:02Z
**Workflow:** regular
**Check required:** no
**Reviewer adapter:** claude
**Reviewer model:** claude-opus-5-5
**Reviewer context:** fresh subagent
**Actual execution:** automatic
**Reviewed at:** 2026-10-25T23:54:00Z
**Scope:** current
**Lenses:** quality, security, performance, tests
**Verdict:** passed
**Check result:** not-required

## Handoff

Review the active spec and the complete `a9c43861d78c21d3f9fa5194e42b4e12a2a7b4db..fda8cc430bb7fe3ca0dbd4a0a8143905b1b2147b` delta in a fresh
session or isolated subagent without the builder conversation. Run all Audit lenses from scratch.
Run Check when required above. Do not edit product code, accept findings, or
reuse the existing findings as the review scope.

## Commands

- `git rev-parse HEAD`, `git merge-base main HEAD`, `git status --porcelain`, `sha256sum blueprint/context/current-feature.md`: pass (HEAD = target, merge base = base, spec hash matches, only `blueprint/context/review.md` dirty, no untracked files)
- `cd api_requests && python -m unittest tests.test_scrapper`: pass (45 tests)
- `python -m unittest discover -s postgres_etl/tests`: pass (201 tests)
- `python -m unittest discover -s gold_etl/tests`: pass (262 tests)
- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`: pass (72 tests)
- `python neon_publish/main.py --list-tables`: pass (40 mappings)
- `python gold_etl/main.py -sc E2026 --dry-run`: pass
- `python gold_etl/main.py -sc E2026 --quality-only`: pass ("Gold quality: passed", no WARN lines)
- Read-only local PostgreSQL queries (read-only session) on `gold` and `silver` schemas: pass
- Scratch read-only script comparing `RawSeason.rows("people"/"registrations")` with and without `v2/rosters/*` files for every E and U season: pass

## Evidence

- Full delta reviewed: 54 files, 3 commits (8cedfef, d38422d, fda8cc4); code in `gold_etl/{schema,loader,main,quality,team_pbp}.py`, `neon_publish/contract.py`, the new `neon_publish/migrations/drop_unused_app_tables.sql`, `api_requests/{main,scrapper,utils}.py`, `postgres_etl/{flat_schema,main,quality,raw_transform}.py`, seven deleted modules/tests, all changed tests and docs.
- Schema: the seven tables are gone from `GOLD_TABLES`; `SEASON_DERIVED_NAMES` now holds only names `read_aggregate_rows` dispatches explicitly, so its final `read_team_rows` fallthrough is reached only by `app_team_season_stats`. `APP_TABLES` = 40 and equals `set(GOLD_TABLES)` (test asserts).
- Moved quality checks read only columns `app_standings_stats` carries (`connected`, `srs`, `adj_net_rating`, `possessions`, `games_played`, `wins`, `mov`, split columns and the four round-1 tie columns), all projected from the same in-memory derivations; the API cross-check re-derives `team_round_stats` in memory and keeps only the final round per scope and club (new test `test_only_the_final_round_is_compared`).
- Local database: `gold` holds exactly the 40 allowlisted tables; `silver` has no shot-zone, opponents or roster tables; `silver.season_team_stats_traditional` holds only `accumulated` rows (E 1708, U 2294); Silver has 26 typed + 7 advanced tables, matching the docs.
- Roster removal: 52 E/U seasons have archived `v2/rosters/*` files; with or without them the `people` and `registrations` key sequences are identical in every season (people pages are read first and de-duplication is first-wins, so payloads are unchanged too).
- Fetcher: team v3 feeds request `accumulated` only and opponents feeds are gone; the loader skips archived opponents and per-game team files; the Silver missing-feed check expects only `accumulated` for team tables (tests cover each).
- Security: no new input, auth or trust boundary; no secrets in the delta; the drop script is a single transaction with `lock_timeout`, no `CASCADE`, never run by the publisher. No pipeline, task or script references a removed module, table, `-api` or `rosters` option.
- Spec drift: two docs still describe shot zones as built (F-12); one stale code comment (F-13). Existing F-05 and F-11 were not re-examined for status changes and are left unchanged.

## Findings

- F-12 [P3] open - Two current docs still describe shot zones as built (docs/SILVER_CATALOG.md:125, README.md:87)
- F-13 [P3] open - Stale comment above LIVE_ENDPOINTS describes the removed optional datasets (api_requests/utils.py:46)

## Remaining risk

- Neon was not connected (by instruction): the owner-applied drop on 2026-10-26 and the post-drop Neon preflight (`python neon_publish/main.py -sc E2026 --dry-run`, `python pipeline.py --skip-fetch --dry-run-publish`) were not re-verified by this review; the first live publish after the drop is the next scheduled refresh.
- The web app (`jmp-euroleague2`) is out of scope; that it no longer reads the seven tables rests on the owner's deploy confirmation.
- `gold_etl/main.py --quality-only` for `app_standings_stats` now re-derives the team round rows from Silver a second time for the API cross-check (unverified performance cost for `--all` runs; E2026 completed normally).
- The `app_standings_stats` quality wiring in `gold_etl/main.py` has no unit test of its own; it was exercised only by the real E2026 `--quality-only` run.

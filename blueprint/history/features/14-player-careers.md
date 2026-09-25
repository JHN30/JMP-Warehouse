# Feature: Player careers

**From build-plan:** feature 14
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/player-careers`

## Goal

Precompute one lookup row per player (`person_code`), so the app can look up
"who is this player" and their career span/club history without a
season-scoped query, in one join key that already unlocks careers, archives,
and head-to-head views.

No existing Express contract to mirror (confirmed: nothing in the backend
references careers/archives/head-to-head). The build-plan line is terse and
names three use cases; investigation before writing this spec (approved with
the user 2026-09-25) found two of them need no new table at all:

- **Archives** (a player's season-by-season club history) is already fully
  in `app_registrations`, keyed by `person_key`. Confirmed empirically:
  `person_key` and `person_code` are identical for every one of the 5,515
  distinct players in local history (no divergence found) — `person_code`
  already works as a stable cross-season join key on every existing
  season-scoped table (`app_people`, `app_registrations`,
  `app_game_player_stats`, `app_season_stats_*`). Archives only needed a
  place to look a player up by that key without picking a season first.
- **Head-to-head** (games where two players opposed each other) is likewise
  already fully answerable today from `app_game_player_stats` joined on
  `person_key`/`person_code` — no new table needed.
- **Careers**: approved as identity/lookup only, not precomputed career stat
  totals. `app_season_stats_traditional` already has the per-season numbers;
  a career total is just a sum across a player's rows there via
  `person_code`, the same shape of query as any other cross-season lookup —
  not a new derived contract this feature needs to own.

So this feature's actual deliverable is the one missing piece: a single
cross-season player-identity table.

## In scope

- `app_players` - one row per `person_code`, restricted to person codes that
  appear as a player (`role_code = 'J'`) in `app_registrations` at least
  once (excludes staff/coaches/referees-only records in `app_people`).
- Latest-known identity fields (name, country, height, weight, birth date,
  birth country, position) — taken from that player's most recent season's
  `app_people`/`app_registrations` rows, since these can change slightly
  season to season (a listed height/weight, a position change) and the app
  needs one current-best answer, not a per-season one.
- Career span: `first_season_code`, `last_season_code`, `seasons_played`
  (distinct seasons with a `role_code = 'J'` registration).
- `clubs` (JSONB): the distinct `(season, club)` pairs a player was
  registered to as a player, ordered by season — the compact "archive"
  summary; the full per-season detail stays in `app_registrations`.
- Like feature 11's records tables (not feature 12/13's season-scoped ones),
  this table is NOT season-scoped: a player's row spans every season they
  appeared in, so it needs the same whole-table-replace treatment, not a
  per-season delete.
- Reuse `neon_publish/publish.py`'s existing `publish_records` for the Neon
  publish step — it is already fully generic (works from `TABLES[name]`,
  not hardcoded to the records tables), so `app_players` needs no new
  publish-side code, only inclusion in the cross-season table list that
  `neon_publish/main.py` already routes to it.

## Out of scope

- Career stat totals (points/rebounds/assists/PIR summed across seasons per
  player) — approved out of scope 2026-09-25; the app can already compute
  these itself from `app_season_stats_traditional` via `person_code`.
- A dedicated head-to-head table — already answerable from
  `app_game_player_stats`; no new table needed.
- Player photos/headshot URL — not named in the build-plan line; feature 12
  already tracks photo *availability* (not the URL itself) separately.
- Any change to `jmp-euroleague2` to read from this table — coordinated
  later, like every other app-facing table so far.
- EuroCup (`competition_code = 'U'`) — still deferred project-wide.

## Build loop

Per `blueprint/config.json` (`workflow.stepReview: "feature"`), one review
packet after all steps; checkpoint commits disabled. `/complete` makes the
final commit.

## Build steps

- [x] **Step 1 - Schema** - Add `app_players` to `postgres_etl/flat_schema.py`,
  bypassing the season-scoped `table()` helper the way `app_records_*` do
  (key `(competition_code, person_code)`, no `season_code` in the key — it's
  a plain data column via `first_season_code`/`last_season_code` instead).
  Add to `PUBLISHED_TABLES`. *Done when:* `python postgres_etl/main.py
  --list-tables` lists the new name.
- [x] **Step 2 - Local computation** - Add `postgres_etl/players.py`
  (mirrors `records.py`'s cross-season, whole-table-replace shape: connect,
  `TRUNCATE`, one ranked-free `INSERT ... SELECT`, dry-run support that
  counts without writing). The query: restrict to `person_code`s with a
  `role_code = 'J'` row in `app_registrations`; pull latest identity fields
  from the `app_people`/`app_registrations` rows with `MAX(season_code)`
  for that player; aggregate `first_season_code`, `last_season_code`,
  `seasons_played`, and the `clubs` JSONB array from all of that player's
  `role_code = 'J'` registration rows. *Done when:* running it against the
  local dev database populates `app_players` with one row per player found
  in `app_registrations`, and a manual spot-check of one long-career player
  (for example a player active 20+ seasons) shows the correct
  `first_season_code`/`last_season_code`/`seasons_played`/`clubs` against
  their actual `app_registrations` history.
- [x] **Step 3 - Wire into the loader** - In `postgres_etl/main.py`, route
  `app_players` the same way `RECORDS_TABLES` are routed (not season-scoped;
  runs once per invocation regardless of `-sc`), reusing `players.py`'s
  `build_players`/`validate_players`. *Done when:* `python postgres_etl/main.py
  -tb app_players` refreshes the table from full local history.
- [x] **Step 4 - Quality checks** - Add checks (in `players.py`, following
  the `validate_records` pattern rather than `quality.py`'s season-scoped
  `Check`/`scoped_count` machinery, since this table isn't season-scoped
  either): no duplicate `person_code`; `first_season_code <=
  last_season_code`; `seasons_played` equals the actual count of distinct
  seasons in that row's `clubs` array; every row has a non-empty `clubs`
  array. *Done when:* `python postgres_etl/main.py --quality-only -tb
  app_players` reports 0 errors after a fresh Step 2/3 run.
- [x] **Step 5 - Neon publish** - In `neon_publish/main.py`, add
  `app_players` to the cross-season table list already routed to
  `publish_records` (alongside `RECORDS_TABLES`); expect no
  `neon_publish/publish.py` changes. *Done when:* `python
  neon_publish/main.py --dry-run -tb app_players` reports the planned
  whole-table replace.
- [x] **Step 6 - Data dictionary** - Document `app_players` in
  `docs/DATA_DICTIONARY.md`: key, the `role_code = 'J'` player filter,
  "latest known" identity rule, career-span fields, `clubs` JSONB shape, and
  the explicit note that career totals and head-to-head are already
  answerable from existing tables via `person_code` and are not duplicated
  here.
- [x] **Step 7 - Tests** - Add unit tests under `postgres_etl/tests/` (a new
  `test_players.py`, matching `test_records.py`'s no-database convention):
  the SQL excludes non-player (`role_code != 'J'`) people; dry-run never
  writes; real run truncates then inserts; unknown-table rejection. *Done
  when:* `python -m unittest discover -s postgres_etl/tests` passes,
  including the new tests.

## Files / areas

- `postgres_etl/flat_schema.py` - new table definition, `PUBLISHED_TABLES`.
- `postgres_etl/players.py` (new) - computation, dry-run, and validation.
- `postgres_etl/main.py` - route `app_players` like the records tables.
- `neon_publish/main.py` - add `app_players` to the cross-season publish list.
- `postgres_etl/tests/test_players.py` (new).
- `docs/DATA_DICTIONARY.md` - new table documentation.

## Data / contracts

- Key: `(competition_code, person_code)`.
- Columns: `name`, `country_code`, `country_name`, `height_cm`, `weight_kg`,
  `birth_at`, `birth_country_code`, `birth_country_name`, `position`,
  `position_name` (all "latest known" — from the row with the maximum
  `season_code` for that player), `first_season_code`, `last_season_code`,
  `seasons_played` (INTEGER NOT NULL), `clubs` (JSONB NOT NULL, array of
  `{seasonCode, clubCode, clubName}` ordered by season, one entry per
  distinct season+club the player was registered to as a player).
- Scope: only `person_code`s with at least one `role_code = 'J'`
  registration row (excludes coaches/staff/referee-only people).
- Rebuild is idempotent and whole-table: every run recomputes every row from
  current local `app_people`/`app_registrations` data and replaces prior
  contents in one transaction, same as feature 11's records tables.

## Testing

- `python -m unittest discover -s postgres_etl/tests` covers the
  player-filter and dry-run/real-run logic (Step 7).
- Manual verification per step's *Done when* above: `--list-tables`,
  `--quality-only`, `neon_publish/main.py --dry-run` output, and one manual
  cross-check of a real long-career player's row.
- No UI to test; this is a data pipeline change only.

## Notes for the AI

- Reuse feature 11's cross-season, whole-table-replace shape
  (`records.py`'s `build_records`/`validate_records` pattern) for
  `players.py` — same category of table, same reason (not season-scoped).
- Reuse `neon_publish/publish.py`'s existing `publish_records` function
  directly; it is already generic over any table name list. Do not write a
  parallel `publish_players`.
- Don't add career stat totals or a head-to-head table — both were
  explicitly scoped out with the user; they're already queryable from
  existing tables via `person_code`.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":10048,"specSha256":"f0eb7a7df739d2e53c143d69abf86f35689ba2e845e53e30ef808fb7b937def6","branch":"refs/heads/feature/player-careers","head":"3036bff648a7a88a0057c6cd8c143fc0b725a729","baseRef":"refs/heads/main","baseCommit":"3036bff648a7a88a0057c6cd8c143fc0b725a729","sourceTree":"1bdb64c8b97a3e22c6f7eb44db7c9da6739644df","absentOptional":[]} -->

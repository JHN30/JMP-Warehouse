# Fix: One registration row per person, club and role in a season

**Type:** Fix
**Status:** verified
**Branch:** fix/one-registration-row-per-person-club-and-role-in-a-season

## The problem

`gold.app_registrations` is a plain copy of `silver.registrations` (`replace_scope` in
`gold_etl/loader.py`), one row per source registration. When a club deregisters a person and
registers them again in the same season, Gold holds two or three rows for the same
`(competition_code, season_code, person_key, club_code, role_code)`. The app treats the table
as roster membership, so it lists the person twice on the team roster, the coaches list,
Compare rosters (duplicate React key, failing `compare.spec.js`) and the player club chips.
Handoff from the app repository: `registrations-duplicate-stints.md` (Nemanja Dangubic,
`005942`, `DUB`, `E2026`).

The source rows are real re-registrations, not bad data, so Silver stays as it is.

Local counts (groups with more than one row):

| Competition | J | Z | A | E | F | U |
|---|---|---|---|---|---|---|
| E | 17 | 26 | 10 | 3 | 2 | 2 |
| U | 10 | 3 | 7 | 1 | 2 | 2 |

EuroLeague seasons affected: E2001, E2007, E2016-E2026. No group has a null club or role.
Three staff groups overlap in time; player groups never do.

## The fix

- New `gold_etl/registrations.py`: a pure `collapse(rows)` that groups Silver rows by
  `(competition_code, season_code, person_key, club_code, role_code)` and returns one row per
  group, plus `read_rows(cursor, competition_code, season_code)` that reads the Silver scope
  and collapses it.
- Collapse rules:

  | Column | Value |
  |---|---|
  | `active` | true if any period is active, else false |
  | `start_at` | earliest non-null `start_at` (null only if all are null) |
  | `end_at` | latest non-null `end_at` (null only if all are null) |
  | every other column, including `registration_key` | from the latest period: greatest `start_at` (null sorts first), then greatest `end_at` (null first), then greatest `external_id` |

  Reusing the latest period's `registration_key` keeps the key unique and stable across
  rebuilds without a hash; the app says the key may change.
- `replace_scope` writes the collapsed rows for `registrations` in the same
  delete-and-insert transaction; every other copied table keeps the plain copy.
- `check_scope` for `registrations` compares Gold with `collapse` of the Silver scope (equal
  row counts, no source-column difference) and reports an `ERROR` if any group has more
  than one Gold row.
- Columns, types and primary key of `app_registrations` stay the same, so no Neon migration.
- Must not change: Silver `registrations`, real transfers (two clubs in one season stay two
  rows, 103 EuroLeague players today), different roles or seasons, the identity tables
  (they read Silver), any other copied table.
- Docs: `docs/DATA_DICTIONARY.md`, `docs/GOLD_TABLE_REFERENCE.md`, `docs/DATA_CATALOG.md` and
  `gold_etl/README.md` describe `app_registrations` as one row per person, club and role per
  season.
- Neon: fixing the live copy needs a publish of `app_registrations` for every affected season.
  That is a separate step after the owner's explicit yes, not part of this build. Done
  2026-10-27 with the owner's yes: `-tb app_registrations` for E2001, E2007 and E2016-E2026
  (66 rows merged away, every season committed), and the four acceptance checks pass on Neon.

## Build steps

- [x] 1. `gold_etl/registrations.py`, loader and quality changes, with tests in
   `gold_etl/tests/` for: one active period plus one inactive (Dangubic shape), no active
   period, three periods (Colom shape), null `start_at`/`end_at`, a transfer staying two
   rows, a different role staying separate. Done when all four test suites pass.
- [x] 2. Docs. Done when no current doc describes `app_registrations` as one row per source
   registration.
- [x] 3. Local rebuild: `python gold_etl/main.py -cp euroleague -sc all -tb app_registrations` and
   the same for `eurocup`. Done when the handoff's acceptance checks 1-4 pass on local `gold`.

## Verify

- All four test suites pass.
- `python gold_etl/main.py -sc all -tb app_registrations --quality-only` passes for both
  competitions.
- Handoff acceptance checks on local `gold`:
  1. No `(season, person, club, role)` group with more than one row: 0 rows.
  2. `E2026` / `005942` / `DUB`: 1 row, active, 2026-08-12 to 2027-06-30, jersey 2.
  3. `E2020` / `009056` / `BAR`: 1 row, inactive.
  4. EuroLeague players with two or more clubs in a season: still 103.
- `python neon_publish/main.py -sc E2026 -tb app_registrations --dry-run` shows the expected
  smaller count with no schema complaint (the shrink stays far above the 90% guard).


<!-- blueprint:completion {"schemaVersion":1,"specBytes":4712,"specSha256":"a2f4feefb75fdfaf067bcd7c8dff5fe18122ec48ac01cf39ea898ff4c271bebb","branch":"refs/heads/fix/one-registration-row-per-person-club-and-role-in-a-season","head":"38f63364ddc55c4a699c58f99d08b9916ce71bc7","baseRef":"refs/heads/main","baseCommit":"38f63364ddc55c4a699c58f99d08b9916ce71bc7","sourceTree":"257ac36eef7580c4da0fa0cbc78dd096bf8e5f29","absentOptional":[]} -->

# Fix: Standardize Silver text values

**Type:** Fix
**Status:** verified
**Branch:** fix/standardize-silver-names

## The problem

The Silver loader stores several text columns exactly as the API sends them, so
the same thing has more than one spelling and the app has to repair values on
display:

- **Person names in capitals.** `BROWN III, JOHN`, `McCARTY, KELLY`,
  `COWAN JR, ANTHONY`, `O´BANNON, LARRY`. The app capitalizes the first letter
  of each word, so `III` becomes `Iii`, `IV` becomes `Iv` and `McCarty` becomes
  `Mccarty`. Some feeds write the same given name two ways (`DeJUAN` and
  `DEJUAN`), and `Mc` is sometimes a separate word (`MC DUFFIE`).
- **Club cities in mixed styles.** The same city appears as `ISTANBUL` and
  `Istanbul`, as `St Petersburg` and `Saint Petersburg`, or with the country
  attached (`Trabzon, Turkey`). A few values are club names, not cities
  (`BENFICA`, `Kalev`, `Ovarense`).
- **Countries with two codes.** `UK` and `GBR`, `IVO` and `CIV`, `ZAI` and
  `COD`, `FYR` and `MKD`, plus the non-countries `LAD` (Adriatic League) and
  `NAT` (No country). Country names repeat the problem (`Cote D’Ivoire`, `----`).
- **Labels.** `role_name` mixes `Unified_Score_Crew` with `Physical therapist`
  and has the typo `Assitant coach`. `games.group_name` mixes
  `Group SEMIFINAL A` with `Group Semi-Final 1` and `Group 3RD PLACE GAME`.
- **Positions.** `registrations.position` and `game_player_stats.position` use
  `-1` and `0` for "no position" next to `1`-`3`.

## The fix

Clean these values once, at Silver load, and store the display form in place
(no extra `_raw` columns; Bronze keeps the exact source values).

- New `postgres_etl/text_clean.py` with one function per kind of value:
  `person_name`, `city_name`, `country_code`, `country_name`, `role_name`,
  `group_name`, `position`. Small fixed maps hold the known exceptions (camel
  case given names, city corrections, country codes, the role typo).
- `Field` in `postgres_etl/flat_schema.py` gets an optional `clean` name (a
  string, so `flat_schema` imports nothing and `gold_etl` can still import it as
  a package). `FlatSeason.rows` in `postgres_etl/flat_transform.py` applies it
  after `cast`.
- Person names: title case in `Surname, Given` form; `II`, `III`, `IV` stay in
  capitals; `JR` becomes `Jr.`; `Mc` names become `McCarty`; known camel case
  given names (`DeJuan`, `LaRon`) keep their form; two-letter initials (`PJ`,
  `AJ`) stay in capitals; source apostrophes (`´`, `’`) become `'`. Names with
  a missing given name and passport numbers are left as they are.
- Owner decisions: club names and venue names are not changed (sponsors;
  EuroLeague writes venues in capitals). `jersey_name` and `abbreviated_name`
  are not changed. The standings `position` (a rank) is not changed.
- Must not break: player and club matching. Gold matches on IDs and on
  `normalized_name` from the raw payload, not on these columns, so the
  name-matching warnings of a full run must stay the same. No schema change, no
  new dependency, no Neon access.
- `docs/DATA_DICTIONARY.md` documents the stored forms under Source value rules,
  and notes that `status`, not the raw `game_status`, is the game state to use.

## Build steps

The code for both steps was written and run in this branch before the spec was
recorded. `/implement` reviews it against these steps instead of rewriting it.

- [x] 1. **Cleaning functions and schema wiring.** `text_clean.py`, the `clean`
  names in `flat_schema.py`, the call in `flat_transform.py`, and
  `postgres_etl/tests/test_text_clean.py` covering each function and the column
  mapping (including the columns that must stay uncleaned).
  Done when: the four test commands in `AGENTS.md` pass.

- [x] 2. **Local rebuild and docs.** Update `docs/DATA_DICTIONARY.md`, then
  rebuild everything locally from existing Bronze:
  `python pipeline.py --all --skip-fetch` and
  `python pipeline.py -cp eurocup --all --skip-fetch`.
  Done when: both runs exit 0 with Gold quality passing and no Neon connection;
  `silver.people` has no all-caps `name`; each city has one spelling;
  `UK`, `IVO`, `ZAI`, `FYR`, `LAD` and `NAT` are gone from the country columns;
  `role_name` has no underscores or `Assitant`; `position` holds only 1, 2, 3
  or NULL; Gold tables carry the new names; and the name-matching warnings
  match the 2026-10-10 full run.

## Verify

- The four test commands in `AGENTS.md` pass.
- The checks in step 2's "done when" hold in the local database.
- Spot-check in Gold: `Brown III, John`, `Wright IV, McKinley`,
  `Cowan Jr., Anthony`, `McCarty, Kelly`, `O'Bannon, Larry`, `Istanbul`.
- Neon is not touched by this fix. A republish of all EuroLeague seasons
  E2000-E2026 follows separately, after the owner tests locally and approves,
  and is timed with the frontend changes in `jmp-euroleague2`. EuroCup stays
  local.
- The change touches only Silver value parsing and docs (no auth, secrets,
  destructive operations or publishing), so the `when-sensitive` independent
  review is not expected to be selected; `/audit current` remains available.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":5122,"specSha256":"cf5cd086fc9aebeea26bc6e7626e1edb8190e522336e5e0cd9f06f5736b825f2","branch":"refs/heads/fix/standardize-silver-names","head":"775e80438b6405356d47173ec5e0a975696a2787","baseRef":"refs/heads/main","baseCommit":"775e80438b6405356d47173ec5e0a975696a2787","sourceTree":"baadadf9662eeaed72825549498816ca8b545e35","absentOptional":[]} -->

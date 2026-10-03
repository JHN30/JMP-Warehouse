# Fix: Correct per-game dictionary wording and measure the Neon size

**Type:** Fix
**Status:** verified (both steps; guard tests pass; Neon size measured read-only on 2026-10-03)
**Branch:** `fix/correct-per-game-dictionary-wording-and-measure-the-neon-size`
**Fixes:** F-08, F-09, F-10

## The problem

Three P3 findings from the 30h-30j audit of 2026-10-02 are still open. Two are
wording in [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) (the "Nine per-game
tables" paragraph, lines 520-528 now; the findings cited 518-519), one is an
unmeasured number:

- **F-09:** the paragraph says each table "is defined in its own section below
  (see "Derived per-game advanced tables" and the `game_team_*` and
  `game_player_on_court` sections)". `game_stat_gaps` has no section of its own:
  it is defined in the Silver table list ("Silver table names and keys", row at
  line 97) and the stat-name note at line 486. `game_team_lineup_stints` has a
  section but only `game_player_on_court` is named. One source line is about 150
  characters while its neighbours wrap near 90.
- **F-10:** the same paragraph says the tables are "published to Neon as
  `public.app_<name>` for E2025 and E2026" while the per-table sections add "once
  the reviewed migration is applied". The 30h-30j tables were published for E2026
  by the `refresh_20261003_174706` run, but that log shows only E2026, so the flat
  statement is not proven for E2025.
- **F-08:** "about 25 MB for all of 30h-30j in Neon" (build-plan item 30i,
  project overview item 30j) was scaled from Silver table sizes on top of a 153 MB
  baseline (512 MB free tier). Nothing in the repository records a measured Neon
  size.

## The fix

**1. Wording (F-09, F-10)** in the "Nine per-game tables" paragraph only:

- name the real places: "Derived per-game advanced tables" for
  `game_player_advanced` and `game_team_advanced`; the `game_team_possessions`
  through `game_team_lineup_stints` sections (including `game_player_on_court`);
  and "Silver table names and keys" for `game_stat_gaps`;
- add "once their reviewed migrations are applied" to the publish sentence, as
  every per-table section already does;
- rewrap the long line to the neighbours' width.

No requirement or table description changes.

**2. Measure the size (F-08).** With the owner's yes, run one read-only query
against Neon (no writes) from a scratch script outside the repository:
`pg_database_size(current_database())` and `pg_total_relation_size` of the nine
`public.app_*` tables of 30h-30j. Record the measured database size, the sum for
the nine tables and the date in one sentence of the dictionary's "Neon app-table
contract" section. The planning documents (`build-plan.md`, `project-overview.md`)
keep their original estimate: they are the owner's plan, and changing them would
move the overview's source fingerprint.

**Must not break:**
- every other dictionary section and the tables the tests read;
- the planning documents and the archived feature specs (history stays as written).

## Build steps

- [x] **Step 1 - Dictionary wording (F-09, F-10)** - edit the paragraph as above.
  *Done when:* `git diff` touches only that paragraph and every section it names
  exists in the dictionary (check the headings with `grep`).
- [x] **Step 2 - Measured Neon size (F-08)** - run the read-only size query with
  the owner's yes and add one sentence with the figures to the Neon contract
  section. *Done when:* the sentence states the measured size and date, and the
  query output is quoted in the summary of the step.

## Verify

- `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`
  still passes (no test reads the dictionary, so this only guards the tree).
- `grep -n "Nine per-game tables" -A 10 docs/DATA_DICTIONARY.md` shows the named
  sections, the migration qualifier and no line over about 95 characters.
- The measured size is below the 512 MB free-tier limit, or the owner is told
  otherwise.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":3989,"specSha256":"de260673a35627442d77d979c76d44b09c6fabab8d3b1a46369c88ff2d1f2adb","branch":"refs/heads/fix/correct-per-game-dictionary-wording-and-measure-the-neon-size","head":"b16fb5e5395ed4c23844b466af92894fc7289ef0","baseRef":"refs/heads/main","baseCommit":"b16fb5e5395ed4c23844b466af92894fc7289ef0","sourceTree":"e2c3c491c298f88e3d912b0fbd6d55f77e1f45de","absentOptional":[]} -->

## Findings

### correct-per-game-dictionary-wording-and-measure-the-neon-size/F-08 [P3] closed - The roughly 25 MB Neon size for 30h-30j is an estimate, not a measurement

**File:** blueprint/context/current-feature.md:76
**Found:** 2026-10-02 by /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the figure comes from Silver table sizes scaled by row counts. Neon was
153 MB of the 512 MB free tier when measured, so there is headroom, but nothing has been
published yet to confirm the real size, including primary-key index overhead.
**Suggested fix:** after the migrations are applied and E2025 and E2026 are published,
compare `pg_database_size` with the 153 MB baseline.
**Resolution:** fixed on 2026-10-03 by fix/correct-per-game-dictionary-wording-and-measure-the-neon-size. Read-only query on Neon: the nine 30h-30j tables take 24.8 MB (the 25 MB planned) and the database 197.9 MB of the 512 MB free tier; recorded in the dictionary's Neon app-table contract section. Closed by /audit current on 2026-10-03: the recorded figures match a second read-only check, and E2025 and E2026 are both in the nine tables.

### correct-per-game-dictionary-wording-and-measure-the-neon-size/F-09 [P3] closed - The dictionary's per-game paragraph points at sections that do not exist for all nine tables

**File:** docs/DATA_DICTIONARY.md:518
**Found:** 2026-10-02 by /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the new "Nine per-game tables" paragraph says each table "is defined in its
own section below (see 'Derived per-game advanced tables' and the `game_team_*` and
`game_player_on_court` sections)". `game_stat_gaps` has no section of its own (it is defined in
the Silver table list and the stat-name notes), and `game_player_on_court` is the only on-court
section the pointer names although `game_team_lineup_stints` has one too. The same paragraph has
one source line over 150 characters where the neighbours wrap near 90.
**Suggested fix:** name the exact sections ("Derived per-game advanced tables", `game_team_possessions`
through `game_team_lineup_stints`, and the Silver table list for `game_stat_gaps`) and rewrap the
long line. No current requirement would be lost.
**Resolution:** fixed on 2026-10-03 by fix/correct-per-game-dictionary-wording-and-measure-the-neon-size. The paragraph names "Derived per-game advanced tables", the sections from `game_team_possessions` through `game_team_lineup_stints`, and "Silver table names and keys" for `game_stat_gaps`; the long line is rewrapped. Closed by /audit current on 2026-10-03: every named heading exists in the dictionary and no line of the paragraph exceeds 95 characters.

### correct-per-game-dictionary-wording-and-measure-the-neon-size/F-10 [P3] closed - The same paragraph says the tables are published to Neon without the migration qualifier

**File:** docs/DATA_DICTIONARY.md:519
**Found:** 2026-10-02 by /audit (scope: current; lenses: quality, security, performance, tests)
**Why it matters:** the paragraph states the nine tables are "published to Neon as
`public.app_<name>` for E2025 and E2026", while each per-table section (and the Neon contract
paragraph) adds "once the reviewed migration is applied". Until the owner applies the 30h, 30i and
30j migrations and publishes, the flat statement is untrue. It becomes accurate after publishing.
**Suggested fix:** add "once their reviewed migrations are applied" to the sentence, or leave it
and re-read it after the first publish.
**Resolution:** fixed on 2026-10-03 by fix/correct-per-game-dictionary-wording-and-measure-the-neon-size. The publish sentence now reads "once their reviewed migrations are applied", like the per-table sections. Closed by /audit current on 2026-10-03: a read-only query shows E2025 and E2026 rows in all nine tables except the empty `app_game_stat_gaps`, so the wording is accurate.

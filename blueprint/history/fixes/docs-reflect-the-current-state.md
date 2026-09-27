# Fix: Docs reflect the current state

**Type:** Fix
**Status:** verified
**Branch:** `fix/docs-reflect-the-current-state`

## The problem

`docs/` should hold only what describes the project today, with the data
dictionary as the one reference for the tables:

- `docs/PIPELINE-ANALYSIS.md` (pre-Blueprint analysis, target design and
  milestones) and `docs/PIPELINE-HANDOFF.md` (the original handoff from the
  web-app repo) are history, not the current state. `README.md` line 58 links
  to both.
- `docs/DATA_DICTIONARY.md` has two outdated statements about the web app
  (checked against `jmp-euroleague2/backend/src` on 2026-09-27):
  - Coverage section (around line 440): says Express hardcodes `shotLocations`
    and `playByPlay` as `unavailable` and that fixing it is later work. Express
    now reads `app_coverage_seasons` / `app_coverage_games` directly
    (`db/season-coverage.ts`).
  - `app_team_season_stats` (line 379) and the coverage intro (line 403) say
    "mirroring" an Express route. Express now reads both tables
    (`db/season-games.ts`, `db/season-coverage.ts`).

## The fix

- Delete `docs/PIPELINE-ANALYSIS.md` and `docs/PIPELINE-HANDOFF.md` (Git keeps
  their history).
- Update the `docs/` row in `README.md` to link only the data dictionary.
- In the data dictionary, change only those statements to what the web app
  does today. The records tables stay described as still computed in Express
  (true: `routes/seasons.ts`, `SUPPORTED_SEASONS` E2025-E2026).
- Must not change: any table description, column contract, or section layout of
  the data dictionary (owner decision: leave the table explanations as they are).

## Build steps

- [x] **Step 1 - Remove the history docs and correct the web-app status** - the
  three edits above. *Done when:* `docs/` holds only `DATA_DICTIONARY.md`; a
  search of the repository (excluding `data/` and `blueprint/history/`) finds no
  link to either `PIPELINE-*` file; the dictionary no longer says Express
  hardcodes the coverage items or only mirrors the two tables; `git diff` of the
  dictionary touches only those statements.

## Verify

- `ls docs` shows only `DATA_DICTIONARY.md`.
- The README `docs/` row links the data dictionary only.
- Read the coverage and team-season-stats sections of the dictionary.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":2342,"specSha256":"708dc0b185a2c63e0cb1c6c5ba4a0c82a364bcfe3a4ea6f9ff60956f714225c4","branch":"refs/heads/fix/docs-reflect-the-current-state","head":"15d22f99970c433163e8343f6c9e1b7f7a78011a","baseRef":"refs/heads/main","baseCommit":"15d22f99970c433163e8343f6c9e1b7f7a78011a","sourceTree":"83655c826219cf76d767902ef6f6ec63e0fff8c9","absentOptional":[]} -->

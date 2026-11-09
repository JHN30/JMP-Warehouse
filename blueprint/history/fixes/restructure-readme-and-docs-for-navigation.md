# Fix: Restructure README and docs for navigation

**Type:** Fix
**Status:** verified
**Branch:** `fix/restructure-readme-and-docs-for-navigation`

## The problem

The root `README.md`, the five stage READMEs and the eight files in `docs/`
(about 7,700 lines) are hard to navigate in VS Code and on GitHub:

- Long files have no contents list; the stage READMEs (`postgres_etl`,
  `gold_etl`, `neon_publish`) are walls of text without headings.
- Very wide tables: the `api_requests` endpoint table has 7 columns, and
  `STAT_GLOSSARY.md` rows reach 749 characters because every cell repeats long
  inline links.
- Topics are repeated across files (document maps in every doc, the Neon
  contract, provenance, refresh rules, endpoints), so copies drift.
- Several statements are wrong or stale against the code:
  - root README quick start runs `python api_requests/main.py -sc E2025`, which
    the fetcher rejects (it accepts start years only);
  - `SILVER_TABLE_REFERENCE.md` and `SILVER_CATALOG.md` say 36 Silver data
    tables; `flat_schema.ALL_TABLES` has 33;
  - `DATA_CATALOG.md` and `SILVER_CATALOG.md` still treat the retired
    `team_round_*` tables as Gold tables to read or join;
  - `DATA_DICTIONARY.md` says some tables are "not published until the
    cutover", names `app_season_stats_traditional` (does not exist), and says
    the app supports E2025-E2026 only (it supports E2000-E2026);
  - `neon_publish/README.md` omits the applied `30k` and `30l` migrations.

The owner supplied documentation writing rules (structure, short sections,
tables for comparisons, one authoritative place per topic, verify against code,
mark destructive commands).

## The fix

Documentation only; no code, schema or behaviour changes.

- Rewrite the six READMEs with an intro, contents, option tables, numbered
  steps and warning callouts for live Neon publishing and the scheduled task.
- Restructure the `docs/` files: contents lists, consistent per-table blocks,
  reference-style links in the glossary tables, back-to-list links in the two
  column references.
- One home per topic: root README holds the documentation map; `api_requests`
  README covers fetcher behaviour, `BRONZE_CATALOG.md` what is stored;
  `DATA_DICTIONARY.md` calculation rules and validation; `STAT_GLOSSARY.md`
  metric definitions.
- Correct the stale statements listed above, each checked against the code (or
  the app repo for app-side facts).
- Mark `docs/gold-name-alignment-2026-10-10.md` as a historical record.

Must not change:

- `docs/` filenames: the app repo copies them by name into
  `jmp-euroleague-2/docs_from_warehouse/`.
- Headings linked from outside: `DATA_DICTIONARY.md#standard-column-names`,
  `#season-player-qualification-columns-30l`,
  `#derived-per-game-advanced-tables`, `SILVER_CATALOG.md#eurocup`,
  `#provenance`, `GOLD_TABLE_REFERENCE.md#app_*`, `#record-metric-values`.
- Any recorded rule, formula or validation figure (restructured, not dropped).

## Build steps

- [x] **Step 1 - Restructure and correct the READMEs and docs** - the edits
  above (already drafted in the working tree on `main`; move them to the fix
  branch). *Done when:* all 14 files follow the structure above, the stale
  statements are corrected, and a relative-link and anchor check over the 14
  files plus `AGENTS.md` and `blueprint/context/*.md` reports no problems.

## Verify

- Run a link check over the edited Markdown: every relative file link exists and
  every `#anchor` matches a heading (GitHub slug rules); every reference-style
  link in `STAT_GLOSSARY.md` has a definition.
- Run the command fixes: `python api_requests/main.py -sc E2025 -ds seasons`
  fails with "Invalid season code" while `-sc 2025` parses; the Silver table
  count from `flat_schema.ALL_TABLES` is 33.
- Existing unit tests still pass (no code changed):
  `cd api_requests && python -m unittest tests.test_scrapper`,
  `python -m unittest discover -s postgres_etl/tests`,
  `python -m unittest discover -s gold_etl/tests`,
  `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export`.
- Manual: open `README.md` and one `docs/` file in VS Code preview and on
  GitHub; the contents links jump to their sections and tables fit the page.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":4332,"specSha256":"e392c3a833a6415ef0da6bcf4540b2076540f8d40a4e789711905b2c81d8448d","branch":"refs/heads/fix/restructure-readme-and-docs-for-navigation","head":"344791497e33f59c06a64dc14d1a809e8124a08a","baseRef":"refs/heads/main","baseCommit":"344791497e33f59c06a64dc14d1a809e8124a08a","sourceTree":"b2db5625d5c97e2e3cece82de044682c63043a85","absentOptional":[]} -->

# Feature: CSV Export of Every Table

**From build-plan:** feature 31
**Build attempt:** 1
**Status:** verified
**Branch:** `feature/csv-export-all-tables`

## Goal

Change `tables_to_csv` so every table in the local `silver` and `gold` schemas is exported as one CSV file per table (all seasons), ready to import into SQL Server Management Studio for analysis. This replaces the previous per-season, Silver-flat-tables-only layout.

## In scope

- Tables discovered from the database (`information_schema`, both schemas, base tables only), so derived and local-only tables are included without code changes. Output `data/csv_export/<competition>/<schema>/<table>.csv`.
- CLI: `--layer silver|gold|all`, `-tb` (name in both layers exports both), `-sc` defaulting to `all` (filters tables with a `season_code` column), `-cp` (filters tables with a `competition_code` column), `--dry-run`, `--list-tables` (now reads the database), `--output-root`, `--config`.
- SSMS-friendly format: UTF-8 with a byte-order mark, header row, booleans as 1/0, rows ordered by primary key, temporary file then atomic replace.
- Tests, `tables_to_csv/README.md`, `README.md` runbook and layout, `AGENTS.md`.

## Out of scope

- SQL Server `CREATE TABLE` or `BULK INSERT` scripts, per-season files, Neon, and any change to the database.

## Build loop

Follow `workflow.stepReview: "feature"`; `workflow.checkpointCommits: "disabled"`; `/complete` creates the work commit.

## Build steps

- [x] **Step 1 - Discovery, queries and export.** New `utils.py` and `main.py`.
  *Done when:* unit tests cover CLI defaults, table selection, query building (filters, key order, boolean cast, quoting), discovery grouping, the byte-order mark and atomic replace; `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export` passes.
- [x] **Step 2 - Real-data check and docs.** Dry run for all tables, export three tables, check the BOM, booleans and quoting, update the docs.
  *Done when:* `--dry-run` reports 75 tables, the exported files have the BOM and 1/0 booleans, and the docs describe the command.

## Files / areas

- `tables_to_csv/main.py`, `tables_to_csv/utils.py`, `tables_to_csv/tests/test_csv_export.py`, `tables_to_csv/README.md`, `README.md`, `AGENTS.md`.

## Data / contracts

- Read-only session, `REPEATABLE READ`. Identifiers and literals are quoted in the generated SQL; identifiers come from the catalog and season codes are validated by `select_seasons`.

## Testing

- Unit tests with fake cursors; real-data check on E2000-E2026 (75 tables, 10.8 million rows on a dry run).

## Notes for the AI

- Feature added at the owner's request, one file per table chosen over per-season files. numpy and pandas are not needed.


<!-- blueprint:completion {"schemaVersion":1,"specBytes":2742,"specSha256":"16a476c501d443d2a7c69579176a349b9bb61b7c9a164113c7b25c18f6e49b97","branch":"refs/heads/feature/csv-export-all-tables","head":"83bf232662aef4f54f69d9b23f6a3037337b710b","baseRef":"refs/heads/main","baseCommit":"83bf232662aef4f54f69d9b23f6a3037337b710b","sourceTree":"01dd7150edb47fdbe6bbcd8dcf9a453a957830c2","absentOptional":[]} -->

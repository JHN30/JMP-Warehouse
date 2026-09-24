# Coding Standards

> Tuned to this project by `/adopt` (2026-09-24): a Python + PostgreSQL data
> pipeline with no web framework. These describe what the code already does.

## Python

- Python 3.13, standard library first. Third-party packages in use: `requests`
  (fetch) and `psycopg2-binary` (PostgreSQL). Add a dependency only for a
  current need. There is no dependency file yet (build-plan item 17).
- No dbt, DuckDB, pandas or ORM. Transformations are Python; queries are plain SQL.
- `snake_case` functions, variables and modules; `PascalCase` classes;
  `UPPER_CASE` module constants.
- Dataclasses for small records (`Field`, `Table`, `Check`, `Issue`).
- `pathlib.Path` for files; UTF-8 explicitly when reading or writing text.

## Project Structure

- One folder per pipeline stage, each with `main.py` (argparse CLI), its
  modules, `README.md` and `tests/`:
  - `api_requests/` - fetch into bronze
  - `postgres_etl/` - load into local PostgreSQL and quality checks
  - `neon_publish/` - publish to Neon
  - `tables_to_csv/` - CSV export
- `common/` holds code shared by stages: `bronze.py`, `db.py`, `seasons.py`.
  Stage scripts put the project root on `sys.path` in one place (for example
  `postgres_etl/shared.py`, `api_requests/scrapper.py`) and import `common` from there.
- `pipeline.py` orchestrates the stages as subprocesses.
- `docs/` holds the data dictionary and pipeline notes; keep them in sync with
  schema or rule changes. `old/` is retired material, never imported.
- Scripts run from the repository root (`python <stage>/main.py ...`); the
  fetcher also runs from inside `api_requests/`.

## CLI Conventions

- Shared flags: `-cp/--competition` (`euroleague`, `eurocup`),
  `-sc/--season-code` (year, `E2025`, range `2000-2025`, `current`, `latest`,
  `all`), `-tb/--table` (logical names without `etl_flat_`), `--dry-run`.
- Exit codes: 0 success, 1 failure, 130 interrupted.
- Progress goes to stdout with `flush=True`; each run is also written to
  `logs/<stage>/` (`common.db.log_directory`).

## Data Rules

- Bronze is never edited: exact response bytes, one new version only when the
  content changes. Readers use the latest version.
- `NULL` means unavailable, never 0. When the source uses 0 for "unknown",
  store `NULL` and keep the reason visible (a note column, `game_stat_gaps`, or
  a quality warning). Do not silently fix or fill source problems.
- Every season-scoped table has `competition_code` + `season_code` in its
  primary key; keep source natural keys, not surrogate ids.
- Table schemas live in `postgres_etl/flat_schema.py` (columns, types, source
  paths, keys). Derived values use `@name` paths filled in `raw_transform.py`.
- One owner per aggregation: a figure is computed either in this pipeline or in
  the app API, never both.

## Database

- `psycopg2` with parameters (`%s`) for values and `psycopg2.sql.Identifier`
  (or schema-registered names) for identifiers. Never build SQL from input.
- Local loads replace one table, competition and season in one transaction
  (DELETE then INSERT). Neon publishes replace one season in one transaction
  with row-count verification and the shrink guard.
- Schema changes are additive: `CREATE TABLE IF NOT EXISTS`, add missing
  columns. Never `DROP` in pipeline code.
- Local connection settings come from `postgres_etl/config_connection.json`
  (not committed); Neon from the `NEON_DATABASE_URL` environment variable.
  Never write credentials to files, logs or docs.

## Error Handling

- Fetch failures are recorded (`failures.jsonl`, manifest) and never stop a
  season; reruns resume from bronze.
- Loaders raise `ValueError` with table, field and season context; the CLI
  prints it and exits 1.
- Quality checks: `ERROR` for broken integrity (fails the load and blocks the
  pipeline's publish), `WARN` for known, explained source problems.

## Testing

The project has a test runner: plain `unittest` (see Commands in `AGENTS.md`).
**Tests are a gate for logic-bearing steps.** A step that adds or changes logic
ships a passing test in the same reviewable diff, and all test commands must be
green before the step is approved and before `/complete` merges.

- **What to test:** pure logic where a wrong answer is possible: transforms
  and derivation rules, parsers, season-code selection, refresh rules, quality
  check selection, publish guards.
- **How:** tests live in `<stage>/tests/test_*.py`. Build inputs with temporary
  directories and `BronzeStore` fixtures, fake API clients and fake cursors.
  Unit tests never call the EuroLeague API or a real database.
- **What not to unit test:** real API calls and real database behaviour. Verify
  those with a dry run, read-only queries, or a load or publish into a scratch
  schema of the local database that is dropped afterwards.
- An empty suite should fail, not pass, so "no tests ran" never looks like "passed".

## Data Verification

This project has no UI, so "browser evidence" does not apply. Behavioural
evidence for pipeline changes is:

- `postgres_etl/main.py ... --dry-run` for parsing, types and keys, then a real
  load and its quality report for the affected seasons.
- Read-only SQL against local PostgreSQL to confirm row counts and the rule's
  effect (before and after), across all seasons when the rule is season-dependent.
- `neon_publish/main.py --dry-run` before any publish. Publishing to Neon, or
  any API request beyond a small smoke test, needs the owner's explicit yes.

## Code Quality

- No commented-out code unless specified
- No unused imports or variables
- Keep functions under 50 lines when possible

## Comments

Write code that explains itself; comment only what the code cannot say.
Over-commenting is a common AI tell, so resist it.

- Comment the **why**, not the **what**. Delete any comment that restates the code.
- No banner/header blocks, section dividers, or step-by-step narration of obvious
  code. A file does not need a comment announcing each region.
- A comment earns its place only when it captures something the code can't: a
  non-obvious decision, a gotcha or workaround, why a value is what it is, or a
  link to a spec or issue.
- Prefer self-documenting names and small functions over explanatory comments.
- Keep doc comments minimal: a one-line purpose on an exported type or function is
  plenty; don't write JSDoc that just repeats the signature.
- When in doubt, leave the comment out.

## Writing

- No em dashes (U+2014) in generated content: docs, comments, commit messages,
  READMEs, specs. They read as AI-generated.
- Use a hyphen for `term - description` separators; rephrase prose with commas,
  parentheses, or a colon. Avoid en dashes and the ellipsis character too.

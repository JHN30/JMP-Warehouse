# JMP Warehouse

**JMP Warehouse** is the data pipeline behind [JMP EuroLeague](https://www.jmpeuroleague.com/). It collects EuroLeague API data, preserves the original responses, loads clean tables into local PostgreSQL, calculates advanced basketball statistics, and publishes the tables the web app reads to Neon.

It also provides a local database and CSV exports for historical analysis and the [JMP Rating](https://github.com/JHN30/JMP-Rating) project.

**Live App:** https://www.jmpeuroleague.com/

---

## Motivation

The goal was to build a reliable foundation for exploring EuroLeague basketball, both in the web app and through my own analysis.

The source data is spread across several APIs. Some endpoints overlap, others update late, and historical records have gaps or inconsistent identifiers. Keeping the original responses makes it possible to trace a number back to its source and rebuild the database without downloading everything again.

I also wanted to go beyond the statistics supplied by the API. Box scores, play-by-play, shots, and substitutions let us calculate advanced player and team statistics, reconstruct lineups, and follow how performance changes throughout a season.

JMP Warehouse brings that work into one pipeline: preserve the source, make its limitations visible, calculate the statistics once, and give the app and my analysis a consistent set of tables.

---

## Quick Start

### Set Up Locally

Use Python 3.13 and a local PostgreSQL database. The project is developed with PostgreSQL 18 on Windows; the commands below use PowerShell and run from the repository root.

```powershell
# Clone the repository
git clone https://github.com/JHN30/JMP-Warehouse.git
cd JMP-Warehouse

# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install the packages used by the pipeline
python -m pip install requests psycopg2-binary numpy

# Copy the local database configuration
Copy-Item postgres_etl/config_connection.example.json postgres_etl/config_connection.json
```

Create the database named in the configuration, then edit `postgres_etl/config_connection.json` with your local connection settings. The loaders create their schemas and tables. NumPy is needed for RAPM; the other stages use Requests, psycopg2, and the standard library. There is no dependency file yet.

### Build a Season Locally

```powershell
# Fetch API responses into Bronze
python api_requests/main.py -sc E2025

# Check the cached source data without connecting to PostgreSQL
python postgres_etl/main.py -sc E2025 --dry-run

# Load Silver and calculate its per-game statistics
python postgres_etl/main.py -sc E2025

# Build Gold and check the results
python gold_etl/main.py -sc E2025
python gold_etl/main.py -sc E2025 --quality-only
```

`E2025` means the 2025-26 season. Fetching a full season can take time: API requests are spaced 2.5 seconds apart by default. Reruns reuse cached responses and resume completed downloads.

These commands build the local database. Neon configuration is needed only for the publishing stage.

---

## Usage

### Core Features

- **API extraction and refresh**
  Download fixtures, clubs, people, rosters, box scores, standings, season statistics, play-by-play, and shots. Refresh changing current-season data and retain earlier snapshots when the API returns an older or less complete statistics feed.

- **Bronze archive**
  Keep exact response bytes in compressed, versioned files with request manifests. A new version is stored only when the response changes.

- **Silver tables and provenance**
  Load 28 typed source tables with consistent column names, load IDs, timestamps, and references to the Bronze versions used. Record missing statistics and source problems so they remain visible.

- **Advanced player and team statistics**
  Calculate per-game and cumulative per-round statistics, including possessions, pace, ratings, four factors, player rates, Game Score, PIE, PER, Win Shares, strength-adjusted ratings, and home/away and recent-game splits.

- **Play-by-play and lineup analytics**
  Count possessions, measure score flow and clutch results, build shot splits and zones, reconstruct on-court intervals and lineup stints, and calculate on/off, 2/3/5-man lineup ratings, and RAPM.

- **App-ready Gold tables**
  Build standings, team-season totals, coverage, all-time records, postseason series, cross-season player and club identities, and player ranking qualification fields. Gold also includes the per-game tables needed for game detail pages.

- **Guarded Neon publishing**
  Publish through 47 fixed Gold-to-Neon mappings, where each local Gold table has the same name as its Neon table, with schema checks, Gold quality checks, row-count checks, and a shrink guard. All selected scopes commit together; a failed publish rolls back.

- **CSV export**
  Export every local Silver and Gold table to one CSV file per table, with optional season and table filters, for analysis and import into SQL Server Management Studio.

---

### Data

The pipeline follows four stages:

```text
EuroLeague APIs -> Bronze files -> local Silver -> local Gold -> Neon -> web app
                                                       |
                                                       +-> CSV / private analysis
```

| Layer | Contents |
| --- | --- |
| **Bronze** | Exact, gzipped API responses under `data/bronze/`, with manifests and version history |
| **Silver** | Clean source tables, load provenance, and per-game calculations in local PostgreSQL |
| **Gold** | Source projections, aggregates, identities, advanced statistics, and app-ready tables built from Silver |
| **Neon** | The Gold tables under the same `app_*` names in PostgreSQL `public`, published per season for the separate web app |

CSV export reads both local Silver and Gold tables.

Key concepts:

- Local EuroLeague history covers E2000 onward, including the current season. Play-by-play and shot-based analytics start at E2007 and depend on source coverage.
- Local historical coverage is broader than the season data published to Neon. The newer advanced and per-game publishing work was scoped to E2025 and E2026; older-season publishing depends on storage and an approved publishing scope.
- `competition_code` and `season_code` identify season data. Player and club identity tables connect records across seasons.
- Missing or unrecorded values stay `NULL`. Known gaps and source inconsistencies are reported rather than silently filled with zero.
- Box-score possession estimates and possessions counted from play-by-play are kept separately.
- Player season statistics include calculated per-game rows where needed, a minimum-games threshold, and a `qualified` flag for rankings.

Table definitions, formulas, coverage rules, and published names are documented in [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md).

JMP Rating, win probabilities, and prediction work belong to the separate [JMP Rating](https://github.com/JHN30/JMP-Rating) project. EuroCup expansion, broader historical publishing, dependency packaging and CI, and scheduled refreshes remain planned work.

---

### Common Commands

Run from the repository root:

```powershell
# Refresh the current season, build local tables, and preview Neon changes
python pipeline.py --dry-run-publish

# Fetch and rebuild all local history (no Neon publish)
python pipeline.py --all

# Rebuild Silver and Gold from existing Bronze (no API fetch or Neon publish)
python pipeline.py --all --skip-fetch

# Inspect or check local data
python postgres_etl/main.py -sc E2025 --quality-only
python gold_etl/main.py -sc all --dry-run
python gold_etl/main.py -sc all --quality-only

# Build selected Gold tables
python gold_etl/main.py -sc E2025 -tb app_team_round_stats app_player_round_stats

# Inspect publishing mappings and preview one season
python neon_publish/main.py --list-tables
python neon_publish/main.py -sc E2025 --dry-run

# Preview CSV row counts, then export local tables
python tables_to_csv/main.py --dry-run
python tables_to_csv/main.py
```

`pipeline.py --dry-run-publish` still fetches data and writes local Silver and Gold tables; only the Neon stage is read-only. It needs a Neon connection and keeps publishing pending for a later live retry.

`pipeline.py --all` selects API years from 2000 through the current season automatically, using the fetcher's normal caching rules and refreshing changing current-season feeds. Both full-history commands load all cached seasons into Silver, rebuild all loaded seasons in Gold, and check Gold quality. They always rebuild even if the fetch found no changes, stop at a failed stage, write a refresh log and summary, and never connect to Neon. They leave the current-season publish pending for a later `python pipeline.py`. The same commands are available as VS Code tasks. `--all` rejects `-sc`, `--dry-run-publish`, and `--allow-shrink`.

After explicit owner approval, `python pipeline.py` runs the current-season refresh through live Neon publishing. It skips downstream work when nothing changed and no publish is pending, and finishes with a summary and a log in `logs/refresh/`.

Individual fetch and local load/build stages accept season codes, years, ranges such as `2000-2025`, and selectors such as `current` or `all`. The Neon publisher handles one season per invocation. See each stage's README for its exact selectors and options.

---

### Tech Stack

**Pipeline**

- Python 3.13
- Requests for API extraction
- psycopg2-binary for PostgreSQL access
- NumPy for RAPM ridge regression
- Standard-library tools for compression, JSON, CSV, command-line parsing, and orchestration

**Storage**

- Versioned gzip/JSON files for Bronze
- Local PostgreSQL 18 for Silver and Gold
- Neon PostgreSQL for app-facing tables
- CSV exports for SQL Server / SSMS analysis

**Testing**

- Python `unittest`
- Temporary Bronze fixtures, fake API clients, and fake database cursors
- Dry runs and quality reports for data verification

**Operation**

- Manual command-line runs on the owner's Windows PC
- Per-stage logs, a current-season refresh command, and full local history rebuilds
- The web app lives in a separate repository

---

## Contributing

Contributions are welcome, especially improvements to extraction, data quality, statistical calculations, documentation, and tests.

### What You Can Do

- Review transformation rules and advanced-stat formulas.
- Add regression coverage for API quirks and historical edge cases.
- Improve quality reports, command-line behavior, and documentation.
- Report missing data, incorrect values, or feature ideas through issues.

### Running Locally

Use your own PostgreSQL instance and the setup above. Source data is fetched from the EuroLeague APIs; Bronze files, credentials, and local run output are not included in the repository. You can build and analyse local data without access to the owner's Neon database.

Unit tests use fixtures and fake connections and do not call the real APIs or databases:

```powershell
# API extraction tests
Push-Location api_requests
python -m unittest tests.test_scrapper
Pop-Location

# Silver and Gold tests
python -m unittest discover -s postgres_etl/tests
python -m unittest discover -s gold_etl/tests

# Publishing and CSV export tests
python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export
```

There is no build, lint, format, typecheck, or combined Verify command yet.

### Contributing Workflow

- Fork the repository and create a feature branch.
- Read [AGENTS.md](AGENTS.md) and the [coding standards](blueprint/context/coding-standards.md).
- Keep relevant tests, stage documentation, and the data dictionary in sync with changes.
- Open a pull request to `main`.

The project uses Blueprint to track planned work and completed features. See [blueprint/build-plan.md](blueprint/build-plan.md) and [blueprint/history/](blueprint/history/).

---

### Configuration

Local PostgreSQL settings live in `postgres_etl/config_connection.json`, copied from the committed [example](postgres_etl/config_connection.example.json):

```json
{
  "database": "jmp_euroleague",
  "user": "postgres",
  "password": "<your local PostgreSQL password>",
  "host": "localhost",
  "port": "5432"
}
```

For Neon previews or publishing, set `NEON_DATABASE_URL` in the environment or in a `.env` file at the repository root. Use a direct, non-pooled connection:

```dotenv
NEON_DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require
```

Both credential files are ignored by Git. Live Neon publishing and applying migrations require explicit owner approval. The recurring publisher checks the schema but never runs migrations itself. Migration details are in [neon_publish/README.md](neon_publish/README.md).

---

### Project Layout

| Path | Purpose |
| --- | --- |
| [pipeline.py](pipeline.py) | Current-season refresh and full local history rebuild |
| [api_requests/](api_requests/README.md) | API extraction, caching, and refresh rules |
| [postgres_etl/](postgres_etl/README.md) | Silver loading, provenance, per-game analytics, and quality checks |
| [gold_etl/](gold_etl/README.md) | Gold projections, aggregates, and advanced statistics |
| [neon_publish/](neon_publish/README.md) | Guarded publishing contracts and reviewed migrations |
| [tables_to_csv/](tables_to_csv/README.md) | CSV exports of local tables |
| `common/` | Shared Bronze, database, and season helpers |
| [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) | Table contracts, statistical definitions, and data rules |
| `blueprint/` | Project plans, workflow context, and completed-work history |
| `data/`, `logs/` | Local data and run output, ignored by Git |

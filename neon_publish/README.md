# Neon publisher (`neon_publish`)

The publisher copies one EuroLeague season from the local `gold` schema to the `public.app_*` tables on Neon, which the web app (repository `jmp-euroleague2`) reads. It is the last stage of the pipeline and the only one that writes to a remote database.

> [!WARNING]
> A live publish changes the production data the web app shows. It requires the owner's explicit approval. The daily scheduled refresh is the owner's standing approval for its own current-season publish; every other live run needs a separate yes.

## Contents

- [How publishing works](#how-publishing-works)
- [Running the publisher](#running-the-publisher)
- [Safety guards](#safety-guards)
- [Configuration](#configuration)
- [Schema migrations](#schema-migrations)
- [Testing](#testing)

## How publishing works

The publisher uses 40 fixed mappings. Every Gold table has exactly the same name as its Neon target, for example `gold.app_games` → `public.app_games`; names are copied as they are and never prefixed.

| Tables | What one run replaces |
| --- | --- |
| Records (`app_records_player_seasons`, `app_records_single_games`, `app_records_team_seasons`) and identities (`app_players`, `app_club_identities`) | All rows for competition `E` |
| `app_play_by_play`, `app_shots` | Only the games of the selected season whose Gold rows differ from Neon; games no longer present locally are removed |
| The other 33 tables | All rows of the selected season |

All selected scopes commit in **one Neon transaction**. If any step fails, the transaction rolls back and the web app keeps seeing the previous data.

Neon holds every locally loaded EuroLeague season: E2000-E2026 for the catalog, box-score, standings and round tables, and E2007-E2026 for the play-by-play, shot and lineup tables, whose source data starts in E2007 (checked read-only on 2026-10-25). EuroCup is not published.

## Running the publisher

Run from the repository root. The usual order is: check Gold, preview, then publish.

```powershell
# List the 40 mappings and their scopes (no database connection)
python neon_publish/main.py --list-tables

# 1. Gold must pass its quality checks
python gold_etl/main.py -sc E2025 --quality-only

# 2. Read-only preview: counts, schema problems, game changes, shrink refusals
python neon_publish/main.py -sc E2025 --dry-run

# 3. Live publish (owner approval required)
python neon_publish/main.py -sc E2025
```

| Option | Default | Meaning |
| --- | --- | --- |
| `-sc`, `--season-code` | `current` | `current`, a four-digit year, or an `EYYYY` code. One season per run; it never publishes several historical seasons at once. |
| `-tb`, `--table` | `all` | Registered physical tables, for example `-tb app_games app_standings`. |
| `--dry-run` | off | Report local and Neon counts, schema problems, proposed game changes and shrink refusals. Writes no data and no DDL. |
| `--allow-shrink` | off | Override the [shrink guard](#safety-guards) only. |
| `--list-tables` | off | Print every mapping and scope without connecting. |
| `--print-migration [30g\|30h\|30i\|30j]` | `30g` | Print the reviewed DDL for the tables a feature added. No database connection. |

`python pipeline.py` runs the same publish as its last stage. If the publish fails, the pipeline keeps a pending flag and retries on its next run; fix the problem and rerun.

## Safety guards

A live publish stops and rolls back when any of these fail:

| Guard | What it checks |
| --- | --- |
| Gold quality | The local Gold quality checks must pass before anything is sent. |
| Schema preflight | Every Neon table and column the publisher writes must exist with a compatible type and nullability. A missing table or column stops the run with a "missing table" or missing-column report. |
| Shrink guard | No scope may drop below 90% of its current Neon row count, unless `--allow-shrink` is given. |
| Copy and post-copy count | The `COPY` must succeed and the Neon row counts afterwards must match the local ones. |

The recurring publisher never runs migrations and never drops columns.

## Configuration

Set `NEON_DATABASE_URL` to a **direct, non-pooled** PostgreSQL URL, either in the environment or in the `.env` file at the repository root:

```dotenv
NEON_DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require
```

Credentials are never printed. The publisher refuses a pooled host (one containing `-pooler`) and a URL with more than one `@`; URL-encode an `@` in the password.

[database_size.sql](database_size.sql) is a read-only query for the Neon database size and its ten largest tables. Check it before publishing another season.

## Schema migrations

New tables or columns on Neon are created by one-time, reviewed SQL files in [migrations/](migrations/). Applying one is a manual step on the direct Neon connection and needs the owner's approval, coordinated with the web app. Until a migration is applied, the schema preflight refuses the publish and Neon stays unchanged.

Neon has only the owner role, so the migrations write no `GRANT`. A read-only role added later needs grants on every `app_*` table.

All migrations below have been applied.

| Migration | What it does | Applied |
| --- | --- | --- |
| [30f_in_place.sql](migrations/30f_in_place.sql) | One-time in-place cutover of the Neon schema to the Gold contract, based on a read-only schema inspection | 2026-09-28, with the first E2026 publish |
| [30g_new_tables.sql](migrations/30g_new_tables.sql) | Creates the advanced round and season tables. Four of its twelve tables were later retired, so `--print-migration` now prints only the eight current ones; a test checks the file still creates each of them. | Yes; first published for E2025 and E2026, since then for every loaded season |
| [30h_game_advanced.sql](migrations/30h_game_advanced.sql) | Creates `app_game_player_advanced` and `app_game_team_advanced` (`--print-migration 30h`) | Yes |
| [30i_game_play_by_play.sql](migrations/30i_game_play_by_play.sql) | Creates the per-game possession, score flow and shot split tables, plus the since-retired `app_game_team_shot_zones` (`--print-migration 30i`) | Yes |
| [30j_game_on_court_and_gaps.sql](migrations/30j_game_on_court_and_gaps.sql) | Creates `app_game_player_on_court`, `app_game_team_lineup_stints` and `app_game_stat_gaps` (`--print-migration 30j`). `app_game_stat_gaps` is empty for E2025 and E2026. | Yes |
| [30k_win_shares_per_40.sql](migrations/30k_win_shares_per_40.sql) | Renames the Win Shares rate column to `win_shares_per_40` (40-minute games instead of 48) | Yes |
| [30l_player_stats_qualification.sql](migrations/30l_player_stats_qualification.sql) | Adds `is_calculated`, `min_games` and `qualified` to the four `app_season_player_stats_*` tables. After applying it, every season must be republished, because older rows hold placeholder values until they are replaced. | Yes |
| [drop_unused_app_tables.sql](migrations/drop_unused_app_tables.sql) | Drops the seven retired tables (see [gold_etl](../gold_etl/README.md#retired-tables)) | 2026-10-26, after the app deploy |

The checked-in files keep the tables each feature originally created; `--print-migration` prints the current subset.

## Testing

```powershell
python -m unittest neon_publish.tests.test_publish
```

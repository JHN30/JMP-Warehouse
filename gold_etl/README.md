# Gold builder (`gold_etl`)

The Gold builder reads the local `silver` schema and writes the 40 `app_*` tables in the local `gold` schema. These are the tables the web app reads: every Gold table has exactly the same name as its Neon table in `public`, so the app can use the same unqualified names with `search_path=gold` locally and `public` on Neon.

The stage reads no Bronze files and never writes Silver or Neon. Publishing is a separate, owner-approved step in [neon_publish](../neon_publish/README.md).

Related documentation:

- [Gold data catalog](../docs/DATA_CATALOG.md): which table to use for which page, and how to join it
- [Gold table reference](../docs/GOLD_TABLE_REFERENCE.md): every column, type and key
- [Statistics glossary](../docs/STAT_GLOSSARY.md): formulas and meaning of each statistic
- [Data dictionary](../docs/DATA_DICTIONARY.md): calculation and qualification rules

## Contents

- [Running the builder](#running-the-builder)
- [What Gold contains](#what-gold-contains)
- [Rebuild scope](#rebuild-scope)
- [Postseason series rules](#postseason-series-rules)
- [Season player qualification](#season-player-qualification)
- [Retired tables](#retired-tables)
- [Testing](#testing)

## Running the builder

Run from the repository root, with the local connection settings in `postgres_etl/config_connection.json`.

```powershell
python gold_etl/main.py --list-tables                  # the 40 table names
python gold_etl/main.py -sc E2025 --dry-run            # source and derived row counts, no writes
python gold_etl/main.py -sc all                        # build every loaded season
python gold_etl/main.py -sc all --quality-only         # compare Gold with Silver, no writes
python gold_etl/main.py -sc E2025 -tb app_standings    # build selected tables
```

| Option | Default | Meaning |
| --- | --- | --- |
| `-cp`, `--competition` | `euroleague` | `euroleague` or `eurocup`. EuroCup is built locally only and never published. |
| `-sc`, `--season-code` | `latest` | Codes, years, ranges, `current`, `latest` or `all`, from the seasons loaded in Silver. |
| `-tb`, `--table` | `all` | Table names from `--list-tables`. The older logical names without `app_` (for example `games`, `player_round_stats`) are also accepted. |
| `--dry-run` | off | Read-only: show source and derived row counts. |
| `--quality-only` | off | Read-only: compare Gold with Silver and the invariants of the derived tables. Ends with `Gold quality: passed` or `failed` (exit code 1). |

To fetch, load and rebuild all local history in one command, use `python pipeline.py --all`, or `python pipeline.py --all --skip-fetch` to reuse existing Bronze files. Both stay local and leave the current-season Neon publish pending.

### Examples by table group

```powershell
# Standings and team-season totals
python gold_etl/main.py -sc E2025 -tb app_standings app_team_season_stats

# Season player feeds, including the derived PS and perGame rows
python gold_etl/main.py -sc E2025 -tb season_player_stats_traditional season_player_stats_misc

# Records and postseason series
python gold_etl/main.py -sc E2025 -tb app_records_player_seasons app_records_single_games app_records_team_seasons app_postseason_series

# Player and club identities (always every loaded season)
python gold_etl/main.py -sc all -tb app_players app_club_identities

# Advanced round and season statistics
python gold_etl/main.py -sc all -tb player_round_stats player_round_ratings player_round_win_shares app_standings_stats team_pbp_stats player_on_off lineup_ratings player_rapm

# Per-game tables
python gold_etl/main.py -sc E2025 -tb game_team_advanced game_player_advanced
python gold_etl/main.py -sc E2025 -tb game_team_possessions game_team_score_flow game_team_shot_splits
python gold_etl/main.py -sc E2025 -tb game_player_on_court game_team_lineup_stints game_stat_gaps
```

`player_rapm` needs NumPy.

## What Gold contains

| Group | Tables | How they are built |
| --- | --- | --- |
| **Source projections** (16) | `app_seasons`, `app_clubs`, `app_people`, `app_registrations`, `app_rounds`, `app_games`, `app_game_officials`, `app_game_period_scores`, `app_game_player_stats`, `app_game_team_stats`, the four `app_season_player_stats_*`, `app_play_by_play`, `app_shots` | Copied from Silver with the same values, `NULL`s, types and primary keys. Silver's `load_id` and `loaded_at` are left out. |
| **Derived from Silver** (8) | `app_standings`, `app_team_season_stats`, `app_records_player_seasons`, `app_records_single_games`, `app_records_team_seasons`, `app_postseason_series`, `app_players`, `app_club_identities` | Standings page table from the seven standings feeds; team-season totals; top-50 all-time records; postseason series; cross-season player and club identities. |
| **Advanced round and season statistics** (8) | `app_player_round_stats`, `app_player_round_ratings`, `app_player_round_win_shares`, `app_standings_stats`, `app_team_pbp_stats`, `app_player_on_off`, `app_lineup_ratings`, `app_player_rapm` | Cumulative per-round player rates, PER and Win Shares; team ratings and splits; play-by-play aggregates; on/off, lineup ratings and RAPM. |
| **Per-game** (8) | `app_game_player_advanced`, `app_game_team_advanced`, `app_game_team_possessions`, `app_game_team_score_flow`, `app_game_team_shot_splits`, `app_game_player_on_court`, `app_game_team_lineup_stints`, `app_game_stat_gaps` | The two advanced tables project Silver's per-game advanced tables to the published columns; the player table adds single-game PER (`game_uper`, `game_aper`, `game_per`). The other six are copied from Silver unchanged. |

Exceptions to a plain copy:

- **`app_registrations`** merges a person's re-registrations with the same club and role in one season into one row (`registrations.py`).
- **Season player feeds.** The traditional and misc tables get derived postseason `PS` rows from played postseason box scores (EuroLeague `PI`/`PO`/`FF`, EuroCup knockout phases). All four get calculated `perGame` rows and qualification columns ([see below](#season-player-qualification)). The advanced and scoring feeds otherwise remain the API's rows.
- **`app_standings_stats`** combines three team round derivations (totals, ratings, splits) that run in memory and are not stored separately.

Gold creation also ensures four secondary indexes on standings, play-by-play and shots, in addition to each table's primary key.

## Rebuild scope

Each build replaces one table, competition and season slice in one transaction. Some tables have a wider scope:

| Tables | Scope replaced per run |
| --- | --- |
| Records (`app_records_*`) | The competition's full leaderboard, from every loaded season, regardless of `-sc` |
| Identities (`app_players`, `app_club_identities`) | The full competition, from every loaded season, regardless of `-sc` |
| `app_postseason_series` | One selected season at a time |
| Everything else | One selected season at a time |

Selecting the traditional or misc season player tables handles the source slice first, then its derived `PS` slice. A source rerun keeps the existing `PS` rows until they are recalculated.

`app_players` includes only player registrations. `app_club_identities` stores the latest profile and the season span of each club code.

## Postseason series rules

`app_postseason_series` lists every pairing, including scheduled fixtures; only played games count as wins.

- **EuroLeague** postseason phases are the play-in (`PI`), playoffs (`PO`) and Final Four (`FF`).
- **EuroCup** postseason phases are its knockout rounds: `8F`, `4F`, `2F`, `Final`, plus `L32` and `L16` in U2007.
- Two-leg ties (U2002-U2015, listed in `gold_etl/qualification.py`) are won on aggregate points. Every other tie is won on game wins.
- Cancelled games (U2019) are left out.
- A `Final` phase can hold a final tournament or a third-place game as separate pairings. The championship pairing is the one the season champion wins.

## Season player qualification

The four `app_season_player_stats_*` tables get, in the same transaction as their copy:

- a calculated `perGame` row for every player the API lists only in `accumulated` mode, and
- the columns `is_calculated`, `min_games` and `qualified` on every row.

The games threshold is in `qualification.py` and the derived rows in `per_game_rows.py`. A rebuild of the current season recomputes them, so they follow each refresh. `--quality-only` checks them and prints `WARN` lines where the API feed disagrees. The rule is documented in the [data dictionary](../docs/DATA_DICTIONARY.md#season-player-qualification-columns-30l).

## Retired tables

Seven earlier tables are no longer built or published, because the web app does not read them. Their Neon copies were dropped on 2026-10-26.

| Table | Reason |
| --- | --- |
| `app_coverage_seasons`, `app_coverage_games` | Not used by the app |
| `app_team_round_stats`, `app_team_round_ratings`, `app_team_round_splits` | Duplicates of `app_standings_stats`; the derivations now run only in memory |
| `app_game_team_shot_zones`, `app_team_shot_zone_stats` | Official A-J shot zones; the app derives its own zones from `app_shots` |

The one-time rename of older local Gold tables to the `app_*` names was applied on 2026-10-10. Its script, `gold_etl/migrate_names.py`, was removed afterwards and remains in Git history.

## Testing

```powershell
python -m unittest discover -s gold_etl/tests
```

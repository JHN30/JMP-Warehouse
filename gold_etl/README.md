# Local Gold stage

`gold_etl/main.py` builds `gold` from the local PostgreSQL `silver` schema. It copies the 16
source tables, plus seven per-game tables (below). It reads only the registered Silver columns,
leaving `load_id` and `loaded_at` in Silver. It keeps source values, NULLs,
types, and primary keys. It also derives traditional and misc player-season
`PS` rows from played PI/PO/FF box scores, builds `gold.app_standings` from
the seven Silver standings feeds, and derives team-season totals plus season
and game coverage from Silver. It also builds three full-history top-50 record
tables and season-scoped postseason series. Cross-season player and club identity
tables are also built from Silver. Advanced and scoring player stats
remain API rows, with calculated perGame rows added (below).

The four season player tables (`season_player_stats_*`) also get, in the same transaction
as their copy, a calculated `perGame` row for every player the feed lists only in `accumulated`
mode, plus the columns `is_calculated`, `min_games` and `qualified` on every row (feature 30l).
The rule and the checks behind it are in `docs/DATA_DICTIONARY.md`; the code is
`qualification.py` (the games threshold) and `per_game_rows.py` (the derived rows). A rebuild of
the current season recomputes them, so they follow each refresh.

Nine per-game tables came with features 30h-30j. `game_team_possessions`,
`game_team_score_flow`, `game_team_shot_splits`, `game_team_shot_zones`,
`game_player_on_court`, `game_team_lineup_stints` and `game_stat_gaps` are copied from Silver
unchanged (values, NULLs, types and keys, without `load_id` and `loaded_at`).
`game_player_advanced` and `game_team_advanced` project Silver's per-game advanced tables to
the published columns, and the player table adds single-game PER (`game_uper`, `game_aper`,
`game_per`). Their definitions are in `docs/DATA_DICTIONARY.md`.

All 47 physical Gold tables are named `app_*`, exactly like Neon `public`.
For example, Silver `games` projects to `gold.app_games`. The web app can use
identical unqualified names with `search_path=gold` locally and `public` on Neon.
`--list-tables` lists physical names. Builds accept both physical names and the
original logical selectors used in the examples below. Gold creation ensures
four app secondary indexes on standings, play-by-play and shots, in addition
to each table's primary key.

To rebuild the complete local pipeline in one command, use `python pipeline.py --all`.
It fetches API years from 2000 through the current season, loads Silver, builds Gold
and checks Gold quality. `python pipeline.py --all --skip-fetch` runs the local
builds and checks using existing Bronze files. Both modes stay local, preserve
the `app_*` Gold names and leave the current-season publish pending for later.

Existing installations must rename their Gold tables before the next refresh:

```powershell
python gold_etl/migrate_names.py          # preview, no schema changes
python gold_etl/migrate_names.py --apply  # local Gold only, one transaction
```

The migration preserves table storage, all seasons, columns, primary keys and
existing indexes. It refuses missing tables, unexpected tables and collisions
between old and new names. It is repeatable and never connects to Neon. It also
adds the app's four secondary indexes locally.

Run from the repository root with the local connection settings in
`postgres_etl/config_connection.json`:

```powershell
python gold_etl/main.py --list-tables
python gold_etl/main.py -sc E2025 --dry-run
python gold_etl/main.py -sc all
python gold_etl/main.py -sc all --quality-only
python gold_etl/main.py -sc E2025 -tb games
python gold_etl/main.py -sc E2025 -tb season_player_stats_traditional season_player_stats_misc app_standings
python gold_etl/main.py -sc E2025 -tb app_team_season_stats app_coverage_seasons app_coverage_games
python gold_etl/main.py -sc E2025 -tb app_records_player_seasons app_records_single_games app_records_team_seasons app_postseason_series
python gold_etl/main.py -sc all -tb app_players app_club_identities
python gold_etl/main.py -sc E2025 -tb game_team_advanced game_player_advanced
python gold_etl/main.py -sc E2025 -tb game_team_possessions game_team_score_flow game_team_shot_splits game_team_shot_zones
python gold_etl/main.py -sc E2025 -tb game_player_on_court game_team_lineup_stints game_stat_gaps
python gold_etl/main.py -sc all -tb team_round_stats team_round_ratings team_round_splits player_round_stats player_round_ratings player_round_win_shares app_standings_stats team_pbp_stats team_shot_zone_stats player_on_off lineup_ratings player_rapm
```

`-cp` selects `euroleague` (default) or `eurocup`; `-sc` accepts codes, years,
ranges, `current`, `latest`, or `all` from locally loaded Silver seasons. `-tb`
selects registered table names. The dry run and quality check connect read-only.
A load replaces one source or derived table, competition, and season slice in
one transaction. Selecting traditional or misc stats handles the non-`PS`
source slice first, then its
derived `PS` slice; a source rerun preserves existing `PS` rows until they are
recalculated. `-tb app_standings` selects only the standings page table; each
team or coverage table can also be selected alone. The quality path compares
full source and derived values, including the eight ordered JSON coverage items.
Records always read every locally loaded EuroLeague season and replace the
selected table's full leaderboard once per invocation, even with `-sc E2025`.
EuroCup records are not supported. The identity tables also use every locally
loaded Silver season for the selected competition and replace one full
competition scope per table, regardless of `-sc`. `app_players` includes only
player registrations; `app_club_identities` stores the latest profile and season
span for each club code. `app_postseason_series` uses the selected
seasons and is replaced one season at a time. Its game list includes scheduled
fixtures; only played games count as wins. The stage reads no Bronze files and
never writes Silver or Neon. Publishing to Neon is a separate, owner-approved step; see
[neon_publish/README.md](../neon_publish/README.md).

Run focused tests with `python -m unittest discover -s gold_etl/tests`.

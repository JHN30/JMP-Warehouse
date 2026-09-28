# PostgreSQL silver loader

`main.py` reads the latest version of each resource in the local bronze store
and builds 28 source-derived tables in the PostgreSQL `silver` schema. The
connection uses `search_path = silver`, so SQL and `-tb` use bare table names.
The loader creates the schema if it is missing. Source responses remain in
bronze; silver rows contain typed columns and no derived gold aggregates or
postseason `PS` rows.

Run from the repository root:

```powershell
python postgres_etl/main.py --list-tables
python postgres_etl/main.py -sc 2025 --dry-run
python postgres_etl/main.py -sc 2025
python postgres_etl/main.py -sc all
python postgres_etl/main.py -sc 2025 --quality-only
```

The dry run checks parsing, types, required fields, and duplicate keys without
a database. A real load needs `psycopg2` and the credentials in
`postgres_etl/config_connection.json`. Each table and season is replaced in
one transaction. Missing source files skip that table. `-cp eurocup` selects
EuroCup; `-sc` accepts a year, full code, range, `current`, `latest`, or
`all`; `-tb` selects names from `--list-tables`.

Every inserted row receives the load's UUID `load_id` and UTC `loaded_at`.
The loader appends one `silver.load_log` record per table, competition, and
season replacement in the same transaction, including replacements that insert
zero rows. It records the inserted `row_count` and a sorted JSON array of
bronze version paths relative to `data/bronze/`. Reruns keep earlier log
entries while current rows point to the new load. A failed replacement rolls
back both the rows and log entry. Quality checks report missing row metadata,
missing matching log entries, and mismatched current row counts.

| Source | Silver tables |
| --- | --- |
| v2 catalogue and people | `seasons`, `clubs`, `people`, `registrations`, `rounds` |
| v2 games and box scores | `games`, `game_officials`, `game_period_scores`, `game_player_stats`, `game_team_stats`, `game_stat_gaps` |
| v3 player statistics | `season_player_stats_traditional`, `season_player_stats_advanced`, `season_player_stats_scoring`, `season_player_stats_misc` |
| v3 team statistics | `season_team_stats_traditional`, `season_team_stats_advanced`, `season_team_stats_opponents_traditional`, `season_team_stats_opponents_advanced` |
| v3 standings | `standings_basic`, `standings_calendar`, `standings_streaks`, `standings_ahead_behind`, `standings_margins`, `standings_calendar_streaks`, `standings_basic_form` |
| Live API | `play_by_play`, `shots` |

Every key starts with `competition_code` and `season_code`. Silver uses one
name for each stat across v2 and v3, including `assists`, `pir`, `points`,
`two_pointers_made`, and `fouls_drawn`. The [data dictionary](../docs/DATA_DICTIONARY.md)
has the complete names and source mapping.

```sql
SELECT game_code, person_key, points, two_pointers_made, assists
FROM silver.game_player_stats
WHERE competition_code = 'E' AND season_code = 'E2025'
LIMIT 20;

SELECT row.game_code, row.load_id, log.loaded_at, log.bronze_versions
FROM silver.games AS row
JOIN silver.load_log AS log
  ON log.competition_code = row.competition_code
 AND log.season_code = row.season_code
 AND log.table_name = 'games' AND log.load_id = row.load_id
WHERE row.competition_code = 'E' AND row.season_code = 'E2025'
LIMIT 20;
```

The quality report checks source gaps, orphan rows, missing stats feeds,
invalid played-game fields, and other recorded anomalies.

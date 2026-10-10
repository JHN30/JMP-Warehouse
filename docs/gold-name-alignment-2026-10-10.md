# Gold and Neon name alignment verification

Date: 2026-10-10. Branch: `fix/align-gold-table-names-with-neon`.

All requested database and runtime checks passed. The 36 legacy local Gold tables were renamed in one transaction; all 47 now use the same names as Neon public. No Neon DDL was executed. The separate web app repository was not edited.

## Table inventories

These are the complete live table inventories captured after the refresh and live publish. Both contain 47 tables; every row matches.

| Local `gold` table | Neon `public` table | Result |
| --- | --- | --- |
| `app_club_identities` | `app_club_identities` | Match |
| `app_clubs` | `app_clubs` | Match |
| `app_coverage_games` | `app_coverage_games` | Match |
| `app_coverage_seasons` | `app_coverage_seasons` | Match |
| `app_game_officials` | `app_game_officials` | Match |
| `app_game_period_scores` | `app_game_period_scores` | Match |
| `app_game_player_advanced` | `app_game_player_advanced` | Match |
| `app_game_player_on_court` | `app_game_player_on_court` | Match |
| `app_game_player_stats` | `app_game_player_stats` | Match |
| `app_game_stat_gaps` | `app_game_stat_gaps` | Match |
| `app_game_team_advanced` | `app_game_team_advanced` | Match |
| `app_game_team_lineup_stints` | `app_game_team_lineup_stints` | Match |
| `app_game_team_possessions` | `app_game_team_possessions` | Match |
| `app_game_team_score_flow` | `app_game_team_score_flow` | Match |
| `app_game_team_shot_splits` | `app_game_team_shot_splits` | Match |
| `app_game_team_shot_zones` | `app_game_team_shot_zones` | Match |
| `app_game_team_stats` | `app_game_team_stats` | Match |
| `app_games` | `app_games` | Match |
| `app_lineup_ratings` | `app_lineup_ratings` | Match |
| `app_people` | `app_people` | Match |
| `app_play_by_play` | `app_play_by_play` | Match |
| `app_player_on_off` | `app_player_on_off` | Match |
| `app_player_rapm` | `app_player_rapm` | Match |
| `app_player_round_ratings` | `app_player_round_ratings` | Match |
| `app_player_round_stats` | `app_player_round_stats` | Match |
| `app_player_round_win_shares` | `app_player_round_win_shares` | Match |
| `app_players` | `app_players` | Match |
| `app_postseason_series` | `app_postseason_series` | Match |
| `app_records_player_seasons` | `app_records_player_seasons` | Match |
| `app_records_single_games` | `app_records_single_games` | Match |
| `app_records_team_seasons` | `app_records_team_seasons` | Match |
| `app_registrations` | `app_registrations` | Match |
| `app_rounds` | `app_rounds` | Match |
| `app_season_player_stats_advanced` | `app_season_player_stats_advanced` | Match |
| `app_season_player_stats_misc` | `app_season_player_stats_misc` | Match |
| `app_season_player_stats_scoring` | `app_season_player_stats_scoring` | Match |
| `app_season_player_stats_traditional` | `app_season_player_stats_traditional` | Match |
| `app_seasons` | `app_seasons` | Match |
| `app_shots` | `app_shots` | Match |
| `app_standings` | `app_standings` | Match |
| `app_standings_stats` | `app_standings_stats` | Match |
| `app_team_pbp_stats` | `app_team_pbp_stats` | Match |
| `app_team_round_ratings` | `app_team_round_ratings` | Match |
| `app_team_round_splits` | `app_team_round_splits` | Match |
| `app_team_round_stats` | `app_team_round_stats` | Match |
| `app_team_season_stats` | `app_team_season_stats` | Match |
| `app_team_shot_zone_stats` | `app_team_shot_zone_stats` | Match |

## The 39 web app tables

All 39 requested tables exist locally and in Neon. All 972 column names and PostgreSQL types match, including numeric precision/scale and timestamp timezone type. Nullability also matches. There are no missing, extra or differently typed columns in these tables. Column names/types also match for the other eight Gold tables.

The complete per-column comparison is [gold-name-alignment-columns.csv](gold-name-alignment-columns.csv). Types come from PostgreSQL `format_type(atttypid, atttypmod)`, rather than inferred Python types.

| Table | Local columns | Neon columns | Differences |
| --- | ---: | ---: | --- |
| `app_clubs` | 22 | 22 | None |
| `app_coverage_games` | 4 | 4 | None |
| `app_coverage_seasons` | 3 | 3 | None |
| `app_game_period_scores` | 6 | 6 | None |
| `app_game_player_advanced` | 21 | 21 | None |
| `app_game_player_on_court` | 9 | 9 | None |
| `app_game_player_stats` | 43 | 43 | None |
| `app_game_team_advanced` | 22 | 22 | None |
| `app_game_team_lineup_stints` | 15 | 15 | None |
| `app_game_team_possessions` | 10 | 10 | None |
| `app_game_team_score_flow` | 19 | 19 | None |
| `app_game_team_shot_splits` | 12 | 12 | None |
| `app_game_team_stats` | 31 | 31 | None |
| `app_games` | 53 | 53 | None |
| `app_lineup_ratings` | 16 | 16 | None |
| `app_people` | 22 | 22 | None |
| `app_play_by_play` | 21 | 21 | None |
| `app_player_on_off` | 26 | 26 | None |
| `app_player_rapm` | 12 | 12 | None |
| `app_player_round_ratings` | 12 | 12 | None |
| `app_player_round_stats` | 46 | 46 | None |
| `app_player_round_win_shares` | 13 | 13 | None |
| `app_postseason_series` | 12 | 12 | None |
| `app_registrations` | 19 | 19 | None |
| `app_rounds` | 10 | 10 | None |
| `app_season_player_stats_advanced` | 31 | 31 | None |
| `app_season_player_stats_misc` | 24 | 24 | None |
| `app_season_player_stats_scoring` | 30 | 30 | None |
| `app_season_player_stats_traditional` | 41 | 41 | None |
| `app_seasons` | 11 | 11 | None |
| `app_shots` | 24 | 24 | None |
| `app_standings` | 79 | 79 | None |
| `app_standings_stats` | 69 | 69 | None |
| `app_team_pbp_stats` | 29 | 29 | None |
| `app_team_round_ratings` | 17 | 17 | None |
| `app_team_round_splits` | 33 | 33 | None |
| `app_team_round_stats` | 49 | 49 | None |
| `app_team_season_stats` | 46 | 46 | None |
| `app_team_shot_zone_stats` | 10 | 10 | None |

## Historical data and indexes

- Every original local Gold table retained its OID and storage file identity through the rename. All original column definitions and index OIDs were preserved.
- Every per-season local Gold count matches its pre-migration count, both immediately after the rename and after the E2026 refresh. Local season coverage remains E2000-E2026 (27 seasons).
- All 47 primary keys have the same indexed columns as Neon. Local Gold now has all 51 Neon-equivalent index definitions: 47 primary-key indexes and four secondary indexes.
- The added secondary indexes are `idx_flat_app_standings_club_code` on `app_standings(club_code)`, `idx_flat_play_by_play_game_code_play_number` on `app_play_by_play(game_code, play_number)`, `idx_flat_play_by_play_person_code` on `app_play_by_play(person_code)`, and `idx_flat_shots_person_code` on `app_shots(person_code)`. Gold creation ensures these indexes for new installations and later refreshes.
- Original local primary-key constraint/index names are retained; their definitions match Neon. Only table names needed alignment.
- Every Neon table OID, storage file identity, column definition, index definition/OID, and per-season count matches the pre-change snapshot. Neon season coverage remains E2023-E2026.
- Silver and Bronze naming and schema contracts were unchanged. The authorized current-season refresh used their normal existing fetch/load behavior.

## Runtime verification

| Check | Result |
| --- | --- |
| `python gold_etl/migrate_names.py` before apply | 36 renames previewed |
| `python gold_etl/migrate_names.py --apply` | 36 renamed atomically; four app indexes added locally |
| Migration preview after apply | 0 renames, repeatable |
| `python pipeline.py -sc E2026 --force --dry-run-publish` | Exit 0; full API fetch, Silver load, Gold build/quality and Neon preview passed |
| `python pipeline.py -sc E2026 --skip-fetch` | Exit 0; cached local refresh and authorized live Neon publish committed |
| Published typed values compared by primary key | All 71,952 rows match across the 47 E2026 and competition-wide scopes |
| Current-season Silver quality | 38,361 source rows; 0 errors; expected missing-attendance warning for two games |
| Current-season Gold quality | Passed |
| Unqualified app names with local `search_path=gold` | All 47 resolve |
| Final Gold inventory | 47 app-prefixed tables; no legacy names recreated |
| Pipeline publish state | `publish_pending=false` |
| Database views, application functions and PostgreSQL cron jobs | None in either database |
| Matching Windows scheduled tasks | None found |
| VS Code refresh tasks | Existing pipeline commands remain valid |

The attendance warning is expected missing API data, accepted by the owner in this session. No attempt was made to manufacture attendance values.

Text sorting differs between database defaults, so value comparison used primary-key maps rather than relying on identical row order. No database collation settings were changed.

## Automated tests

| Command | Result |
| --- | --- |
| `cd api_requests; python -m unittest tests.test_scrapper` | 46 passed |
| `python -m unittest discover -s postgres_etl/tests` | 199 passed |
| `python -m unittest discover -s gold_etl/tests` | 277 passed |
| `python -m unittest neon_publish.tests.test_publish tables_to_csv.tests.test_csv_export` | 65 passed |
| Total | 587 passed |

## Local evidence

- Refresh and preview: `logs/refresh/refresh_20261010_161154.log`.
- Live publish: `logs/refresh/refresh_20261010_161548.log`.
- Catalog/count snapshots: `logs/gold_name_alignment/local_before.json`, `local_renamed.json`, `local_after.json`, `neon_before.json`, `neon_after.json`.
- Exact published value comparison: `logs/gold_name_alignment/published_scope_values.json`.
- Test output: `logs/gold_name_alignment/tests_api.txt`, `tests_silver.txt`, `tests_gold.txt`, `tests_publish_csv.txt`.

## Review handoff

Implementation and requested database verification are complete. The owner approved an immutable checkpoint and independent review. Review runs in a clean worktree at that checkpoint; existing unrelated README edits remain preserved and uncommitted in the original checkout. No merge or push is authorized.

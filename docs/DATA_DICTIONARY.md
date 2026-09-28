# EuroLeague data dictionary

The current local database has 28 source-derived tables in the PostgreSQL
`silver` schema. The loader and CSV exporter use `search_path = silver`, so
a bare name such as `games` means `silver.games`. Exact SQL columns, types,
source JSON paths, and keys are defined in
[flat_schema.py](../postgres_etl/flat_schema.py). Bronze keeps the exact API
responses. Silver contains cleaned source data. The local `gold` schema holds
16 source projections from Silver; derived Gold tables and Neon publishing are
still paused. Existing Neon tables are unchanged in the meantime.

## Silver provenance

Each of the 28 source tables has `load_id UUID NOT NULL` and
`loaded_at TIMESTAMPTZ NOT NULL`. A table, competition, and season replacement
gives every inserted row the same load ID and UTC time. These columns are
metadata and do not change source table keys or grains.

`silver.load_log` is a separate metadata table with one append-only record per
successful table/competition/season replacement, including zero-row loads.
Its key is (`competition_code`, `season_code`, `table_name`, `load_id`). It also
contains `loaded_at TIMESTAMPTZ NOT NULL`, `row_count BIGINT NOT NULL`, and
`bronze_versions JSONB NOT NULL`. `row_count` is the number of rows inserted
by that replacement. `bronze_versions` is a sorted, deduplicated JSON array of
the exact files read, using POSIX paths relative to `data/bronze/`, for example
`euroleague/E2025/v2/games/<fetched_at>_<sha16>.json.gz`. The list can include
catalog and auxiliary resources used during transformation. A rerun retains
the old log entry, but its current rows point to the new load ID.

```sql
SELECT g.game_code, g.loaded_at, l.bronze_versions
FROM silver.games AS g
JOIN silver.load_log AS l
  ON l.competition_code = g.competition_code
 AND l.season_code = g.season_code
 AND l.table_name = 'games' AND l.load_id = g.load_id
WHERE g.competition_code = 'E' AND g.season_code = 'E2025'
LIMIT 20;
```

The feature 16b historical backfill reloaded all 27 cached EuroLeague seasons
(E2000-E2026). All 727 existing table/season scopes retained their row counts:
3,987,204 source rows in total. The initial load wrote 742 log entries,
including zero-row replacements; a controlled E2025 `games` rerun added one
more. Every current row matches its log entry, and both provenance columns
are non-null in all 28 source tables.

## Silver table names and keys

Every primary key begins with `competition_code` and `season_code`.
Filter on both: `E2025` means the 2025-26 EuroLeague season. Codes such as
`person_code` are text to preserve leading zeroes. The extra key shown below
completes the primary key.

| Table | Extra key | Source/grain |
| --- | --- | --- |
| `seasons` | none | One competition season from the v2 catalogue. |
| `clubs` | `club_code` | One club in one season. |
| `people` | `person_key` | One deduplicated person in one season. |
| `registrations` | `registration_key` | One person's club and role registration. |
| `rounds` | `round_key` | One phase and round definition. |
| `games` | `game_code` | One played or scheduled fixture. |
| `game_officials` | `game_code`, `official_number` | One official assigned to a game. |
| `game_period_scores` | `game_code`, `side`, `period_number` | One quarter or overtime score. |
| `game_player_stats` | `game_code`, `side`, `person_key` | One player's game box score. |
| `game_team_stats` | `game_code`, `side`, `stats_kind` | One team's box score row or total. |
| `game_stat_gaps` | `game_code`, `stat_name` | A missing or unrecorded game measure; `*` means no box score. |
| `play_by_play` | `game_code`, `period`, `event_ordinal` | One live event. |
| `shots` | `game_code`, `shot_ordinal` | One shot attempt. |
| `season_player_stats_traditional` | `phase_code`, `mode`, `entry_ordinal` | One player entry in a v3 traditional feed. |
| `season_player_stats_advanced` | same | One player entry in an advanced feed. |
| `season_player_stats_scoring` | same | One player entry in a scoring feed. |
| `season_player_stats_misc` | same | One player entry in a misc feed. |
| `season_team_stats_traditional` | `phase_code`, `mode`, `club_code` | One club in a v3 traditional feed. |
| `season_team_stats_advanced` | same | One club in an advanced feed. |
| `season_team_stats_opponents_traditional` | same | One club's opponents in a traditional feed. |
| `season_team_stats_opponents_advanced` | same | One club's opponents in an advanced feed. |
| `standings_basic` | `phase_code`, `round_number`, `club_code` | One club snapshot after a round. |
| `standings_calendar` | same | Calendar standings snapshot. |
| `standings_streaks` | same | Streak summaries. |
| `standings_ahead_behind` | same | Checkpoint ahead/behind summaries. |
| `standings_margins` | same | Margin summaries. |
| `standings_calendar_streaks` | `phase_code`, `round_number`, `club_code`, `streak_ordinal` | One calendar streak. |
| `standings_basic_form` | `phase_code`, `round_number`, `club_code`, `result_ordinal` | One recent result. |

## Standard column names

The source JSON paths have not changed. Where these stats occur, the SQL
columns use one name across v2 and v3:

| Former column | Silver column |
| --- | --- |
| `assistances` | `assists` |
| `fouls_commited` | `fouls_committed` |
| `fouls_received` | `fouls_drawn` |
| `blocks_favour` | `blocks` |
| `valuation` | `pir` |
| `field_goals_made2`, `field_goals_attempted2` | `two_pointers_made`, `two_pointers_attempted` |
| `field_goals_made3`, `field_goals_attempted3` | `three_pointers_made`, `three_pointers_attempted` |
| `field_goals_made_total`, `field_goals_attempted_total` | `field_goals_made`, `field_goals_attempted` |
| `points_scored` | `points` |
| `time_played` | `seconds_played` |
| `possesions` | `possessions` |
| `quater1_*`, `quater3_*` | `quarter1_*`, `quarter3_*` |
| `longest_wins_streak_*`, `longest_loses_streak_*` | `longest_win_streak_*`, `longest_loss_streak_*` |
| `point_difference1to5`, `6to10`, `11to15`, `_more_than15` | `point_difference_1_to_5`, `_6_to_10`, `_11_to_15`, `_more_than_15` |
| `dorsal`, `dorsal_raw` | `jersey_number`, `jersey_number_raw` |

`game_stat_gaps.stat_name` uses these silver names, or `*` for no box score.
Source zeros that mean a stat was not recorded become SQL `NULL` and are
listed there. Future fixtures remain in `games` with `played = false` and
NULL result scores. Quarter and overtime scores have separate child rows.
The source's `winner` object is the season champion;
`match_winner_club_code` is the winner of a played game. V3 percentage strings
such as `45.5%` become numeric `45.5` (percentage points).

Player and team season stats contain only API rows; the derived `PS` rows were
removed. A player stats row is one entry in a category, phase, and mode feed,
not a unique person for the season. `accumulated` and `perGame` feeds may have
different populations. The API can return stale or partial feeds; the downloader
keeps the stronger stored response and the load quality report flags missing or
partial phase/mode feeds. Live `player_code` is the upstream ID while
`person_code` is the matched person key; join on `person_code`.

## Local Gold source tables

Feature 30a builds these 16 tables in the local `gold` schema, with the same
names, source columns, types, and natural primary keys as their Silver sources:
`seasons`, `clubs`, `people`, `registrations`, `rounds`, `games`,
`game_officials`, `game_period_scores`, `game_player_stats`, `game_team_stats`,
`season_player_stats_traditional`, `season_player_stats_advanced`,
`season_player_stats_scoring`, `season_player_stats_misc`, `play_by_play`, and
`shots`. Gold omits Silver's `load_id` and `loaded_at` metadata. It copies
source values and NULLs unchanged. The four player-season tables copy only
non-`PS` API rows; future derived `PS` rows belong to feature 30b and survive
a rerun of this source copy. The other 12 Silver tables and `silver.load_log`
are not copied by 30a.

`python gold_etl/main.py -sc all` builds all locally loaded Silver seasons.
`--dry-run` reports Silver source counts without Gold writes;
`--quality-only` compares Gold counts and full source-column values with
Silver. Both read the local database only. Gold is not published to Neon yet.
Use explicit `gold.games` or `silver.games` names because local connections
still search `silver` by default.

## Historical web-app tables

**Paused until features 30b-30f.** This section preserves the former derived
web-app table contract as a reference. The 30a source tables above are built
locally, but these derived tables are not yet rebuilt or published. Existing
Neon tables remain in place for the web app and receive no updates during the
pause.

### `app_standings`

| Extra key | One row represents | Essential use |
| --- | --- | --- |
| `phase_code`, `round_number`, `club_code` | One club in the standings of one phase and round, with every standings feed. | Filter season, phase and round; order by `group_name`, `basic_position`, `club_code`. The latest round is `max(round_number)`. |

Built from the v3 standings feeds and the season's clubs. Rows exist exactly
for the clubs in basicstandings (a quality check enforces it), so group-phase
rounds only. Verified field by field against the web app's current 7-table
standings query for all seasons (0 differences).

**Contract for the web app** (replaces the `getStandings` join and its two list
queries):

- Columns map to `StandingEntry` mechanically: feed prefix (`basic_`,
  `calendar_`, `streaks_`, `ahead_behind_`, `margins_`) plus the snake_case of
  the field name. Examples: `basic.winPercentage` -> `basic_win_percentage`,
  `aheadBehind.quarter1Ahead` -> `ahead_behind_quarter1_ahead`,
  `streaks.longestWinStreakCurrentSeason` ->
  `streaks_longest_win_streak_current_season`, `margins.pointDifference1To5`
  -> `margins_point_difference_1_to_5`.
- `clubCode`, `clubName`, `clubTvCode`, `crestUrl`, `groupName` ->
  `club_code`, `club_name`, `club_tv_code`, `crest_url`, `group_name`.
- A feed object is `null` when all of its columns are `NULL` (that feed had no
  row for the club), as with today's left joins.
- `form` (JSONB) is the `form` list and `streak_history` (JSONB) the
  `streakHistory` list, already in API shape and order; `[]` when empty. Dates
  are strings like `2025-09-01T00:00:00.000Z`.
- NUMERIC columns (`basic_win_percentage`, `ahead_behind_wins_percentage`)
  arrive as strings from node-postgres, as today.
- The web app reads the existing Neon `app_standings`. The seven former
  `app_standings_*` feed tables were retired from Neon in feature 23; their
  source snapshots now live under `silver.standings_*` locally.

### `app_records_player_seasons`, `app_records_single_games`, `app_records_team_seasons`

All-time EuroLeague leaderboards (top 50 per metric), computed by
`postgres_etl/records.py` from already-loaded local data, not from bronze
files. Unlike every other table, they are **not season-scoped**: a table's
rows span every season loaded locally (`E2000`-current), so `season_code` is
a plain column (which season a record happened in), not part of the key.
Mirrors the `/records/player-seasons`, `/records/single-games` and
`/records/team-seasons` routes in the jmp-euroleague2 Express backend, same
metrics, source filters and tie-break order, so rows are self-contained
(player and club names are already on the row; no join to `app_games` or
`app_people` is needed to render one).

| Table | Key | One row represents | Metrics |
| --- | --- | --- | --- |
| `app_records_player_seasons` | `competition_code`, `metric`, `rank_ordinal` | One player's season total, from `app_season_stats_traditional` (`phase_code = 'all'`, `mode = 'accumulated'`). | `points_scored`, `total_rebounds`, `assists`, `pir` |
| `app_records_single_games` | `competition_code`, `metric`, `rank_ordinal` | One player's box score in one played game, from `app_game_player_stats`. | `points`, `valuation`, `total_rebounds`, `assistances` |
| `app_records_team_seasons` | `competition_code`, `metric`, `rank_ordinal` | One club's season total (`stats_kind = 'total'`), summed from `app_game_team_stats`. | `points`, `valuation`, `total_rebounds`, `assistances` |

- `rank_ordinal` is 1-50 per metric (fewer when a metric has fewer than 50
  qualifying rows); dense, no gaps or duplicates.
- Tie-break order: player-seasons and team-seasons by value desc, then
  `season_code` asc, then `person_key`/`club_code` asc; single-games by value
  desc, then `season_code` asc, `game_code` asc, `person_key` asc.
- Forfeits are excluded from the two game-level tables via `app_games.played
  = TRUE` (a forfeit has no box-score rows to rank in the first place);
  `app_records_player_seasons` reads a season-level source aggregate, so no
  separate forfeit filter applies there.
- The former builder recomputed these cross-season rows from local data.
  Feature 30 will define the replacement gold build and publish path.
- The jmp-euroleague2 Express API still computes these records itself for
  now (`SUPPORTED_SEASONS`, currently `E2025`-`E2026` only); switching it to
  read these tables is a separate, coordinated change in that repo.

### `app_team_season_stats`

Team-season totals, own and opponent, served by the Express
`/teams/:clubCode/team-stats?phase=` route, which reads this table. Unlike the records tables above,
**this table IS season-scoped** (one row set per season, like every other
table) and fits the normal per-season load and Neon publish path.

| Key | One row represents |
| --- | --- |
| `phase_code`, `club_code` | One club's totals in one phase of one season, from played games only (`stats_kind = 'total'`). |

- `club_name`, `games_played`, then `own_<measure>` and `opp_<measure>`
  (NUMERIC) for 20 measures: `points`, `field_goals_made_2/attempted_2`,
  `field_goals_made_3/attempted_3`, `free_throws_made/attempted`,
  `field_goals_made_total/attempted_total`, `total_rebounds`,
  `defensive_rebounds`, `offensive_rebounds`, `assistances`, `steals`,
  `turnovers`, `blocks_favour`, `blocks_against`, `fouls_commited`,
  `fouls_received`, `valuation`.
- "Own" sums the club's own `app_game_team_stats` row for a game; "opponent"
  sums the other side's row in the same game.
- One row per phase actually present in that season's games (`RS`, `PI`,
  `PO`, `FF`, or older `TS`) — no synthetic "all phases" row; Express has
  none either.

### `app_coverage_seasons` and `app_coverage_games`

Data-coverage counts, served by the Express `/coverage` route (with and
without `?gameCode=`), which reads these tables. Both **are season-scoped**. `app_coverage_seasons` has
one row per season; `app_coverage_games` has one row per game (played or
not).

| Table | Key | One row represents |
| --- | --- | --- |
| `app_coverage_seasons` | (season only) | 8 data-coverage items for one season. |
| `app_coverage_games` | `game_code` | The same 8 items, scoped to one game. |

Both store their items as one `items JSONB NOT NULL` column: an array of
exactly 8 objects, always in this order, each shaped
`{key, label, status, availableCount, applicableCount}`:

| # | `key` | `availableCount` / `applicableCount` (season row) | Status rule |
| - | --- | --- | --- |
| 1 | `boxScores` | games with an `app_game_team_stats` `total` row / played games | gameStatus |
| 2 | `periodScores` | games with an `app_game_period_scores` row / played games | gameStatus |
| 3 | `officialStandings` | distinct clubs in `app_standings_basicstandings` / distinct clubs in `app_clubs` | rosterStatus |
| 4 | `rosters` | distinct clubs with a row in `app_registrations` / distinct clubs in `app_clubs` | rosterStatus |
| 5 | `playerPhotos` | distinct `person_key` with a headshot in `app_game_player_stats` among played games / played games | gameStatus |
| 6 | `seasonStatistics` | distinct `person_key` in `app_season_stats_traditional` / distinct clubs in `app_clubs` | rosterStatus |
| 7 | `shotLocations` | games with an `app_shots` row / played games | gameStatus |
| 8 | `playByPlay` | games with an `app_play_by_play` row / played games | gameStatus |

Items 5 and 6 compare a player count against a game/club count — an existing
Express quirk, replicated as-is, not a design choice made here.

- **gameStatus**(available, applicable): `applicable = 0` →
  `notYetApplicable`; `available = 0` → `unavailable`; `available >=
  applicable` → `available`; otherwise `partial`.
- **rosterStatus**: same as gameStatus, but `incomplete` instead of `partial`.
- `app_coverage_games` scoping: items 1, 2, 5, 7, 8 narrow every count to that
  one game (`applicableCount` becomes 0 or 1, per whether the game is
  played); items 3, 4, 6 stay season-wide, identical to that season's
  `app_coverage_seasons` row. This mismatched scoping is Express's existing
  behavior, replicated exactly.
- **Approved change from Express:** `shotLocations` and `playByPlay` are
  computed from this pipeline's own `app_shots`/`app_play_by_play` data. Before
  Express read these tables, it hardcoded both as `unavailable`.

### `app_postseason_series`

One row per club pairing per phase per season, for `phase_code IN ('PI',
'PO', 'FF')` only (play-in, playoffs, Final Four — not the `TS` "Top 16"
round-robin group stage, which isn't postseason). No existing Express
contract exists for this table; unlike the tables above, it's a new design,
deliberately conservative: it reports only facts already in `app_games` and
invents no bracket-position labels ("Quarterfinal 1", seed numbers, etc.)
that the source data doesn't carry.

| Key | One row represents |
| --- | --- |
| `phase_code`, `club_a_code`, `club_b_code` | Every game two clubs played against each other in one phase of one season. `club_a_code < club_b_code` alphabetically, so the same pairing never produces two rows regardless of which club was local/road in a given game. |

- `club_a_name`, `club_b_name`, `games_played` (count of games between the
  pair, played or not), `club_a_wins`, `club_b_wins` (counted only from
  `played = TRUE` games), `winner_club_code` (the club with strictly more
  wins; `NULL` while tied, including a series still in progress).
- `games` (JSONB NOT NULL): array ordered by `round_number`, one entry per
  game between the pair: `{gameCode, roundNumber, scheduledAt,
  localClubCode, roadClubCode, localScore, roadScore, winnerClubCode}`.
  `localScore`, `roadScore`, `winnerClubCode` are `null` for a not-yet-played
  game.
- One definition covers every era without hardcoding a format: today's `PO`
  is a best-of-5 quarterfinal (confirmed against E2025: 2 home games, 2
  away, a deciding 5th only when tied 2-2); older seasons show different
  game counts per pairing (for example best-of-3), and the row just reports
  however many games were actually played. `FF` semifinals/final and `PI`
  pairings don't repeat within a season, so each naturally becomes its own
  1-game row (confirmed against E2025: three distinct `PI` pairings, not one
  pair playing twice; a 3-game `FF` with no third-place game that year).
- No "series is decided" status field: whether a series is finished isn't
  reliably derivable without hardcoding a best-of-N target per era, so it's
  intentionally not stored. `winner_club_code` plus the game list already
  show the state.

### `app_players`

One row per player (`person_code`), like the records tables above (not
season-scoped: a player's row spans every season they appeared in). No
existing Express contract exists for this table. The build-plan line named
three uses — careers, archives, head-to-head — but only "identity lookup"
needed a new table: archives (season-by-season club history) is already
fully in `app_registrations`, and head-to-head (shared games) is already
fully in `app_game_player_stats`, both joinable by `person_code` (confirmed
identical to `person_key` for every player in local history). Career stat
totals are deliberately not precomputed here either — `app_season_stats_traditional`
already has the per-season numbers, summable by `person_code` like any other
cross-season query.

| Key | One row represents |
| --- | --- |
| `person_code` | One player who has at least one `role_code = 'J'` row in `app_registrations` (excludes coaches, staff, and referee-only people). |

- `name`, `country_code`, `country_name`, `height_cm`, `weight_kg`,
  `birth_at`, `birth_country_code`, `birth_country_name`, `position`,
  `position_name`: "latest known" — taken from the row with the maximum
  `season_code` for that player, since these can change slightly season to
  season and the app needs one current-best answer.
- `first_season_code`, `last_season_code`, `seasons_played` (INTEGER NOT
  NULL): the player's career span, from every `role_code = 'J'`
  registration.
- `clubs` (JSONB NOT NULL): array of `{seasonCode, clubCode, clubName}`,
  ordered by season, one entry per distinct season+club the player was
  registered to as a player — the compact archive summary; full per-season
  detail (dorsal, position that season, exact dates) stays in
  `app_registrations`.

## Source responses

The complete API responses are the bronze files under `data/bronze/` (see
`README.md`), not a database table. `etl_source_payloads`, a copy of them in
PostgreSQL, was dropped in feature 23.

## Common query patterns

The local connection searches `silver` by default. Explicit schema names also work:

```sql
SELECT game_code, scheduled_at, local_score, road_score
FROM silver.games
WHERE competition_code = 'E' AND season_code = 'E2025' AND played IS TRUE;

SELECT person_key, player_name, club_code, games_played, points
FROM silver.season_player_stats_traditional
WHERE competition_code = 'E' AND season_code = 'E2025'
  AND phase_code = 'RS' AND mode = 'accumulated';

SELECT club_code, club_name, position, games_played
FROM silver.standings_basic
WHERE competition_code = 'E' AND season_code = 'E2025'
  AND phase_code = 'RS' AND round_number = 38;
```

## Post-load checks

Normal flat-table loads now run read-only quality checks after loading each
selected season. To check an already-loaded season without changing data:

```powershell
python postgres_etl/main.py -sc 2025 --quality-only
python postgres_etl/main.py -sc 2025 -tb games game_player_stats --quality-only
```

The checks count loaded rows, flag empty selected tables, verify played and
unplayed game result rules, and check game, club, and person references when
both participating tables were selected. Database primary keys already
prevent duplicate keys. A partial-table load is checked only against its
selected tables. Checks do **not** certify upstream completeness, historical
live-feed availability, or every metric's sports meaning. Use
`--skip-quality-check` only when intentionally bypassing the automatic
post-load pass. Tests for this behavior live in `postgres_etl/tests/`.

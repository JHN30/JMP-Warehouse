# EuroLeague data dictionary

This describes the **column-first PostgreSQL tables** produced by
`postgres_etl/main.py` and exported by `tables_to_csv/main.py`. The exact SQL
columns, types, source-field paths, and primary keys are defined in
[postgres_etl/flat_schema.py](postgres_etl/flat_schema.py). The table names
below omit the prefix: the web-app tables are stored as `app_<name>` (see
[Table names](#table-names)), the others as `etl_flat_<name>`;
`source_payloads` is stored as `etl_source_payloads`.

## Table names

The 32 tables the web app reads are published to Neon with clean `app_*`
names, locally and in Neon: `app_standings`; the 21 v2/v3 tables, each named
`app_<name>` (for example `app_games`, `app_game_player_stats`); play-by-play
and shots (`app_play_by_play`, `app_shots`); and the eight newer tables from
features 11-14 — `app_records_player_seasons`, `app_records_single_games`,
`app_records_team_seasons`, `app_team_season_stats`, `app_coverage_seasons`,
`app_coverage_games`, `app_postseason_series`, `app_players` — all `app_*`-named
from the start. See [Web-app tables](#web-app-tables) for what each one is.
Every other (non-web-app) table keeps its `etl_flat_` name.

**Legacy `etl_flat_*` views:** the 21 v2/v3 tables and play-by-play/shots
were called `etl_flat_<name>` before feature 22 (2026-09). Neon still keeps
a view under each old name (`etl_flat_<name>` -> `app_<name>`) so the app
doesn't break mid-switchover; a column added after the rename appears only
under the `app_*` name, never the old view. Once the web app reads only
`app_*` names (and any Drizzle table filter is updated to match), drop the
old views with `python neon_publish/main.py --drop-old-names --dry-run`,
then the same command without `--dry-run` — it drops only the views, never
a table. Grant `SELECT` on the views if the web app connects with a
different database role than the publisher.

## Conventions to apply to every query

- All tables are shared by EuroLeague and EuroCup. Always filter on both
  `competition_code` (`E` or `U`) and `season_code` (`E2025`, `U2025`, etc.).
  `E2025` means the **2025–26** season, not calendar year 2025 alone.
- Both scope columns are part of every primary key. The **extra key** shown
  below completes that table's primary key. A `game_code` or `club_code` by
  itself is not globally unique. Keep codes such as `person_code` as text so
  leading zeroes are not lost.
- `side` is `local` or `road`. In the legacy live feed, fields ending in `A`
  or `B` retain the source's labels; join to a game before assuming a team.
- Live tables (`play_by_play`, `shots`, `live_boxscore_players`) carry two
  player columns. `player_code` is the id exactly as the live API sends it
  (padding trimmed): `P` + person code, such as `P014102` or `PKLT`, or a
  team/coach marker such as `CO_A`. `person_code` is the standardized code
  (`014102`, `KLT`) that equals `people.person_key` everywhere else. It is `NULL`
  for markers, which are not people. **Join on `person_code`.**
  `person_code_method` says how it was found: `live_id` (the id is "P" + the
  code of a player in that game's v2 box score; nearly all rows), or a correction
  for live ids that are wrong in the source (e.g. Kanter E2008: `P000936` vs v2
  `000110`): `jersey_number` or `name` (same team in that game's box score),
  `play_by_play` (shots: the id as corrected in the same game's play-by-play),
  `season_roster` (the id is a person of that season who is not in the game's
  box score), or `unmatched` (`person_code` is NULL).
- SQL `NULL` means absent, not applicable, or not yet played. It is not zero.
  Future fixtures remain in `games` with `played = false`, but result scores
  and `match_winner_club_code` are `NULL`. Games without overtime have no
  overtime rows. Optional profile, venue, or image fields may also be `NULL`.
- Percentage strings from v3 are converted to numeric **percentage points**:
  `45.5` means 45.5%, not 0.455. Timestamps marked `TIMESTAMPTZ` carry a time
  zone; `TIMESTAMP` values are source-local/unspecified and need care when
  compared across locations.
- `champion_club_code` and the source `winner` object identify the **season
  champion**, not the winner of each game. For a played match, use
  `games.match_winner_club_code` (or compare the two scores).
- Club crests and many player headshots are full URLs. An official's
  `image_vertical_small` is an opaque upstream identifier, not a ready URL.
- The same concept may appear in v2, v3, and live tables. These are separate
  source views, **not additive records**. Pick a source and grain for each
  calculation rather than summing overlapping tables together.

## v2 catalogue, people, and games

| Table                | Extra key                            | One row represents                                            | Essential use/filter                                                                                            |
| -------------------- | ------------------------------------ | ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `seasons`            | none                                 | A competition season and its catalogue metadata.              | `champion_club_code` is the season champion, when known.                                                        |
| `clubs`              | `club_code`                          | A club's season-specific metadata.                            | `crest_url` is a displayable image URL when present. Join on both scope columns and club code.                  |
| `people`             | `person_key`                         | A deduplicated person in that season.                         | Join to registrations for club/role; `person_code` is text and may have leading zeroes.                         |
| `registrations`      | `registration_key`                   | A person's club/role registration or interval.                | One person can have multiple rows. Use `role_code`, `club_code`, `active`, and dates as needed.                 |
| `rounds`             | `round_key`                          | A phase/round definition.                                     | Use `phase_code` with `round_number`; do not treat a round number as season-wide without its phase.             |
| `games`              | `game_code`                          | A fixture, played or scheduled, with teams and result fields. | Filter `played = true` for results. Use `match_winner_club_code`, not `champion_club_code`, for match outcomes. Use `status` (below) for scheduled/cancelled/completed. |
| `game_officials`     | `game_code`, `official_number`       | One assigned official in a game.                              | `official_code` identifies the person; `image_vertical_small` is not a URL.                                     |
| `game_period_scores` | `game_code`, `side`, `period_number` | One team's score in one period.                               | Periods 1–4 are regulation; 5+ are overtime. Absence of 5+ means no overtime.                                   |
| `game_player_stats`  | `game_code`, `side`, `person_key`    | One player's v2 game box-score row.                           | Join to `games` and `people` using scope and keys. `headshot_url` may be missing.                               |
| `game_team_stats`    | `game_code`, `side`, `stats_kind`    | One side's v2 `team` or `total` statistics object.            | Filter `stats_kind` to **one** of `team` or `total` before aggregating.                                         |
| `game_stat_gaps`     | `game_code`, `stat_name`             | A box-score measure the source did not record for a game.     | `stat_name` is a column name (e.g. `plus_minus`), or `*` when the game has no player box score at all (forfeit). |

### Game status and unrecorded statistics

`games.status` is derived by the loader for the web app:

| `status` | Meaning |
| --- | --- |
| `completed` | Played; results are filled. |
| `scheduled` | Future fixture. |
| `awaiting_result` | Current season: start time has passed but the source has no result yet (live, just finished, or postponed). Depends on the load time. |
| `postponed` | The source says postponed. |
| `cancelled` | Never played. `status_note` says whether the source said so (E2021: 28 games of the Russian clubs) or it is **inferred** because the season is over (E2019: 54 games after the COVID stop, which the source still calls "Confirmed"). |

Unrecorded statistics are `NULL`, not 0. A box-score measure that is 0 for
**every** player in a game (for example plus/minus, which was not recorded before
E2012, or fouls received in a few E2000–E2002 games) is stored as `NULL` for that
game in `game_player_stats` and `game_team_stats`, and listed in
`game_stat_gaps`. A real 0 for one player stays 0. Games with no player box
score (the forfeits E2001 game 264, 2–0, and E2003 game 200, 20–0) keep the
official score in `games` but have `NULL` team statistics. Exclude them from
records.

`games.audience` is `NULL` when the source reports 0: for unplayed games, and
for played games where the crowd was not recorded (most of E2004/E2005) or the
game was behind closed doors. The source cannot tell these apart.
`audience_note` explains every played game with `NULL` attendance: "likely
behind closed doors (COVID period)" between March 2020 and June 2022, otherwise
"attendance not recorded (or behind closed doors)".

## Live game detail

These tables supplement, and sometimes overlap, v2/v3. Older seasons may not
have live-feed data. A missing live row should not automatically be interpreted
as a zero-valued performance. Play-by-play and shots are stored as
`app_play_by_play` and `app_shots` and published to Neon (see below); the other
live tables stay local.

| Table                                | Extra key                                          | One row represents                                                  | Essential use/filter                                                                                           |
| ------------------------------------ | -------------------------------------------------- | ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `play_by_play`                       | `game_code`, `period`, `event_ordinal`             | One source event in a game period.                                  | Order within a game by period in play order (not alphabetically), then event ordinal; `points_a`/`points_b` are often `NULL` on non-scoring events. |
| `shots`                              | `game_code`, `shot_ordinal`                        | One shooting-chart attempt, including misses.                       | `points = 0` can mean a miss. Coordinates use the source's system; do not assume screen pixels.                |
| `live_boxscores`                     | `game_code`                                        | Game-level live box-score summary.                                  | Includes attendance, live flag, and referee text where supplied.                                               |
| `live_boxscore_players`              | `game_code`, `side`, `player_ordinal`              | One live box-score player entry.                                    | Overlaps v2 `game_player_stats`; `minutes` is source text, not a numeric duration.                             |
| `live_boxscore_teams`                | `game_code`, `side`, `stats_kind`                  | One live team summary block.                                        | Filter `stats_kind` (`tmr` or `totr`) before comparing/aggregating.                                            |
| `live_boxscore_period_scores`        | `game_code`, `side`, `score_kind`, `period_number` | One live period or end-of-period score.                             | `score_kind = 'period'` is that period's points; `cumulative` is the running score. Period 5+ is overtime.     |
| `live_evolution`                     | `game_code`                                        | A game's live score-evolution summary.                              | Parent of minute and largest-difference rows.                                                                  |
| `live_evolution_minutes`             | `game_code`, `minute_ordinal`                      | One entry in the minute-by-minute score progression.                | `minute_ordinal` is source list order; `score_difference` is local minus road where both scores exist.         |
| `live_evolution_largest_differences` | `game_code`, `side_index`, `slot_index`            | One non-null entry from the live largest-difference arrays.         | Indexes are source array positions; interpret with the source payload if needed.                               |
| `live_comparison`                    | `game_code`                                        | One source comparison summary for a game.                           | A/B and starter/bench values are comparison metrics, not additional box scores.                                |
| `live_scoring`                       | `game_code`                                        | One game's fast-break, turnover, and second-chance scoring summary. | A/B values come from the live source; do not add them to total points.                                         |

### Web-app contract: `app_play_by_play` and `app_shots`

- **Seasons in Neon:** E2025 and E2026 only (all seasons would be about 1.5 GB).
  Older seasons exist locally from E2007.
- **Play-by-play:** key `game_code`, `period`, `event_ordinal`. Order a game by
  the period in play order (`FirstQuarter`, `SecondQuarter`, `ThirdQuarter`,
  `ForthQuarter` (source spelling), `ExtraTime` for all overtime), then
  `event_ordinal`, which restarts at 0 in each period. `period` is text, so
  sorting on it directly puts `ExtraTime` first and `ForthQuarter` before
  `SecondQuarter`; map it to its position instead. `play_number` is unique
  within a season and game (it links each shot to its event) but is not
  chronological, so do not order by it.
  `play_type` is the source event code, `marker_time` the game clock text,
  `comment`/`play_info` free source text.
- **Shots:** key `game_code`, `shot_ordinal`, one row per attempt including
  misses (`points = 0`). `coord_x`/`coord_y` use the source's court system (not
  screen pixels); `zone`, `fastbreak`, `second_chance`, `points_off_turnover`
  come from the source; `shot_at` is a UTC timestamp.
- **Scores:** `points_a`/`points_b` are the source's A/B sides and are often
  `NULL` on non-scoring events; join to `app_games` (local/road) before
  labelling them.
- **Players:** `player_code` is the live feed's id; use `person_code` to join to
  `app_people` and box scores. `person_code_method` says how it was matched.
  Team and game events (for example a team rebound or a period start) have no
  `person_code` and no method; an `unmatched` player has no `person_code`
  either. Every shot has a play-by-play event with the same `play_number`.
- **Freshness:** a refresh replaces only games whose rows changed, so a game
  appears after the refresh that follows it and corrections replace the whole
  game at once.

## v3 season player statistics

All four tables have extra key `phase_code`, `mode`, `entry_ordinal`. One row
is **one player entry in one category/phase/mode feed**, not one unique person
for the season. `entry_ordinal` is a feed position, not a stable player ID.
Join people by `person_key` and filter a single `phase_code` (for example
`RS`, `PO`, `PI`, `FF`, or `all`) and a single `mode` (`accumulated` or
`perGame`). The populations in these feeds can differ. Do not sum per-game
rates or add an `all` row to its individual phase rows.

| Table                      | Metric family                                                                                    |
| -------------------------- | ------------------------------------------------------------------------------------------------ |
| `season_stats_traditional` | Games, minutes, scoring, shooting, rebounds, assists, steals, turnovers, blocks, fouls, and PIR. |
| `season_stats_advanced`    | Efficiency, usage-related ratios, shooting efficiency, rebound/assist ratios, and possessions.   |
| `season_stats_scoring`     | Shot-attempt shares and the makeup of a player's points.                                         |
| `season_stats_misc`        | Games, wins/losses, minutes, double-doubles, and triple-doubles.                                 |

## v3 standings snapshots

The five feed tables below share extra key `phase_code`, `round_number`,
`club_code`: one club's **snapshot after a particular round in a phase**.
They are not season totals to sum across rounds. Filter the desired phase and
round, or choose its latest available round. Not every phase has a standings
feed; E2025 currently has 38 regular-season rounds in the basic feed.

| Table                         | Feed-specific information                                                          |
| ----------------------------- | ---------------------------------------------------------------------------------- |
| `standings_basicstandings`    | Position, win percentage, points for/against, and record summaries.                |
| `standings_calendarstandings` | Calendar standings snapshot; expanded streak entries are in the child table below. |
| `standings_streaks`           | Home/away and recent-form record or streak summaries.                              |
| `standings_aheadbehind`       | Ahead/behind/tied summaries at game checkpoints.                                   |
| `standings_margins`           | Margin bands and other distribution summaries.                                     |
| `standings_calendar_streaks`  | One calendar streak per club/round; extra key also has `streak_ordinal`.           |
| `standings_basic_form`        | One recent-form result per club/round; extra key also has `result_ordinal`.        |

## Web-app tables

Page-shaped tables built for the web app, with clean table and column names
(no source misspellings). Published to Neon with the other `app_*` tables.
This section is the up-to-date contract for the `jmp-euroleague2` repo: for
each table, what it replaces (if anything) in the current Express API, its
exact columns, and what's still that repo's own work to switch over.

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
- Until the app switches, the 7 standings feed tables (`app_standings_*`,
  formerly `etl_flat_standings_*`) keep being published. Stop publishing and
  drop them only after the app no longer reads them.

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
- A rebuild (`python postgres_etl/main.py -tb app_records_player_seasons
  app_records_single_games app_records_team_seasons`) always recomputes every
  row from current local data and replaces prior contents; it ignores
  `-sc`/`--season-code`. Neon publish is likewise a whole-table replace, not
  the usual per-season delete.
- The jmp-euroleague2 Express API still computes these records itself for
  now (`SUPPORTED_SEASONS`, currently `E2025`-`E2026` only); switching it to
  read these tables is a separate, coordinated change in that repo.

### `app_team_season_stats`

Team-season totals, own and opponent, mirroring the Express
`/teams/:clubCode/team-stats?phase=` route. Unlike the records tables above,
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

Data-coverage counts, mirroring the Express `/coverage` route (with and
without `?gameCode=`). Both **are season-scoped**. `app_coverage_seasons` has
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
  computed from this pipeline's own `app_shots`/`app_play_by_play` data.
  Express currently hardcodes both as `unavailable` always (stale — it
  hasn't been updated since feature 21 added that data). Fixing that on the
  Express side is separate, coordinated, later work.

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

## Source archive

`etl_source_payloads` has extra key `relative_path`: one cached source response
per path. It stores `sha256` of the original file and its full parsed response
in `payload JSONB`. This preserves fields not modeled in flat columns and is
useful for provenance or reprocessing, but it is **not** a flat analytical
table. Its CSV can be large because the JSON is included as text.

## Common query patterns

```sql
-- Completed games; the season champion is a different field.
SELECT game_code, scheduled_at, local_club_code, road_club_code,
       local_score, road_score, match_winner_club_code
FROM public.app_games
WHERE competition_code = 'E' AND season_code = 'E2025' AND played IS TRUE
ORDER BY game_code;

-- One comparable player-statistics population.
SELECT person_key, player_name, club_code, games_played, points_scored
FROM public.app_season_stats_traditional
WHERE competition_code = 'E' AND season_code = 'E2025'
  AND phase_code = 'RS' AND mode = 'accumulated';

-- A standings snapshot, not a sum of all round rows.
SELECT club_code, club_name, position, games_played
FROM public.app_standings_basicstandings
WHERE competition_code = 'E' AND season_code = 'E2025'
  AND phase_code = 'RS' AND round_number = 38
ORDER BY position;
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

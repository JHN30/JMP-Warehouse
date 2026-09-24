# EuroLeague data dictionary

This describes the **column-first PostgreSQL tables** produced by
`postgres_etl/main.py` and exported by `tables_to_csv/main.py`. The exact SQL
columns, types, source-field paths, and primary keys are defined in
[postgres_etl/flat_schema.py](postgres_etl/flat_schema.py). The table names
below omit the `etl_flat_` prefix; `source_payloads` is the exception and is
stored as `etl_source_payloads`.

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
as a zero-valued performance.

| Table                                | Extra key                                          | One row represents                                                  | Essential use/filter                                                                                           |
| ------------------------------------ | -------------------------------------------------- | ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `play_by_play`                       | `game_code`, `period`, `event_ordinal`             | One source event in a game period.                                  | Order within a game by period and event ordinal; `points_a`/`points_b` are often `NULL` on non-scoring events. |
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

Page-shaped tables built for the web app, with clean names (no `etl_flat_`
prefix, no source misspellings). Published to Neon with the flat tables.

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
- Until the app switches, the 7 `etl_flat_standings_*` tables keep being
  published. Stop publishing and drop them only after the app no longer reads them.

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
FROM public.etl_flat_games
WHERE competition_code = 'E' AND season_code = 'E2025' AND played IS TRUE
ORDER BY game_code;

-- One comparable player-statistics population.
SELECT person_key, player_name, club_code, games_played, points_scored
FROM public.etl_flat_season_stats_traditional
WHERE competition_code = 'E' AND season_code = 'E2025'
  AND phase_code = 'RS' AND mode = 'accumulated';

-- A standings snapshot, not a sum of all round rows.
SELECT club_code, club_name, position, games_played
FROM public.etl_flat_standings_basicstandings
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

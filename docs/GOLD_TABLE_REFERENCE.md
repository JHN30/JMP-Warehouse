# Gold table reference

Complete column reference for the 47 registered Gold tables, checked against
[gold_etl/schema.py](../gold_etl/schema.py) and its imported Silver definitions
on 2026-10-20. Names, types and primary keys come from the code contract.
No live schema, data refresh or Neon publish was performed for this document.

Use the [catalog](DATA_CATALOG.md) to choose a table and the
[player/team stats glossary](STAT_GLOSSARY.md) for calculation details.
The [pipeline dictionary](DATA_DICTIONARY.md) retains Silver and operational notes.
For upstream EuroLeague lineage and columns, see the [Bronze catalog](BRONZE_CATALOG.md),
[Silver catalog](SILVER_CATALOG.md), and [Silver reference](SILVER_TABLE_REFERENCE.md).

## Reading the reference

`gold.<name>` is local and `public.<name>` is the Neon target. SQL names below
are exact, including legacy spellings. PK marks a primary-key column. Nullable
is No for every PK column even if the field definition omits explicit NOT NULL,
because PostgreSQL primary keys enforce it. Nullable Yes permits missing data;
it does not say how many stored rows are missing.

`TEXT` preserves identifier leading zeroes. `NUMERIC` is PostgreSQL decimal;
it may represent a count, a fraction, points, seconds or a model score.
`TIMESTAMP` has no time zone; `TIMESTAMPTZ` represents an instant with time-zone
handling. Do not silently attach the frontend's local zone to source timestamps.
`JSONB` values retain camelCase object keys documented at the end.

All joins include competition and, where present, season. Join guidance is
logical guidance; the publish contract does not add foreign-key constraints.
Gold omits Silver `load_id`, `loaded_at` and `load_log` provenance.

## Tables

- **Profiles, roster and schedule:** [seasons](#app_seasons), [clubs](#app_clubs), [people](#app_people), [registrations](#app_registrations), [rounds](#app_rounds), [games](#app_games), [game_officials](#app_game_officials), [players](#app_players), [club_identities](#app_club_identities).
- **Official box scores and season player feeds:** [game_period_scores](#app_game_period_scores), [game_player_stats](#app_game_player_stats), [game_team_stats](#app_game_team_stats), [season_player_stats_traditional](#app_season_player_stats_traditional), [season_player_stats_advanced](#app_season_player_stats_advanced), [season_player_stats_scoring](#app_season_player_stats_scoring), [season_player_stats_misc](#app_season_player_stats_misc).
- **Standings, coverage, records and postseason:** [standings](#app_standings), [team_season_stats](#app_team_season_stats), [coverage_seasons](#app_coverage_seasons), [coverage_games](#app_coverage_games), [records_player_seasons](#app_records_player_seasons), [records_single_games](#app_records_single_games), [records_team_seasons](#app_records_team_seasons), [postseason_series](#app_postseason_series).
- **Calculated team statistics:** [standings_stats](#app_standings_stats), [team_round_stats](#app_team_round_stats), [team_round_ratings](#app_team_round_ratings), [team_round_splits](#app_team_round_splits), [team_pbp_stats](#app_team_pbp_stats), [team_shot_zone_stats](#app_team_shot_zone_stats).
- **Calculated player and lineup statistics:** [player_round_stats](#app_player_round_stats), [player_round_ratings](#app_player_round_ratings), [player_round_win_shares](#app_player_round_win_shares), [player_on_off](#app_player_on_off), [lineup_ratings](#app_lineup_ratings), [player_rapm](#app_player_rapm).
- **Events and calculated game detail:** [play_by_play](#app_play_by_play), [shots](#app_shots), [game_player_advanced](#app_game_player_advanced), [game_team_advanced](#app_game_team_advanced), [game_team_possessions](#app_game_team_possessions), [game_team_score_flow](#app_game_team_score_flow), [game_team_shot_splits](#app_game_team_shot_splits), [game_team_shot_zones](#app_game_team_shot_zones), [game_player_on_court](#app_game_player_on_court), [game_team_lineup_stints](#app_game_team_lineup_stints), [game_stat_gaps](#app_game_stat_gaps).

## app_seasons

**Purpose:** Season selector and season metadata.

**Grain:** one competition-season. **Columns:** 11.

**Primary key:** `competition_code`, `season_code`.

**Definition / implementation:** [postgres_etl/flat_schema.py](../postgres_etl/flat_schema.py).

**Usage and limitations:** The year is the starting year: E2025 means 2025-26. Champion fields describe the season champion.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `name` | `TEXT` | Yes |  | Display name supplied by the source; identity tables use the latest season profile. |
| `start_year` | `INTEGER` | Yes |  | Starting calendar year of the season. |
| `alias` | `TEXT` | Yes |  | Source alternative display name or alias. |
| `competition_name` | `TEXT` | Yes |  | Source competition name. |
| `start_at` | `TIMESTAMP` | Yes |  | Source start timestamp without time zone for the season or registration. |
| `activation_at` | `TIMESTAMP` | Yes |  | Source season activation timestamp without time zone. |
| `end_at` | `TIMESTAMP` | Yes |  | Source end timestamp without time zone for the season or registration. |
| `champion_club_code` | `TEXT` | Yes |  | Season champion's club code; not this game's winner. |
| `champion_club_name` | `TEXT` | Yes |  | Season champion's display name. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_clubs

**Purpose:** Season-specific team names, crests and profiles.

**Grain:** one club per season. **Columns:** 22.

**Primary key:** `competition_code`, `season_code`, `club_code`.

**Definition / implementation:** [postgres_etl/flat_schema.py](../postgres_etl/flat_schema.py).

**Usage and limitations:** Join by competition_code, season_code and club_code. Use app_club_identities for one cross-season club profile.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `club_code` | `TEXT` | No | PK | Club identifier, text; join season profiles on competition, season and club. |
| `name` | `TEXT` | Yes |  | Display name supplied by the source; identity tables use the latest season profile. |
| `abbreviated_name` | `TEXT` | Yes |  | Source shortened display name. |
| `editorial_name` | `TEXT` | Yes |  | Source editorial club display name. |
| `tv_code` | `TEXT` | Yes |  | Source television abbreviation for the club. |
| `is_virtual` | `BOOLEAN` | Yes |  | Source flag for a virtual club entry. |
| `crest_url` | `TEXT` | Yes |  | Source team crest image URL. |
| `sponsor` | `TEXT` | Yes |  | Source club sponsor label. |
| `permanent_name` | `TEXT` | Yes |  | Source persistent club name retained separately from the seasonal sponsor name. |
| `permanent_alias` | `TEXT` | Yes |  | Source persistent club alias. |
| `country_code` | `TEXT` | Yes |  | Source country code for the person, club or official. |
| `country_name` | `TEXT` | Yes |  | Source country display name. |
| `address` | `TEXT` | Yes |  | Source club postal/street address. |
| `website` | `TEXT` | Yes |  | Source club website URL. |
| `tickets_url` | `TEXT` | Yes |  | Source club ticketing URL. |
| `twitter_account` | `TEXT` | Yes |  | Source Twitter account value. |
| `venue_code` | `TEXT` | Yes |  | Source venue identifier. |
| `city` | `TEXT` | Yes |  | Source club city. |
| `president` | `TEXT` | Yes |  | Source club president name, season-specific metadata. |
| `phone` | `TEXT` | Yes |  | Source club telephone value. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_people

**Purpose:** Season-specific person profiles and the bridge between person_key and person_code.

**Grain:** one person per season. **Columns:** 22.

**Primary key:** `competition_code`, `season_code`, `person_key`.

**Definition / implementation:** [postgres_etl/flat_schema.py](../postgres_etl/flat_schema.py).

**Usage and limitations:** Includes people other than players. Join box scores by person_key; join career identity by person_code. Preserve leading zeroes.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `person_key` | `TEXT` | No | PK | Season person identity used by box scores; bridge to career person_code through app_people. |
| `person_code` | `TEXT` | Yes |  | Person code; career identity in profiles, resolved box-score person_key in live-event tables. |
| `name` | `TEXT` | Yes |  | Display name supplied by the source; identity tables use the latest season profile. |
| `alias` | `TEXT` | Yes |  | Source alternative display name or alias. |
| `alias_raw` | `TEXT` | Yes |  | Unmodified person alias retained alongside the normalized alias. |
| `passport_name` | `TEXT` | Yes |  | Source given name used in passport details. |
| `passport_surname` | `TEXT` | Yes |  | Source surname used in passport details. |
| `jersey_name` | `TEXT` | Yes |  | Name printed on the player's jersey according to the source. |
| `abbreviated_name` | `TEXT` | Yes |  | Source shortened display name. |
| `country_code` | `TEXT` | Yes |  | Source country code for the person, club or official. |
| `country_name` | `TEXT` | Yes |  | Source country display name. |
| `height_cm` | `INTEGER` | Yes |  | Source person height in centimeters. |
| `weight_kg` | `INTEGER` | Yes |  | Source person weight in kilograms. |
| `birth_at` | `TIMESTAMP` | Yes |  | Source birth date stored as a timestamp without time zone. |
| `birth_country_code` | `TEXT` | Yes |  | Source birth-country code. |
| `birth_country_name` | `TEXT` | Yes |  | Source birth-country display name. |
| `twitter_account` | `TEXT` | Yes |  | Source Twitter account value. |
| `instagram_account` | `TEXT` | Yes |  | Source Instagram account value. |
| `facebook_account` | `TEXT` | Yes |  | Source Facebook account value. |
| `is_referee` | `BOOLEAN` | Yes |  | Source flag indicating a referee profile. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_registrations

**Purpose:** Rosters, jersey numbers, positions and registration dates.

**Grain:** one person-club-role registration per season. **Columns:** 19.

**Primary key:** `competition_code`, `season_code`, `registration_key`.

**Definition / implementation:** [postgres_etl/flat_schema.py](../postgres_etl/flat_schema.py).

**Usage and limitations:** role_code = 'J' selects players. A person may have multiple registrations; joining a box score directly to all registrations can multiply rows.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `registration_key` | `TEXT` | No | PK | Natural identity of the source registration, not a player identity. |
| `person_key` | `TEXT` | No |  | Season person identity used by box scores; bridge to career person_code through app_people. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `role_code` | `TEXT` | Yes |  | Registration role code; J means player, other codes represent staff roles. |
| `role_name` | `TEXT` | Yes |  | Source label of the registration role. |
| `active` | `BOOLEAN` | Yes |  | Source active flag for a registration or official. |
| `start_at` | `TIMESTAMP` | Yes |  | Source start timestamp without time zone for the season or registration. |
| `end_at` | `TIMESTAMP` | Yes |  | Source end timestamp without time zone for the season or registration. |
| `sort_order` | `INTEGER` | Yes |  | Source registration display order. |
| `jersey_number` | `TEXT` | Yes |  | Source jersey number stored as text; retain leading zeroes and special values. |
| `jersey_number_raw` | `TEXT` | Yes |  | Original registration jersey value retained alongside jersey_number. |
| `position` | `INTEGER` | Yes |  | Source position code for a player; not a standings rank. |
| `position_name` | `TEXT` | Yes |  | Source label for the player's position. |
| `last_team` | `TEXT` | Yes |  | Source previous-team label attached to the registration. |
| `external_id` | `INTEGER` | Yes |  | Source external person/registration identifier, not a warehouse join key. |
| `person_name` | `TEXT` | Yes |  | Person display name attached to this registration or box score. |
| `club_name` | `TEXT` | Yes |  | Club display name for this season or row. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_rounds

**Purpose:** Round names, phase labels and date ranges.

**Grain:** one round definition per season. **Columns:** 10.

**Primary key:** `competition_code`, `season_code`, `round_key`.

**Definition / implementation:** [postgres_etl/flat_schema.py](../postgres_etl/flat_schema.py).

**Usage and limitations:** round_key is the source identity. round_number alone is not the primary key.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `round_key` | `TEXT` | No | PK | Natural identity of a source round definition. |
| `phase_code` | `TEXT` | No |  | Phase identifier: all, RS, TS, PI, PO, FF or derived PS as supported by this table. |
| `round_number` | `INTEGER` | No |  | Source game/standings round number; cumulative snapshots include games through this round. |
| `round_index` | `INTEGER` | Yes |  | Source index of this round definition, distinct from round_number. |
| `name` | `TEXT` | Yes |  | Display name supplied by the source; identity tables use the latest season profile. |
| `first_game_at` | `TIMESTAMP` | Yes |  | Source first-game timestamp for the round, without time zone. |
| `last_game_at` | `TIMESTAMP` | Yes |  | Source last-game timestamp for the round, without time zone. |
| `formatted_dates` | `TEXT` | Yes |  | Source preformatted round date label. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_games

**Purpose:** Schedule, results, game status and venue details.

**Grain:** one fixture per season. **Columns:** 53.

**Primary key:** `competition_code`, `season_code`, `game_code`.

**Definition / implementation:** [postgres_etl/flat_schema.py](../postgres_etl/flat_schema.py).

**Usage and limitations:** Use status and played to distinguish future fixtures from completed games. local/road is the source designation even at neutral venues. Do not use champion_club_code as the game winner.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `source_id` | `TEXT` | Yes |  | Raw source game identity retained alongside game_code. |
| `identifier` | `TEXT` | Yes |  | Source game identifier label. |
| `phase_code` | `TEXT` | Yes |  | Phase identifier: all, RS, TS, PI, PO, FF or derived PS as supported by this table. |
| `phase_name` | `TEXT` | Yes |  | Source phase display name. |
| `phase_alias` | `TEXT` | Yes |  | Source phase alias. |
| `phase_is_group` | `BOOLEAN` | Yes |  | Source flag that this phase is a group stage. |
| `group_id` | `TEXT` | Yes |  | Source group identifier within the phase. |
| `group_name` | `TEXT` | Yes |  | Source group display name. |
| `group_raw_name` | `TEXT` | Yes |  | Unmodified group name. |
| `group_order` | `INTEGER` | Yes |  | Source group display order. |
| `round_number` | `INTEGER` | Yes |  | Source game/standings round number; cumulative snapshots include games through this round. |
| `round_name` | `TEXT` | Yes |  | Source round display name. |
| `round_alias` | `TEXT` | Yes |  | Source round alias. |
| `scheduled_at` | `TIMESTAMPTZ` | Yes |  | Scheduled tipoff as a timestamp with time zone; convert for frontend display. |
| `source_date` | `TEXT` | Yes |  | Original source game-date text retained for traceability. |
| `local_date` | `TIMESTAMP` | Yes |  | Source venue-local game date/time stored as a timestamp without time zone. |
| `local_time_zone_minutes` | `INTEGER` | Yes |  | Source venue time-zone offset in minutes. |
| `played` | `BOOLEAN` | Yes |  | Source flag that the fixture has been played. |
| `game_status` | `TEXT` | Yes |  | Unmodified source game-status label. |
| `status` | `TEXT` | Yes |  | Derived completed, scheduled, awaiting_result, postponed or cancelled status. |
| `status_note` | `TEXT` | Yes |  | Explanation accompanying the derived game status. |
| `confirmed_date` | `BOOLEAN` | Yes |  | Source flag that the fixture date is confirmed. |
| `confirmed_hour` | `BOOLEAN` | Yes |  | Source flag that the fixture time is confirmed. |
| `local_club_code` | `TEXT` | Yes |  | Source local-side club; joins app_clubs within competition and season. |
| `local_club_name` | `TEXT` | Yes |  | Source local-side club name. |
| `local_club_abbreviated_name` | `TEXT` | Yes |  | Source abbreviated local-side club name. |
| `local_club_tv_code` | `TEXT` | Yes |  | Source local-side television abbreviation. |
| `road_club_code` | `TEXT` | Yes |  | Source road-side club; joins app_clubs within competition and season. |
| `road_club_name` | `TEXT` | Yes |  | Source road-side club name. |
| `road_club_abbreviated_name` | `TEXT` | Yes |  | Source abbreviated road-side club name. |
| `road_club_tv_code` | `TEXT` | Yes |  | Source road-side television abbreviation. |
| `local_score` | `INTEGER` | Yes |  | Official local-side final score; NULL until a result is available. |
| `road_score` | `INTEGER` | Yes |  | Official road-side final score; NULL until a result is available. |
| `local_standings_score` | `INTEGER` | Yes |  | Source local-side score used for standings, retained separately from the final score. |
| `road_standings_score` | `INTEGER` | Yes |  | Source road-side score used for standings, retained separately from the final score. |
| `match_winner_club_code` | `TEXT` | Yes |  | Winner of this played game; distinct from the season champion. |
| `champion_club_code` | `TEXT` | Yes |  | Season champion's club code; not this game's winner. |
| `champion_club_name` | `TEXT` | Yes |  | Season champion's display name. |
| `audience` | `INTEGER` | Yes |  | Reported attendance; source zero for unknown is stored as NULL. |
| `audience_note` | `TEXT` | Yes |  | Explanation when attendance is unavailable or source zero was normalized. |
| `audience_confirmed` | `BOOLEAN` | Yes |  | Source attendance-confirmation flag. |
| `venue_code` | `TEXT` | Yes |  | Source venue identifier. |
| `venue_name` | `TEXT` | Yes |  | Source venue display name. |
| `venue_capacity` | `INTEGER` | Yes |  | Reported venue seating capacity. |
| `venue_address` | `TEXT` | Yes |  | Source venue address. |
| `venue_active` | `BOOLEAN` | Yes |  | Source venue-active flag. |
| `venue_notes` | `TEXT` | Yes |  | Source venue notes. |
| `is_neutral_venue` | `BOOLEAN` | Yes |  | Source flag for a neutral venue; do not infer it from side. |
| `social_feed` | `TEXT` | Yes |  | Source game social-feed metadata. |
| `operations_code` | `TEXT` | Yes |  | Source game operations code. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_game_officials

**Purpose:** Referee assignments for game details.

**Grain:** one official slot per game. **Columns:** 11.

**Primary key:** `competition_code`, `season_code`, `game_code`, `official_number`.

**Definition / implementation:** [postgres_etl/flat_schema.py](../postgres_etl/flat_schema.py).

**Usage and limitations:** Join to app_games using competition_code, season_code and game_code.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `official_number` | `INTEGER` | No | PK | Official's ordinal slot in this game's assignments. |
| `official_code` | `TEXT` | Yes |  | Source official identifier. |
| `name` | `TEXT` | Yes |  | Display name supplied by the source; identity tables use the latest season profile. |
| `alias` | `TEXT` | Yes |  | Source alternative display name or alias. |
| `country_code` | `TEXT` | Yes |  | Source country code for the person, club or official. |
| `country_name` | `TEXT` | Yes |  | Source country display name. |
| `active` | `BOOLEAN` | Yes |  | Source active flag for a registration or official. |
| `image_vertical_small` | `TEXT` | Yes |  | Source small portrait URL for the official. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_players

**Purpose:** One player identity across seasons, with career span and club history.

**Grain:** one player per competition and person_code. **Columns:** 16.

**Primary key:** `competition_code`, `person_code`.

**Definition / implementation:** [gold_etl/identity.py](../gold_etl/identity.py).

**Usage and limitations:** Includes role_code = 'J' registrations only. Profile values come from the latest season row; NULLs remain NULL. Career span is based on registrations, not counted appearances. Join via app_people to bridge person_key.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `person_code` | `TEXT` | No | PK | Person code; career identity in profiles, resolved box-score person_key in live-event tables. |
| `name` | `TEXT` | Yes |  | Display name supplied by the source; identity tables use the latest season profile. |
| `country_code` | `TEXT` | Yes |  | Source country code for the person, club or official. |
| `country_name` | `TEXT` | Yes |  | Source country display name. |
| `height_cm` | `INTEGER` | Yes |  | Source person height in centimeters. |
| `weight_kg` | `INTEGER` | Yes |  | Source person weight in kilograms. |
| `birth_at` | `TIMESTAMP` | Yes |  | Source birth date stored as a timestamp without time zone. |
| `birth_country_code` | `TEXT` | Yes |  | Source birth-country code. |
| `birth_country_name` | `TEXT` | Yes |  | Source birth-country display name. |
| `position` | `INTEGER` | Yes |  | Source position code for a player; not a standings rank. |
| `position_name` | `TEXT` | Yes |  | Source label for the player's position. |
| `first_season_code` | `TEXT` | No |  | Earliest loaded season for this identity; player span uses player registrations. |
| `last_season_code` | `TEXT` | No |  | Latest loaded season for this identity; player span uses player registrations. |
| `seasons_played` | `INTEGER` | No |  | Count of distinct loaded seasons for this identity, registration-based for players. |
| `clubs` | `JSONB` | No |  | JSON array of player registration history: seasonCode, clubCode, clubName. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_club_identities

**Purpose:** One club identity across seasons.

**Grain:** one club per competition. **Columns:** 9.

**Primary key:** `competition_code`, `club_code`.

**Definition / implementation:** [gold_etl/identity.py](../gold_etl/identity.py).

**Usage and limitations:** Profile comes from the latest loaded season; first/last season and seasons_played describe loaded club seasons. Season-specific names stay in app_clubs.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `club_code` | `TEXT` | No | PK | Club identifier, text; join season profiles on competition, season and club. |
| `name` | `TEXT` | Yes |  | Display name supplied by the source; identity tables use the latest season profile. |
| `crest_url` | `TEXT` | Yes |  | Source team crest image URL. |
| `country_code` | `TEXT` | Yes |  | Source country code for the person, club or official. |
| `country_name` | `TEXT` | Yes |  | Source country display name. |
| `first_season_code` | `TEXT` | No |  | Earliest loaded season for this identity; player span uses player registrations. |
| `last_season_code` | `TEXT` | No |  | Latest loaded season for this identity; player span uses player registrations. |
| `seasons_played` | `INTEGER` | No |  | Count of distinct loaded seasons for this identity, registration-based for players. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_game_period_scores

**Purpose:** Quarter and overtime scoring.

**Grain:** one side-period per game. **Columns:** 6.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`, `period_number`.

**Definition / implementation:** [postgres_etl/flat_schema.py](../postgres_etl/flat_schema.py).

**Usage and limitations:** score is the points in that period. Periods 1-4 are regulation; 5+ are overtime. Include side when joining team-game rows.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Source side, local or road; local is not proof of a non-neutral home venue. |
| `period_number` | `INTEGER` | No | PK | Period number: 1-4 for quarters, 5 and above for overtime. |
| `score` | `INTEGER` | Yes |  | Points scored by this side in this period, not the cumulative score. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_game_player_stats

**Purpose:** Official player box scores, including DNP lines.

**Grain:** one player-side per game. **Columns:** 43.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`, `person_key`.

**Definition / implementation:** [postgres_etl/flat_schema.py](../postgres_etl/flat_schema.py).

**Usage and limitations:** Join advanced rows on competition_code, season_code, game_code, side and person_key. seconds_played is seconds, not minutes. DNP box-score rows are not appearances in the cumulative player tables.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Source side, local or road; local is not proof of a non-neutral home venue. |
| `person_key` | `TEXT` | No | PK | Season person identity used by box scores; bridge to career person_code through app_people. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `person_name` | `TEXT` | Yes |  | Person display name attached to this registration or box score. |
| `club_name` | `TEXT` | Yes |  | Club display name for this season or row. |
| `player_type_code` | `TEXT` | Yes |  | Source classification of the box-score person. |
| `registration_active` | `BOOLEAN` | Yes |  | Source active flag for the attached registration. |
| `registration_start_at` | `TIMESTAMP` | Yes |  | Start of the attached registration, timestamp without time zone. |
| `registration_end_at` | `TIMESTAMP` | Yes |  | End of the attached registration, timestamp without time zone. |
| `position` | `INTEGER` | Yes |  | Source position code for a player; not a standings rank. |
| `position_name` | `TEXT` | Yes |  | Source label for the player's position. |
| `jersey_number` | `TEXT` | Yes |  | Source jersey number stored as text; retain leading zeroes and special values. |
| `external_id` | `INTEGER` | Yes |  | Source external person/registration identifier, not a warehouse join key. |
| `headshot_url` | `TEXT` | Yes |  | Source game box-score portrait URL. |
| `points` | `NUMERIC` | Yes |  | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |
| `seconds_played` | `NUMERIC` | Yes |  | Official playing time in seconds; player seconds or aggregate team player-seconds in box scores. |
| `pir` | `NUMERIC` | Yes |  | Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. |
| `two_pointers_made` | `NUMERIC` | Yes |  | Successful two-point field goals (2PM). |
| `two_pointers_attempted` | `NUMERIC` | Yes |  | Two-point field-goal attempts (2PA), including makes. |
| `three_pointers_made` | `NUMERIC` | Yes |  | Successful three-point field goals (3PM). |
| `three_pointers_attempted` | `NUMERIC` | Yes |  | Three-point field-goal attempts (3PA), including makes. |
| `free_throws_made` | `NUMERIC` | Yes |  | Successful free throws (FTM). |
| `free_throws_attempted` | `NUMERIC` | Yes |  | Free-throw attempts (FTA), including makes. |
| `field_goals_made` | `NUMERIC` | Yes |  | Successful two- and three-point field goals (FGM), excluding free throws. |
| `field_goals_attempted` | `NUMERIC` | Yes |  | All two- and three-point field-goal attempts (FGA), including blocked attempts. |
| `accuracy_made` | `NUMERIC` | Yes |  | Raw source accuracyMade measure; meaning is not established by the warehouse. Do not treat it as FG%. |
| `accuracy_attempted` | `NUMERIC` | Yes |  | Raw source accuracyAttempted measure; meaning is not established by the warehouse. Do not treat it as FGA. |
| `total_rebounds` | `NUMERIC` | Yes |  | Offensive plus defensive rebounds (REB); official team totals can include team rebounds. |
| `defensive_rebounds` | `NUMERIC` | Yes |  | Rebounds recovered after the opponent's missed shot (DREB). |
| `offensive_rebounds` | `NUMERIC` | Yes |  | Rebounds recovered after the player's or club's missed shot (OREB). |
| `assists` | `NUMERIC` | Yes |  | Official credited assists (AST), including EuroLeague assists that lead to free throws. |
| `steals` | `NUMERIC` | Yes |  | Official credited steals (STL). |
| `turnovers` | `NUMERIC` | Yes |  | Lost possessions charged to the player or team (TOV). |
| `blocks` | `NUMERIC` | Yes |  | Opponent field-goal attempts blocked by the player or team (BLK). |
| `blocks_against` | `NUMERIC` | Yes |  | The player's or team's field-goal attempts blocked by opponents. |
| `fouls_committed` | `NUMERIC` | Yes |  | Personal fouls charged to the player or team (PF). |
| `fouls_drawn` | `NUMERIC` | Yes |  | Opponent fouls drawn by the player or team. |
| `plus_minus` | `NUMERIC` | Yes |  | Source point margin while the player was on court; raw points, not per 100 possessions. |
| `started` | `BOOLEAN` | Yes |  | Primary source starter flag used in on-court reconstruction and appearance counts. |
| `started_alt` | `BOOLEAN` | Yes |  | Alternate source starter flag retained separately. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_game_team_stats

**Purpose:** Official team box scores and team-only contributions.

**Grain:** one stats_kind per side-game. **Columns:** 31.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`, `stats_kind`.

**Definition / implementation:** [postgres_etl/flat_schema.py](../postgres_etl/flat_schema.py).

**Usage and limitations:** Filter stats_kind = 'total' for the complete team box score. The 'team' row is team-only contributions; adding it to the total double counts those contributions. Resolve club_code through app_games and side.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Source side, local or road; local is not proof of a non-neutral home venue. |
| `stats_kind` | `TEXT` | No | PK | total is the complete team box score; team is the team-only contribution row. |
| `coach_code` | `TEXT` | Yes |  | Source coach identifier for this side-game. |
| `coach_name` | `TEXT` | Yes |  | Source coach display name. |
| `points` | `NUMERIC` | Yes |  | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |
| `seconds_played` | `NUMERIC` | Yes |  | Official playing time in seconds; player seconds or aggregate team player-seconds in box scores. |
| `pir` | `NUMERIC` | Yes |  | Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. |
| `two_pointers_made` | `NUMERIC` | Yes |  | Successful two-point field goals (2PM). |
| `two_pointers_attempted` | `NUMERIC` | Yes |  | Two-point field-goal attempts (2PA), including makes. |
| `three_pointers_made` | `NUMERIC` | Yes |  | Successful three-point field goals (3PM). |
| `three_pointers_attempted` | `NUMERIC` | Yes |  | Three-point field-goal attempts (3PA), including makes. |
| `free_throws_made` | `NUMERIC` | Yes |  | Successful free throws (FTM). |
| `free_throws_attempted` | `NUMERIC` | Yes |  | Free-throw attempts (FTA), including makes. |
| `field_goals_made` | `NUMERIC` | Yes |  | Successful two- and three-point field goals (FGM), excluding free throws. |
| `field_goals_attempted` | `NUMERIC` | Yes |  | All two- and three-point field-goal attempts (FGA), including blocked attempts. |
| `accuracy_made` | `NUMERIC` | Yes |  | Raw source accuracyMade measure; meaning is not established by the warehouse. Do not treat it as FG%. |
| `accuracy_attempted` | `NUMERIC` | Yes |  | Raw source accuracyAttempted measure; meaning is not established by the warehouse. Do not treat it as FGA. |
| `total_rebounds` | `NUMERIC` | Yes |  | Offensive plus defensive rebounds (REB); official team totals can include team rebounds. |
| `defensive_rebounds` | `NUMERIC` | Yes |  | Rebounds recovered after the opponent's missed shot (DREB). |
| `offensive_rebounds` | `NUMERIC` | Yes |  | Rebounds recovered after the player's or club's missed shot (OREB). |
| `assists` | `NUMERIC` | Yes |  | Official credited assists (AST), including EuroLeague assists that lead to free throws. |
| `steals` | `NUMERIC` | Yes |  | Official credited steals (STL). |
| `turnovers` | `NUMERIC` | Yes |  | Lost possessions charged to the player or team (TOV). |
| `blocks` | `NUMERIC` | Yes |  | Opponent field-goal attempts blocked by the player or team (BLK). |
| `blocks_against` | `NUMERIC` | Yes |  | The player's or team's field-goal attempts blocked by opponents. |
| `fouls_committed` | `NUMERIC` | Yes |  | Personal fouls charged to the player or team (PF). |
| `fouls_drawn` | `NUMERIC` | Yes |  | Opponent fouls drawn by the player or team. |
| `plus_minus` | `NUMERIC` | Yes |  | Source point margin while the player was on court; raw points, not per 100 possessions. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_season_player_stats_traditional

**Purpose:** Player season totals and per-game box-score leaderboards.

**Grain:** one feed entry per phase and mode. **Columns:** 41.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `mode`, `entry_ordinal`.

**Definition / implementation:** [gold_etl/per_game_rows.py](../gold_etl/per_game_rows.py).

**Usage and limitations:** Select phase_code and mode explicitly. Percentages are on a 0-100 scale. Gold derives missing perGame rows and PS rows; qualified controls leaderboard eligibility.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | Phase identifier: all, RS, TS, PI, PO, FF or derived PS as supported by this table. |
| `mode` | `TEXT` | No | PK | accumulated or perGame; select one before reading player season measures. |
| `entry_ordinal` | `INTEGER` | No | PK | Feed row ordinal within phase and mode, not a stable player identifier. |
| `person_key` | `TEXT` | No |  | Season person identity used by box scores; bridge to career person_code through app_people. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `player_name` | `TEXT` | Yes |  | Player display name; cumulative round rows use the latest appearance's name. |
| `player_age` | `INTEGER` | Yes |  | Age reported in the source season feed, not recalculated current age. |
| `player_image_url` | `TEXT` | Yes |  | Source player portrait URL. |
| `club_name` | `TEXT` | Yes |  | Club display name for this season or row. |
| `club_tv_codes` | `TEXT` | Yes |  | Source team television abbreviations. |
| `club_image_url` | `TEXT` | Yes |  | Source team image URL for the season feed. |
| `player_ranking` | `INTEGER` | Yes |  | Source leaderboard ranking; calculated perGame rows have NULL. |
| `games_played` | `NUMERIC` | Yes |  | Games/appearances in the selected row scope; see table notes for counted games and series fixture counts. |
| `games_started` | `NUMERIC` | Yes |  | Games in which the player started; cumulative appearance count or retained feed count. |
| `minutes_played` | `NUMERIC` | Yes |  | Playing time in minutes in season feeds; traditional perGame rows use minutes per appearance. |
| `points` | `NUMERIC` | Yes |  | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |
| `two_pointers_made` | `NUMERIC` | Yes |  | Successful two-point field goals (2PM). |
| `two_pointers_attempted` | `NUMERIC` | Yes |  | Two-point field-goal attempts (2PA), including makes. |
| `two_pointers_percentage` | `NUMERIC` | Yes |  | Two-point shooting percentage, 100 * 2PM / 2PA, on the feed's 0-100 scale. |
| `three_pointers_made` | `NUMERIC` | Yes |  | Successful three-point field goals (3PM). |
| `three_pointers_attempted` | `NUMERIC` | Yes |  | Three-point field-goal attempts (3PA), including makes. |
| `three_pointers_percentage` | `NUMERIC` | Yes |  | Three-point shooting percentage, 100 * 3PM / 3PA, on the feed's 0-100 scale. |
| `free_throws_made` | `NUMERIC` | Yes |  | Successful free throws (FTM). |
| `free_throws_attempted` | `NUMERIC` | Yes |  | Free-throw attempts (FTA), including makes. |
| `free_throws_percentage` | `NUMERIC` | Yes |  | Free-throw shooting percentage, 100 * FTM / FTA, on the feed's 0-100 scale. |
| `offensive_rebounds` | `NUMERIC` | Yes |  | Rebounds recovered after the player's or club's missed shot (OREB). |
| `defensive_rebounds` | `NUMERIC` | Yes |  | Rebounds recovered after the opponent's missed shot (DREB). |
| `total_rebounds` | `NUMERIC` | Yes |  | Offensive plus defensive rebounds (REB); official team totals can include team rebounds. |
| `assists` | `NUMERIC` | Yes |  | Official credited assists (AST), including EuroLeague assists that lead to free throws. |
| `steals` | `NUMERIC` | Yes |  | Official credited steals (STL). |
| `turnovers` | `NUMERIC` | Yes |  | Lost possessions charged to the player or team (TOV). |
| `blocks` | `NUMERIC` | Yes |  | Opponent field-goal attempts blocked by the player or team (BLK). |
| `blocks_against` | `NUMERIC` | Yes |  | The player's or team's field-goal attempts blocked by opponents. |
| `fouls_committed` | `NUMERIC` | Yes |  | Personal fouls charged to the player or team (PF). |
| `fouls_drawn` | `NUMERIC` | Yes |  | Opponent fouls drawn by the player or team. |
| `pir` | `NUMERIC` | Yes |  | Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. |
| `is_calculated` | `BOOLEAN` | No |  | True for a row derived by Gold (PS or a missing perGame row), false for a copied feed row. |
| `min_games` | `INTEGER` | No |  | Games threshold: floor(distinct played rounds in scope / 2) + 1; FF uses 1. |
| `qualified` | `BOOLEAN` | No |  | Player season row has games_played >= min_games; this is not qualification for the playoffs. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_season_player_stats_advanced

**Purpose:** API player shooting efficiency, rebound rates and other reference ratios.

**Grain:** one feed entry per phase and mode. **Columns:** 31.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `mode`, `entry_ordinal`.

**Definition / implementation:** [gold_etl/per_game_rows.py](../gold_etl/per_game_rows.py).

**Usage and limitations:** API definitions are retained. They are not aliases for the calculated round rates. Advanced PS rows are not derived. See the glossary for differences and unverified source definitions.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | Phase identifier: all, RS, TS, PI, PO, FF or derived PS as supported by this table. |
| `mode` | `TEXT` | No | PK | accumulated or perGame; select one before reading player season measures. |
| `entry_ordinal` | `INTEGER` | No | PK | Feed row ordinal within phase and mode, not a stable player identifier. |
| `person_key` | `TEXT` | No |  | Season person identity used by box scores; bridge to career person_code through app_people. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `player_name` | `TEXT` | Yes |  | Player display name; cumulative round rows use the latest appearance's name. |
| `player_age` | `INTEGER` | Yes |  | Age reported in the source season feed, not recalculated current age. |
| `player_image_url` | `TEXT` | Yes |  | Source player portrait URL. |
| `club_name` | `TEXT` | Yes |  | Club display name for this season or row. |
| `club_tv_codes` | `TEXT` | Yes |  | Source team television abbreviations. |
| `club_image_url` | `TEXT` | Yes |  | Source team image URL for the season feed. |
| `player_ranking` | `INTEGER` | Yes |  | Source leaderboard ranking; calculated perGame rows have NULL. |
| `games_played` | `NUMERIC` | Yes |  | Games/appearances in the selected row scope; see table notes for counted games and series fixture counts. |
| `minutes_played` | `NUMERIC` | Yes |  | Playing time in minutes in season feeds; traditional perGame rows use minutes per appearance. |
| `effective_field_goal_percentage` | `NUMERIC` | Yes |  | API eFG percentage on the 0-100 scale; calculated efg_pct uses a fraction instead. |
| `true_shooting_percentage` | `NUMERIC` | Yes |  | API true-shooting percentage on the 0-100 scale; calculated ts_pct/true_shooting_pct use fractions. |
| `offensive_rebounds_percentage` | `NUMERIC` | Yes |  | API offensive rebound percentage on the 0-100 scale, retaining source team-minute conventions. |
| `defensive_rebounds_percentage` | `NUMERIC` | Yes |  | API defensive rebound percentage on the 0-100 scale, retaining source team-minute conventions. |
| `rebounds_percentage` | `NUMERIC` | Yes |  | API total rebound percentage on the 0-100 scale, retaining source team-minute conventions. |
| `assists_to_turnovers_ratio` | `NUMERIC` | Yes |  | API assists-to-turnovers ratio (AST/TOV), retained as supplied including source zero-denominator handling. |
| `assists_ratio` | `NUMERIC` | Yes |  | API assists ratio, retained without recomputation; denominator differs from calculated assist_ratio/ast_pct. |
| `turnovers_ratio` | `NUMERIC` | Yes |  | API turnovers ratio, retained without recomputation; not calculated tov_pct. |
| `two_point_attempts_ratio` | `NUMERIC` | Yes |  | API two-point attempt ratio; exact denominator and scale are not established by the warehouse. |
| `three_point_attempts_ratio` | `NUMERIC` | Yes |  | API three-point attempt ratio; exact denominator and scale are not established by the warehouse. |
| `free_throws_rate` | `NUMERIC` | Yes |  | API free-throw rate; definition differs from calculated FTM/FGA ft_rate. Do not substitute it. |
| `possessions` | `NUMERIC` | Yes |  | In calculated team rows: mean of the two clubs' possession estimates, summed for cumulative rows. API player feed possessions has a separate source definition. |
| `is_calculated` | `BOOLEAN` | No |  | True for a row derived by Gold (PS or a missing perGame row), false for a copied feed row. |
| `min_games` | `INTEGER` | No |  | Games threshold: floor(distinct played rounds in scope / 2) + 1; FF uses 1. |
| `qualified` | `BOOLEAN` | No |  | Player season row has games_played >= min_games; this is not qualification for the playoffs. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_season_player_stats_scoring

**Purpose:** API player shot mix and scoring distribution.

**Grain:** one feed entry per phase and mode. **Columns:** 30.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `mode`, `entry_ordinal`.

**Definition / implementation:** [gold_etl/per_game_rows.py](../gold_etl/per_game_rows.py).

**Usage and limitations:** API definitions and scales are retained. Scoring PS rows are not derived. Fields ending in share or rate need source-specific interpretation; do not infer their denominator from the name.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | Phase identifier: all, RS, TS, PI, PO, FF or derived PS as supported by this table. |
| `mode` | `TEXT` | No | PK | accumulated or perGame; select one before reading player season measures. |
| `entry_ordinal` | `INTEGER` | No | PK | Feed row ordinal within phase and mode, not a stable player identifier. |
| `person_key` | `TEXT` | No |  | Season person identity used by box scores; bridge to career person_code through app_people. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `player_name` | `TEXT` | Yes |  | Player display name; cumulative round rows use the latest appearance's name. |
| `player_age` | `INTEGER` | Yes |  | Age reported in the source season feed, not recalculated current age. |
| `player_image_url` | `TEXT` | Yes |  | Source player portrait URL. |
| `club_name` | `TEXT` | Yes |  | Club display name for this season or row. |
| `club_tv_codes` | `TEXT` | Yes |  | Source team television abbreviations. |
| `club_image_url` | `TEXT` | Yes |  | Source team image URL for the season feed. |
| `player_ranking` | `INTEGER` | Yes |  | Source leaderboard ranking; calculated perGame rows have NULL. |
| `games_played` | `NUMERIC` | Yes |  | Games/appearances in the selected row scope; see table notes for counted games and series fixture counts. |
| `games_started` | `NUMERIC` | Yes |  | Games in which the player started; cumulative appearance count or retained feed count. |
| `two_point_attempts_share` | `NUMERIC` | Yes |  | API two-point attempt share; denominator and scale are not established by the warehouse. |
| `three_point_attempts_share` | `NUMERIC` | Yes |  | API three-point attempt share; denominator and scale are not established by the warehouse. |
| `free_throws_attempts_share` | `NUMERIC` | Yes |  | API free-throw attempt share; denominator and scale are not established by the warehouse. |
| `two_pointers_made_share` | `NUMERIC` | Yes |  | API two-point makes share; denominator and scale are not established by the warehouse. |
| `three_pointers_made_share` | `NUMERIC` | Yes |  | API three-point makes share; denominator and scale are not established by the warehouse. |
| `free_throws_made_share` | `NUMERIC` | Yes |  | API free-throw makes share; denominator and scale are not established by the warehouse. |
| `two_point_rate` | `NUMERIC` | Yes |  | API two-point rate; denominator and scale are not established by the warehouse. |
| `three_point_rate` | `NUMERIC` | Yes |  | API three-point rate; denominator and scale are not established by the warehouse. |
| `points_from_two_pointers_percentage` | `NUMERIC` | Yes |  | API percentage of points from two-pointers, 0-100 scale. |
| `points_from_three_pointers_percentage` | `NUMERIC` | Yes |  | API percentage of points from three-pointers, 0-100 scale. |
| `points_from_free_throws_percentage` | `NUMERIC` | Yes |  | API percentage of points from free throws, 0-100 scale. |
| `is_calculated` | `BOOLEAN` | No |  | True for a row derived by Gold (PS or a missing perGame row), false for a copied feed row. |
| `min_games` | `INTEGER` | No |  | Games threshold: floor(distinct played rounds in scope / 2) + 1; FF uses 1. |
| `qualified` | `BOOLEAN` | No |  | Player season row has games_played >= min_games; this is not qualification for the playoffs. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_season_player_stats_misc

**Purpose:** Player starts, wins/losses and double/triple doubles.

**Grain:** one feed entry per phase and mode. **Columns:** 24.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `mode`, `entry_ordinal`.

**Definition / implementation:** [gold_etl/per_game_rows.py](../gold_etl/per_game_rows.py).

**Usage and limitations:** Gold derives PS and missing perGame rows. Do not divide every numeric field by games: generated misc perGame rows retain accumulated measures.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | Phase identifier: all, RS, TS, PI, PO, FF or derived PS as supported by this table. |
| `mode` | `TEXT` | No | PK | accumulated or perGame; select one before reading player season measures. |
| `entry_ordinal` | `INTEGER` | No | PK | Feed row ordinal within phase and mode, not a stable player identifier. |
| `person_key` | `TEXT` | No |  | Season person identity used by box scores; bridge to career person_code through app_people. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `player_name` | `TEXT` | Yes |  | Player display name; cumulative round rows use the latest appearance's name. |
| `player_age` | `INTEGER` | Yes |  | Age reported in the source season feed, not recalculated current age. |
| `player_image_url` | `TEXT` | Yes |  | Source player portrait URL. |
| `club_name` | `TEXT` | Yes |  | Club display name for this season or row. |
| `club_tv_codes` | `TEXT` | Yes |  | Source team television abbreviations. |
| `club_image_url` | `TEXT` | Yes |  | Source team image URL for the season feed. |
| `player_ranking` | `INTEGER` | Yes |  | Source leaderboard ranking; calculated perGame rows have NULL. |
| `games_played` | `NUMERIC` | Yes |  | Games/appearances in the selected row scope; see table notes for counted games and series fixture counts. |
| `games_started` | `NUMERIC` | Yes |  | Games in which the player started; cumulative appearance count or retained feed count. |
| `wins` | `NUMERIC` | Yes |  | Games won in this row's scope; source player misc values follow the API. |
| `losses` | `NUMERIC` | Yes |  | Games lost in this row's scope; source player misc values follow the API. |
| `minutes_played` | `NUMERIC` | Yes |  | Playing time in minutes in season feeds; traditional perGame rows use minutes per appearance. |
| `double_doubles` | `NUMERIC` | Yes |  | Source count of games reaching ten in at least two categories; derived PS uses points, rebounds, assists, steals and blocks. |
| `triple_doubles` | `NUMERIC` | Yes |  | Source count of games reaching ten in at least three categories; derived PS uses points, rebounds, assists, steals and blocks. |
| `is_calculated` | `BOOLEAN` | No |  | True for a row derived by Gold (PS or a missing perGame row), false for a copied feed row. |
| `min_games` | `INTEGER` | No |  | Games threshold: floor(distinct played rounds in scope / 2) + 1; FF uses 1. |
| `qualified` | `BOOLEAN` | No |  | Player season row has games_played >= min_games; this is not qualification for the playoffs. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_standings

**Purpose:** Official standings page, form, streaks and standings splits.

**Grain:** one club-phase-round snapshot. **Columns:** 79.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `round_number`, `club_code`.

**Definition / implementation:** [gold_etl/standings.py](../gold_etl/standings.py).

**Usage and limitations:** basic_*, calendar_*, streaks_*, ahead_behind_* and margins_* preserve separate feeds. Use basic_position for official position. These snapshots can differ from game-derived round totals, particularly historical round alignment.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | Phase identifier: all, RS, TS, PI, PO, FF or derived PS as supported by this table. |
| `round_number` | `INTEGER` | No | PK | Source game/standings round number; cumulative snapshots include games through this round. |
| `club_code` | `TEXT` | No | PK | Club identifier, text; join season profiles on competition, season and club. |
| `club_name` | `TEXT` | Yes |  | Club display name for this season or row. |
| `club_tv_code` | `TEXT` | Yes |  | Source club television abbreviation. |
| `crest_url` | `TEXT` | Yes |  | Source team crest image URL. |
| `group_name` | `TEXT` | Yes |  | Source group display name. |
| `basic_position` | `INTEGER` | Yes |  | basic feed: Official rank in the source standings snapshot. |
| `basic_position_change` | `TEXT` | Yes |  | basic feed: Source position movement label. |
| `basic_games_played` | `INTEGER` | Yes |  | basic feed: Source games played in this standings snapshot. |
| `basic_games_won` | `INTEGER` | Yes |  | basic feed: Source games won in this standings snapshot. |
| `basic_games_lost` | `INTEGER` | Yes |  | basic feed: Source games lost in this standings snapshot. |
| `basic_qualified` | `BOOLEAN` | Yes |  | basic feed: Source playoff/phase qualification flag, distinct from player leaderboard eligibility. |
| `basic_win_percentage` | `NUMERIC` | Yes |  | basic feed: Source win percentage retained as supplied; verify its scale before formatting. |
| `basic_points_difference` | `INTEGER` | Yes |  | basic feed: Source points for minus points against. |
| `basic_points_for` | `INTEGER` | Yes |  | basic feed: Source cumulative points scored. |
| `basic_points_against` | `INTEGER` | Yes |  | basic feed: Source cumulative points conceded. |
| `basic_home_record` | `TEXT` | Yes |  | basic feed: Source win-loss record text for home record; preserve its text format. |
| `basic_away_record` | `TEXT` | Yes |  | basic feed: Source win-loss record text for away record; preserve its text format. |
| `basic_neutral_record` | `TEXT` | Yes |  | basic feed: Source win-loss record text for neutral record; preserve its text format. |
| `basic_overtime_record` | `TEXT` | Yes |  | basic feed: Source win-loss record text for overtime record; preserve its text format. |
| `basic_last_ten_record` | `TEXT` | Yes |  | basic feed: Source win-loss record text for last ten record; preserve its text format. |
| `calendar_position` | `INTEGER` | Yes |  | calendar feed: Official rank in the source standings snapshot. |
| `calendar_position_change` | `TEXT` | Yes |  | calendar feed: Source position movement label. |
| `calendar_games_played` | `INTEGER` | Yes |  | calendar feed: Source games played in this standings snapshot. |
| `calendar_games_won` | `INTEGER` | Yes |  | calendar feed: Source games won in this standings snapshot. |
| `calendar_games_lost` | `INTEGER` | Yes |  | calendar feed: Source games lost in this standings snapshot. |
| `calendar_qualified` | `BOOLEAN` | Yes |  | calendar feed: Source playoff/phase qualification flag, distinct from player leaderboard eligibility. |
| `streaks_position` | `INTEGER` | Yes |  | streaks feed: Official rank in the source standings snapshot. |
| `streaks_position_change` | `TEXT` | Yes |  | streaks feed: Source position movement label. |
| `streaks_games_played` | `INTEGER` | Yes |  | streaks feed: Source games played in this standings snapshot. |
| `streaks_games_won` | `INTEGER` | Yes |  | streaks feed: Source games won in this standings snapshot. |
| `streaks_games_lost` | `INTEGER` | Yes |  | streaks feed: Source games lost in this standings snapshot. |
| `streaks_qualified` | `BOOLEAN` | Yes |  | streaks feed: Source playoff/phase qualification flag, distinct from player leaderboard eligibility. |
| `streaks_home_record` | `TEXT` | Yes |  | streaks feed: Source win-loss record text for home record; preserve its text format. |
| `streaks_away_record` | `TEXT` | Yes |  | streaks feed: Source win-loss record text for away record; preserve its text format. |
| `streaks_last10` | `TEXT` | Yes |  | streaks feed: Source win-loss record text for last10; preserve its text format. |
| `streaks_home_last5` | `TEXT` | Yes |  | streaks feed: Source win-loss record text for home last5; preserve its text format. |
| `streaks_away_last5` | `TEXT` | Yes |  | streaks feed: Source win-loss record text for away last5; preserve its text format. |
| `streaks_longest_win_streak_current_season` | `INTEGER` | Yes |  | streaks feed: Source longest win streak current season, measured in games. |
| `streaks_longest_lose_streak_current_season` | `INTEGER` | Yes |  | streaks feed: Source longest lose streak current season, measured in games. |
| `streaks_longest_win_streak_any_season` | `INTEGER` | Yes |  | streaks feed: Source longest win streak any season, measured in games. |
| `streaks_longest_lose_streak_any_season` | `INTEGER` | Yes |  | streaks feed: Source longest lose streak any season, measured in games. |
| `ahead_behind_position` | `INTEGER` | Yes |  | ahead_behind feed: Official rank in the source standings snapshot. |
| `ahead_behind_position_change` | `TEXT` | Yes |  | ahead_behind feed: Source position movement label. |
| `ahead_behind_games_played` | `INTEGER` | Yes |  | ahead_behind feed: Source games played in this standings snapshot. |
| `ahead_behind_games_won` | `INTEGER` | Yes |  | ahead_behind feed: Source games won in this standings snapshot. |
| `ahead_behind_games_lost` | `INTEGER` | Yes |  | ahead_behind feed: Source games lost in this standings snapshot. |
| `ahead_behind_qualified` | `BOOLEAN` | Yes |  | ahead_behind feed: Source playoff/phase qualification flag, distinct from player leaderboard eligibility. |
| `ahead_behind_wins_percentage` | `NUMERIC` | Yes |  | ahead_behind feed: Source wins percentage retained as supplied; verify its scale before formatting. |
| `ahead_behind_quarter1_ahead` | `TEXT` | Yes |  | ahead_behind feed: Source win-loss record text for games quarter1 ahead at that checkpoint. |
| `ahead_behind_quarter1_behind` | `TEXT` | Yes |  | ahead_behind feed: Source win-loss record text for games quarter1 behind at that checkpoint. |
| `ahead_behind_quarter1_tied` | `TEXT` | Yes |  | ahead_behind feed: Source win-loss record text for games quarter1 tied at that checkpoint. |
| `ahead_behind_half1_ahead` | `TEXT` | Yes |  | ahead_behind feed: Source win-loss record text for games half1 ahead at that checkpoint. |
| `ahead_behind_half1_behind` | `TEXT` | Yes |  | ahead_behind feed: Source win-loss record text for games half1 behind at that checkpoint. |
| `ahead_behind_half1_tied` | `TEXT` | Yes |  | ahead_behind feed: Source win-loss record text for games half1 tied at that checkpoint. |
| `ahead_behind_quarter3_ahead` | `TEXT` | Yes |  | ahead_behind feed: Source win-loss record text for games quarter3 ahead at that checkpoint. |
| `ahead_behind_quarter3_behind` | `TEXT` | Yes |  | ahead_behind feed: Source win-loss record text for games quarter3 behind at that checkpoint. |
| `ahead_behind_quarter3_tied` | `TEXT` | Yes |  | ahead_behind feed: Source win-loss record text for games quarter3 tied at that checkpoint. |
| `margins_position` | `INTEGER` | Yes |  | margins feed: Official rank in the source standings snapshot. |
| `margins_position_change` | `TEXT` | Yes |  | margins feed: Source position movement label. |
| `margins_games_played` | `INTEGER` | Yes |  | margins feed: Source games played in this standings snapshot. |
| `margins_games_won` | `INTEGER` | Yes |  | margins feed: Source games won in this standings snapshot. |
| `margins_games_lost` | `INTEGER` | Yes |  | margins feed: Source games lost in this standings snapshot. |
| `margins_qualified` | `BOOLEAN` | Yes |  | margins feed: Source playoff/phase qualification flag, distinct from player leaderboard eligibility. |
| `margins_point_difference_1_to_5` | `TEXT` | Yes |  | margins feed: Source win-loss record text for games with final margin 1 to 5 points. |
| `margins_point_difference_6_to_10` | `TEXT` | Yes |  | margins feed: Source win-loss record text for games with final margin 6 to 10 points. |
| `margins_point_difference_11_to_15` | `TEXT` | Yes |  | margins feed: Source win-loss record text for games with final margin 11 to 15 points. |
| `margins_point_difference_more_than_15` | `TEXT` | Yes |  | margins feed: Source win-loss record text for games with final margin more than 15 points. |
| `margins_rebounds` | `TEXT` | Yes |  | margins feed: Source comparison/split record text for rebounds; not a raw statistical total. |
| `margins_assists` | `TEXT` | Yes |  | margins feed: Source comparison/split record text for assists; not a raw statistical total. |
| `margins_blocks` | `TEXT` | Yes |  | margins feed: Source comparison/split record text for blocks; not a raw statistical total. |
| `margins_three_pointers` | `TEXT` | Yes |  | margins feed: Source comparison/split record text for three pointers; not a raw statistical total. |
| `margins_two_pointers` | `TEXT` | Yes |  | margins feed: Source comparison/split record text for two pointers; not a raw statistical total. |
| `margins_free_throws` | `TEXT` | Yes |  | margins feed: Source comparison/split record text for free throws; not a raw statistical total. |
| `form` | `JSONB` | No |  | Ordered JSON array of recent official standings results; see the JSON contract below. |
| `streak_history` | `JSONB` | No |  | Ordered JSON array of official calendar streaks; see the JSON contract below. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_team_season_stats

**Purpose:** Team and opponent season box-score totals.

**Grain:** one club-phase per season, for phases actually present in games. **Columns:** 46.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `club_code`.

**Definition / implementation:** [gold_etl/team_season.py](../gold_etl/team_season.py).

**Usage and limitations:** No synthetic all or PS rows. Legacy own_/opp_ spellings are intentional, for example own_assistances and own_valuation. Counted games exclude forfeits without box scores. Use app_standings_stats for calculated efficiency and ratings.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | Phase identifier: all, RS, TS, PI, PO, FF or derived PS as supported by this table. |
| `club_code` | `TEXT` | No | PK | Club identifier, text; join season profiles on competition, season and club. |
| `club_name` | `TEXT` | Yes |  | Club display name for this season or row. |
| `games_played` | `INTEGER` | No |  | Games/appearances in the selected row scope; see table notes for counted games and series fixture counts. |
| `own_points` | `NUMERIC` | Yes |  | Team total: Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |
| `own_field_goals_made2` | `NUMERIC` | Yes |  | Team total: Successful two-point field goals (2PM). |
| `own_field_goals_attempted2` | `NUMERIC` | Yes |  | Team total: Two-point field-goal attempts (2PA), including makes. |
| `own_field_goals_made3` | `NUMERIC` | Yes |  | Team total: Successful three-point field goals (3PM). |
| `own_field_goals_attempted3` | `NUMERIC` | Yes |  | Team total: Three-point field-goal attempts (3PA), including makes. |
| `own_free_throws_made` | `NUMERIC` | Yes |  | Team total: Successful free throws (FTM). |
| `own_free_throws_attempted` | `NUMERIC` | Yes |  | Team total: Free-throw attempts (FTA), including makes. |
| `own_field_goals_made_total` | `NUMERIC` | Yes |  | Team total: Successful two- and three-point field goals (FGM), excluding free throws. |
| `own_field_goals_attempted_total` | `NUMERIC` | Yes |  | Team total: All two- and three-point field-goal attempts (FGA), including blocked attempts. |
| `own_total_rebounds` | `NUMERIC` | Yes |  | Team total: Offensive plus defensive rebounds (REB); official team totals can include team rebounds. |
| `own_defensive_rebounds` | `NUMERIC` | Yes |  | Team total: Rebounds recovered after the opponent's missed shot (DREB). |
| `own_offensive_rebounds` | `NUMERIC` | Yes |  | Team total: Rebounds recovered after the player's or club's missed shot (OREB). |
| `own_assistances` | `NUMERIC` | Yes |  | Team total: Official credited assists (AST), including EuroLeague assists that lead to free throws. |
| `own_steals` | `NUMERIC` | Yes |  | Team total: Official credited steals (STL). |
| `own_turnovers` | `NUMERIC` | Yes |  | Team total: Lost possessions charged to the player or team (TOV). |
| `own_blocks_favour` | `NUMERIC` | Yes |  | Team total: Opponent field-goal attempts blocked by the player or team (BLK). |
| `own_blocks_against` | `NUMERIC` | Yes |  | Team total: The player's or team's field-goal attempts blocked by opponents. |
| `own_fouls_commited` | `NUMERIC` | Yes |  | Team total: Personal fouls charged to the player or team (PF). |
| `own_fouls_received` | `NUMERIC` | Yes |  | Team total: Opponent fouls drawn by the player or team. |
| `own_valuation` | `NUMERIC` | Yes |  | Team total: Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. |
| `opp_points` | `NUMERIC` | Yes |  | Opponent total: Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |
| `opp_field_goals_made2` | `NUMERIC` | Yes |  | Opponent total: Successful two-point field goals (2PM). |
| `opp_field_goals_attempted2` | `NUMERIC` | Yes |  | Opponent total: Two-point field-goal attempts (2PA), including makes. |
| `opp_field_goals_made3` | `NUMERIC` | Yes |  | Opponent total: Successful three-point field goals (3PM). |
| `opp_field_goals_attempted3` | `NUMERIC` | Yes |  | Opponent total: Three-point field-goal attempts (3PA), including makes. |
| `opp_free_throws_made` | `NUMERIC` | Yes |  | Opponent total: Successful free throws (FTM). |
| `opp_free_throws_attempted` | `NUMERIC` | Yes |  | Opponent total: Free-throw attempts (FTA), including makes. |
| `opp_field_goals_made_total` | `NUMERIC` | Yes |  | Opponent total: Successful two- and three-point field goals (FGM), excluding free throws. |
| `opp_field_goals_attempted_total` | `NUMERIC` | Yes |  | Opponent total: All two- and three-point field-goal attempts (FGA), including blocked attempts. |
| `opp_total_rebounds` | `NUMERIC` | Yes |  | Opponent total: Offensive plus defensive rebounds (REB); official team totals can include team rebounds. |
| `opp_defensive_rebounds` | `NUMERIC` | Yes |  | Opponent total: Rebounds recovered after the opponent's missed shot (DREB). |
| `opp_offensive_rebounds` | `NUMERIC` | Yes |  | Opponent total: Rebounds recovered after the player's or club's missed shot (OREB). |
| `opp_assistances` | `NUMERIC` | Yes |  | Opponent total: Official credited assists (AST), including EuroLeague assists that lead to free throws. |
| `opp_steals` | `NUMERIC` | Yes |  | Opponent total: Official credited steals (STL). |
| `opp_turnovers` | `NUMERIC` | Yes |  | Opponent total: Lost possessions charged to the player or team (TOV). |
| `opp_blocks_favour` | `NUMERIC` | Yes |  | Opponent total: Opponent field-goal attempts blocked by the player or team (BLK). |
| `opp_blocks_against` | `NUMERIC` | Yes |  | Opponent total: The player's or team's field-goal attempts blocked by opponents. |
| `opp_fouls_commited` | `NUMERIC` | Yes |  | Opponent total: Personal fouls charged to the player or team (PF). |
| `opp_fouls_received` | `NUMERIC` | Yes |  | Opponent total: Opponent fouls drawn by the player or team. |
| `opp_valuation` | `NUMERIC` | Yes |  | Opponent total: Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_coverage_seasons

**Purpose:** Coverage badges for a season.

**Grain:** one season. **Columns:** 3.

**Primary key:** `competition_code`, `season_code`.

**Definition / implementation:** [gold_etl/coverage.py](../gold_etl/coverage.py).

**Usage and limitations:** items describes eight coverage categories with available/applicable counts. It is evidence of source coverage, not certification of every derived metric.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `items` | `JSONB` | No |  | JSON array of eight coverage items; see the JSON contract below. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_coverage_games

**Purpose:** Coverage badges for a fixture.

**Grain:** one game. **Columns:** 4.

**Primary key:** `competition_code`, `season_code`, `game_code`.

**Definition / implementation:** [gold_etl/coverage.py](../gold_etl/coverage.py).

**Usage and limitations:** Join to app_games on the complete game key. Some categories have zero applicable items for future fixtures.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `items` | `JSONB` | No |  | JSON array of eight coverage items; see the JSON contract below. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_records_player_seasons

**Purpose:** Historical top player-season leaderboards.

**Grain:** one rank slot per metric and competition. **Columns:** 9.

**Primary key:** `competition_code`, `metric`, `rank_ordinal`.

**Definition / implementation:** [gold_etl/records.py](../gold_etl/records.py).

**Usage and limitations:** Built from all loaded EuroLeague seasons regardless of the selected build season. Filter metric before ordering by rank_ordinal. See metric values below.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `metric` | `TEXT` | No | PK | Leaderboard measure name; filter this before interpreting value or rank_ordinal. |
| `rank_ordinal` | `INTEGER` | No | PK | Stored top-50 slot within a competition and metric; ties occupy separate slots. |
| `season_code` | `TEXT` | No |  | Starting-year season code, for example E2025 for 2025-26. |
| `person_key` | `TEXT` | No |  | Season person identity used by box scores; bridge to career person_code through app_people. |
| `player_name` | `TEXT` | Yes |  | Player display name; cumulative round rows use the latest appearance's name. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `club_name` | `TEXT` | Yes |  | Club display name for this season or row. |
| `value` | `NUMERIC` | No |  | Value of the selected leaderboard metric, with the metric's own units. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_records_single_games

**Purpose:** Historical top individual game performances.

**Grain:** one rank slot per metric and competition. **Columns:** 11.

**Primary key:** `competition_code`, `metric`, `rank_ordinal`.

**Definition / implementation:** [gold_etl/records.py](../gold_etl/records.py).

**Usage and limitations:** Competition-wide top-50 entries per metric; forfeits without a box score are excluded. season_code is a payload field as well as part of the game join, not part of this leaderboard key.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `metric` | `TEXT` | No | PK | Leaderboard measure name; filter this before interpreting value or rank_ordinal. |
| `rank_ordinal` | `INTEGER` | No | PK | Stored top-50 slot within a competition and metric; ties occupy separate slots. |
| `season_code` | `TEXT` | No |  | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No |  | Game identifier within competition and season, not globally unique. |
| `scheduled_at` | `TIMESTAMPTZ` | Yes |  | Scheduled tipoff as a timestamp with time zone; convert for frontend display. |
| `person_key` | `TEXT` | No |  | Season person identity used by box scores; bridge to career person_code through app_people. |
| `player_name` | `TEXT` | Yes |  | Player display name; cumulative round rows use the latest appearance's name. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `club_name` | `TEXT` | Yes |  | Club display name for this season or row. |
| `value` | `NUMERIC` | No |  | Value of the selected leaderboard metric, with the metric's own units. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_records_team_seasons

**Purpose:** Historical top team-season leaderboards.

**Grain:** one rank slot per metric and competition. **Columns:** 7.

**Primary key:** `competition_code`, `metric`, `rank_ordinal`.

**Definition / implementation:** [gold_etl/records.py](../gold_etl/records.py).

**Usage and limitations:** Competition-wide top-50 entries per metric. Do not sum value across different metrics or rank slots.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `metric` | `TEXT` | No | PK | Leaderboard measure name; filter this before interpreting value or rank_ordinal. |
| `rank_ordinal` | `INTEGER` | No | PK | Stored top-50 slot within a competition and metric; ties occupy separate slots. |
| `season_code` | `TEXT` | No |  | Starting-year season code, for example E2025 for 2025-26. |
| `club_code` | `TEXT` | No |  | Club identifier, text; join season profiles on competition, season and club. |
| `club_name` | `TEXT` | Yes |  | Club display name for this season or row. |
| `value` | `NUMERIC` | No |  | Value of the selected leaderboard metric, with the metric's own units. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_postseason_series

**Purpose:** Play-in, playoff and Final Four pairings with game lists.

**Grain:** one sorted club pair per postseason phase and season. **Columns:** 12.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `club_a_code`, `club_b_code`.

**Definition / implementation:** [gold_etl/series.py](../gold_etl/series.py).

**Usage and limitations:** club_a/club_b are sorted codes, not home/away. games_played currently counts all listed fixtures, including scheduled ones. Wins count played fixtures only. winner_club_code is the current wins leader and can exist before a series is decided.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | Phase identifier: all, RS, TS, PI, PO, FF or derived PS as supported by this table. |
| `club_a_code` | `TEXT` | No | PK | Lexicographically first code in this postseason pairing. |
| `club_b_code` | `TEXT` | No | PK | Lexicographically second code in this postseason pairing. |
| `club_a_name` | `TEXT` | Yes |  | Display name of club A in this pairing. |
| `club_b_name` | `TEXT` | Yes |  | Display name of club B in this pairing. |
| `games_played` | `INTEGER` | No |  | Number of fixtures in the pairing, INCLUDING scheduled fixtures; this implementation does not count played fixtures only. |
| `club_a_wins` | `INTEGER` | No |  | Played fixtures won by club A in this pairing. |
| `club_b_wins` | `INTEGER` | No |  | Played fixtures won by club B in this pairing. |
| `winner_club_code` | `TEXT` | Yes |  | Club currently ahead in pairing wins, NULL when tied; not a series-completion flag. |
| `games` | `JSONB` | No |  | JSON array of scheduled and played fixtures in round/game order; see JSON contract below. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_standings_stats

**Purpose:** One frontend-ready team advanced-stat row combining the three team-round tables.

**Grain:** one club-scope-round snapshot. **Columns:** 69.

**Primary key:** `competition_code`, `season_code`, `scope`, `round_number`, `club_code`.

**Definition / implementation:** [gold_etl/standings_stats.py](../gold_etl/standings_stats.py).

**Usage and limitations:** Preferred source for a wide team advanced table. Values are projected without recalculation. Join official standings with scope = phase_code plus competition, season, round and club; use a left join because historical rounds can disagree.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `scope` | `TEXT` | No | PK | Aggregation scope: all, one phase, or PS (PI + PO + FF). RAPM supports all only. |
| `round_number` | `INTEGER` | No | PK | Source game/standings round number; cumulative snapshots include games through this round. |
| `club_code` | `TEXT` | No | PK | Club identifier, text; join season profiles on competition, season and club. |
| `club_name` | `TEXT` | Yes |  | Club display name for this season or row. |
| `games_played` | `INTEGER` | No |  | Games/appearances in the selected row scope; see table notes for counted games and series fixture counts. |
| `wins` | `INTEGER` | No |  | Games won in this row's scope; source player misc values follow the API. |
| `losses` | `INTEGER` | No |  | Games lost in this row's scope; source player misc values follow the API. |
| `points_for` | `NUMERIC` | Yes |  | Points scored by this club or lineup in the row's game, stint or cumulative scope. |
| `points_against` | `NUMERIC` | Yes |  | Points conceded by this club or lineup in the same sample. |
| `possessions` | `NUMERIC` | Yes |  | In calculated team rows: mean of the two clubs' possession estimates, summed for cumulative rows. API player feed possessions has a separate source definition. |
| `mov` | `NUMERIC` | Yes |  | (points_for - points_against) / games_played, mean margin in points per game. |
| `pythagorean_win_pct` | `NUMERIC` | Yes |  | PF^10.25 / (PF^10.25 + PA^10.25), expected win fraction from cumulative scores. |
| `pythagorean_wins` | `NUMERIC` | Yes |  | pythagorean_win_pct * games_played, expected wins. |
| `pace` | `NUMERIC` | Yes |  | 40 * estimated possessions / game_minutes, possessions per regulation-length team game. |
| `offensive_rating` | `NUMERIC` | Yes |  | 100 * points_for / estimated possessions, points scored per 100 possessions. |
| `defensive_rating` | `NUMERIC` | Yes |  | 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. |
| `net_rating` | `NUMERIC` | Yes |  | Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. |
| `efg_pct` | `NUMERIC` | Yes |  | (FGM + 0.5 * 3PM) / FGA, a fraction that can exceed 1. |
| `tov_pct` | `NUMERIC` | Yes |  | TOV / (FGA + 0.44 * FTA + TOV), a fraction. |
| `orb_pct` | `NUMERIC` | Yes |  | Offensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. |
| `drb_pct` | `NUMERIC` | Yes |  | Defensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. |
| `ft_rate` | `NUMERIC` | Yes |  | FTM / FGA, made free throws per field-goal attempt; not FTA / FGA. |
| `opp_efg_pct` | `NUMERIC` | Yes |  | Opponent total: (FGM + 0.5 * 3PM) / FGA, a fraction that can exceed 1. |
| `opp_tov_pct` | `NUMERIC` | Yes |  | Opponent total: TOV / (FGA + 0.44 * FTA + TOV), a fraction. |
| `opp_ft_rate` | `NUMERIC` | Yes |  | Opponent total: FTM / FGA, made free throws per field-goal attempt; not FTA / FGA. |
| `true_shooting_pct` | `NUMERIC` | Yes |  | PTS / (2 * (FGA + 0.44 * FTA)), a fraction that can exceed 1. |
| `assist_ratio` | `NUMERIC` | Yes |  | AST / FGM in calculated team tables; not the API assists_ratio. |
| `connected` | `BOOLEAN` | No |  | True if the played-game graph links every club in this scope-round; governs adjusted-rating availability. |
| `league_offensive_rating` | `NUMERIC` | Yes |  | 100 * league points / league estimated possessions in this scope through this round, both sides counted. |
| `league_pace` | `NUMERIC` | Yes |  | 40 * league estimated possessions / league game-clock minutes, both sides counted. |
| `relative_offensive_rating` | `NUMERIC` | Yes |  | Club offensive_rating minus league_offensive_rating; positive means better offense. |
| `relative_defensive_rating` | `NUMERIC` | Yes |  | Club defensive_rating minus league_offensive_rating; negative means better defense. |
| `relative_pace` | `NUMERIC` | Yes |  | Club pace minus league_pace, possessions per 40 minutes above/below the league. |
| `srs` | `NUMERIC` | Yes |  | Simple Rating System: MOV plus mean opponent SRS, solved with league mean zero; points per game. |
| `sos` | `NUMERIC` | Yes |  | Strength of schedule: mean opponent SRS over all counted games, equal to SRS - MOV. |
| `sov` | `NUMERIC` | Yes |  | Strength of victory: mean opponent SRS in games won; NULL without wins. |
| `adj_offensive_rating` | `NUMERIC` | Yes |  | Possession-weighted opponent-adjusted offensive rating, centered on league offensive rating. |
| `adj_defensive_rating` | `NUMERIC` | Yes |  | Possession-weighted opponent-adjusted defensive rating, centered on league offensive rating; lower is better. |
| `adj_net_rating` | `NUMERIC` | Yes |  | Possession-weighted opponent-adjusted net rating, centered on zero; higher is better. |
| `home_games` | `INTEGER` | No |  | Local-side games in this scope through this round: Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. |
| `home_wins` | `INTEGER` | No |  | Local-side games in this scope through this round: Games won in this row's scope; source player misc values follow the API. |
| `home_mov` | `NUMERIC` | Yes |  | Local-side games in this scope through this round: (points_for - points_against) / games_played, mean margin in points per game. |
| `home_offensive_rating` | `NUMERIC` | Yes |  | Local-side games in this scope through this round: 100 * points_for / estimated possessions, points scored per 100 possessions. |
| `home_defensive_rating` | `NUMERIC` | Yes |  | Local-side games in this scope through this round: 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. |
| `home_net_rating` | `NUMERIC` | Yes |  | Local-side games in this scope through this round: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. |
| `home_pace` | `NUMERIC` | Yes |  | Local-side games in this scope through this round: 40 * estimated possessions / game_minutes, possessions per regulation-length team game. |
| `away_games` | `INTEGER` | No |  | Road-side games in this scope through this round: Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. |
| `away_wins` | `INTEGER` | No |  | Road-side games in this scope through this round: Games won in this row's scope; source player misc values follow the API. |
| `away_mov` | `NUMERIC` | Yes |  | Road-side games in this scope through this round: (points_for - points_against) / games_played, mean margin in points per game. |
| `away_offensive_rating` | `NUMERIC` | Yes |  | Road-side games in this scope through this round: 100 * points_for / estimated possessions, points scored per 100 possessions. |
| `away_defensive_rating` | `NUMERIC` | Yes |  | Road-side games in this scope through this round: 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. |
| `away_net_rating` | `NUMERIC` | Yes |  | Road-side games in this scope through this round: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. |
| `away_pace` | `NUMERIC` | Yes |  | Road-side games in this scope through this round: 40 * estimated possessions / game_minutes, possessions per regulation-length team game. |
| `last5_games` | `INTEGER` | No |  | Last up to five counted games in this scope: Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. |
| `last5_wins` | `INTEGER` | No |  | Last up to five counted games in this scope: Games won in this row's scope; source player misc values follow the API. |
| `last5_mov` | `NUMERIC` | Yes |  | Last up to five counted games in this scope: (points_for - points_against) / games_played, mean margin in points per game. |
| `last5_offensive_rating` | `NUMERIC` | Yes |  | Last up to five counted games in this scope: 100 * points_for / estimated possessions, points scored per 100 possessions. |
| `last5_defensive_rating` | `NUMERIC` | Yes |  | Last up to five counted games in this scope: 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. |
| `last5_net_rating` | `NUMERIC` | Yes |  | Last up to five counted games in this scope: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. |
| `last5_pace` | `NUMERIC` | Yes |  | Last up to five counted games in this scope: 40 * estimated possessions / game_minutes, possessions per regulation-length team game. |
| `last10_games` | `INTEGER` | No |  | Last up to ten counted games in this scope: Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. |
| `last10_wins` | `INTEGER` | No |  | Last up to ten counted games in this scope: Games won in this row's scope; source player misc values follow the API. |
| `last10_mov` | `NUMERIC` | Yes |  | Last up to ten counted games in this scope: (points_for - points_against) / games_played, mean margin in points per game. |
| `last10_offensive_rating` | `NUMERIC` | Yes |  | Last up to ten counted games in this scope: 100 * points_for / estimated possessions, points scored per 100 possessions. |
| `last10_defensive_rating` | `NUMERIC` | Yes |  | Last up to ten counted games in this scope: 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. |
| `last10_net_rating` | `NUMERIC` | Yes |  | Last up to ten counted games in this scope: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. |
| `last10_pace` | `NUMERIC` | Yes |  | Last up to ten counted games in this scope: 40 * estimated possessions / game_minutes, possessions per regulation-length team game. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_team_round_stats

**Purpose:** Cumulative team totals, possession efficiency and expected wins.

**Grain:** one club-scope-round snapshot. **Columns:** 49.

**Primary key:** `competition_code`, `season_code`, `scope`, `round_number`, `club_code`.

**Definition / implementation:** [gold_etl/team_rounds.py](../gold_etl/team_rounds.py).

**Usage and limitations:** Use the final round within the selected scope for season totals. Idle rounds carry forward. Rates use cumulative totals, not means of game rates. Includes only played games with complete box scores for both sides.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `scope` | `TEXT` | No | PK | Aggregation scope: all, one phase, or PS (PI + PO + FF). RAPM supports all only. |
| `round_number` | `INTEGER` | No | PK | Source game/standings round number; cumulative snapshots include games through this round. |
| `club_code` | `TEXT` | No | PK | Club identifier, text; join season profiles on competition, season and club. |
| `club_name` | `TEXT` | Yes |  | Club display name for this season or row. |
| `games_played` | `INTEGER` | No |  | Games/appearances in the selected row scope; see table notes for counted games and series fixture counts. |
| `wins` | `INTEGER` | No |  | Games won in this row's scope; source player misc values follow the API. |
| `losses` | `INTEGER` | No |  | Games lost in this row's scope; source player misc values follow the API. |
| `points_for` | `NUMERIC` | Yes |  | Points scored by this club or lineup in the row's game, stint or cumulative scope. |
| `points_against` | `NUMERIC` | Yes |  | Points conceded by this club or lineup in the same sample. |
| `own_field_goals_made` | `NUMERIC` | Yes |  | Team total: Successful two- and three-point field goals (FGM), excluding free throws. |
| `own_field_goals_attempted` | `NUMERIC` | Yes |  | Team total: All two- and three-point field-goal attempts (FGA), including blocked attempts. |
| `own_three_pointers_made` | `NUMERIC` | Yes |  | Team total: Successful three-point field goals (3PM). |
| `own_free_throws_made` | `NUMERIC` | Yes |  | Team total: Successful free throws (FTM). |
| `own_free_throws_attempted` | `NUMERIC` | Yes |  | Team total: Free-throw attempts (FTA), including makes. |
| `own_offensive_rebounds` | `NUMERIC` | Yes |  | Team total: Rebounds recovered after the player's or club's missed shot (OREB). |
| `own_defensive_rebounds` | `NUMERIC` | Yes |  | Team total: Rebounds recovered after the opponent's missed shot (DREB). |
| `own_turnovers` | `NUMERIC` | Yes |  | Team total: Lost possessions charged to the player or team (TOV). |
| `own_assists` | `NUMERIC` | Yes |  | Team total: Official credited assists (AST), including EuroLeague assists that lead to free throws. |
| `opp_field_goals_made` | `NUMERIC` | Yes |  | Opponent total: Successful two- and three-point field goals (FGM), excluding free throws. |
| `opp_field_goals_attempted` | `NUMERIC` | Yes |  | Opponent total: All two- and three-point field-goal attempts (FGA), including blocked attempts. |
| `opp_three_pointers_made` | `NUMERIC` | Yes |  | Opponent total: Successful three-point field goals (3PM). |
| `opp_free_throws_made` | `NUMERIC` | Yes |  | Opponent total: Successful free throws (FTM). |
| `opp_free_throws_attempted` | `NUMERIC` | Yes |  | Opponent total: Free-throw attempts (FTA), including makes. |
| `opp_offensive_rebounds` | `NUMERIC` | Yes |  | Opponent total: Rebounds recovered after the player's or club's missed shot (OREB). |
| `opp_defensive_rebounds` | `NUMERIC` | Yes |  | Opponent total: Rebounds recovered after the opponent's missed shot (DREB). |
| `opp_turnovers` | `NUMERIC` | Yes |  | Opponent total: Lost possessions charged to the player or team (TOV). |
| `opp_assists` | `NUMERIC` | Yes |  | Opponent total: Official credited assists (AST), including EuroLeague assists that lead to free throws. |
| `game_minutes` | `NUMERIC` | Yes |  | Game-clock minutes, 40 plus 5 per overtime; cumulative sum in team-round rows, not player-minutes. |
| `possessions` | `NUMERIC` | Yes |  | In calculated team rows: mean of the two clubs' possession estimates, summed for cumulative rows. API player feed possessions has a separate source definition. |
| `mov` | `NUMERIC` | Yes |  | (points_for - points_against) / games_played, mean margin in points per game. |
| `pythagorean_exponent` | `NUMERIC` | Yes |  | Fixed exponent 10.25 used in this warehouse's expected-win model. |
| `pythagorean_win_pct` | `NUMERIC` | Yes |  | PF^10.25 / (PF^10.25 + PA^10.25), expected win fraction from cumulative scores. |
| `pythagorean_wins` | `NUMERIC` | Yes |  | pythagorean_win_pct * games_played, expected wins. |
| `pace` | `NUMERIC` | Yes |  | 40 * estimated possessions / game_minutes, possessions per regulation-length team game. |
| `offensive_rating` | `NUMERIC` | Yes |  | 100 * points_for / estimated possessions, points scored per 100 possessions. |
| `defensive_rating` | `NUMERIC` | Yes |  | 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. |
| `net_rating` | `NUMERIC` | Yes |  | Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. |
| `efg_pct` | `NUMERIC` | Yes |  | (FGM + 0.5 * 3PM) / FGA, a fraction that can exceed 1. |
| `tov_pct` | `NUMERIC` | Yes |  | TOV / (FGA + 0.44 * FTA + TOV), a fraction. |
| `orb_pct` | `NUMERIC` | Yes |  | Offensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. |
| `drb_pct` | `NUMERIC` | Yes |  | Defensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. |
| `ft_rate` | `NUMERIC` | Yes |  | FTM / FGA, made free throws per field-goal attempt; not FTA / FGA. |
| `opp_efg_pct` | `NUMERIC` | Yes |  | Opponent total: (FGM + 0.5 * 3PM) / FGA, a fraction that can exceed 1. |
| `opp_tov_pct` | `NUMERIC` | Yes |  | Opponent total: TOV / (FGA + 0.44 * FTA + TOV), a fraction. |
| `opp_ft_rate` | `NUMERIC` | Yes |  | Opponent total: FTM / FGA, made free throws per field-goal attempt; not FTA / FGA. |
| `true_shooting_pct` | `NUMERIC` | Yes |  | PTS / (2 * (FGA + 0.44 * FTA)), a fraction that can exceed 1. |
| `assist_ratio` | `NUMERIC` | Yes |  | AST / FGM in calculated team tables; not the API assists_ratio. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_team_round_ratings

**Purpose:** League-relative and opponent-adjusted team strength.

**Grain:** one club-scope-round snapshot. **Columns:** 17.

**Primary key:** `competition_code`, `season_code`, `scope`, `round_number`, `club_code`.

**Definition / implementation:** [gold_etl/team_ratings.py](../gold_etl/team_ratings.py).

**Usage and limitations:** Same key and counted games as app_team_round_stats. Disconnected schedules give NULL SRS/SOS/SOV and adjusted ratings; bipartite schedules also prevent separation of adjusted offense and defense.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `scope` | `TEXT` | No | PK | Aggregation scope: all, one phase, or PS (PI + PO + FF). RAPM supports all only. |
| `round_number` | `INTEGER` | No | PK | Source game/standings round number; cumulative snapshots include games through this round. |
| `club_code` | `TEXT` | No | PK | Club identifier, text; join season profiles on competition, season and club. |
| `connected` | `BOOLEAN` | No |  | True if the played-game graph links every club in this scope-round; governs adjusted-rating availability. |
| `league_offensive_rating` | `NUMERIC` | Yes |  | 100 * league points / league estimated possessions in this scope through this round, both sides counted. |
| `league_pace` | `NUMERIC` | Yes |  | 40 * league estimated possessions / league game-clock minutes, both sides counted. |
| `relative_offensive_rating` | `NUMERIC` | Yes |  | Club offensive_rating minus league_offensive_rating; positive means better offense. |
| `relative_defensive_rating` | `NUMERIC` | Yes |  | Club defensive_rating minus league_offensive_rating; negative means better defense. |
| `relative_pace` | `NUMERIC` | Yes |  | Club pace minus league_pace, possessions per 40 minutes above/below the league. |
| `srs` | `NUMERIC` | Yes |  | Simple Rating System: MOV plus mean opponent SRS, solved with league mean zero; points per game. |
| `sos` | `NUMERIC` | Yes |  | Strength of schedule: mean opponent SRS over all counted games, equal to SRS - MOV. |
| `sov` | `NUMERIC` | Yes |  | Strength of victory: mean opponent SRS in games won; NULL without wins. |
| `adj_offensive_rating` | `NUMERIC` | Yes |  | Possession-weighted opponent-adjusted offensive rating, centered on league offensive rating. |
| `adj_defensive_rating` | `NUMERIC` | Yes |  | Possession-weighted opponent-adjusted defensive rating, centered on league offensive rating; lower is better. |
| `adj_net_rating` | `NUMERIC` | Yes |  | Possession-weighted opponent-adjusted net rating, centered on zero; higher is better. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_team_round_splits

**Purpose:** Home/away and last-5/last-10 team form.

**Grain:** one club-scope-round snapshot. **Columns:** 33.

**Primary key:** `competition_code`, `season_code`, `scope`, `round_number`, `club_code`.

**Definition / implementation:** [gold_etl/team_splits.py](../gold_etl/team_splits.py).

**Usage and limitations:** Windows use counted games within the scope ordered by round_number, game_code. Early windows can have fewer than 5/10 games. Neutral games retain local/road designation.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `scope` | `TEXT` | No | PK | Aggregation scope: all, one phase, or PS (PI + PO + FF). RAPM supports all only. |
| `round_number` | `INTEGER` | No | PK | Source game/standings round number; cumulative snapshots include games through this round. |
| `club_code` | `TEXT` | No | PK | Club identifier, text; join season profiles on competition, season and club. |
| `home_games` | `INTEGER` | No |  | Local-side games in this scope through this round: Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. |
| `home_wins` | `INTEGER` | No |  | Local-side games in this scope through this round: Games won in this row's scope; source player misc values follow the API. |
| `home_mov` | `NUMERIC` | Yes |  | Local-side games in this scope through this round: (points_for - points_against) / games_played, mean margin in points per game. |
| `home_offensive_rating` | `NUMERIC` | Yes |  | Local-side games in this scope through this round: 100 * points_for / estimated possessions, points scored per 100 possessions. |
| `home_defensive_rating` | `NUMERIC` | Yes |  | Local-side games in this scope through this round: 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. |
| `home_net_rating` | `NUMERIC` | Yes |  | Local-side games in this scope through this round: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. |
| `home_pace` | `NUMERIC` | Yes |  | Local-side games in this scope through this round: 40 * estimated possessions / game_minutes, possessions per regulation-length team game. |
| `away_games` | `INTEGER` | No |  | Road-side games in this scope through this round: Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. |
| `away_wins` | `INTEGER` | No |  | Road-side games in this scope through this round: Games won in this row's scope; source player misc values follow the API. |
| `away_mov` | `NUMERIC` | Yes |  | Road-side games in this scope through this round: (points_for - points_against) / games_played, mean margin in points per game. |
| `away_offensive_rating` | `NUMERIC` | Yes |  | Road-side games in this scope through this round: 100 * points_for / estimated possessions, points scored per 100 possessions. |
| `away_defensive_rating` | `NUMERIC` | Yes |  | Road-side games in this scope through this round: 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. |
| `away_net_rating` | `NUMERIC` | Yes |  | Road-side games in this scope through this round: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. |
| `away_pace` | `NUMERIC` | Yes |  | Road-side games in this scope through this round: 40 * estimated possessions / game_minutes, possessions per regulation-length team game. |
| `last5_games` | `INTEGER` | No |  | Last up to five counted games in this scope: Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. |
| `last5_wins` | `INTEGER` | No |  | Last up to five counted games in this scope: Games won in this row's scope; source player misc values follow the API. |
| `last5_mov` | `NUMERIC` | Yes |  | Last up to five counted games in this scope: (points_for - points_against) / games_played, mean margin in points per game. |
| `last5_offensive_rating` | `NUMERIC` | Yes |  | Last up to five counted games in this scope: 100 * points_for / estimated possessions, points scored per 100 possessions. |
| `last5_defensive_rating` | `NUMERIC` | Yes |  | Last up to five counted games in this scope: 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. |
| `last5_net_rating` | `NUMERIC` | Yes |  | Last up to five counted games in this scope: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. |
| `last5_pace` | `NUMERIC` | Yes |  | Last up to five counted games in this scope: 40 * estimated possessions / game_minutes, possessions per regulation-length team game. |
| `last10_games` | `INTEGER` | No |  | Last up to ten counted games in this scope: Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. |
| `last10_wins` | `INTEGER` | No |  | Last up to ten counted games in this scope: Games won in this row's scope; source player misc values follow the API. |
| `last10_mov` | `NUMERIC` | Yes |  | Last up to ten counted games in this scope: (points_for - points_against) / games_played, mean margin in points per game. |
| `last10_offensive_rating` | `NUMERIC` | Yes |  | Last up to ten counted games in this scope: 100 * points_for / estimated possessions, points scored per 100 possessions. |
| `last10_defensive_rating` | `NUMERIC` | Yes |  | Last up to ten counted games in this scope: 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. |
| `last10_net_rating` | `NUMERIC` | Yes |  | Last up to ten counted games in this scope: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. |
| `last10_pace` | `NUMERIC` | Yes |  | Last up to ten counted games in this scope: 40 * estimated possessions / game_minutes, possessions per regulation-length team game. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_team_pbp_stats

**Purpose:** Season-scope possessions, score flow, clutch and shot-split summaries.

**Grain:** one club-scope per season. **Columns:** 29.

**Primary key:** `competition_code`, `season_code`, `scope`, `club_code`.

**Definition / implementation:** [gold_etl/team_pbp.py](../gold_etl/team_pbp.py).

**Usage and limitations:** E2007+ subject to event coverage. games, timed_games, flagged_games and clutch_games have different meanings. Missing sources can leave some measures NULL. Do not divide every total by games.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `scope` | `TEXT` | No | PK | Aggregation scope: all, one phase, or PS (PI + PO + FF). RAPM supports all only. |
| `club_code` | `TEXT` | No | PK | Club identifier, text; join season profiles on competition, season and club. |
| `games` | `INTEGER` | Yes |  | Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. |
| `counted_possessions` | `NUMERIC` | Yes |  | Team possessions closed by the play-by-play state machine; summed in season-scope aggregates. |
| `estimated_possessions` | `NUMERIC` | Yes |  | Shared box-score possessions estimate copied for comparison; summed in season-scope aggregates. |
| `possession_seconds` | `NUMERIC` | Yes |  | Sum of measurable possession durations in seconds, not necessarily all game-clock seconds. |
| `timed_games` | `INTEGER` | Yes |  | Games with non-NULL time-leading data; denominator for time-based summaries. |
| `time_leading_seconds` | `NUMERIC` | Yes |  | Game-clock seconds the team led; summed over timed games in aggregate rows. |
| `time_trailing_seconds` | `NUMERIC` | Yes |  | Game-clock seconds the team trailed; summed over timed games in aggregate rows. |
| `time_tied_seconds` | `NUMERIC` | Yes |  | Game-clock seconds the score was tied, including 0-0; summed over timed games in aggregates. |
| `runs_6_plus` | `INTEGER` | Yes |  | Number of unanswered scoring runs of at least six points; summed across games in aggregates. |
| `clutch_games` | `INTEGER` | Yes |  | Timed games with positive clutch_seconds, not all close final scores. |
| `clutch_seconds` | `NUMERIC` | Yes |  | Seconds from elapsed second 2100 through game end (including overtime) with margin at most five points. |
| `clutch_points_for` | `NUMERIC` | Yes |  | Team points scored from second 2100 onward when the pre-scoring margin is at most five points. |
| `clutch_points_against` | `NUMERIC` | Yes |  | Opponent points scored from second 2100 onward when the pre-scoring margin is at most five points. |
| `flagged_games` | `INTEGER` | Yes |  | Games with recorded shot-split flags (non-NULL fast_break_points), denominator for flagged scoring coverage. |
| `fast_break_points` | `NUMERIC` | Yes |  | Sum of positive shot points tagged fastbreak, including any flagged made free throws; NULL when flags are unrecorded. |
| `second_chance_points` | `NUMERIC` | Yes |  | Sum of positive shot points tagged second_chance, including any flagged made free throws; NULL when flags are unrecorded. |
| `points_off_turnover_points` | `NUMERIC` | Yes |  | Sum of positive shot points tagged points_off_turnover, including any flagged made free throws; distinct from the Boolean shot flag. |
| `field_goals_made` | `INTEGER` | Yes |  | Successful two- and three-point field goals (FGM), excluding free throws. |
| `assisted_field_goals` | `INTEGER` | Yes |  | min(team AS event count, team made-field-goal event count); summed in aggregates, not shot-by-shot matching. |
| `avg_possession_seconds` | `NUMERIC` | Yes |  | Game: timed seconds / timed possession count. Team aggregate: game averages weighted by counted possessions. |
| `lead_changes_per_game` | `NUMERIC` | Yes |  | Mean of available per-game lead_changes values. |
| `ties_per_game` | `NUMERIC` | Yes |  | Mean of available per-game ties values. |
| `largest_lead` | `NUMERIC` | Yes |  | Largest positive team margin in a game; maximum across games in season-scope aggregates. |
| `longest_run` | `NUMERIC` | Yes |  | Most unanswered points scored in a game; maximum across games in season-scope aggregates. |
| `assisted_fg_pct` | `NUMERIC` | Yes |  | assisted_field_goals / field_goals_made, a fraction. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_team_shot_zone_stats

**Purpose:** Season-scope shot map aggregates and shot mix.

**Grain:** one club-zone-scope per season. **Columns:** 10.

**Primary key:** `competition_code`, `season_code`, `scope`, `club_code`, `zone`.

**Definition / implementation:** [gold_etl/team_shot_zones.py](../gold_etl/team_shot_zones.py).

**Usage and limitations:** Only zones with attempts have rows. fg_pct and attempt_share are fractions. E2007+ subject to shot coverage; no synthetic zero rows for absent zones.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `scope` | `TEXT` | No | PK | Aggregation scope: all, one phase, or PS (PI + PO + FF). RAPM supports all only. |
| `club_code` | `TEXT` | No | PK | Club identifier, text; join season profiles on competition, season and club. |
| `zone` | `TEXT` | No | PK | Source shot-zone label, preserved without a warehouse court taxonomy. |
| `attempts` | `INTEGER` | Yes |  | Field-goal attempts in this source zone, including makes. |
| `made` | `INTEGER` | Yes |  | Successful field goals in this source zone. |
| `points` | `INTEGER` | Yes |  | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |
| `fg_pct` | `NUMERIC` | Yes |  | made / attempts in this zone, a fraction. |
| `attempt_share` | `NUMERIC` | Yes |  | Zone attempts / all zone-tagged field-goal attempts for the club in the scope, a fraction. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_player_round_stats

**Purpose:** Calculated cumulative player totals, rates, per-100 stats, Game Score and PIE.

**Grain:** one player-scope-round snapshot. **Columns:** 46.

**Primary key:** `competition_code`, `season_code`, `scope`, `round_number`, `person_key`.

**Definition / implementation:** [gold_etl/player_rounds.py](../gold_etl/player_rounds.py).

**Usage and limitations:** Includes appearances with seconds_played > 0; carries forward idle rounds. Transfers keep one blended row with the latest club_code. Rates remain box-score estimates even when the per-game rate uses on-court events.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `scope` | `TEXT` | No | PK | Aggregation scope: all, one phase, or PS (PI + PO + FF). RAPM supports all only. |
| `round_number` | `INTEGER` | No | PK | Source game/standings round number; cumulative snapshots include games through this round. |
| `person_key` | `TEXT` | No | PK | Season person identity used by box scores; bridge to career person_code through app_people. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `player_name` | `TEXT` | Yes |  | Player display name; cumulative round rows use the latest appearance's name. |
| `games_played` | `INTEGER` | No |  | Games/appearances in the selected row scope; see table notes for counted games and series fixture counts. |
| `games_started` | `INTEGER` | No |  | Games in which the player started; cumulative appearance count or retained feed count. |
| `seconds_played` | `NUMERIC` | Yes |  | Official playing time in seconds; player seconds or aggregate team player-seconds in box scores. |
| `points` | `NUMERIC` | Yes |  | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |
| `field_goals_made` | `NUMERIC` | Yes |  | Successful two- and three-point field goals (FGM), excluding free throws. |
| `field_goals_attempted` | `NUMERIC` | Yes |  | All two- and three-point field-goal attempts (FGA), including blocked attempts. |
| `three_pointers_made` | `NUMERIC` | Yes |  | Successful three-point field goals (3PM). |
| `three_pointers_attempted` | `NUMERIC` | Yes |  | Three-point field-goal attempts (3PA), including makes. |
| `free_throws_made` | `NUMERIC` | Yes |  | Successful free throws (FTM). |
| `free_throws_attempted` | `NUMERIC` | Yes |  | Free-throw attempts (FTA), including makes. |
| `offensive_rebounds` | `NUMERIC` | Yes |  | Rebounds recovered after the player's or club's missed shot (OREB). |
| `defensive_rebounds` | `NUMERIC` | Yes |  | Rebounds recovered after the opponent's missed shot (DREB). |
| `total_rebounds` | `NUMERIC` | Yes |  | Offensive plus defensive rebounds (REB); official team totals can include team rebounds. |
| `assists` | `NUMERIC` | Yes |  | Official credited assists (AST), including EuroLeague assists that lead to free throws. |
| `steals` | `NUMERIC` | Yes |  | Official credited steals (STL). |
| `turnovers` | `NUMERIC` | Yes |  | Lost possessions charged to the player or team (TOV). |
| `blocks` | `NUMERIC` | Yes |  | Opponent field-goal attempts blocked by the player or team (BLK). |
| `fouls_committed` | `NUMERIC` | Yes |  | Personal fouls charged to the player or team (PF). |
| `pir` | `NUMERIC` | Yes |  | Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. |
| `ts_pct` | `NUMERIC` | Yes |  | Calculated cumulative true shooting: PTS / (2 * (FGA + 0.44 * FTA)), a fraction. |
| `efg_pct` | `NUMERIC` | Yes |  | (FGM + 0.5 * 3PM) / FGA, a fraction that can exceed 1. |
| `usg_pct` | `NUMERIC` | Yes |  | Cumulative box-score usage estimate, ratio of summed usage contributions; not an average of game usage_pct. |
| `ast_pct` | `NUMERIC` | Yes |  | Cumulative AST / sum(time share * team FGM - player FGM), a fraction; no free-throw-trip adjustment. |
| `orb_pct` | `NUMERIC` | Yes |  | Offensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. |
| `drb_pct` | `NUMERIC` | Yes |  | Defensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. |
| `trb_pct` | `NUMERIC` | Yes |  | Total rebound share, a fraction; see glossary for player context and denominators. |
| `stl_pct` | `NUMERIC` | Yes |  | Cumulative STL / sum(time share * estimated game possessions), a fraction. |
| `blk_pct` | `NUMERIC` | Yes |  | Cumulative BLK / sum(time share * opponent 2PA), a fraction. |
| `tov_pct` | `NUMERIC` | Yes |  | TOV / (FGA + 0.44 * FTA + TOV), a fraction. |
| `possessions_played` | `NUMERIC` | Yes |  | Estimated on-court possessions: sum(player seconds / game seconds * estimated game possessions). |
| `points_per_100` | `NUMERIC` | Yes |  | 100 * cumulative points / possessions_played; rate per 100 estimated on-court possessions. |
| `rebounds_per_100` | `NUMERIC` | Yes |  | 100 * cumulative total_rebounds / possessions_played; rate per 100 estimated on-court possessions. |
| `assists_per_100` | `NUMERIC` | Yes |  | 100 * cumulative assists / possessions_played; rate per 100 estimated on-court possessions. |
| `steals_per_100` | `NUMERIC` | Yes |  | 100 * cumulative steals / possessions_played; rate per 100 estimated on-court possessions. |
| `blocks_per_100` | `NUMERIC` | Yes |  | 100 * cumulative blocks / possessions_played; rate per 100 estimated on-court possessions. |
| `turnovers_per_100` | `NUMERIC` | Yes |  | 100 * cumulative turnovers / possessions_played; rate per 100 estimated on-court possessions. |
| `game_score_total` | `NUMERIC` | Yes |  | Sum of Game Score over counted player appearances. |
| `game_score_average` | `NUMERIC` | Yes |  | game_score_total / games_played, mean Game Score per appearance. |
| `pie` | `NUMERIC` | Yes |  | Player Impact Estimate: sum(player PIE numerator) / sum(both teams' PIE numerators in those games), a fraction. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_player_round_ratings

**Purpose:** Cumulative Hollinger PER for player comparisons.

**Grain:** one player-scope-round snapshot. **Columns:** 12.

**Primary key:** `competition_code`, `season_code`, `scope`, `round_number`, `person_key`.

**Definition / implementation:** [gold_etl/player_ratings.py](../gold_etl/player_ratings.py).

**Usage and limitations:** Same player-round key as app_player_round_stats. Seconds-weighted league mean PER is 15. No minimum-minutes cutoff; small samples can be extreme. Season PER is recomputed from cumulative context, not averaged game PER.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `scope` | `TEXT` | No | PK | Aggregation scope: all, one phase, or PS (PI + PO + FF). RAPM supports all only. |
| `round_number` | `INTEGER` | No | PK | Source game/standings round number; cumulative snapshots include games through this round. |
| `person_key` | `TEXT` | No | PK | Season person identity used by box scores; bridge to career person_code through app_people. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `player_name` | `TEXT` | Yes |  | Player display name; cumulative round rows use the latest appearance's name. |
| `games_played` | `INTEGER` | No |  | Games/appearances in the selected row scope; see table notes for counted games and series fixture counts. |
| `seconds_played` | `NUMERIC` | Yes |  | Official playing time in seconds; player seconds or aggregate team player-seconds in box scores. |
| `uper` | `NUMERIC` | Yes |  | Hollinger unadjusted PER per minute, using cumulative player/team totals and scope-round league constants. |
| `aper` | `NUMERIC` | Yes |  | Pace-adjusted uPER: uper * league pace / player's team-context pace. |
| `per` | `NUMERIC` | Yes |  | Cumulative aper normalized so the seconds-weighted league mean in this scope-round is 15. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_player_round_win_shares

**Purpose:** Offensive, defensive and total estimated win contributions.

**Grain:** one player-scope-round snapshot. **Columns:** 13.

**Primary key:** `competition_code`, `season_code`, `scope`, `round_number`, `person_key`.

**Definition / implementation:** [gold_etl/player_win_shares.py](../gold_etl/player_win_shares.py).

**Usage and limitations:** Same player-round key as app_player_round_stats. Per-40 rate uses 40-minute EuroLeague regulation time. Values can be negative; this is a model estimate, not a literal allocation of team wins.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `scope` | `TEXT` | No | PK | Aggregation scope: all, one phase, or PS (PI + PO + FF). RAPM supports all only. |
| `round_number` | `INTEGER` | No | PK | Source game/standings round number; cumulative snapshots include games through this round. |
| `person_key` | `TEXT` | No | PK | Season person identity used by box scores; bridge to career person_code through app_people. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `player_name` | `TEXT` | Yes |  | Player display name; cumulative round rows use the latest appearance's name. |
| `games_played` | `INTEGER` | No |  | Games/appearances in the selected row scope; see table notes for counted games and series fixture counts. |
| `seconds_played` | `NUMERIC` | Yes |  | Official playing time in seconds; player seconds or aggregate team player-seconds in box scores. |
| `off_win_shares` | `NUMERIC` | Yes |  | Offensive estimated win contribution from points produced minus marginal offensive cost; see glossary. |
| `def_win_shares` | `NUMERIC` | Yes |  | Defensive estimated win contribution from stops and individual defensive rating; see glossary. |
| `win_shares` | `NUMERIC` | Yes |  | off_win_shares + def_win_shares; estimated wins, can be negative. |
| `win_shares_per_40` | `NUMERIC` | Yes |  | win_shares * 40 / (seconds_played / 60), estimated wins per 40 player-minutes. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_player_on_off

**Purpose:** Team performance while a player is on or off court.

**Grain:** one player-club-scope per season. **Columns:** 26.

**Primary key:** `competition_code`, `season_code`, `scope`, `club_code`, `person_key`.

**Definition / implementation:** [gold_etl/player_on_off.py](../gold_etl/player_on_off.py).

**Usage and limitations:** E2007+ from complete five-on-five stints. Transfers have separate club rows. Off includes team games the player missed. Positive drtg_diff means more points allowed and worse defense. Not adjusted for teammates or opponents.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `scope` | `TEXT` | No | PK | Aggregation scope: all, one phase, or PS (PI + PO + FF). RAPM supports all only. |
| `club_code` | `TEXT` | No | PK | Club identifier, text; join season profiles on competition, season and club. |
| `person_key` | `TEXT` | No | PK | Season person identity used by box scores; bridge to career person_code through app_people. |
| `player_name` | `TEXT` | Yes |  | Player display name; cumulative round rows use the latest appearance's name. |
| `games` | `INTEGER` | No |  | Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. |
| `on_seconds` | `INTEGER` | Yes |  | Team stints with this player on court: Elapsed on-court time in complete stored stints, summed over the row's sample. |
| `on_possessions_for` | `INTEGER` | Yes |  | Team stints with this player on court: Team counted possessions closed during these stints. |
| `on_possessions_against` | `INTEGER` | Yes |  | Team stints with this player on court: Opponent counted possessions closed during these stints. |
| `on_points_for` | `INTEGER` | Yes |  | Team stints with this player on court: Points scored by this club or lineup in the row's game, stint or cumulative scope. |
| `on_points_against` | `INTEGER` | Yes |  | Team stints with this player on court: Points conceded by this club or lineup in the same sample. |
| `off_seconds` | `INTEGER` | Yes |  | Other team stints in the scope, including games missed: Elapsed on-court time in complete stored stints, summed over the row's sample. |
| `off_possessions_for` | `INTEGER` | Yes |  | Other team stints in the scope, including games missed: Team counted possessions closed during these stints. |
| `off_possessions_against` | `INTEGER` | Yes |  | Other team stints in the scope, including games missed: Opponent counted possessions closed during these stints. |
| `off_points_for` | `INTEGER` | Yes |  | Other team stints in the scope, including games missed: Points scored by this club or lineup in the row's game, stint or cumulative scope. |
| `off_points_against` | `INTEGER` | Yes |  | Other team stints in the scope, including games missed: Points conceded by this club or lineup in the same sample. |
| `on_ortg` | `NUMERIC` | Yes |  | Team stints with this player on court: 100 * points_for / possessions_for from counted stints, offensive points per 100. |
| `on_drtg` | `NUMERIC` | Yes |  | Team stints with this player on court: 100 * points_against / possessions_against from counted stints, defensive points allowed per 100. |
| `on_net_rating` | `NUMERIC` | Yes |  | Team stints with this player on court: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. |
| `off_ortg` | `NUMERIC` | Yes |  | Other team stints in the scope, including games missed: 100 * points_for / possessions_for from counted stints, offensive points per 100. |
| `off_drtg` | `NUMERIC` | Yes |  | Other team stints in the scope, including games missed: 100 * points_against / possessions_against from counted stints, defensive points allowed per 100. |
| `off_net_rating` | `NUMERIC` | Yes |  | Other team stints in the scope, including games missed: Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. |
| `ortg_diff` | `NUMERIC` | Yes |  | on_ortg - off_ortg; positive means the team's offense was better with the player on court. |
| `drtg_diff` | `NUMERIC` | Yes |  | on_drtg - off_drtg; positive means the team's defense allowed more with the player on court. |
| `net_rating_diff` | `NUMERIC` | Yes |  | on_net_rating - off_net_rating, unadjusted team on/off difference per 100 possessions. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_lineup_ratings

**Purpose:** Ratings for pairs, triples and five-man units.

**Grain:** one lineup-size-lineup-club-scope per season. **Columns:** 16.

**Primary key:** `competition_code`, `season_code`, `scope`, `club_code`, `lineup_size`, `lineup`.

**Definition / implementation:** [gold_etl/lineup_ratings.py](../gold_etl/lineup_ratings.py).

**Usage and limitations:** E2007+; lineup sizes are 2, 3 and 5 only. Sorted comma-separated person_key values identify a unit. Pair/triple rows overlap: summing them double counts stints. Retain sample seconds and possessions when ranking.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `scope` | `TEXT` | No | PK | Aggregation scope: all, one phase, or PS (PI + PO + FF). RAPM supports all only. |
| `club_code` | `TEXT` | No | PK | Club identifier, text; join season profiles on competition, season and club. |
| `lineup_size` | `INTEGER` | No | PK | Number of players in the combination: 2, 3 or 5. |
| `lineup` | `TEXT` | No | PK | Sorted comma-separated person_key values identifying this pair, triple or five. |
| `lineup_names` | `TEXT` | Yes |  | Display names in lineup order separated by semicolons; missing names fall back to keys. |
| `games` | `INTEGER` | No |  | Count of contributing games, with a table-specific denominator; in postseason_series this is a JSON fixture list. |
| `seconds` | `INTEGER` | Yes |  | Elapsed on-court time in complete stored stints, summed over the row's sample. |
| `possessions_for` | `INTEGER` | Yes |  | Team counted possessions closed during these stints. |
| `possessions_against` | `INTEGER` | Yes |  | Opponent counted possessions closed during these stints. |
| `points_for` | `INTEGER` | Yes |  | Points scored by this club or lineup in the row's game, stint or cumulative scope. |
| `points_against` | `INTEGER` | Yes |  | Points conceded by this club or lineup in the same sample. |
| `ortg` | `NUMERIC` | Yes |  | 100 * points_for / possessions_for from counted stints, offensive points per 100. |
| `drtg` | `NUMERIC` | Yes |  | 100 * points_against / possessions_against from counted stints, defensive points allowed per 100. |
| `net_rating` | `NUMERIC` | Yes |  | Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_player_rapm

**Purpose:** Regularized adjusted plus-minus from lineup stints.

**Grain:** one player per season with scope = all. **Columns:** 12.

**Primary key:** `competition_code`, `season_code`, `scope`, `person_key`.

**Definition / implementation:** [gold_etl/rapm.py](../gold_etl/rapm.py).

**Usage and limitations:** E2007+; one blended row across clubs. Positive offense and positive defense both mean better performance. No phase or round snapshots. Penalty is fitted per season; compare with sample possessions and seconds.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `scope` | `TEXT` | No | PK | Aggregation scope: all, one phase, or PS (PI + PO + FF). RAPM supports all only. |
| `person_key` | `TEXT` | No | PK | Season person identity used by box scores; bridge to career person_code through app_people. |
| `player_name` | `TEXT` | Yes |  | Player display name; cumulative round rows use the latest appearance's name. |
| `seconds` | `INTEGER` | Yes |  | Elapsed on-court time in complete stored stints, summed over the row's sample. |
| `possessions_offense` | `INTEGER` | Yes |  | Counted offensive possessions contributing to this player's RAPM fit. |
| `possessions_defense` | `INTEGER` | Yes |  | Counted defensive possessions contributing to this player's RAPM fit. |
| `penalty` | `NUMERIC` | Yes |  | Ridge penalty selected by whole-game cross-validation; same value for all players in a season. |
| `offense` | `NUMERIC` | Yes |  | Offensive RAPM coefficient in points per 100 possessions above the fitted baseline; positive is better. |
| `defense` | `NUMERIC` | Yes |  | Defensive RAPM coefficient in points prevented per 100 possessions; positive is better. |
| `rapm` | `NUMERIC` | Yes |  | offense + defense, regularized adjusted plus-minus in points per 100 possessions. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_play_by_play

**Purpose:** Event timeline for game charts and event-level analysis.

**Grain:** one event ordinal within a game period. **Columns:** 21.

**Primary key:** `competition_code`, `season_code`, `game_code`, `period`, `event_ordinal`.

**Definition / implementation:** [postgres_etl/flat_schema.py](../postgres_etl/flat_schema.py).

**Usage and limitations:** Order by explicit period rank, overtime number from minute, then event_ordinal. Alphabetical period order and play_number are unsuitable. person_code is the resolved box-score person_key; player_code is the raw live identity. Available from E2007 where the feed exists.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `period` | `TEXT` | No | PK | Source period label: FirstQuarter, SecondQuarter, ThirdQuarter, ForthQuarter or ExtraTime. Sort using period rank and overtime number from minute, not alphabetically. |
| `event_ordinal` | `INTEGER` | No | PK | Event order within the period; use with period for chronology. |
| `play_number` | `INTEGER` | Yes |  | Source event/shot link number; it is not a reliable chronological sort key. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `player_code` | `TEXT` | Yes |  | Raw live-feed player identifier; use resolved person_code for joins. |
| `person_code` | `TEXT` | Yes |  | Person code; career identity in profiles, resolved box-score person_key in live-event tables. |
| `person_code_method` | `TEXT` | Yes |  | Recorded resolution method used to map the live player identity to a box-score person. |
| `play_type` | `TEXT` | Yes |  | Live action code, for example AS, ST, TO, O, D, FTM, 2FGM or 3FGM. |
| `event_type` | `INTEGER` | Yes |  | Raw live numeric event type. |
| `player_name` | `TEXT` | Yes |  | Player display name; cumulative round rows use the latest appearance's name. |
| `team_name` | `TEXT` | Yes |  | Team label from the live event feed. |
| `jersey_number` | `TEXT` | Yes |  | Source jersey number stored as text; retain leading zeroes and special values. |
| `minute` | `INTEGER` | Yes |  | Source live minute marker; interpret with the period and clock. |
| `marker_time` | `TEXT` | Yes |  | Source time remaining in the period, such as 03:24. |
| `points_a` | `INTEGER` | Yes |  | Live running score of source side A (local). |
| `points_b` | `INTEGER` | Yes |  | Live running score of source side B (road). |
| `comment` | `TEXT` | Yes |  | Source event comment text. |
| `play_info` | `TEXT` | Yes |  | Source event description text. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_shots

**Purpose:** Individual shot events, coordinates and shot flags.

**Grain:** one shot ordinal per game. **Columns:** 24.

**Primary key:** `competition_code`, `season_code`, `game_code`, `shot_ordinal`.

**Definition / implementation:** [postgres_etl/flat_schema.py](../postgres_etl/flat_schema.py).

**Usage and limitations:** Use resolved person_code to reach app_people.person_key within the season. Coordinates and zone codes retain feed conventions; this warehouse does not define a court projection. Feed availability starts in E2007.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `shot_ordinal` | `INTEGER` | No | PK | Source shot row order within the game. |
| `play_number` | `INTEGER` | Yes |  | Source event/shot link number; it is not a reliable chronological sort key. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `player_code` | `TEXT` | Yes |  | Raw live-feed player identifier; use resolved person_code for joins. |
| `person_code` | `TEXT` | Yes |  | Person code; career identity in profiles, resolved box-score person_key in live-event tables. |
| `person_code_method` | `TEXT` | Yes |  | Recorded resolution method used to map the live player identity to a box-score person. |
| `player_name` | `TEXT` | Yes |  | Player display name; cumulative round rows use the latest appearance's name. |
| `action_code` | `TEXT` | Yes |  | Source shot action code; distinguishes made/missed field goals and other shot actions. |
| `action` | `TEXT` | Yes |  | Source shot action label. |
| `points` | `INTEGER` | Yes |  | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |
| `coord_x` | `NUMERIC` | Yes |  | Shot x coordinate in the source coordinate system; no warehouse court-unit contract. |
| `coord_y` | `NUMERIC` | Yes |  | Shot y coordinate in the source coordinate system; no warehouse court-unit contract. |
| `zone` | `TEXT` | Yes |  | Source shot-zone label, preserved without a warehouse court taxonomy. |
| `fastbreak` | `BOOLEAN` | Yes |  | Source flag that the shot was a fast-break action; NULL means unrecorded. |
| `second_chance` | `BOOLEAN` | Yes |  | Source flag that the shot followed an offensive rebound; NULL means unrecorded. |
| `points_off_turnover` | `BOOLEAN` | Yes |  | Boolean source flag for a shot after a turnover; it is not a points count. |
| `minute` | `INTEGER` | Yes |  | Source live minute marker; interpret with the period and clock. |
| `console_time` | `TEXT` | Yes |  | Clock text attached to a shot in the live feed. |
| `points_a` | `INTEGER` | Yes |  | Live running score of source side A (local). |
| `points_b` | `INTEGER` | Yes |  | Live running score of source side B (road). |
| `shot_at` | `TIMESTAMPTZ` | Yes |  | Source shot time with time zone. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_game_player_advanced

**Purpose:** Game-level player efficiency, on-court rates, Game Score and game PER.

**Grain:** one player-side per game with a counted box score. **Columns:** 21.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`, `person_key`.

**Definition / implementation:** [gold_etl/game_advanced.py](../gold_etl/game_advanced.py).

**Usage and limitations:** The seven time-dependent rates use on-court events when available, otherwise estimates. Gold does not expose Silver rate_source. game_per is NULL below 180 seconds; game_uper and game_aper are retained. Use cumulative PER for a season.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Source side, local or road; local is not proof of a non-neutral home venue. |
| `person_key` | `TEXT` | No | PK | Season person identity used by box scores; bridge to career person_code through app_people. |
| `club_code` | `TEXT` | No |  | Club identifier, text; join season profiles on competition, season and club. |
| `seconds_played` | `NUMERIC` | Yes |  | Official playing time in seconds; player seconds or aggregate team player-seconds in box scores. |
| `game_score` | `NUMERIC` | Yes |  | Hollinger Game Score from the player's game box score; see the exact weighted formula in the glossary. |
| `usage_pct` | `NUMERIC` | Yes |  | Player share of used plays; actual on-court denominator when available, otherwise the game box-score estimate. |
| `assist_pct` | `NUMERIC` | Yes |  | Player share of teammate scoring chances; on-court calculation also includes eligible free-throw trips. |
| `orb_pct` | `NUMERIC` | Yes |  | Offensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. |
| `drb_pct` | `NUMERIC` | Yes |  | Defensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. |
| `trb_pct` | `NUMERIC` | Yes |  | Total rebound share, a fraction; see glossary for player context and denominators. |
| `steal_pct` | `NUMERIC` | Yes |  | Player steals / opponent possessions while on court (counted events or time-share estimate). |
| `block_pct` | `NUMERIC` | Yes |  | Player blocks / opponent two-point attempts while on court (counted events or time-share estimate). |
| `tov_pct` | `NUMERIC` | Yes |  | TOV / (FGA + 0.44 * FTA + TOV), a fraction. |
| `efg_pct` | `NUMERIC` | Yes |  | (FGM + 0.5 * 3PM) / FGA, a fraction that can exceed 1. |
| `true_shooting_pct` | `NUMERIC` | Yes |  | PTS / (2 * (FGA + 0.44 * FTA)), a fraction that can exceed 1. |
| `game_uper` | `NUMERIC` | Yes |  | Unadjusted PER per minute from this game's box score with phase-through-round league constants. |
| `game_aper` | `NUMERIC` | Yes |  | game_uper * phase-through-round league pace / this game's team pace. |
| `game_per` | `NUMERIC` | Yes |  | game_aper normalized to a seconds-weighted mean of 15 within its phase-round; NULL below 180 seconds. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_game_team_advanced

**Purpose:** Game-level team estimated possessions, pace, ratings and four factors.

**Grain:** one side per game with a counted box score. **Columns:** 22.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`.

**Definition / implementation:** [gold_etl/game_advanced.py](../gold_etl/game_advanced.py).

**Usage and limitations:** Possessions are the shared box-score estimate. Counted event possessions live in app_game_team_possessions. Join on competition, season, game and side; club_code is available for display joins.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Source side, local or road; local is not proof of a non-neutral home venue. |
| `club_code` | `TEXT` | No |  | Club identifier, text; join season profiles on competition, season and club. |
| `game_minutes` | `NUMERIC` | Yes |  | Game-clock minutes, 40 plus 5 per overtime; cumulative sum in team-round rows, not player-minutes. |
| `own_possessions_estimate` | `NUMERIC` | Yes |  | Club box-score estimate: FGA + 0.44 * FTA - OREB + TOV. |
| `possessions` | `NUMERIC` | Yes |  | In calculated team rows: mean of the two clubs' possession estimates, summed for cumulative rows. API player feed possessions has a separate source definition. |
| `pace` | `NUMERIC` | Yes |  | 40 * estimated possessions / game_minutes, possessions per regulation-length team game. |
| `offensive_rating` | `NUMERIC` | Yes |  | 100 * points_for / estimated possessions, points scored per 100 possessions. |
| `defensive_rating` | `NUMERIC` | Yes |  | 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. |
| `net_rating` | `NUMERIC` | Yes |  | Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. |
| `efg_pct` | `NUMERIC` | Yes |  | (FGM + 0.5 * 3PM) / FGA, a fraction that can exceed 1. |
| `opp_efg_pct` | `NUMERIC` | Yes |  | Opponent total: (FGM + 0.5 * 3PM) / FGA, a fraction that can exceed 1. |
| `tov_pct` | `NUMERIC` | Yes |  | TOV / (FGA + 0.44 * FTA + TOV), a fraction. |
| `opp_tov_pct` | `NUMERIC` | Yes |  | Opponent total: TOV / (FGA + 0.44 * FTA + TOV), a fraction. |
| `orb_pct` | `NUMERIC` | Yes |  | Offensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. |
| `drb_pct` | `NUMERIC` | Yes |  | Defensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. |
| `ft_rate` | `NUMERIC` | Yes |  | FTM / FGA, made free throws per field-goal attempt; not FTA / FGA. |
| `opp_ft_rate` | `NUMERIC` | Yes |  | Opponent total: FTM / FGA, made free throws per field-goal attempt; not FTA / FGA. |
| `true_shooting_pct` | `NUMERIC` | Yes |  | PTS / (2 * (FGA + 0.44 * FTA)), a fraction that can exceed 1. |
| `assist_ratio` | `NUMERIC` | Yes |  | AST / FGM in calculated team tables; not the API assists_ratio. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_game_team_possessions

**Purpose:** Counted possessions and possession duration beside the box-score estimate.

**Grain:** one side per game with usable events and an advanced row. **Columns:** 10.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`.

**Definition / implementation:** [postgres_etl/possessions.py](../postgres_etl/possessions.py).

**Usage and limitations:** E2007+ subject to feed coverage. Counts belong to the team that used the possession. Do not substitute them silently for the estimates used by box-score ratings.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Source side, local or road; local is not proof of a non-neutral home venue. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `opponent_club_code` | `TEXT` | Yes |  | Opposing club in the game. |
| `counted_possessions` | `INTEGER` | Yes |  | Team possessions closed by the play-by-play state machine; summed in season-scope aggregates. |
| `possession_seconds` | `NUMERIC` | Yes |  | Sum of measurable possession durations in seconds, not necessarily all game-clock seconds. |
| `avg_possession_seconds` | `NUMERIC` | Yes |  | Game: timed seconds / timed possession count. Team aggregate: game averages weighted by counted possessions. |
| `estimated_possessions` | `NUMERIC` | Yes |  | Shared box-score possessions estimate copied for comparison; summed in season-scope aggregates. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_game_team_score_flow

**Purpose:** Lead changes, runs, time ahead/behind and clutch scoring.

**Grain:** one side per game with a running score. **Columns:** 19.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`.

**Definition / implementation:** [postgres_etl/score_flow.py](../postgres_etl/score_flow.py).

**Usage and limitations:** E2007+ subject to feed coverage. lead_changes and ties are game-wide and repeated on both rows. Clutch means the final five minutes of regulation or overtime with margin at most five points.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Source side, local or road; local is not proof of a non-neutral home venue. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `opponent_club_code` | `TEXT` | Yes |  | Opposing club in the game. |
| `points_for` | `INTEGER` | Yes |  | Points scored by this club or lineup in the row's game, stint or cumulative scope. |
| `points_against` | `INTEGER` | Yes |  | Points conceded by this club or lineup in the same sample. |
| `lead_changes` | `INTEGER` | Yes |  | Times the leading team changes; identical on the two game-side rows. |
| `ties` | `INTEGER` | Yes |  | Times the score becomes level above 0-0; identical on the two game-side rows. |
| `time_leading_seconds` | `NUMERIC` | Yes |  | Game-clock seconds the team led; summed over timed games in aggregate rows. |
| `time_trailing_seconds` | `NUMERIC` | Yes |  | Game-clock seconds the team trailed; summed over timed games in aggregate rows. |
| `time_tied_seconds` | `NUMERIC` | Yes |  | Game-clock seconds the score was tied, including 0-0; summed over timed games in aggregates. |
| `largest_lead` | `INTEGER` | Yes |  | Largest positive team margin in a game; maximum across games in season-scope aggregates. |
| `longest_run` | `INTEGER` | Yes |  | Most unanswered points scored in a game; maximum across games in season-scope aggregates. |
| `runs_6_plus` | `INTEGER` | Yes |  | Number of unanswered scoring runs of at least six points; summed across games in aggregates. |
| `clutch_seconds` | `NUMERIC` | Yes |  | Seconds from elapsed second 2100 through game end (including overtime) with margin at most five points. |
| `clutch_points_for` | `INTEGER` | Yes |  | Team points scored from second 2100 onward when the pre-scoring margin is at most five points. |
| `clutch_points_against` | `INTEGER` | Yes |  | Opponent points scored from second 2100 onward when the pre-scoring margin is at most five points. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_game_team_shot_splits

**Purpose:** Fast-break, second-chance, turnover and assisted scoring.

**Grain:** one side per game with usable events. **Columns:** 12.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`.

**Definition / implementation:** [postgres_etl/shot_splits.py](../postgres_etl/shot_splits.py).

**Usage and limitations:** E2007+ subject to coverage. Shot flags can be unrecorded in older feeds, so NULL does not mean zero. Assisted field goals are matched to event assists; categories of flagged points can overlap.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Source side, local or road; local is not proof of a non-neutral home venue. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `opponent_club_code` | `TEXT` | Yes |  | Opposing club in the game. |
| `fast_break_points` | `INTEGER` | Yes |  | Sum of positive shot points tagged fastbreak, including any flagged made free throws; NULL when flags are unrecorded. |
| `second_chance_points` | `INTEGER` | Yes |  | Sum of positive shot points tagged second_chance, including any flagged made free throws; NULL when flags are unrecorded. |
| `points_off_turnover_points` | `INTEGER` | Yes |  | Sum of positive shot points tagged points_off_turnover, including any flagged made free throws; distinct from the Boolean shot flag. |
| `field_goals_made` | `INTEGER` | Yes |  | Successful two- and three-point field goals (FGM), excluding free throws. |
| `assisted_field_goals` | `INTEGER` | Yes |  | min(team AS event count, team made-field-goal event count); summed in aggregates, not shot-by-shot matching. |
| `assisted_fg_pct` | `NUMERIC` | Yes |  | assisted_field_goals / field_goals_made, a fraction. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_game_team_shot_zones

**Purpose:** Made shots, attempts and points by source zone.

**Grain:** one side-zone per game with zone-tagged shots. **Columns:** 9.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`, `zone`.

**Definition / implementation:** [postgres_etl/shot_zones.py](../postgres_etl/shot_zones.py).

**Usage and limitations:** E2007+ subject to coverage. Field goals only; only attempted zones are present. Zone codes are source labels, not a warehouse-defined court taxonomy.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Source side, local or road; local is not proof of a non-neutral home venue. |
| `zone` | `TEXT` | No | PK | Source shot-zone label, preserved without a warehouse court taxonomy. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `attempts` | `INTEGER` | Yes |  | Field-goal attempts in this source zone, including makes. |
| `made` | `INTEGER` | Yes |  | Successful field goals in this source zone. |
| `points` | `INTEGER` | Yes |  | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_game_player_on_court

**Purpose:** Continuous player on-court intervals.

**Grain:** one interval ordinal per player-side-game. **Columns:** 9.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`, `person_key`, `interval_ordinal`.

**Definition / implementation:** [postgres_etl/on_court.py](../postgres_etl/on_court.py).

**Usage and limitations:** Elapsed game seconds, reconstructed from starters and substitutions. Duration is end_seconds - start_seconds. Event gaps and older minute-rounded box scores can produce discrepancies.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Source side, local or road; local is not proof of a non-neutral home venue. |
| `person_key` | `TEXT` | No | PK | Season person identity used by box scores; bridge to career person_code through app_people. |
| `interval_ordinal` | `INTEGER` | No | PK | On-court interval number for this player-side-game, starting at 1. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `start_seconds` | `INTEGER` | Yes |  | Interval or stint start in elapsed game seconds from tipoff. |
| `end_seconds` | `INTEGER` | Yes |  | Interval or stint end in elapsed game seconds; duration is end minus start. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_game_team_lineup_stints

**Purpose:** Five-on-five stints with scoring and counted possessions.

**Grain:** one side-stint per game. **Columns:** 15.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`, `stint_ordinal`.

**Definition / implementation:** [postgres_etl/lineups.py](../postgres_etl/lineups.py).

**Usage and limitations:** Only complete five-versus-five lineups are stored. Attribution follows event order, so substitutions at one clock time can split free throws. Incomplete portions can make totals differ from the final score.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Source side, local or road; local is not proof of a non-neutral home venue. |
| `stint_ordinal` | `INTEGER` | No | PK | Stored lineup stint number within the game, starting at 1. |
| `club_code` | `TEXT` | Yes |  | Club identifier, text; join season profiles on competition, season and club. |
| `opponent_club_code` | `TEXT` | Yes |  | Opposing club in the game. |
| `start_seconds` | `INTEGER` | Yes |  | Interval or stint start in elapsed game seconds from tipoff. |
| `end_seconds` | `INTEGER` | Yes |  | Interval or stint end in elapsed game seconds; duration is end minus start. |
| `players` | `TEXT` | Yes |  | Sorted comma-separated person_key values for the team's five players. |
| `opponent_players` | `TEXT` | Yes |  | Sorted comma-separated person_key values for the opposing five players. |
| `possessions_for` | `INTEGER` | Yes |  | Team counted possessions closed during these stints. |
| `possessions_against` | `INTEGER` | Yes |  | Opponent counted possessions closed during these stints. |
| `points_for` | `INTEGER` | Yes |  | Points scored by this club or lineup in the row's game, stint or cumulative scope. |
| `points_against` | `INTEGER` | Yes |  | Points conceded by this club or lineup in the same sample. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## app_game_stat_gaps

**Purpose:** Reasons an official box-score measure is unavailable.

**Grain:** one stat_name per game. **Columns:** 5.

**Primary key:** `competition_code`, `season_code`, `game_code`, `stat_name`.

**Definition / implementation:** [postgres_etl/flat_schema.py](../postgres_etl/flat_schema.py).

**Usage and limitations:** stat_name = * means a game lacks a box score, including forfeits. An empty gap table does not guarantee every derived or event-based metric exists.

| Column | PostgreSQL type | Nullable | Key | Description |
| --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Competition identifier: E for EuroLeague, U for EuroCup (support is deferred). |
| `season_code` | `TEXT` | No | PK | Starting-year season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Game identifier within competition and season, not globally unique. |
| `stat_name` | `TEXT` | No | PK | Missing measure's SQL column name; * means no box score for the game. |
| `reason` | `TEXT` | Yes |  | Explanation of the source gap, retained rather than filling it with zero. |

[Back to catalog](DATA_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## JSON column contracts

JSON arrays are ordered as described here; empty arrays are valid and differ
from SQL NULL. Object values can be NULL when the corresponding source is missing.

| Table.column | Array element keys | Meaning / order |
| --- | --- | --- |
| `app_players.clubs` | `seasonCode`, `clubCode`, `clubName` | One distinct registered season/club per player; ordered by season and club in the identity builder. |
| `app_coverage_seasons.items`, `app_coverage_games.items` | `key`, `label`, `status`, `availableCount`, `applicableCount` | Fixed category order shown below. Counts depend on category; not always a numerator/denominator for a percentage. |
| `app_standings.form` | `resultOrdinal`, `result` | Official recent result labels in resultOrdinal order. |
| `app_standings.streak_history` | `streakOrdinal`, `startAt`, `endAt`, `winLossRecord` | Official calendar streaks in streakOrdinal order; dates serialized in UTC ISO format with milliseconds. |
| `app_postseason_series.games` | `gameCode`, `roundNumber`, `scheduledAt`, `localClubCode`, `roadClubCode`, `localScore`, `roadScore`, `winnerClubCode` | Ordered by round then game; includes scheduled fixtures. Future scores/winner are NULL. scheduledAt is UTC ISO text with milliseconds. |

Coverage item order is `boxScores`, `periodScores`, `officialStandings`, `rosters`,
`playerPhotos`, `seasonStatistics`, `shotLocations`, `playByPlay`. Status is
`notYetApplicable` when applicableCount is zero, `unavailable` when availableCount
is zero, `available` when availableCount reaches applicableCount, otherwise
`incomplete` for standings/rosters/seasonStatistics and `partial` for other items.
Game items for standings, rosters and seasonStatistics reuse the season summary.

The implementation counts photos as distinct photographed players, compared with
played games, and season statistics as distinct feed players, compared with clubs.
Those counts are retained coverage indicators, not percentages of players covered.
See [coverage.py](../gold_etl/coverage.py) before calculating any badge percentage.

## Record metric values

| Table | Exact metric strings | Interpretation |
| --- | --- | --- |
| `app_records_player_seasons` | `points_scored`, `total_rebounds`, `assists`, `pir` | Whole-season accumulated player measures from the all-phase feed. |
| `app_records_single_games` | `points`, `valuation`, `total_rebounds`, `assistances` | Player game points, PIR, rebounds and assists. |
| `app_records_team_seasons` | `points`, `valuation`, `total_rebounds`, `assistances` | Sum of official team total rows across the season. |

Legacy metric strings differ from standardized column names. Rank slots are
assigned with deterministic tie ordering, not competition ranking with shared
rank numbers. The three record tables and two identity tables are replaced by
competition; all other Gold tables are replaced by selected season scopes.

## Maintaining this reference

When a schema changes, compare the full table/column/key inventory with
`gold_etl.schema.PHYSICAL_TABLES` and `neon_publish.contract.APP_TABLES`, update
the affected purpose and definitions, and add new statistics to the glossary.
For changed calculations, verify the producing module as well as the schema.
This document is checked in as Markdown; it is not refreshed automatically.

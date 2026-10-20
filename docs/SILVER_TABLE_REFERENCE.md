# EuroLeague Silver table reference

Every column of the 36 registered Silver data tables, plus the load-log metadata
table. Checked against [flat_schema.py](../postgres_etl/flat_schema.py),
[raw_transform.py](../postgres_etl/raw_transform.py),
[flat_transform.py](../postgres_etl/flat_transform.py) and the calculated-table
modules on 2026-10-20. This is the declared code contract, not a live-schema audit.
Examples and coverage refer to EuroLeague only.

Choose tables in the [Silver catalog](SILVER_CATALOG.md), trace resources in the
[Bronze catalog](BRONZE_CATALOG.md), and read metric definitions in the shared
[player/team stats glossary](STAT_GLOSSARY.md). App-facing contracts are in the
[Gold column reference](GOLD_TABLE_REFERENCE.md).

## Reading columns and source paths

All SQL names are in schema `silver`. PK means primary-key column. Nullable is
No for key columns and explicitly required fields. The two provenance columns
are required on all 36 data tables, even though they are appended by the writer
rather than listed in each table's field tuple. `load_log` has its own schema.

`TEXT` identifiers retain leading zeroes. `NUMERIC` can mean counts, points,
seconds, percentages or ratios; it does not imply common units. `TIMESTAMPTZ`
represents an instant; `TIMESTAMP` stores no zone. For source timestamps carrying
an offset, the transformer converts to UTC wall time before removing the zone
for a TIMESTAMP column. Zone-less values retain their wall time; do not attach
an arbitrary frontend zone. Undefined/missing numeric values become NULL.

For source tables, a **Source / derivation** path is relative to the selected row
object, not necessarily the root response. Child official/period/standings rows
change that object. `@name` means a value prepared by the raw transformer, such
as an identity, normalized status, phase from a resource name, or resolved player
code. See the linked resource for its container. Calculated fields say Derived;
their schema path is not a Bronze JSON path. Writer fields identify provenance.

Source statistics are copied without Gold qualification/fallback/PS enrichment.
Calculated game rows use the shared glossary's formulas, with no season PER,
Win Shares or RAPM columns in Silver. Source-field interpretation that is not
established by the warehouse remains marked as such.

## Tables

- **Season, clubs, people and registration:** [seasons](#seasons), [clubs](#clubs), [people](#people), [registrations](#registrations), [rounds](#rounds).
- **Fixtures and official box scores:** [games](#games), [game_officials](#game_officials), [game_period_scores](#game_period_scores), [game_player_stats](#game_player_stats), [game_team_stats](#game_team_stats), [game_stat_gaps](#game_stat_gaps).
- **API player and team season statistics:** [season_player_stats_traditional](#season_player_stats_traditional), [season_player_stats_advanced](#season_player_stats_advanced), [season_player_stats_scoring](#season_player_stats_scoring), [season_player_stats_misc](#season_player_stats_misc), [season_team_stats_traditional](#season_team_stats_traditional), [season_team_stats_advanced](#season_team_stats_advanced), [season_team_stats_opponents_traditional](#season_team_stats_opponents_traditional), [season_team_stats_opponents_advanced](#season_team_stats_opponents_advanced).
- **Official standings and child rows:** [standings_basic](#standings_basic), [standings_calendar](#standings_calendar), [standings_streaks](#standings_streaks), [standings_ahead_behind](#standings_ahead_behind), [standings_margins](#standings_margins), [standings_calendar_streaks](#standings_calendar_streaks), [standings_basic_form](#standings_basic_form).
- **Live events and shots:** [play_by_play](#play_by_play), [shots](#shots).
- **Calculated game tables:** [game_team_advanced](#game_team_advanced), [game_player_advanced](#game_player_advanced), [game_team_possessions](#game_team_possessions), [game_team_score_flow](#game_team_score_flow), [game_team_shot_splits](#game_team_shot_splits), [game_team_shot_zones](#game_team_shot_zones), [game_player_on_court](#game_player_on_court), [game_team_lineup_stints](#game_team_lineup_stints).
- **Load metadata:** [load_log](#load_log).

## seasons

**Purpose:** Competition season names, dates and champion.

**Grain:** one season.

**Primary key:** `competition_code`, `season_code`.

**Upstream:** `_catalog/v2/seasons`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_seasons`](GOLD_TABLE_REFERENCE.md#app_seasons).

**Notes:** Selects this season from the competition-wide catalog response.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `name` | `TEXT` | Yes |  | `@name` | Display name supplied by the source; identity tables use the latest season profile. |
| `start_year` | `INTEGER` | Yes |  | `@start_year` | Starting calendar year of the season. |
| `alias` | `TEXT` | Yes |  | `alias` | Source alternative display name or alias. |
| `competition_name` | `TEXT` | Yes |  | `name` | Source competition name. |
| `start_at` | `TIMESTAMP` | Yes |  | `startDate` | Source start timestamp without time zone for the season or registration. |
| `activation_at` | `TIMESTAMP` | Yes |  | `activationDate` | Source season activation timestamp without time zone. |
| `end_at` | `TIMESTAMP` | Yes |  | `endDate` | Source end timestamp without time zone for the season or registration. |
| `champion_club_code` | `TEXT` | Yes |  | `@champion_club_code` | Season champion's club code; not this game's winner. |
| `champion_club_name` | `TEXT` | Yes |  | `winner.name` | Season champion's display name. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## clubs

**Purpose:** Season club profiles, names, crests and venue codes.

**Grain:** one club-season.

**Primary key:** `competition_code`, `season_code`, `club_code`.

**Upstream:** `v2/clubs`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_clubs`](GOLD_TABLE_REFERENCE.md#app_clubs); app_club_identities; names/crests in page and aggregate tables.

**Notes:** Season-specific profiles; the cross-season identity is built in Gold.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `club_code` | `TEXT` | No | PK | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `name` | `TEXT` | Yes |  | `@name` | Display name supplied by the source; identity tables use the latest season profile. |
| `abbreviated_name` | `TEXT` | Yes |  | `abbreviatedName` | Source shortened display name. |
| `editorial_name` | `TEXT` | Yes |  | `editorialName` | Source editorial club display name. |
| `tv_code` | `TEXT` | Yes |  | `tvCode` | Source television abbreviation for the club. |
| `is_virtual` | `BOOLEAN` | Yes |  | `isVirtual` | Source flag for a virtual club entry. |
| `crest_url` | `TEXT` | Yes |  | `images.crest` | Source team crest image URL. |
| `sponsor` | `TEXT` | Yes |  | `sponsor` | Source club sponsor label. |
| `permanent_name` | `TEXT` | Yes |  | `clubPermanentName` | Source persistent club name retained separately from the seasonal sponsor name. |
| `permanent_alias` | `TEXT` | Yes |  | `clubPermanentAlias` | Source persistent club alias. |
| `country_code` | `TEXT` | Yes |  | `country.code` | Source country code for the person, club or official. |
| `country_name` | `TEXT` | Yes |  | `country.name` | Source country display name. |
| `address` | `TEXT` | Yes |  | `address` | Source club postal/street address. |
| `website` | `TEXT` | Yes |  | `website` | Source club website URL. |
| `tickets_url` | `TEXT` | Yes |  | `ticketsUrl` | Source club ticketing URL. |
| `twitter_account` | `TEXT` | Yes |  | `twitterAccount` | Source Twitter account value. |
| `venue_code` | `TEXT` | Yes |  | `venueCode` | Source venue identifier. |
| `city` | `TEXT` | Yes |  | `city` | Source club city. |
| `president` | `TEXT` | Yes |  | `president` | Source club president name, season-specific metadata. |
| `phone` | `TEXT` | Yes |  | `phone` | Source club telephone value. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## people

**Purpose:** Deduplicated season person profiles and identity bridge.

**Grain:** one person-season.

**Primary key:** `competition_code`, `season_code`, `person_key`.

**Upstream:** `v2/season_people_pages/offset_* and v2/rosters/{club}`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_people`](GOLD_TABLE_REFERENCE.md#app_people); app_players (via player registrations).

**Notes:** Includes players, coaches, officials and staff. First-seen person profile wins during deduplication; preserve NULLs and leading zeroes.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `person_key` | `TEXT` | No | PK | `@person_key` | Season person identity used by box scores and registrations; bridge to career person_code through silver.people. |
| `person_code` | `TEXT` | Yes |  | `@person_code` | Person identity code in people; in live events it is the resolved box-score person_key. Preserve leading zeroes. |
| `name` | `TEXT` | Yes |  | `@name` | Display name supplied by the source; identity tables use the latest season profile. |
| `alias` | `TEXT` | Yes |  | `alias` | Source alternative display name or alias. |
| `alias_raw` | `TEXT` | Yes |  | `aliasRaw` | Unmodified person alias retained alongside the normalized alias. |
| `passport_name` | `TEXT` | Yes |  | `passportName` | Source given name used in passport details. |
| `passport_surname` | `TEXT` | Yes |  | `passportSurname` | Source surname used in passport details. |
| `jersey_name` | `TEXT` | Yes |  | `jerseyName` | Name printed on the player's jersey according to the source. |
| `abbreviated_name` | `TEXT` | Yes |  | `abbreviatedName` | Source shortened display name. |
| `country_code` | `TEXT` | Yes |  | `country.code` | Source country code for the person, club or official. |
| `country_name` | `TEXT` | Yes |  | `country.name` | Source country display name. |
| `height_cm` | `INTEGER` | Yes |  | `height` | Source person height in centimeters. |
| `weight_kg` | `INTEGER` | Yes |  | `weight` | Source person weight in kilograms. |
| `birth_at` | `TIMESTAMP` | Yes |  | `birthDate` | Source birth date stored as a timestamp without time zone. |
| `birth_country_code` | `TEXT` | Yes |  | `birthCountry.code` | Source birth-country code. |
| `birth_country_name` | `TEXT` | Yes |  | `birthCountry.name` | Source birth-country display name. |
| `twitter_account` | `TEXT` | Yes |  | `twitterAccount` | Source Twitter account value. |
| `instagram_account` | `TEXT` | Yes |  | `instagramAccount` | Source Instagram account value. |
| `facebook_account` | `TEXT` | Yes |  | `facebookAccount` | Source Facebook account value. |
| `is_referee` | `BOOLEAN` | Yes |  | `isReferee` | Source flag indicating a referee profile. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## registrations

**Purpose:** Club/role registrations and roster details.

**Grain:** one registration-season.

**Primary key:** `competition_code`, `season_code`, `registration_key`.

**Upstream:** `v2/season_people_pages/offset_* and v2/rosters/{club}`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_registrations`](GOLD_TABLE_REFERENCE.md#app_registrations); app_players.

**Notes:** registration_key hashes person, club, role, start date and external ID. role_code = J selects players; one person can have multiple registrations.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `registration_key` | `TEXT` | No | PK | `@registration_key` | Natural identity of the source registration, not a player identity. |
| `person_key` | `TEXT` | No |  | `@person_key` | Season person identity used by box scores and registrations; bridge to career person_code through silver.people. |
| `club_code` | `TEXT` | Yes |  | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `role_code` | `TEXT` | Yes |  | `@role_code` | Registration role code; J means player, other codes represent staff roles. |
| `role_name` | `TEXT` | Yes |  | `typeName` | Source label of the registration role. |
| `active` | `BOOLEAN` | Yes |  | `@active` | Source active flag for a registration or official. |
| `start_at` | `TIMESTAMP` | Yes |  | `startDate` | Source start timestamp without time zone for the season or registration. |
| `end_at` | `TIMESTAMP` | Yes |  | `endDate` | Source end timestamp without time zone for the season or registration. |
| `sort_order` | `INTEGER` | Yes |  | `order` | Source registration display order. |
| `jersey_number` | `TEXT` | Yes |  | `dorsal` | Source jersey number stored as text; retain leading zeroes and special values. |
| `jersey_number_raw` | `TEXT` | Yes |  | `dorsalRaw` | Original registration jersey value retained alongside jersey_number. |
| `position` | `INTEGER` | Yes |  | `position` | Standings rank in standings tables; player position code in profile, registration and box-score tables. |
| `position_name` | `TEXT` | Yes |  | `positionName` | Source label for the player's position. |
| `last_team` | `TEXT` | Yes |  | `lastTeam` | Source previous-team label attached to the registration. |
| `external_id` | `INTEGER` | Yes |  | `externalId` | Source external person/registration identifier, not a warehouse join key. |
| `person_name` | `TEXT` | Yes |  | `person.name` | Person display name attached to this registration or box score. |
| `club_name` | `TEXT` | Yes |  | `club.name` | Club display name for this season or row. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## rounds

**Purpose:** Source round definitions and date ranges.

**Grain:** one round definition-season.

**Primary key:** `competition_code`, `season_code`, `round_key`.

**Upstream:** `v2/rounds`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_rounds`](GOLD_TABLE_REFERENCE.md#app_rounds).

**Notes:** round_key is a deterministic hash of phase, number, source index and name. Do not join on round_number alone.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `round_key` | `TEXT` | No | PK | `@round_key` | Natural identity of a source round definition. |
| `phase_code` | `TEXT` | No |  | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `round_number` | `INTEGER` | No |  | `@round_number` | Source game or standings round number; not a cumulative snapshot created by Silver. |
| `round_index` | `INTEGER` | Yes |  | `index` | Source index of this round definition, distinct from round_number. |
| `name` | `TEXT` | Yes |  | `@name` | Display name supplied by the source; identity tables use the latest season profile. |
| `first_game_at` | `TIMESTAMP` | Yes |  | `minGameStartDate` | Source first-game timestamp for the round, without time zone. |
| `last_game_at` | `TIMESTAMP` | Yes |  | `maxGameStartDate` | Source last-game timestamp for the round, without time zone. |
| `formatted_dates` | `TEXT` | Yes |  | `datesFormmated` | Source preformatted round date label. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## games

**Purpose:** Every scheduled or played fixture with result, status and venue.

**Grain:** one game-season.

**Primary key:** `competition_code`, `season_code`, `game_code`.

**Upstream:** `v2/games`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_games`](GOLD_TABLE_REFERENCE.md#app_games); team/player round tables, standings_stats, coverage, records, postseason_series and event/lineup aggregates.

**Notes:** Unknown attendance zero becomes NULL with a note. Future scores stay NULL. Source local/road does not imply a non-neutral venue.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | `@game_code` | Game identifier within competition and season, not globally unique. |
| `source_id` | `TEXT` | Yes |  | `id` | Raw source game identity retained alongside game_code. |
| `identifier` | `TEXT` | Yes |  | `identifier` | Source game identifier label. |
| `phase_code` | `TEXT` | Yes |  | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `phase_name` | `TEXT` | Yes |  | `phaseType.name` | Source phase display name. |
| `phase_alias` | `TEXT` | Yes |  | `phaseType.alias` | Source phase alias. |
| `phase_is_group` | `BOOLEAN` | Yes |  | `phaseType.isGroupPhase` | Source flag that this phase is a group stage. |
| `group_id` | `TEXT` | Yes |  | `group.id` | Source group identifier within the phase. |
| `group_name` | `TEXT` | Yes |  | `group.name` | Source group display name. |
| `group_raw_name` | `TEXT` | Yes |  | `group.rawName` | Unmodified group name. |
| `group_order` | `INTEGER` | Yes |  | `group.order` | Source group display order. |
| `round_number` | `INTEGER` | Yes |  | `@round_number` | Source game or standings round number; not a cumulative snapshot created by Silver. |
| `round_name` | `TEXT` | Yes |  | `roundName` | Source round display name. |
| `round_alias` | `TEXT` | Yes |  | `roundAlias` | Source round alias. |
| `scheduled_at` | `TIMESTAMPTZ` | Yes |  | `@scheduled_at` | Scheduled tipoff as a timestamp with time zone; convert for frontend display. |
| `source_date` | `TEXT` | Yes |  | `date` | Original source game-date text retained for traceability. |
| `local_date` | `TIMESTAMP` | Yes |  | `localDate` | Source venue-local game date/time stored as a timestamp without time zone. |
| `local_time_zone_minutes` | `INTEGER` | Yes |  | `localTimeZone` | Source venue time-zone offset in minutes. |
| `played` | `BOOLEAN` | Yes |  | `@played` | Source flag that the fixture has been played. |
| `game_status` | `TEXT` | Yes |  | `gameStatus` | Unmodified source game-status label. |
| `status` | `TEXT` | Yes |  | `@status` | Derived completed, scheduled, awaiting_result, postponed or cancelled status. |
| `status_note` | `TEXT` | Yes |  | `@status_note` | Explanation accompanying the derived game status. |
| `confirmed_date` | `BOOLEAN` | Yes |  | `confirmedDate` | Source flag that the fixture date is confirmed. |
| `confirmed_hour` | `BOOLEAN` | Yes |  | `confirmedHour` | Source flag that the fixture time is confirmed. |
| `local_club_code` | `TEXT` | Yes |  | `@local_club_code` | Source local-side club; joins app_clubs within competition and season. |
| `local_club_name` | `TEXT` | Yes |  | `local.club.name` | Source local-side club name. |
| `local_club_abbreviated_name` | `TEXT` | Yes |  | `local.club.abbreviatedName` | Source abbreviated local-side club name. |
| `local_club_tv_code` | `TEXT` | Yes |  | `local.club.tvCode` | Source local-side television abbreviation. |
| `road_club_code` | `TEXT` | Yes |  | `@road_club_code` | Source road-side club; joins app_clubs within competition and season. |
| `road_club_name` | `TEXT` | Yes |  | `road.club.name` | Source road-side club name. |
| `road_club_abbreviated_name` | `TEXT` | Yes |  | `road.club.abbreviatedName` | Source abbreviated road-side club name. |
| `road_club_tv_code` | `TEXT` | Yes |  | `road.club.tvCode` | Source road-side television abbreviation. |
| `local_score` | `INTEGER` | Yes |  | `@local_score` | Official local-side final score; NULL until a result is available. |
| `road_score` | `INTEGER` | Yes |  | `@road_score` | Official road-side final score; NULL until a result is available. |
| `local_standings_score` | `INTEGER` | Yes |  | `@local_standings_score` | Source local-side score used for standings, retained separately from the final score. |
| `road_standings_score` | `INTEGER` | Yes |  | `@road_standings_score` | Source road-side score used for standings, retained separately from the final score. |
| `match_winner_club_code` | `TEXT` | Yes |  | `@match_winner_club_code` | Winner of this played game; distinct from the season champion. |
| `champion_club_code` | `TEXT` | Yes |  | `@champion_club_code` | Season champion's club code; not this game's winner. |
| `champion_club_name` | `TEXT` | Yes |  | `winner.name` | Season champion's display name. |
| `audience` | `INTEGER` | Yes |  | `@audience` | Reported attendance; source zero for unknown is stored as NULL. |
| `audience_note` | `TEXT` | Yes |  | `@audience_note` | Explanation when attendance is unavailable or source zero was normalized. |
| `audience_confirmed` | `BOOLEAN` | Yes |  | `audienceConfirmed` | Source attendance-confirmation flag. |
| `venue_code` | `TEXT` | Yes |  | `venue.code` | Source venue identifier. |
| `venue_name` | `TEXT` | Yes |  | `venue.name` | Source venue display name. |
| `venue_capacity` | `INTEGER` | Yes |  | `venue.capacity` | Reported venue seating capacity. |
| `venue_address` | `TEXT` | Yes |  | `venue.address` | Source venue address. |
| `venue_active` | `BOOLEAN` | Yes |  | `venue.active` | Source venue-active flag. |
| `venue_notes` | `TEXT` | Yes |  | `venue.notes` | Source venue notes. |
| `is_neutral_venue` | `BOOLEAN` | Yes |  | `isNeutralVenue` | Source flag for a neutral venue; do not infer it from side. |
| `social_feed` | `TEXT` | Yes |  | `socialFeed` | Source game social-feed metadata. |
| `operations_code` | `TEXT` | Yes |  | `operationsCode` | Source game operations code. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## game_officials

**Purpose:** Official assignments extracted from the fixture list.

**Grain:** one official slot-game.

**Primary key:** `competition_code`, `season_code`, `game_code`, `official_number`.

**Upstream:** `v2/games`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_game_officials`](GOLD_TABLE_REFERENCE.md#app_game_officials).

**Notes:** referee1 through referee4 become separate rows; a missing official slot produces no row.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | `@game_code` | Game identifier within competition and season, not globally unique. |
| `official_number` | `INTEGER` | No | PK | `@official_number` | Official's ordinal slot in this game's assignments. |
| `official_code` | `TEXT` | Yes |  | `@official_code` | Source official identifier. |
| `name` | `TEXT` | Yes |  | `@name` | Display name supplied by the source; identity tables use the latest season profile. |
| `alias` | `TEXT` | Yes |  | `alias` | Source alternative display name or alias. |
| `country_code` | `TEXT` | Yes |  | `country.code` | Source country code for the person, club or official. |
| `country_name` | `TEXT` | Yes |  | `country.name` | Source country display name. |
| `active` | `BOOLEAN` | Yes |  | `active` | Source active flag for a registration or official. |
| `image_vertical_small` | `TEXT` | Yes |  | `images.verticalSmall` | Source small portrait URL for the official. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## game_period_scores

**Purpose:** Quarter and overtime points extracted from fixtures.

**Grain:** one side-period-game.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`, `period_number`.

**Upstream:** `v2/games`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_game_period_scores`](GOLD_TABLE_REFERENCE.md#app_game_period_scores).

**Notes:** Regulation periods are 1-4; extraPeriods become 5+. score is period points.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | `@game_code` | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | `@side` | Source side, local or road; local is not proof of a non-neutral home venue. |
| `period_number` | `INTEGER` | No | PK | `@period_number` | Period number: 1-4 for quarters, 5 and above for overtime. |
| `score` | `INTEGER` | Yes |  | `@score` | Points scored by this side in this period, not the cumulative score. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## game_player_stats

**Purpose:** Official player box-score lines and registration context.

**Grain:** one player-side-game.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`, `person_key`.

**Upstream:** `v2/game_stats/{game}`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_game_player_stats`](GOLD_TABLE_REFERENCE.md#app_game_player_stats); player round stats/PER/Win Shares, game PER, PS player rows, app_records_single_games.

**Notes:** Includes DNP lines. Unrecorded all-zero measures are NULLed and explained in game_stat_gaps. Gold appearance aggregates require positive seconds.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | `@game_code` | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | `@side` | Source side, local or road; local is not proof of a non-neutral home venue. |
| `person_key` | `TEXT` | No | PK | `@person_key` | Season person identity used by box scores and registrations; bridge to career person_code through silver.people. |
| `club_code` | `TEXT` | Yes |  | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `person_name` | `TEXT` | Yes |  | `player.person.name` | Person display name attached to this registration or box score. |
| `club_name` | `TEXT` | Yes |  | `player.club.name` | Club display name for this season or row. |
| `player_type_code` | `TEXT` | Yes |  | `player.type` | Source classification of the box-score person. |
| `registration_active` | `BOOLEAN` | Yes |  | `player.active` | Source active flag for the attached registration. |
| `registration_start_at` | `TIMESTAMP` | Yes |  | `player.startDate` | Start of the attached registration, timestamp without time zone. |
| `registration_end_at` | `TIMESTAMP` | Yes |  | `player.endDate` | End of the attached registration, timestamp without time zone. |
| `position` | `INTEGER` | Yes |  | `player.position` | Standings rank in standings tables; player position code in profile, registration and box-score tables. |
| `position_name` | `TEXT` | Yes |  | `player.positionName` | Source label for the player's position. |
| `jersey_number` | `TEXT` | Yes |  | `player.dorsal` | Source jersey number stored as text; retain leading zeroes and special values. |
| `external_id` | `INTEGER` | Yes |  | `player.externalId` | Source external person/registration identifier, not a warehouse join key. |
| `headshot_url` | `TEXT` | Yes |  | `player.images.headshot` | Source game box-score portrait URL. |
| `points` | `NUMERIC` | Yes |  | `@points` | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |
| `seconds_played` | `NUMERIC` | Yes |  | `stats.timePlayed` | Official playing time in seconds; player seconds or aggregate team player-seconds in box scores. |
| `pir` | `NUMERIC` | Yes |  | `stats.valuation` | Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. |
| `two_pointers_made` | `NUMERIC` | Yes |  | `stats.fieldGoalsMade2` | Successful two-point field goals (2PM). |
| `two_pointers_attempted` | `NUMERIC` | Yes |  | `stats.fieldGoalsAttempted2` | Two-point field-goal attempts (2PA), including makes. |
| `three_pointers_made` | `NUMERIC` | Yes |  | `stats.fieldGoalsMade3` | Successful three-point field goals (3PM). |
| `three_pointers_attempted` | `NUMERIC` | Yes |  | `stats.fieldGoalsAttempted3` | Three-point field-goal attempts (3PA), including makes. |
| `free_throws_made` | `NUMERIC` | Yes |  | `stats.freeThrowsMade` | Successful free throws (FTM). |
| `free_throws_attempted` | `NUMERIC` | Yes |  | `stats.freeThrowsAttempted` | Free-throw attempts (FTA), including makes. |
| `field_goals_made` | `NUMERIC` | Yes |  | `stats.fieldGoalsMadeTotal` | Successful two- and three-point field goals (FGM), excluding free throws. |
| `field_goals_attempted` | `NUMERIC` | Yes |  | `stats.fieldGoalsAttemptedTotal` | All two- and three-point field-goal attempts (FGA), including blocked attempts. |
| `accuracy_made` | `NUMERIC` | Yes |  | `stats.accuracyMade` | Raw source accuracyMade measure; meaning is not established by the warehouse. Do not treat it as FG%. |
| `accuracy_attempted` | `NUMERIC` | Yes |  | `stats.accuracyAttempted` | Raw source accuracyAttempted measure; meaning is not established by the warehouse. Do not treat it as FGA. |
| `total_rebounds` | `NUMERIC` | Yes |  | `stats.totalRebounds` | Offensive plus defensive rebounds (REB); official team totals can include team rebounds. |
| `defensive_rebounds` | `NUMERIC` | Yes |  | `stats.defensiveRebounds` | Rebounds recovered after the opponent's missed shot (DREB). |
| `offensive_rebounds` | `NUMERIC` | Yes |  | `stats.offensiveRebounds` | Rebounds recovered after the player's or club's missed shot (OREB). |
| `assists` | `NUMERIC` | Yes |  | `stats.assistances` | Official credited assists (AST), including EuroLeague assists that lead to free throws. |
| `steals` | `NUMERIC` | Yes |  | `stats.steals` | Official credited steals (STL). |
| `turnovers` | `NUMERIC` | Yes |  | `stats.turnovers` | Lost possessions charged to the player or team (TOV). |
| `blocks` | `NUMERIC` | Yes |  | `stats.blocksFavour` | Opponent field-goal attempts blocked by the player or team (BLK). |
| `blocks_against` | `NUMERIC` | Yes |  | `stats.blocksAgainst` | The player's or team's field-goal attempts blocked by opponents. |
| `fouls_committed` | `NUMERIC` | Yes |  | `stats.foulsCommited` | Personal fouls charged to the player or team (PF). |
| `fouls_drawn` | `NUMERIC` | Yes |  | `stats.foulsReceived` | Opponent fouls drawn by the player or team. |
| `plus_minus` | `NUMERIC` | Yes |  | `stats.plusMinus` | Source point margin while the player was on court; raw points, not per 100 possessions. |
| `started` | `BOOLEAN` | Yes |  | `stats.startFive` | Primary source starter flag used in on-court reconstruction and appearance counts. |
| `started_alt` | `BOOLEAN` | Yes |  | `stats.startFive2` | Alternate source starter flag retained separately. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## game_team_stats

**Purpose:** Official team-only and complete team box scores.

**Grain:** one stats_kind-side-game.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`, `stats_kind`.

**Upstream:** `v2/game_stats/{game}`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_game_team_stats`](GOLD_TABLE_REFERENCE.md#app_game_team_stats); app_team_season_stats, team/player round calculations, app_records_team_seasons.

**Notes:** Use stats_kind = total for a full box score. team is the separate team-only contribution row. club_code is obtained from games and side.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | `@game_code` | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | `@side` | Source side, local or road; local is not proof of a non-neutral home venue. |
| `stats_kind` | `TEXT` | No | PK | `@stats_kind` | total is the complete team box score; team is the team-only contribution row. |
| `coach_code` | `TEXT` | Yes |  | `@coach_code` | Source coach identifier for this side-game. |
| `coach_name` | `TEXT` | Yes |  | `@coach_name` | Source coach display name. |
| `points` | `NUMERIC` | Yes |  | `points` | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |
| `seconds_played` | `NUMERIC` | Yes |  | `timePlayed` | Official playing time in seconds; player seconds or aggregate team player-seconds in box scores. |
| `pir` | `NUMERIC` | Yes |  | `valuation` | Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. |
| `two_pointers_made` | `NUMERIC` | Yes |  | `fieldGoalsMade2` | Successful two-point field goals (2PM). |
| `two_pointers_attempted` | `NUMERIC` | Yes |  | `fieldGoalsAttempted2` | Two-point field-goal attempts (2PA), including makes. |
| `three_pointers_made` | `NUMERIC` | Yes |  | `fieldGoalsMade3` | Successful three-point field goals (3PM). |
| `three_pointers_attempted` | `NUMERIC` | Yes |  | `fieldGoalsAttempted3` | Three-point field-goal attempts (3PA), including makes. |
| `free_throws_made` | `NUMERIC` | Yes |  | `freeThrowsMade` | Successful free throws (FTM). |
| `free_throws_attempted` | `NUMERIC` | Yes |  | `freeThrowsAttempted` | Free-throw attempts (FTA), including makes. |
| `field_goals_made` | `NUMERIC` | Yes |  | `fieldGoalsMadeTotal` | Successful two- and three-point field goals (FGM), excluding free throws. |
| `field_goals_attempted` | `NUMERIC` | Yes |  | `fieldGoalsAttemptedTotal` | All two- and three-point field-goal attempts (FGA), including blocked attempts. |
| `accuracy_made` | `NUMERIC` | Yes |  | `accuracyMade` | Raw source accuracyMade measure; meaning is not established by the warehouse. Do not treat it as FG%. |
| `accuracy_attempted` | `NUMERIC` | Yes |  | `accuracyAttempted` | Raw source accuracyAttempted measure; meaning is not established by the warehouse. Do not treat it as FGA. |
| `total_rebounds` | `NUMERIC` | Yes |  | `totalRebounds` | Offensive plus defensive rebounds (REB); official team totals can include team rebounds. |
| `defensive_rebounds` | `NUMERIC` | Yes |  | `defensiveRebounds` | Rebounds recovered after the opponent's missed shot (DREB). |
| `offensive_rebounds` | `NUMERIC` | Yes |  | `offensiveRebounds` | Rebounds recovered after the player's or club's missed shot (OREB). |
| `assists` | `NUMERIC` | Yes |  | `assistances` | Official credited assists (AST), including EuroLeague assists that lead to free throws. |
| `steals` | `NUMERIC` | Yes |  | `steals` | Official credited steals (STL). |
| `turnovers` | `NUMERIC` | Yes |  | `turnovers` | Lost possessions charged to the player or team (TOV). |
| `blocks` | `NUMERIC` | Yes |  | `blocksFavour` | Opponent field-goal attempts blocked by the player or team (BLK). |
| `blocks_against` | `NUMERIC` | Yes |  | `blocksAgainst` | The player's or team's field-goal attempts blocked by opponents. |
| `fouls_committed` | `NUMERIC` | Yes |  | `foulsCommited` | Personal fouls charged to the player or team (PF). |
| `fouls_drawn` | `NUMERIC` | Yes |  | `foulsReceived` | Opponent fouls drawn by the player or team. |
| `plus_minus` | `NUMERIC` | Yes |  | `plusMinus` | Source point margin while the player was on court; raw points, not per 100 possessions. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## game_stat_gaps

**Purpose:** Explicit explanations of missing official box-score measures.

**Grain:** one stat_name-game.

**Primary key:** `competition_code`, `season_code`, `game_code`, `stat_name`.

**Upstream:** `v2/game_stats/{game}`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_game_stat_gaps`](GOLD_TABLE_REFERENCE.md#app_game_stat_gaps).

**Notes:** stat_name = * denotes no player box score. The normalization rules inspect a fixed list of measures, not every possible missing event or derived rate.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | `@game_code` | Game identifier within competition and season, not globally unique. |
| `stat_name` | `TEXT` | No | PK | `@stat_name` | Missing measure's SQL column name; * means no box score for the game. |
| `reason` | `TEXT` | Yes |  | `@reason` | Explanation of the source gap, retained rather than filling it with zero. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## season_player_stats_traditional

**Purpose:** Source player traditional statistics by phase and mode.

**Grain:** one entry ordinal-phase-mode.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `mode`, `entry_ordinal`.

**Upstream:** `v3/season_stats/players_traditional_{phase}_{mode}`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_season_player_stats_traditional`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_traditional).

**Notes:** API rows only, including nonqualified players only where the feed lists them. No Gold qualification flags, missing perGame fallback, or synthetic PS. Transferred players can have a semicolon-separated multi-club code rather than one club identity. Percentages retain source scale; see the shared glossary.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `mode` | `TEXT` | No | PK | `@mode` | accumulated or perGame as provided by the API; Silver does not synthesize missing perGame rows. |
| `entry_ordinal` | `INTEGER` | No | PK | `@entry_ordinal` | Zero-based entry position within this category, phase and mode, not a stable player identity. |
| `person_key` | `TEXT` | No |  | `@person_key` | Season person identity used by box scores and registrations; bridge to career person_code through silver.people. |
| `club_code` | `TEXT` | Yes |  | `@club_code` | Source player-team code, possibly semicolon-separated for a transfer (for example BAS;TEL). Such multi-club values are not one clubs row. |
| `player_name` | `TEXT` | Yes |  | `player.name` | Source player name attached to the season statistics or live event row. |
| `player_age` | `INTEGER` | Yes |  | `player.age` | Age reported in the source season feed, not recalculated current age. |
| `player_image_url` | `TEXT` | Yes |  | `player.imageUrl` | Source player portrait URL. |
| `club_name` | `TEXT` | Yes |  | `player.team.name` | Club display name for this season or row. |
| `club_tv_codes` | `TEXT` | Yes |  | `player.team.tvCodes` | Source team television abbreviations. |
| `club_image_url` | `TEXT` | Yes |  | `player.team.imageUrl` | Source team image URL for the season feed. |
| `player_ranking` | `INTEGER` | Yes |  | `playerRanking` | Source leaderboard ranking; calculated perGame rows have NULL. |
| `games_played` | `NUMERIC` | Yes |  | `gamesPlayed` | Source games count within the selected phase and mode; no Silver-derived season snapshots. |
| `games_started` | `NUMERIC` | Yes |  | `gamesStarted` | Games in which the player started; cumulative appearance count or retained feed count. |
| `minutes_played` | `NUMERIC` | Yes |  | `minutesPlayed` | Playing time in minutes in season feeds; traditional perGame rows use minutes per appearance. |
| `points` | `NUMERIC` | Yes |  | `pointsScored` | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |
| `two_pointers_made` | `NUMERIC` | Yes |  | `twoPointersMade` | Successful two-point field goals (2PM). |
| `two_pointers_attempted` | `NUMERIC` | Yes |  | `twoPointersAttempted` | Two-point field-goal attempts (2PA), including makes. |
| `two_pointers_percentage` | `NUMERIC` | Yes |  | `twoPointersPercentage` | Two-point shooting percentage, 100 * 2PM / 2PA, on the feed's 0-100 scale. |
| `three_pointers_made` | `NUMERIC` | Yes |  | `threePointersMade` | Successful three-point field goals (3PM). |
| `three_pointers_attempted` | `NUMERIC` | Yes |  | `threePointersAttempted` | Three-point field-goal attempts (3PA), including makes. |
| `three_pointers_percentage` | `NUMERIC` | Yes |  | `threePointersPercentage` | Three-point shooting percentage, 100 * 3PM / 3PA, on the feed's 0-100 scale. |
| `free_throws_made` | `NUMERIC` | Yes |  | `freeThrowsMade` | Successful free throws (FTM). |
| `free_throws_attempted` | `NUMERIC` | Yes |  | `freeThrowsAttempted` | Free-throw attempts (FTA), including makes. |
| `free_throws_percentage` | `NUMERIC` | Yes |  | `freeThrowsPercentage` | Free-throw shooting percentage, 100 * FTM / FTA, on the feed's 0-100 scale. |
| `offensive_rebounds` | `NUMERIC` | Yes |  | `offensiveRebounds` | Rebounds recovered after the player's or club's missed shot (OREB). |
| `defensive_rebounds` | `NUMERIC` | Yes |  | `defensiveRebounds` | Rebounds recovered after the opponent's missed shot (DREB). |
| `total_rebounds` | `NUMERIC` | Yes |  | `totalRebounds` | Offensive plus defensive rebounds (REB); official team totals can include team rebounds. |
| `assists` | `NUMERIC` | Yes |  | `assists` | Official credited assists (AST), including EuroLeague assists that lead to free throws. |
| `steals` | `NUMERIC` | Yes |  | `steals` | Official credited steals (STL). |
| `turnovers` | `NUMERIC` | Yes |  | `turnovers` | Lost possessions charged to the player or team (TOV). |
| `blocks` | `NUMERIC` | Yes |  | `blocks` | Opponent field-goal attempts blocked by the player or team (BLK). |
| `blocks_against` | `NUMERIC` | Yes |  | `blocksAgainst` | The player's or team's field-goal attempts blocked by opponents. |
| `fouls_committed` | `NUMERIC` | Yes |  | `foulsCommited` | Personal fouls charged to the player or team (PF). |
| `fouls_drawn` | `NUMERIC` | Yes |  | `foulsDrawn` | Opponent fouls drawn by the player or team. |
| `pir` | `NUMERIC` | Yes |  | `pir` | Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## season_player_stats_advanced

**Purpose:** Source player advanced statistics by phase and mode.

**Grain:** one entry ordinal-phase-mode.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `mode`, `entry_ordinal`.

**Upstream:** `v3/season_stats/players_advanced_{phase}_{mode}`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_season_player_stats_advanced`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_advanced).

**Notes:** API rows only, including nonqualified players only where the feed lists them. No Gold qualification flags, missing perGame fallback, or synthetic PS. Transferred players can have a semicolon-separated multi-club code rather than one club identity. Percentages retain source scale; see the shared glossary.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `mode` | `TEXT` | No | PK | `@mode` | accumulated or perGame as provided by the API; Silver does not synthesize missing perGame rows. |
| `entry_ordinal` | `INTEGER` | No | PK | `@entry_ordinal` | Zero-based entry position within this category, phase and mode, not a stable player identity. |
| `person_key` | `TEXT` | No |  | `@person_key` | Season person identity used by box scores and registrations; bridge to career person_code through silver.people. |
| `club_code` | `TEXT` | Yes |  | `@club_code` | Source player-team code, possibly semicolon-separated for a transfer (for example BAS;TEL). Such multi-club values are not one clubs row. |
| `player_name` | `TEXT` | Yes |  | `player.name` | Source player name attached to the season statistics or live event row. |
| `player_age` | `INTEGER` | Yes |  | `player.age` | Age reported in the source season feed, not recalculated current age. |
| `player_image_url` | `TEXT` | Yes |  | `player.imageUrl` | Source player portrait URL. |
| `club_name` | `TEXT` | Yes |  | `player.team.name` | Club display name for this season or row. |
| `club_tv_codes` | `TEXT` | Yes |  | `player.team.tvCodes` | Source team television abbreviations. |
| `club_image_url` | `TEXT` | Yes |  | `player.team.imageUrl` | Source team image URL for the season feed. |
| `player_ranking` | `INTEGER` | Yes |  | `playerRanking` | Source leaderboard ranking; calculated perGame rows have NULL. |
| `games_played` | `NUMERIC` | Yes |  | `gamesPlayed` | Source games count within the selected phase and mode; no Silver-derived season snapshots. |
| `minutes_played` | `NUMERIC` | Yes |  | `minutesPlayed` | Playing time in minutes in season feeds; traditional perGame rows use minutes per appearance. |
| `effective_field_goal_percentage` | `NUMERIC` | Yes |  | `effectiveFieldGoalPercentage` | API eFG percentage on the 0-100 scale; calculated efg_pct uses a fraction instead. |
| `true_shooting_percentage` | `NUMERIC` | Yes |  | `trueShootingPercentage` | API true-shooting percentage on the 0-100 scale; calculated ts_pct/true_shooting_pct use fractions. |
| `offensive_rebounds_percentage` | `NUMERIC` | Yes |  | `offensiveReboundsPercentage` | API offensive rebound percentage on the 0-100 scale, retaining source team-minute conventions. |
| `defensive_rebounds_percentage` | `NUMERIC` | Yes |  | `defensiveReboundsPercentage` | API defensive rebound percentage on the 0-100 scale, retaining source team-minute conventions. |
| `rebounds_percentage` | `NUMERIC` | Yes |  | `reboundsPercentage` | API total rebound percentage on the 0-100 scale, retaining source team-minute conventions. |
| `assists_to_turnovers_ratio` | `NUMERIC` | Yes |  | `assistsToTurnoversRatio` | API assists-to-turnovers ratio (AST/TOV), retained as supplied including source zero-denominator handling. |
| `assists_ratio` | `NUMERIC` | Yes |  | `assistsRatio` | API assists ratio, retained without recomputation; denominator differs from calculated assist_ratio/ast_pct. |
| `turnovers_ratio` | `NUMERIC` | Yes |  | `turnoversRatio` | API turnovers ratio, retained without recomputation; not calculated tov_pct. |
| `two_point_attempts_ratio` | `NUMERIC` | Yes |  | `twoPointAttemptsRatio` | API two-point attempt ratio; exact denominator and scale are not established by the warehouse. |
| `three_point_attempts_ratio` | `NUMERIC` | Yes |  | `threePointAttemptsRatio` | API three-point attempt ratio; exact denominator and scale are not established by the warehouse. |
| `free_throws_rate` | `NUMERIC` | Yes |  | `freeThrowsRate` | API free-throw rate; definition differs from calculated FTM/FGA ft_rate. Do not substitute it. |
| `possessions` | `NUMERIC` | Yes |  | `possesions` | Calculated team rows: average of both club box-score estimates. Season player API rows: source possessions measure with a separate definition. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## season_player_stats_scoring

**Purpose:** Source player scoring statistics by phase and mode.

**Grain:** one entry ordinal-phase-mode.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `mode`, `entry_ordinal`.

**Upstream:** `v3/season_stats/players_scoring_{phase}_{mode}`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_season_player_stats_scoring`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_scoring).

**Notes:** API rows only, including nonqualified players only where the feed lists them. No Gold qualification flags, missing perGame fallback, or synthetic PS. Transferred players can have a semicolon-separated multi-club code rather than one club identity. Percentages retain source scale; see the shared glossary.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `mode` | `TEXT` | No | PK | `@mode` | accumulated or perGame as provided by the API; Silver does not synthesize missing perGame rows. |
| `entry_ordinal` | `INTEGER` | No | PK | `@entry_ordinal` | Zero-based entry position within this category, phase and mode, not a stable player identity. |
| `person_key` | `TEXT` | No |  | `@person_key` | Season person identity used by box scores and registrations; bridge to career person_code through silver.people. |
| `club_code` | `TEXT` | Yes |  | `@club_code` | Source player-team code, possibly semicolon-separated for a transfer (for example BAS;TEL). Such multi-club values are not one clubs row. |
| `player_name` | `TEXT` | Yes |  | `player.name` | Source player name attached to the season statistics or live event row. |
| `player_age` | `INTEGER` | Yes |  | `player.age` | Age reported in the source season feed, not recalculated current age. |
| `player_image_url` | `TEXT` | Yes |  | `player.imageUrl` | Source player portrait URL. |
| `club_name` | `TEXT` | Yes |  | `player.team.name` | Club display name for this season or row. |
| `club_tv_codes` | `TEXT` | Yes |  | `player.team.tvCodes` | Source team television abbreviations. |
| `club_image_url` | `TEXT` | Yes |  | `player.team.imageUrl` | Source team image URL for the season feed. |
| `player_ranking` | `INTEGER` | Yes |  | `playerRanking` | Source leaderboard ranking; calculated perGame rows have NULL. |
| `games_played` | `NUMERIC` | Yes |  | `gamesPlayed` | Source games count within the selected phase and mode; no Silver-derived season snapshots. |
| `games_started` | `NUMERIC` | Yes |  | `gamesStarted` | Games in which the player started; cumulative appearance count or retained feed count. |
| `two_point_attempts_share` | `NUMERIC` | Yes |  | `twoPointAttemptsShare` | API two-point attempt share; denominator and scale are not established by the warehouse. |
| `three_point_attempts_share` | `NUMERIC` | Yes |  | `threePointAttemptsShare` | API three-point attempt share; denominator and scale are not established by the warehouse. |
| `free_throws_attempts_share` | `NUMERIC` | Yes |  | `freeThrowsAttemptsShare` | API free-throw attempt share; denominator and scale are not established by the warehouse. |
| `two_pointers_made_share` | `NUMERIC` | Yes |  | `twoPointersMadeShare` | API two-point makes share; denominator and scale are not established by the warehouse. |
| `three_pointers_made_share` | `NUMERIC` | Yes |  | `threePointersMadeShare` | API three-point makes share; denominator and scale are not established by the warehouse. |
| `free_throws_made_share` | `NUMERIC` | Yes |  | `freeThrowsMadeShare` | API free-throw makes share; denominator and scale are not established by the warehouse. |
| `two_point_rate` | `NUMERIC` | Yes |  | `twoPointRate` | API two-point rate; denominator and scale are not established by the warehouse. |
| `three_point_rate` | `NUMERIC` | Yes |  | `threePointRate` | API three-point rate; denominator and scale are not established by the warehouse. |
| `points_from_two_pointers_percentage` | `NUMERIC` | Yes |  | `pointsFromTwoPointersPercentage` | API percentage of points from two-pointers, 0-100 scale. |
| `points_from_three_pointers_percentage` | `NUMERIC` | Yes |  | `pointsFromThreePointersPercentage` | API percentage of points from three-pointers, 0-100 scale. |
| `points_from_free_throws_percentage` | `NUMERIC` | Yes |  | `pointsFromFreeThrowsPercentage` | API percentage of points from free throws, 0-100 scale. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## season_player_stats_misc

**Purpose:** Source player misc statistics by phase and mode.

**Grain:** one entry ordinal-phase-mode.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `mode`, `entry_ordinal`.

**Upstream:** `v3/season_stats/players_misc_{phase}_{mode}`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_season_player_stats_misc`](GOLD_TABLE_REFERENCE.md#app_season_player_stats_misc).

**Notes:** API rows only, including nonqualified players only where the feed lists them. No Gold qualification flags, missing perGame fallback, or synthetic PS. Transferred players can have a semicolon-separated multi-club code rather than one club identity. Percentages retain source scale; see the shared glossary.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `mode` | `TEXT` | No | PK | `@mode` | accumulated or perGame as provided by the API; Silver does not synthesize missing perGame rows. |
| `entry_ordinal` | `INTEGER` | No | PK | `@entry_ordinal` | Zero-based entry position within this category, phase and mode, not a stable player identity. |
| `person_key` | `TEXT` | No |  | `@person_key` | Season person identity used by box scores and registrations; bridge to career person_code through silver.people. |
| `club_code` | `TEXT` | Yes |  | `@club_code` | Source player-team code, possibly semicolon-separated for a transfer (for example BAS;TEL). Such multi-club values are not one clubs row. |
| `player_name` | `TEXT` | Yes |  | `player.name` | Source player name attached to the season statistics or live event row. |
| `player_age` | `INTEGER` | Yes |  | `player.age` | Age reported in the source season feed, not recalculated current age. |
| `player_image_url` | `TEXT` | Yes |  | `player.imageUrl` | Source player portrait URL. |
| `club_name` | `TEXT` | Yes |  | `player.team.name` | Club display name for this season or row. |
| `club_tv_codes` | `TEXT` | Yes |  | `player.team.tvCodes` | Source team television abbreviations. |
| `club_image_url` | `TEXT` | Yes |  | `player.team.imageUrl` | Source team image URL for the season feed. |
| `player_ranking` | `INTEGER` | Yes |  | `playerRanking` | Source leaderboard ranking; calculated perGame rows have NULL. |
| `games_played` | `NUMERIC` | Yes |  | `gamesPlayed` | Source games count within the selected phase and mode; no Silver-derived season snapshots. |
| `games_started` | `NUMERIC` | Yes |  | `gamesStarted` | Games in which the player started; cumulative appearance count or retained feed count. |
| `wins` | `NUMERIC` | Yes |  | `wins` | Games won in this row's scope; source player misc values follow the API. |
| `losses` | `NUMERIC` | Yes |  | `losses` | Games lost in this row's scope; source player misc values follow the API. |
| `minutes_played` | `NUMERIC` | Yes |  | `minutesPlayed` | Playing time in minutes in season feeds; traditional perGame rows use minutes per appearance. |
| `double_doubles` | `NUMERIC` | Yes |  | `doubleDoubles` | Source count of games reaching ten in at least two categories; derived PS uses points, rebounds, assists, steals and blocks. |
| `triple_doubles` | `NUMERIC` | Yes |  | `tripleDoubles` | Source count of games reaching ten in at least three categories; derived PS uses points, rebounds, assists, steals and blocks. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## season_team_stats_traditional

**Purpose:** Source team traditional reference statistics.

**Grain:** one club-phase-mode.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `mode`, `club_code`.

**Upstream:** `v3/season_stats/teams_traditional_{phase}_{mode}`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** No direct projection; API cross-checks for calculated round statistics.

**Notes:** Local-only API reference feed, no direct Gold/Neon table. Current Gold cross-checks read own-team traditional/advanced accumulated feeds; opponent feeds are retained references. Do not substitute source ratio definitions for calculated Gold ratios.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `mode` | `TEXT` | No | PK | `@mode` | accumulated or perGame as provided by the API; Silver does not synthesize missing perGame rows. |
| `club_code` | `TEXT` | No | PK | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `club_name` | `TEXT` | Yes |  | `team.name` | Club display name for this season or row. |
| `club_tv_codes` | `TEXT` | Yes |  | `team.tvCodes` | Source team television abbreviations. |
| `club_image_url` | `TEXT` | Yes |  | `team.imageUrl` | Source team image URL for the season feed. |
| `team_ranking` | `INTEGER` | Yes |  | `teamRanking` | API team leaderboard ranking in the selected feed, phase and mode. |
| `games_played` | `NUMERIC` | Yes |  | `gamesPlayed` | Source games count within the selected phase and mode; no Silver-derived season snapshots. |
| `minutes_played` | `NUMERIC` | Yes |  | `minutesPlayed` | Playing time in minutes in season feeds; traditional perGame rows use minutes per appearance. |
| `points` | `NUMERIC` | Yes |  | `pointsScored` | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |
| `two_pointers_made` | `NUMERIC` | Yes |  | `twoPointersMade` | Successful two-point field goals (2PM). |
| `two_pointers_attempted` | `NUMERIC` | Yes |  | `twoPointersAttempted` | Two-point field-goal attempts (2PA), including makes. |
| `two_pointers_percentage` | `NUMERIC` | Yes |  | `twoPointersPercentage` | Two-point shooting percentage, 100 * 2PM / 2PA, on the feed's 0-100 scale. |
| `three_pointers_made` | `NUMERIC` | Yes |  | `threePointersMade` | Successful three-point field goals (3PM). |
| `three_pointers_attempted` | `NUMERIC` | Yes |  | `threePointersAttempted` | Three-point field-goal attempts (3PA), including makes. |
| `three_pointers_percentage` | `NUMERIC` | Yes |  | `threePointersPercentage` | Three-point shooting percentage, 100 * 3PM / 3PA, on the feed's 0-100 scale. |
| `free_throws_made` | `NUMERIC` | Yes |  | `freeThrowsMade` | Successful free throws (FTM). |
| `free_throws_attempted` | `NUMERIC` | Yes |  | `freeThrowsAttempted` | Free-throw attempts (FTA), including makes. |
| `free_throws_percentage` | `NUMERIC` | Yes |  | `freeThrowsPercentage` | Free-throw shooting percentage, 100 * FTM / FTA, on the feed's 0-100 scale. |
| `offensive_rebounds` | `NUMERIC` | Yes |  | `offensiveRebounds` | Rebounds recovered after the player's or club's missed shot (OREB). |
| `defensive_rebounds` | `NUMERIC` | Yes |  | `defensiveRebounds` | Rebounds recovered after the opponent's missed shot (DREB). |
| `total_rebounds` | `NUMERIC` | Yes |  | `totalRebounds` | Offensive plus defensive rebounds (REB); official team totals can include team rebounds. |
| `assists` | `NUMERIC` | Yes |  | `assists` | Official credited assists (AST), including EuroLeague assists that lead to free throws. |
| `steals` | `NUMERIC` | Yes |  | `steals` | Official credited steals (STL). |
| `turnovers` | `NUMERIC` | Yes |  | `turnovers` | Lost possessions charged to the player or team (TOV). |
| `blocks` | `NUMERIC` | Yes |  | `blocks` | Opponent field-goal attempts blocked by the player or team (BLK). |
| `blocks_against` | `NUMERIC` | Yes |  | `blocksAgainst` | The player's or team's field-goal attempts blocked by opponents. |
| `fouls_committed` | `NUMERIC` | Yes |  | `foulsCommited` | Personal fouls charged to the player or team (PF). |
| `fouls_drawn` | `NUMERIC` | Yes |  | `foulsDrawn` | Opponent fouls drawn by the player or team. |
| `pir` | `NUMERIC` | Yes |  | `pir` | Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## season_team_stats_advanced

**Purpose:** Source team advanced reference statistics.

**Grain:** one club-phase-mode.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `mode`, `club_code`.

**Upstream:** `v3/season_stats/teams_advanced_{phase}_{mode}`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** No direct projection; API cross-checks for calculated round statistics.

**Notes:** Local-only API reference feed, no direct Gold/Neon table. Current Gold cross-checks read own-team traditional/advanced accumulated feeds; opponent feeds are retained references. Do not substitute source ratio definitions for calculated Gold ratios.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `mode` | `TEXT` | No | PK | `@mode` | accumulated or perGame as provided by the API; Silver does not synthesize missing perGame rows. |
| `club_code` | `TEXT` | No | PK | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `club_name` | `TEXT` | Yes |  | `team.name` | Club display name for this season or row. |
| `club_tv_codes` | `TEXT` | Yes |  | `team.tvCodes` | Source team television abbreviations. |
| `club_image_url` | `TEXT` | Yes |  | `team.imageUrl` | Source team image URL for the season feed. |
| `team_ranking` | `INTEGER` | Yes |  | `teamRanking` | API team leaderboard ranking in the selected feed, phase and mode. |
| `games_played` | `NUMERIC` | Yes |  | `gamesPlayed` | Source games count within the selected phase and mode; no Silver-derived season snapshots. |
| `effective_field_goal_percentage` | `NUMERIC` | Yes |  | `effectiveFieldGoalPercentage` | API eFG percentage on the 0-100 scale; calculated efg_pct uses a fraction instead. |
| `true_shooting_percentage` | `NUMERIC` | Yes |  | `trueShootingPercentage` | API true-shooting percentage on the 0-100 scale; calculated ts_pct/true_shooting_pct use fractions. |
| `offensive_rebounds_percentage` | `NUMERIC` | Yes |  | `offensiveReboundsPercentage` | API offensive rebound percentage on the 0-100 scale, retaining source team-minute conventions. |
| `defensive_rebounds_percentage` | `NUMERIC` | Yes |  | `defensiveReboundsPercentage` | API defensive rebound percentage on the 0-100 scale, retaining source team-minute conventions. |
| `rebounds_percentage` | `NUMERIC` | Yes |  | `reboundsPercentage` | API total rebound percentage on the 0-100 scale, retaining source team-minute conventions. |
| `assists_to_turnovers_ratio` | `NUMERIC` | Yes |  | `assistsToTurnoversRatio` | API assists-to-turnovers ratio (AST/TOV), retained as supplied including source zero-denominator handling. |
| `assists_ratio` | `NUMERIC` | Yes |  | `assistsRatio` | API assists ratio, retained without recomputation; denominator differs from calculated assist_ratio/ast_pct. |
| `turnovers_ratio` | `NUMERIC` | Yes |  | `turnoversRatio` | API turnovers ratio, retained without recomputation; not calculated tov_pct. |
| `two_point_rate` | `NUMERIC` | Yes |  | `twoPointRate` | API two-point rate; denominator and scale are not established by the warehouse. |
| `three_point_rate` | `NUMERIC` | Yes |  | `threePointRate` | API three-point rate; denominator and scale are not established by the warehouse. |
| `free_throws_rate` | `NUMERIC` | Yes |  | `freeThrowsRate` | API free-throw rate; definition differs from calculated FTM/FGA ft_rate. Do not substitute it. |
| `points_from_two_pointers_percentage` | `NUMERIC` | Yes |  | `pointsFromTwoPointersPercentage` | API percentage of points from two-pointers, 0-100 scale. |
| `points_from_three_pointers_percentage` | `NUMERIC` | Yes |  | `pointsFromThreePointersPercentage` | API percentage of points from three-pointers, 0-100 scale. |
| `points_from_free_throws_percentage` | `NUMERIC` | Yes |  | `pointsFromFreeThrowsPercentage` | API percentage of points from free throws, 0-100 scale. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## season_team_stats_opponents_traditional

**Purpose:** Source opponent traditional reference statistics.

**Grain:** one club-phase-mode.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `mode`, `club_code`.

**Upstream:** `v3/season_stats/teams_opponents_traditional_{phase}_{mode}`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** No direct projection; retained opponent reference, not read by current Gold round API checks.

**Notes:** Local-only API reference feed, no direct Gold/Neon table. Current Gold cross-checks read own-team traditional/advanced accumulated feeds; opponent feeds are retained references. Do not substitute source ratio definitions for calculated Gold ratios.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `mode` | `TEXT` | No | PK | `@mode` | accumulated or perGame as provided by the API; Silver does not synthesize missing perGame rows. |
| `club_code` | `TEXT` | No | PK | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `club_name` | `TEXT` | Yes |  | `team.name` | Club display name for this season or row. |
| `club_tv_codes` | `TEXT` | Yes |  | `team.tvCodes` | Source team television abbreviations. |
| `club_image_url` | `TEXT` | Yes |  | `team.imageUrl` | Source team image URL for the season feed. |
| `team_ranking` | `INTEGER` | Yes |  | `teamRanking` | API team leaderboard ranking in the selected feed, phase and mode. |
| `games_played` | `NUMERIC` | Yes |  | `gamesPlayed` | Source games count within the selected phase and mode; no Silver-derived season snapshots. |
| `minutes_played` | `NUMERIC` | Yes |  | `minutesPlayed` | Playing time in minutes in season feeds; traditional perGame rows use minutes per appearance. |
| `points` | `NUMERIC` | Yes |  | `pointsScored` | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |
| `two_pointers_made` | `NUMERIC` | Yes |  | `twoPointersMade` | Successful two-point field goals (2PM). |
| `two_pointers_attempted` | `NUMERIC` | Yes |  | `twoPointersAttempted` | Two-point field-goal attempts (2PA), including makes. |
| `two_pointers_percentage` | `NUMERIC` | Yes |  | `twoPointersPercentage` | Two-point shooting percentage, 100 * 2PM / 2PA, on the feed's 0-100 scale. |
| `three_pointers_made` | `NUMERIC` | Yes |  | `threePointersMade` | Successful three-point field goals (3PM). |
| `three_pointers_attempted` | `NUMERIC` | Yes |  | `threePointersAttempted` | Three-point field-goal attempts (3PA), including makes. |
| `three_pointers_percentage` | `NUMERIC` | Yes |  | `threePointersPercentage` | Three-point shooting percentage, 100 * 3PM / 3PA, on the feed's 0-100 scale. |
| `free_throws_made` | `NUMERIC` | Yes |  | `freeThrowsMade` | Successful free throws (FTM). |
| `free_throws_attempted` | `NUMERIC` | Yes |  | `freeThrowsAttempted` | Free-throw attempts (FTA), including makes. |
| `free_throws_percentage` | `NUMERIC` | Yes |  | `freeThrowsPercentage` | Free-throw shooting percentage, 100 * FTM / FTA, on the feed's 0-100 scale. |
| `offensive_rebounds` | `NUMERIC` | Yes |  | `offensiveRebounds` | Rebounds recovered after the player's or club's missed shot (OREB). |
| `defensive_rebounds` | `NUMERIC` | Yes |  | `defensiveRebounds` | Rebounds recovered after the opponent's missed shot (DREB). |
| `total_rebounds` | `NUMERIC` | Yes |  | `totalRebounds` | Offensive plus defensive rebounds (REB); official team totals can include team rebounds. |
| `assists` | `NUMERIC` | Yes |  | `assists` | Official credited assists (AST), including EuroLeague assists that lead to free throws. |
| `steals` | `NUMERIC` | Yes |  | `steals` | Official credited steals (STL). |
| `turnovers` | `NUMERIC` | Yes |  | `turnovers` | Lost possessions charged to the player or team (TOV). |
| `blocks` | `NUMERIC` | Yes |  | `blocks` | Opponent field-goal attempts blocked by the player or team (BLK). |
| `blocks_against` | `NUMERIC` | Yes |  | `blocksAgainst` | The player's or team's field-goal attempts blocked by opponents. |
| `fouls_committed` | `NUMERIC` | Yes |  | `foulsCommited` | Personal fouls charged to the player or team (PF). |
| `fouls_drawn` | `NUMERIC` | Yes |  | `foulsDrawn` | Opponent fouls drawn by the player or team. |
| `pir` | `NUMERIC` | Yes |  | `pir` | Official Performance Index Rating; source valuation, distinct from PER and Game Score. See player glossary. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## season_team_stats_opponents_advanced

**Purpose:** Source opponent advanced reference statistics.

**Grain:** one club-phase-mode.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `mode`, `club_code`.

**Upstream:** `v3/season_stats/teams_opponents_advanced_{phase}_{mode}`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** No direct projection; retained opponent reference, not read by current Gold round API checks.

**Notes:** Local-only API reference feed, no direct Gold/Neon table. Current Gold cross-checks read own-team traditional/advanced accumulated feeds; opponent feeds are retained references. Do not substitute source ratio definitions for calculated Gold ratios.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `mode` | `TEXT` | No | PK | `@mode` | accumulated or perGame as provided by the API; Silver does not synthesize missing perGame rows. |
| `club_code` | `TEXT` | No | PK | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `club_name` | `TEXT` | Yes |  | `team.name` | Club display name for this season or row. |
| `club_tv_codes` | `TEXT` | Yes |  | `team.tvCodes` | Source team television abbreviations. |
| `club_image_url` | `TEXT` | Yes |  | `team.imageUrl` | Source team image URL for the season feed. |
| `team_ranking` | `INTEGER` | Yes |  | `teamRanking` | API team leaderboard ranking in the selected feed, phase and mode. |
| `games_played` | `NUMERIC` | Yes |  | `gamesPlayed` | Source games count within the selected phase and mode; no Silver-derived season snapshots. |
| `effective_field_goal_percentage` | `NUMERIC` | Yes |  | `effectiveFieldGoalPercentage` | API eFG percentage on the 0-100 scale; calculated efg_pct uses a fraction instead. |
| `true_shooting_percentage` | `NUMERIC` | Yes |  | `trueShootingPercentage` | API true-shooting percentage on the 0-100 scale; calculated ts_pct/true_shooting_pct use fractions. |
| `offensive_rebounds_percentage` | `NUMERIC` | Yes |  | `offensiveReboundsPercentage` | API offensive rebound percentage on the 0-100 scale, retaining source team-minute conventions. |
| `defensive_rebounds_percentage` | `NUMERIC` | Yes |  | `defensiveReboundsPercentage` | API defensive rebound percentage on the 0-100 scale, retaining source team-minute conventions. |
| `rebounds_percentage` | `NUMERIC` | Yes |  | `reboundsPercentage` | API total rebound percentage on the 0-100 scale, retaining source team-minute conventions. |
| `assists_to_turnovers_ratio` | `NUMERIC` | Yes |  | `assistsToTurnoversRatio` | API assists-to-turnovers ratio (AST/TOV), retained as supplied including source zero-denominator handling. |
| `assists_ratio` | `NUMERIC` | Yes |  | `assistsRatio` | API assists ratio, retained without recomputation; denominator differs from calculated assist_ratio/ast_pct. |
| `turnovers_ratio` | `NUMERIC` | Yes |  | `turnoversRatio` | API turnovers ratio, retained without recomputation; not calculated tov_pct. |
| `two_point_rate` | `NUMERIC` | Yes |  | `twoPointRate` | API two-point rate; denominator and scale are not established by the warehouse. |
| `three_point_rate` | `NUMERIC` | Yes |  | `threePointRate` | API three-point rate; denominator and scale are not established by the warehouse. |
| `free_throws_rate` | `NUMERIC` | Yes |  | `freeThrowsRate` | API free-throw rate; definition differs from calculated FTM/FGA ft_rate. Do not substitute it. |
| `points_from_two_pointers_percentage` | `NUMERIC` | Yes |  | `pointsFromTwoPointersPercentage` | API percentage of points from two-pointers, 0-100 scale. |
| `points_from_three_pointers_percentage` | `NUMERIC` | Yes |  | `pointsFromThreePointersPercentage` | API percentage of points from three-pointers, 0-100 scale. |
| `points_from_free_throws_percentage` | `NUMERIC` | Yes |  | `pointsFromFreeThrowsPercentage` | API percentage of points from free throws, 0-100 scale. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## standings_basic

**Purpose:** Official positions, wins/losses, points and record splits.

**Grain:** one club-phase-round.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `round_number`, `club_code`.

**Upstream:** `v3/standings/{phase}_{round}_basicstandings`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings), merged/normalized into one page row.

**Notes:** All measures are source snapshots; they can differ from Gold game-derived cumulative totals.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `round_number` | `INTEGER` | No | PK | `@round_number` | Source game or standings round number; not a cumulative snapshot created by Silver. |
| `club_code` | `TEXT` | No | PK | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `club_name` | `TEXT` | Yes |  | `club.name` | Club display name for this season or row. |
| `club_tv_code` | `TEXT` | Yes |  | `club.tvCode` | Source club television abbreviation. |
| `group_name` | `TEXT` | Yes |  | `groupName` | Source group display name. |
| `position` | `INTEGER` | Yes |  | `position` | Standings rank in standings tables; player position code in profile, registration and box-score tables. |
| `position_change` | `TEXT` | Yes |  | `positionChange` | Source standings position movement label, retained as text. |
| `games_played` | `INTEGER` | Yes |  | `gamesPlayed` | Source games count within the selected phase and mode; no Silver-derived season snapshots. |
| `games_won` | `INTEGER` | Yes |  | `gamesWon` | Source number of games won at this standings snapshot. |
| `games_lost` | `INTEGER` | Yes |  | `gamesLost` | Source number of games lost at this standings snapshot. |
| `qualified` | `BOOLEAN` | Yes |  | `qualified` | Official standings feed qualification flag, not player leaderboard eligibility. |
| `win_percentage` | `NUMERIC` | Yes |  | `winPercentage` | Source win percentage retained as supplied; verify scale before formatting. |
| `points_difference` | `INTEGER` | Yes |  | `pointsDifference` | Source points for minus points against in this standings snapshot. |
| `points_for` | `INTEGER` | Yes |  | `pointsFor` | Points scored by this club or lineup in the row's game, stint or cumulative scope. |
| `points_against` | `INTEGER` | Yes |  | `pointsAgainst` | Points conceded by this club or lineup in the same sample. |
| `home_record` | `TEXT` | Yes |  | `homeRecord` | Source win-loss record text for home record; preserve its text format. |
| `away_record` | `TEXT` | Yes |  | `awayRecord` | Source win-loss record text for away record; preserve its text format. |
| `neutral_record` | `TEXT` | Yes |  | `neutralRecord` | Source win-loss record text for neutral record; preserve its text format. |
| `overtime_record` | `TEXT` | Yes |  | `overtimeRecord` | Source win-loss record text for overtime record; preserve its text format. |
| `last_ten_record` | `TEXT` | Yes |  | `lastTenRecord` | Source win-loss record text for last ten record; preserve its text format. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## standings_calendar

**Purpose:** Official calendar standings snapshot.

**Grain:** one club-phase-round.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `round_number`, `club_code`.

**Upstream:** `v3/standings/{phase}_{round}_calendarstandings`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings), merged/normalized into one page row.

**Notes:** Calendar streak arrays are normalized to standings_calendar_streaks.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `round_number` | `INTEGER` | No | PK | `@round_number` | Source game or standings round number; not a cumulative snapshot created by Silver. |
| `club_code` | `TEXT` | No | PK | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `club_name` | `TEXT` | Yes |  | `club.name` | Club display name for this season or row. |
| `club_tv_code` | `TEXT` | Yes |  | `club.tvCode` | Source club television abbreviation. |
| `group_name` | `TEXT` | Yes |  | `groupName` | Source group display name. |
| `position` | `INTEGER` | Yes |  | `position` | Standings rank in standings tables; player position code in profile, registration and box-score tables. |
| `position_change` | `TEXT` | Yes |  | `positionChange` | Source standings position movement label, retained as text. |
| `games_played` | `INTEGER` | Yes |  | `gamesPlayed` | Source games count within the selected phase and mode; no Silver-derived season snapshots. |
| `games_won` | `INTEGER` | Yes |  | `gamesWon` | Source number of games won at this standings snapshot. |
| `games_lost` | `INTEGER` | Yes |  | `gamesLost` | Source number of games lost at this standings snapshot. |
| `qualified` | `BOOLEAN` | Yes |  | `qualified` | Official standings feed qualification flag, not player leaderboard eligibility. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## standings_streaks

**Purpose:** Official streak and recent-form record summaries.

**Grain:** one club-phase-round.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `round_number`, `club_code`.

**Upstream:** `v3/standings/{phase}_{round}_streaks`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings), merged/normalized into one page row.

**Notes:** Record text is not a count. longest_loss column spelling is normalized here.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `round_number` | `INTEGER` | No | PK | `@round_number` | Source game or standings round number; not a cumulative snapshot created by Silver. |
| `club_code` | `TEXT` | No | PK | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `club_name` | `TEXT` | Yes |  | `club.name` | Club display name for this season or row. |
| `club_tv_code` | `TEXT` | Yes |  | `club.tvCode` | Source club television abbreviation. |
| `group_name` | `TEXT` | Yes |  | `groupName` | Source group display name. |
| `position` | `INTEGER` | Yes |  | `position` | Standings rank in standings tables; player position code in profile, registration and box-score tables. |
| `position_change` | `TEXT` | Yes |  | `positionChange` | Source standings position movement label, retained as text. |
| `games_played` | `INTEGER` | Yes |  | `gamesPlayed` | Source games count within the selected phase and mode; no Silver-derived season snapshots. |
| `games_won` | `INTEGER` | Yes |  | `gamesWon` | Source number of games won at this standings snapshot. |
| `games_lost` | `INTEGER` | Yes |  | `gamesLost` | Source number of games lost at this standings snapshot. |
| `qualified` | `BOOLEAN` | Yes |  | `qualified` | Official standings feed qualification flag, not player leaderboard eligibility. |
| `home_record` | `TEXT` | Yes |  | `homeRecord` | Source win-loss record text for home record; preserve its text format. |
| `away_record` | `TEXT` | Yes |  | `awayRecord` | Source win-loss record text for away record; preserve its text format. |
| `last10` | `TEXT` | Yes |  | `last10` | Source win-loss record text for last10; preserve its text format. |
| `home_last5` | `TEXT` | Yes |  | `homeLast5` | Source win-loss record text for home last5; preserve its text format. |
| `away_last5` | `TEXT` | Yes |  | `awayLast5` | Source win-loss record text for away last5; preserve its text format. |
| `longest_win_streak_current_season` | `INTEGER` | Yes |  | `longestWinsStreakCurrentSeason` | Source longest win streak current season, measured in games. |
| `longest_loss_streak_current_season` | `INTEGER` | Yes |  | `longestLosesStreakCurrentSeason` | Source longest lose streak current season, measured in games. |
| `longest_win_streak_any_season` | `INTEGER` | Yes |  | `longestWinsStreakAnySeason` | Source longest win streak any season, measured in games. |
| `longest_loss_streak_any_season` | `INTEGER` | Yes |  | `longestLosesStreakAnySeason` | Source longest lose streak any season, measured in games. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## standings_ahead_behind

**Purpose:** Official win-loss records by score checkpoint.

**Grain:** one club-phase-round.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `round_number`, `club_code`.

**Upstream:** `v3/standings/{phase}_{round}_aheadbehind`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings), merged/normalized into one page row.

**Notes:** Quarter-1, half-time and quarter-3 ahead/behind/tied values remain source record text.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `round_number` | `INTEGER` | No | PK | `@round_number` | Source game or standings round number; not a cumulative snapshot created by Silver. |
| `club_code` | `TEXT` | No | PK | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `club_name` | `TEXT` | Yes |  | `club.name` | Club display name for this season or row. |
| `club_tv_code` | `TEXT` | Yes |  | `club.tvCode` | Source club television abbreviation. |
| `group_name` | `TEXT` | Yes |  | `groupName` | Source group display name. |
| `position` | `INTEGER` | Yes |  | `position` | Standings rank in standings tables; player position code in profile, registration and box-score tables. |
| `position_change` | `TEXT` | Yes |  | `positionChange` | Source standings position movement label, retained as text. |
| `games_played` | `INTEGER` | Yes |  | `gamesPlayed` | Source games count within the selected phase and mode; no Silver-derived season snapshots. |
| `games_won` | `INTEGER` | Yes |  | `gamesWon` | Source number of games won at this standings snapshot. |
| `games_lost` | `INTEGER` | Yes |  | `gamesLost` | Source number of games lost at this standings snapshot. |
| `qualified` | `BOOLEAN` | Yes |  | `qualified` | Official standings feed qualification flag, not player leaderboard eligibility. |
| `wins_percentage` | `NUMERIC` | Yes |  | `winsPercentage` | Source wins percentage retained as supplied; verify scale before formatting. |
| `quarter1_ahead` | `TEXT` | Yes |  | `quater1Ahead` | Source win-loss record text for games quarter1 ahead at that checkpoint. |
| `quarter1_behind` | `TEXT` | Yes |  | `quater1Behind` | Source win-loss record text for games quarter1 behind at that checkpoint. |
| `quarter1_tied` | `TEXT` | Yes |  | `quater1Tied` | Source win-loss record text for games quarter1 tied at that checkpoint. |
| `half1_ahead` | `TEXT` | Yes |  | `half1Ahead` | Source win-loss record text for games half1 ahead at that checkpoint. |
| `half1_behind` | `TEXT` | Yes |  | `half1Behind` | Source win-loss record text for games half1 behind at that checkpoint. |
| `half1_tied` | `TEXT` | Yes |  | `half1Tied` | Source win-loss record text for games half1 tied at that checkpoint. |
| `quarter3_ahead` | `TEXT` | Yes |  | `quater3Ahead` | Source win-loss record text for games quarter3 ahead at that checkpoint. |
| `quarter3_behind` | `TEXT` | Yes |  | `quater3Behind` | Source win-loss record text for games quarter3 behind at that checkpoint. |
| `quarter3_tied` | `TEXT` | Yes |  | `quater3Tied` | Source win-loss record text for games quarter3 tied at that checkpoint. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## standings_margins

**Purpose:** Official result records by margin and statistical comparison.

**Grain:** one club-phase-round.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `round_number`, `club_code`.

**Upstream:** `v3/standings/{phase}_{round}_margins`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings), merged/normalized into one page row.

**Notes:** rebounds, assists and shooting columns here are source comparison record text, not box-score totals.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `round_number` | `INTEGER` | No | PK | `@round_number` | Source game or standings round number; not a cumulative snapshot created by Silver. |
| `club_code` | `TEXT` | No | PK | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `club_name` | `TEXT` | Yes |  | `club.name` | Club display name for this season or row. |
| `club_tv_code` | `TEXT` | Yes |  | `club.tvCode` | Source club television abbreviation. |
| `group_name` | `TEXT` | Yes |  | `groupName` | Source group display name. |
| `position` | `INTEGER` | Yes |  | `position` | Standings rank in standings tables; player position code in profile, registration and box-score tables. |
| `position_change` | `TEXT` | Yes |  | `positionChange` | Source standings position movement label, retained as text. |
| `games_played` | `INTEGER` | Yes |  | `gamesPlayed` | Source games count within the selected phase and mode; no Silver-derived season snapshots. |
| `games_won` | `INTEGER` | Yes |  | `gamesWon` | Source number of games won at this standings snapshot. |
| `games_lost` | `INTEGER` | Yes |  | `gamesLost` | Source number of games lost at this standings snapshot. |
| `qualified` | `BOOLEAN` | Yes |  | `qualified` | Official standings feed qualification flag, not player leaderboard eligibility. |
| `point_difference_1_to_5` | `TEXT` | Yes |  | `pointDifference1to5` | Source win-loss record text for games with final margin 1 to 5 points. |
| `point_difference_6_to_10` | `TEXT` | Yes |  | `pointDifference6to10` | Source win-loss record text for games with final margin 6 to 10 points. |
| `point_difference_11_to_15` | `TEXT` | Yes |  | `pointDifference11to15` | Source win-loss record text for games with final margin 11 to 15 points. |
| `point_difference_more_than_15` | `TEXT` | Yes |  | `pointDifferenceMoreThan15` | Source win-loss record text for games with final margin more than 15 points. |
| `rebounds` | `TEXT` | Yes |  | `rebounds` | Source comparison/split record text for rebounds; not a raw statistical total. |
| `assists` | `TEXT` | Yes |  | `assists` | Source statistical-comparison record text, not a box-score count. |
| `blocks` | `TEXT` | Yes |  | `blocks` | Source statistical-comparison record text, not a box-score count. |
| `three_pointers` | `TEXT` | Yes |  | `threePointers` | Source comparison/split record text for three pointers; not a raw statistical total. |
| `two_pointers` | `TEXT` | Yes |  | `twoPointers` | Source comparison/split record text for two pointers; not a raw statistical total. |
| `free_throws` | `TEXT` | Yes |  | `freeThrows` | Source comparison/split record text for free throws; not a raw statistical total. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## standings_calendar_streaks

**Purpose:** Normalized child streaks of calendar standings.

**Grain:** one streak ordinal-club-phase-round.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `round_number`, `club_code`, `streak_ordinal`.

**Upstream:** `v3/standings/{phase}_{round}_calendarstandings`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings), merged/normalized into one page row.

**Notes:** One row per streaks array element; ordinal starts at zero and is not a stable identity across refreshes.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `round_number` | `INTEGER` | No | PK | `@round_number` | Source game or standings round number; not a cumulative snapshot created by Silver. |
| `club_code` | `TEXT` | No | PK | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `streak_ordinal` | `INTEGER` | No | PK | `@streak_ordinal` | Zero-based index of the streak in the parent standings calendar row. |
| `start_at` | `TIMESTAMP` | Yes |  | `startDate` | Source start timestamp without time zone for the season or registration. |
| `end_at` | `TIMESTAMP` | Yes |  | `endDate` | Source end timestamp without time zone for the season or registration. |
| `win_loss_record` | `TEXT` | Yes |  | `winLossRecord` | Source win-loss record text for this calendar streak. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## standings_basic_form

**Purpose:** Normalized recent-result labels from basic standings.

**Grain:** one result ordinal-club-phase-round.

**Primary key:** `competition_code`, `season_code`, `phase_code`, `round_number`, `club_code`, `result_ordinal`.

**Upstream:** `v3/standings/{phase}_{round}_basicstandings`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_standings`](GOLD_TABLE_REFERENCE.md#app_standings), merged/normalized into one page row.

**Notes:** One row per last5Form array element, preserving its order. Ordinal starts at zero.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `phase_code` | `TEXT` | No | PK | `@phase_code` | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `round_number` | `INTEGER` | No | PK | `@round_number` | Source game or standings round number; not a cumulative snapshot created by Silver. |
| `club_code` | `TEXT` | No | PK | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `result_ordinal` | `INTEGER` | No | PK | `@result_ordinal` | Zero-based index of the result in the parent last5Form array. |
| `result` | `TEXT` | Yes |  | `@result` | Source recent-form result label, retained as text. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## play_by_play

**Purpose:** Raw typed live event timeline with resolved player identities.

**Grain:** one event ordinal-period-game.

**Primary key:** `competition_code`, `season_code`, `game_code`, `period`, `event_ordinal`.

**Upstream:** `live/{game}/play_by_play`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_play_by_play`](GOLD_TABLE_REFERENCE.md#app_play_by_play).

**Notes:** Source period is TEXT. Sort using regulation period rank, overtime number from minute, and event_ordinal, not alphabetical period or play_number.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | `@game_code` | Game identifier within competition and season, not globally unique. |
| `period` | `TEXT` | No | PK | `@period` | Source period label: FirstQuarter, SecondQuarter, ThirdQuarter, ForthQuarter (source spelling), or ExtraTime. Not an integer. |
| `event_ordinal` | `INTEGER` | No | PK | `@event_ordinal` | Zero-based event order within the source period array; overtime number also comes from minute. |
| `play_number` | `INTEGER` | Yes |  | `@play_number` | Source event/shot link number; it is not a reliable chronological sort key. |
| `club_code` | `TEXT` | Yes |  | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `player_code` | `TEXT` | Yes |  | `@player_code` | Raw live-feed player identifier; use resolved person_code for joins. |
| `person_code` | `TEXT` | Yes |  | `@person_code` | Person identity code in people; in live events it is the resolved box-score person_key. Preserve leading zeroes. |
| `person_code_method` | `TEXT` | Yes |  | `@person_code_method` | Recorded resolution method used to map the live player identity to a box-score person. |
| `play_type` | `TEXT` | Yes |  | `@play_type` | Live action code, for example AS, ST, TO, O, D, FTM, 2FGM or 3FGM. |
| `event_type` | `INTEGER` | Yes |  | `TYPE` | Raw live numeric event type. |
| `player_name` | `TEXT` | Yes |  | `PLAYER` | Source player name attached to the season statistics or live event row. |
| `team_name` | `TEXT` | Yes |  | `TEAM` | Team label from the live event feed. |
| `jersey_number` | `TEXT` | Yes |  | `DORSAL` | Source jersey number stored as text; retain leading zeroes and special values. |
| `minute` | `INTEGER` | Yes |  | `MINUTE` | Source live minute marker; interpret with the period and clock. |
| `marker_time` | `TEXT` | Yes |  | `MARKERTIME` | Source time remaining in the period, such as 03:24. |
| `points_a` | `INTEGER` | Yes |  | `POINTS_A` | Live running score of source side A (local). |
| `points_b` | `INTEGER` | Yes |  | `POINTS_B` | Live running score of source side B (road). |
| `comment` | `TEXT` | Yes |  | `COMMENT` | Source event comment text. |
| `play_info` | `TEXT` | Yes |  | `PLAYINFO` | Source event description text. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## shots

**Purpose:** Typed shot attempts, coordinates, zone and context flags.

**Grain:** one shot ordinal-game.

**Primary key:** `competition_code`, `season_code`, `game_code`, `shot_ordinal`.

**Upstream:** `live/{game}/shooting_charts`.

**Producer:** [postgres_etl/raw_transform.py](../postgres_etl/raw_transform.py).

**Gold use:** [`app_shots`](GOLD_TABLE_REFERENCE.md#app_shots).

**Notes:** person_code resolves to the game box-score person_key; raw player_code remains separate. Source coordinate units/orientation are not standardized by the warehouse.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | `@competition_code` | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | `@season_code` | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | `@game_code` | Game identifier within competition and season, not globally unique. |
| `shot_ordinal` | `INTEGER` | No | PK | `@shot_ordinal` | Zero-based position in the game response Rows array. |
| `play_number` | `INTEGER` | Yes |  | `@play_number` | Source event/shot link number; it is not a reliable chronological sort key. |
| `club_code` | `TEXT` | Yes |  | `@club_code` | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `player_code` | `TEXT` | Yes |  | `@player_code` | Raw live-feed player identifier; use resolved person_code for joins. |
| `person_code` | `TEXT` | Yes |  | `@person_code` | Person identity code in people; in live events it is the resolved box-score person_key. Preserve leading zeroes. |
| `person_code_method` | `TEXT` | Yes |  | `@person_code_method` | Recorded resolution method used to map the live player identity to a box-score person. |
| `player_name` | `TEXT` | Yes |  | `PLAYER` | Source player name attached to the season statistics or live event row. |
| `action_code` | `TEXT` | Yes |  | `ID_ACTION` | Source shot action code; distinguishes made/missed field goals and other shot actions. |
| `action` | `TEXT` | Yes |  | `ACTION` | Source shot action label. |
| `points` | `INTEGER` | Yes |  | `@points` | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |
| `coord_x` | `NUMERIC` | Yes |  | `@coord_x` | Shot x coordinate in the source coordinate system; no warehouse court-unit contract. |
| `coord_y` | `NUMERIC` | Yes |  | `@coord_y` | Shot y coordinate in the source coordinate system; no warehouse court-unit contract. |
| `zone` | `TEXT` | Yes |  | `ZONE` | Source shot-zone label, preserved without a warehouse court taxonomy. |
| `fastbreak` | `BOOLEAN` | Yes |  | `FASTBREAK` | Source flag that the shot was a fast-break action; NULL means unrecorded. |
| `second_chance` | `BOOLEAN` | Yes |  | `SECOND_CHANCE` | Source flag that the shot followed an offensive rebound; NULL means unrecorded. |
| `points_off_turnover` | `BOOLEAN` | Yes |  | `POINTS_OFF_TURNOVER` | Boolean source flag for a shot after a turnover; it is not a points count. |
| `minute` | `INTEGER` | Yes |  | `MINUTE` | Source live minute marker; interpret with the period and clock. |
| `console_time` | `TEXT` | Yes |  | `CONSOLE` | Clock text attached to a shot in the live feed. |
| `points_a` | `INTEGER` | Yes |  | `POINTS_A` | Live running score of source side A (local). |
| `points_b` | `INTEGER` | Yes |  | `POINTS_B` | Live running score of source side B (road). |
| `shot_at` | `TIMESTAMPTZ` | Yes |  | `UTC` | Source shot time with time zone. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## game_team_advanced

**Purpose:** Box-score estimated possessions, pace, ratings and four factors.

**Grain:** one side-game.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`.

**Upstream:** `games, game_period_scores, game_team_stats, game_stat_gaps`.

**Producer:** [postgres_etl/advanced.py](../postgres_etl/advanced.py).

**Gold use:** [`app_game_team_advanced`](GOLD_TABLE_REFERENCE.md#app_game_team_advanced); team/player round calculations, game PER context.

**Notes:** Played games with both total box-score rows only; forfeits without box scores excluded. Gold drops opponent_club_code, phase_code, round_number and provenance.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Derived from Silver | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | Derived from Silver | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Derived from Silver | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Derived from Silver | Source side, local or road; local is not proof of a non-neutral home venue. |
| `club_code` | `TEXT` | Yes |  | Derived from Silver | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `opponent_club_code` | `TEXT` | Yes |  | Derived from Silver | Opposing club in the game. |
| `phase_code` | `TEXT` | Yes |  | Derived from Silver | Source phase code such as RS, TS, PI, PO or FF; season statistics also have all. Silver adds no synthetic PS rows. |
| `round_number` | `INTEGER` | Yes |  | Derived from Silver | Source game or standings round number; not a cumulative snapshot created by Silver. |
| `game_minutes` | `NUMERIC` | Yes |  | Derived from Silver | Game-clock minutes, 40 plus 5 per overtime; cumulative sum in team-round rows, not player-minutes. |
| `possessions` | `NUMERIC` | Yes |  | Derived from Silver | Calculated team rows: average of both club box-score estimates. Season player API rows: source possessions measure with a separate definition. |
| `own_possessions_estimate` | `NUMERIC` | Yes |  | Derived from Silver | Club box-score estimate: FGA + 0.44 * FTA - OREB + TOV. |
| `pace` | `NUMERIC` | Yes |  | Derived from Silver | 40 * estimated possessions / game_minutes, possessions per regulation-length team game. |
| `offensive_rating` | `NUMERIC` | Yes |  | Derived from Silver | 100 * points_for / estimated possessions, points scored per 100 possessions. |
| `defensive_rating` | `NUMERIC` | Yes |  | Derived from Silver | 100 * points_against / estimated possessions, points allowed per 100 possessions; lower is better. |
| `net_rating` | `NUMERIC` | Yes |  | Derived from Silver | Offensive rating minus defensive rating; points per 100 possessions. Lineup rows use counted possessions separately on each side. |
| `efg_pct` | `NUMERIC` | Yes |  | Derived from Silver | (FGM + 0.5 * 3PM) / FGA, a fraction that can exceed 1. |
| `tov_pct` | `NUMERIC` | Yes |  | Derived from Silver | TOV / (FGA + 0.44 * FTA + TOV), a fraction. |
| `orb_pct` | `NUMERIC` | Yes |  | Derived from Silver | Offensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. |
| `drb_pct` | `NUMERIC` | Yes |  | Derived from Silver | Defensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. |
| `ft_rate` | `NUMERIC` | Yes |  | Derived from Silver | FTM / FGA, made free throws per field-goal attempt; not FTA / FGA. |
| `opp_efg_pct` | `NUMERIC` | Yes |  | Derived from Silver | Opponent total: (FGM + 0.5 * 3PM) / FGA, a fraction that can exceed 1. |
| `opp_tov_pct` | `NUMERIC` | Yes |  | Derived from Silver | Opponent total: TOV / (FGA + 0.44 * FTA + TOV), a fraction. |
| `opp_ft_rate` | `NUMERIC` | Yes |  | Derived from Silver | Opponent total: FTM / FGA, made free throws per field-goal attempt; not FTA / FGA. |
| `true_shooting_pct` | `NUMERIC` | Yes |  | Derived from Silver | PTS / (2 * (FGA + 0.44 * FTA)), a fraction that can exceed 1. |
| `assist_ratio` | `NUMERIC` | Yes |  | Derived from Silver | AST / FGM in calculated team tables; not the API assists_ratio. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## game_player_advanced

**Purpose:** Player Game Score, efficiency and on-court/estimated rates.

**Grain:** one player-side-game.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`, `person_key`.

**Upstream:** `games, game_period_scores, game_team_stats, game_player_stats, game_stat_gaps, play_by_play`.

**Producer:** [postgres_etl/advanced.py](../postgres_etl/advanced.py).

**Gold use:** [`app_game_player_advanced`](GOLD_TABLE_REFERENCE.md#app_game_player_advanced); app_player_round_stats Game Score totals.

**Notes:** Seven time-dependent rates use on-court events when possible; rate_source identifies the method. Estimate rates are NULL below 180 seconds. Gold drops rate_source and adds game PER; Silver has no PER columns.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Derived from Silver | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | Derived from Silver | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Derived from Silver | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Derived from Silver | Source side, local or road; local is not proof of a non-neutral home venue. |
| `person_key` | `TEXT` | No | PK | Derived from Silver | Season person identity used by box scores and registrations; bridge to career person_code through silver.people. |
| `club_code` | `TEXT` | Yes |  | Derived from Silver | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `seconds_played` | `NUMERIC` | Yes |  | Derived from Silver | Official playing time in seconds; player seconds or aggregate team player-seconds in box scores. |
| `game_score` | `NUMERIC` | Yes |  | Derived from Silver | Hollinger Game Score from the player's game box score; see the exact weighted formula in the glossary. |
| `true_shooting_pct` | `NUMERIC` | Yes |  | Derived from Silver | PTS / (2 * (FGA + 0.44 * FTA)), a fraction that can exceed 1. |
| `efg_pct` | `NUMERIC` | Yes |  | Derived from Silver | (FGM + 0.5 * 3PM) / FGA, a fraction that can exceed 1. |
| `usage_pct` | `NUMERIC` | Yes |  | Derived from Silver | Player share of used plays; actual on-court denominator when available, otherwise the game box-score estimate. |
| `assist_pct` | `NUMERIC` | Yes |  | Derived from Silver | Player share of teammate scoring chances; on-court calculation also includes eligible free-throw trips. |
| `orb_pct` | `NUMERIC` | Yes |  | Derived from Silver | Offensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. |
| `drb_pct` | `NUMERIC` | Yes |  | Derived from Silver | Defensive rebound share, a fraction; team, player estimated and player on-court denominators differ. See glossary. |
| `trb_pct` | `NUMERIC` | Yes |  | Derived from Silver | Total rebound share, a fraction; see glossary for player context and denominators. |
| `steal_pct` | `NUMERIC` | Yes |  | Derived from Silver | Player steals / opponent possessions while on court (counted events or time-share estimate). |
| `block_pct` | `NUMERIC` | Yes |  | Derived from Silver | Player blocks / opponent two-point attempts while on court (counted events or time-share estimate). |
| `tov_pct` | `NUMERIC` | Yes |  | Derived from Silver | TOV / (FGA + 0.44 * FTA + TOV), a fraction. |
| `rate_source` | `TEXT` | Yes |  | Derived from Silver | on_court when rates use the on-court event walk, otherwise estimate. This field remains local to Silver. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## game_team_possessions

**Purpose:** Counted possessions and their measurable lengths.

**Grain:** one side-game.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`.

**Upstream:** `games, game_team_advanced, play_by_play`.

**Producer:** [postgres_etl/possessions.py](../postgres_etl/possessions.py).

**Gold use:** [`app_game_team_possessions`](GOLD_TABLE_REFERENCE.md#app_game_team_possessions); app_team_pbp_stats.

**Notes:** Event state machine counts possessions separately from the shared box-score estimate. Requires usable events and an advanced team row.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Derived from Silver | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | Derived from Silver | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Derived from Silver | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Derived from Silver | Source side, local or road; local is not proof of a non-neutral home venue. |
| `club_code` | `TEXT` | Yes |  | Derived from Silver | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `opponent_club_code` | `TEXT` | Yes |  | Derived from Silver | Opposing club in the game. |
| `counted_possessions` | `INTEGER` | Yes |  | Derived from Silver | Team possessions closed by the play-by-play state machine; summed in season-scope aggregates. |
| `possession_seconds` | `NUMERIC` | Yes |  | Derived from Silver | Sum of measurable possession durations in seconds, not necessarily all game-clock seconds. |
| `avg_possession_seconds` | `NUMERIC` | Yes |  | Derived from Silver | Game: timed seconds / timed possession count. Team aggregate: game averages weighted by counted possessions. |
| `estimated_possessions` | `NUMERIC` | Yes |  | Derived from Silver | Shared box-score possessions estimate copied for comparison; summed in season-scope aggregates. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## game_team_score_flow

**Purpose:** Running-score leads, runs, time ahead/behind and clutch.

**Grain:** one side-game.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`.

**Upstream:** `games, play_by_play`.

**Producer:** [postgres_etl/score_flow.py](../postgres_etl/score_flow.py).

**Gold use:** [`app_game_team_score_flow`](GOLD_TABLE_REFERENCE.md#app_game_team_score_flow); app_team_pbp_stats.

**Notes:** Lead changes and ties repeat on both side rows. Clutch starts at elapsed second 2100 with pre-event margin at most five; overtime is included.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Derived from Silver | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | Derived from Silver | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Derived from Silver | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Derived from Silver | Source side, local or road; local is not proof of a non-neutral home venue. |
| `club_code` | `TEXT` | Yes |  | Derived from Silver | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `opponent_club_code` | `TEXT` | Yes |  | Derived from Silver | Opposing club in the game. |
| `points_for` | `INTEGER` | Yes |  | Derived from Silver | Points scored by this club or lineup in the row's game, stint or cumulative scope. |
| `points_against` | `INTEGER` | Yes |  | Derived from Silver | Points conceded by this club or lineup in the same sample. |
| `lead_changes` | `INTEGER` | Yes |  | Derived from Silver | Times the leading team changes; identical on the two game-side rows. |
| `ties` | `INTEGER` | Yes |  | Derived from Silver | Times the score becomes level above 0-0; identical on the two game-side rows. |
| `time_leading_seconds` | `NUMERIC` | Yes |  | Derived from Silver | Game-clock seconds the team led; summed over timed games in aggregate rows. |
| `time_trailing_seconds` | `NUMERIC` | Yes |  | Derived from Silver | Game-clock seconds the team trailed; summed over timed games in aggregate rows. |
| `time_tied_seconds` | `NUMERIC` | Yes |  | Derived from Silver | Game-clock seconds the score was tied, including 0-0; summed over timed games in aggregates. |
| `largest_lead` | `INTEGER` | Yes |  | Derived from Silver | Largest positive team margin in a game; maximum across games in season-scope aggregates. |
| `longest_run` | `INTEGER` | Yes |  | Derived from Silver | Most unanswered points scored in a game; maximum across games in season-scope aggregates. |
| `runs_6_plus` | `INTEGER` | Yes |  | Derived from Silver | Number of unanswered scoring runs of at least six points; summed across games in aggregates. |
| `clutch_seconds` | `NUMERIC` | Yes |  | Derived from Silver | Seconds from elapsed second 2100 through game end (including overtime) with margin at most five points. |
| `clutch_points_for` | `INTEGER` | Yes |  | Derived from Silver | Team points scored from second 2100 onward when the pre-scoring margin is at most five points. |
| `clutch_points_against` | `INTEGER` | Yes |  | Derived from Silver | Opponent points scored from second 2100 onward when the pre-scoring margin is at most five points. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## game_team_shot_splits

**Purpose:** Flagged scoring and capped assisted-field-goal counts.

**Grain:** one side-game.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`.

**Upstream:** `games, shots, play_by_play`.

**Producer:** [postgres_etl/shot_splits.py](../postgres_etl/shot_splits.py).

**Gold use:** [`app_game_team_shot_splits`](GOLD_TABLE_REFERENCE.md#app_game_team_shot_splits); app_team_pbp_stats.

**Notes:** Missing flags make all three flagged point totals NULL. assisted_field_goals = min(AS events, made FG events), not shot-by-shot matching.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Derived from Silver | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | Derived from Silver | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Derived from Silver | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Derived from Silver | Source side, local or road; local is not proof of a non-neutral home venue. |
| `club_code` | `TEXT` | Yes |  | Derived from Silver | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `opponent_club_code` | `TEXT` | Yes |  | Derived from Silver | Opposing club in the game. |
| `fast_break_points` | `INTEGER` | Yes |  | Derived from Silver | Sum of positive shot points tagged fastbreak, including any flagged made free throws; NULL when flags are unrecorded. |
| `second_chance_points` | `INTEGER` | Yes |  | Derived from Silver | Sum of positive shot points tagged second_chance, including any flagged made free throws; NULL when flags are unrecorded. |
| `points_off_turnover_points` | `INTEGER` | Yes |  | Derived from Silver | Sum of positive shot points tagged points_off_turnover, including any flagged made free throws; distinct from the Boolean shot flag. |
| `field_goals_made` | `INTEGER` | Yes |  | Derived from Silver | Successful two- and three-point field goals (FGM), excluding free throws. |
| `assisted_field_goals` | `INTEGER` | Yes |  | Derived from Silver | min(team AS event count, team made-field-goal event count); summed in aggregates, not shot-by-shot matching. |
| `assisted_fg_pct` | `NUMERIC` | Yes |  | Derived from Silver | assisted_field_goals / field_goals_made, a fraction. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## game_team_shot_zones

**Purpose:** Field-goal attempts, makes and points by source zone.

**Grain:** one side-zone-game.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`, `zone`.

**Upstream:** `games, shots`.

**Producer:** [postgres_etl/shot_zones.py](../postgres_etl/shot_zones.py).

**Gold use:** [`app_game_team_shot_zones`](GOLD_TABLE_REFERENCE.md#app_game_team_shot_zones); app_team_shot_zone_stats.

**Notes:** Field goals with a nonempty zone only. Zones with no attempts have no row.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Derived from Silver | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | Derived from Silver | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Derived from Silver | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Derived from Silver | Source side, local or road; local is not proof of a non-neutral home venue. |
| `zone` | `TEXT` | No | PK | Derived from Silver | Source shot-zone label, preserved without a warehouse court taxonomy. |
| `club_code` | `TEXT` | Yes |  | Derived from Silver | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `attempts` | `INTEGER` | Yes |  | Derived from Silver | Field-goal attempts in this source zone, including makes. |
| `made` | `INTEGER` | Yes |  | Derived from Silver | Successful field goals in this source zone. |
| `points` | `INTEGER` | Yes |  | Derived from Silver | Scored points; in shots this is points awarded for that shot, and in zone tables points from the zone. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## game_player_on_court

**Purpose:** Reconstructed continuous player on-court stretches.

**Grain:** one interval ordinal-player-side-game.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`, `person_key`, `interval_ordinal`.

**Upstream:** `games, game_player_stats, play_by_play`.

**Producer:** [postgres_etl/on_court.py](../postgres_etl/on_court.py).

**Gold use:** [`app_game_player_on_court`](GOLD_TABLE_REFERENCE.md#app_game_player_on_court).

**Notes:** Uses starters and IN/OUT substitutions in event order. Times are elapsed game seconds; zero-length intervals are dropped.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Derived from Silver | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | Derived from Silver | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Derived from Silver | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Derived from Silver | Source side, local or road; local is not proof of a non-neutral home venue. |
| `person_key` | `TEXT` | No | PK | Derived from Silver | Season person identity used by box scores and registrations; bridge to career person_code through silver.people. |
| `interval_ordinal` | `INTEGER` | No | PK | Derived from Silver | On-court interval number for this player-side-game, starting at 1. |
| `club_code` | `TEXT` | Yes |  | Derived from Silver | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `start_seconds` | `INTEGER` | Yes |  | Derived from Silver | Interval or stint start in elapsed game seconds from tipoff. |
| `end_seconds` | `INTEGER` | Yes |  | Derived from Silver | Interval or stint end in elapsed game seconds; duration is end minus start. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## game_team_lineup_stints

**Purpose:** Complete five-versus-five intervals with scoring and possessions.

**Grain:** one stint ordinal-side-game.

**Primary key:** `competition_code`, `season_code`, `game_code`, `side`, `stint_ordinal`.

**Upstream:** `games, game_player_stats, play_by_play`.

**Producer:** [postgres_etl/lineups.py](../postgres_etl/lineups.py).

**Gold use:** [`app_game_team_lineup_stints`](GOLD_TABLE_REFERENCE.md#app_game_team_lineup_stints); app_player_on_off, app_lineup_ratings, app_player_rapm.

**Notes:** Uses the same event walk as on_court, with both lineups complete; does not simply join stored player interval rows. Incomplete portions are excluded.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Derived from Silver | Competition identifier; this catalog covers EuroLeague rows with E. |
| `season_code` | `TEXT` | No | PK | Derived from Silver | Starting-year EuroLeague season code, for example E2025 for 2025-26. |
| `game_code` | `INTEGER` | No | PK | Derived from Silver | Game identifier within competition and season, not globally unique. |
| `side` | `TEXT` | No | PK | Derived from Silver | Source side, local or road; local is not proof of a non-neutral home venue. |
| `stint_ordinal` | `INTEGER` | No | PK | Derived from Silver | Stored lineup stint number within the game, starting at 1. |
| `club_code` | `TEXT` | Yes |  | Derived from Silver | Club code for this row; joins clubs using competition_code, season_code and club_code. |
| `opponent_club_code` | `TEXT` | Yes |  | Derived from Silver | Opposing club in the game. |
| `start_seconds` | `INTEGER` | Yes |  | Derived from Silver | Interval or stint start in elapsed game seconds from tipoff. |
| `end_seconds` | `INTEGER` | Yes |  | Derived from Silver | Interval or stint end in elapsed game seconds; duration is end minus start. |
| `players` | `TEXT` | Yes |  | Derived from Silver | Sorted comma-separated person_key values for the team's five players. |
| `opponent_players` | `TEXT` | Yes |  | Derived from Silver | Sorted comma-separated person_key values for the opposing five players. |
| `possessions_for` | `INTEGER` | Yes |  | Derived from Silver | Team counted possessions closed during these stints. |
| `possessions_against` | `INTEGER` | Yes |  | Derived from Silver | Opponent counted possessions closed during these stints. |
| `points_for` | `INTEGER` | Yes |  | Derived from Silver | Points scored by this club or lineup in the row's game, stint or cumulative scope. |
| `points_against` | `INTEGER` | Yes |  | Derived from Silver | Points conceded by this club or lineup in the same sample. |
| `load_id` | `UUID` | No |  | Load writer | UUID of the successful table/competition/season replacement; joins load_log with the table name and scope. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load timestamp shared by rows written by this replacement; not the source fetch time. |

[Silver catalog](SILVER_CATALOG.md) | [Statistics glossary](STAT_GLOSSARY.md)

## load_log

**Purpose:** Append-only history of successful data-table scope replacements.

**Grain:** one successful table/competition/season/load ID.

**Primary key:** `competition_code`, `season_code`, `table_name`, `load_id`.

**Producer:** Source and calculated-table writers; schema is create_load_log_sql in [flat_schema.py](../postgres_etl/flat_schema.py).

**Notes:** Log and rows commit together. Old log entries remain after a rerun. Failed replacements roll back both. Derived loads record [] rather than exact upstream Silver load IDs.

| Column | PostgreSQL type | Nullable | Key | Source / derivation | Description |
| --- | --- | --- | --- | --- | --- |
| `competition_code` | `TEXT` | No | PK | Load writer | EuroLeague competition identifier E. |
| `season_code` | `TEXT` | No | PK | Load writer | Starting-year season code of the replacement. |
| `table_name` | `TEXT` | No | PK | Load writer | Logical Silver data-table name whose scope was replaced. |
| `load_id` | `UUID` | No | PK | Load writer | UUID identifying this successful replacement; retained across later loads. |
| `loaded_at` | `TIMESTAMPTZ` | No |  | Load writer | UTC load time recorded by the writer. |
| `row_count` | `BIGINT` | No |  | Load writer | Rows inserted by this replacement, including zero. |
| `bronze_versions` | `JSONB` | No |  | Load writer | Sorted, deduplicated array of exact source version paths relative to data/bronze/; [] for calculated tables. |

## Keeping this reference current

Compare data columns, keys and indexes with ALL_TABLES and provenance with PROVENANCE_COLUMNS in flat_schema.py; load_log is declared separately by create_load_log_sql. Verify source paths against RawSeason/FlatSeason and formulas against the producing module. Update the shared glossary rather than duplicating formula explanations in each layer. This Markdown is maintained in the repository; it is not refreshed automatically.

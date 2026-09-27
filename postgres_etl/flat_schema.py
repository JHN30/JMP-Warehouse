"""Column-first analytical schema for the cached v2, v3, and live responses.

Repeated objects (quarters, overtime, streaks) get child rows rather than many
mostly-NULL columns on their parent.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    name: str
    kind: str
    path: str


@dataclass(frozen=True)
class Table:
    source: str
    key: tuple[str, ...]
    fields: tuple[Field, ...]
    indexes: tuple[tuple[str, ...], ...] = ()


COLUMN_NAMES = {
    "assistances": "assists", "fouls_commited": "fouls_committed",
    "fouls_received": "fouls_drawn", "blocks_favour": "blocks",
    "valuation": "pir", "field_goals_made2": "two_pointers_made",
    "field_goals_attempted2": "two_pointers_attempted",
    "field_goals_made3": "three_pointers_made",
    "field_goals_attempted3": "three_pointers_attempted",
    "field_goals_made_total": "field_goals_made",
    "field_goals_attempted_total": "field_goals_attempted",
    "points_scored": "points", "time_played": "seconds_played",
    "possesions": "possessions", "dorsal": "jersey_number",
    "dorsal_raw": "jersey_number_raw",
    "longest_wins_streak_current_season": "longest_win_streak_current_season",
    "longest_loses_streak_current_season": "longest_loss_streak_current_season",
    "longest_wins_streak_any_season": "longest_win_streak_any_season",
    "longest_loses_streak_any_season": "longest_loss_streak_any_season",
    "point_difference1to5": "point_difference_1_to_5",
    "point_difference6to10": "point_difference_6_to_10",
    "point_difference11to15": "point_difference_11_to_15",
    "point_difference_more_than15": "point_difference_more_than_15",
    **{f"quater{quarter}_{state}": f"quarter{quarter}_{state}"
       for quarter in (1, 3) for state in ("ahead", "behind", "tied")},
}


def f(name, kind, path=None):
    return Field(COLUMN_NAMES.get(name, name), kind, path or name)


def snake(value):
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    return re.sub(r"([a-z\d])([A-Z])", r"\1_\2", value).lower()


def keys(names, kind, path_prefix="", column_prefix=""):
    return tuple(f(column_prefix + snake(name), kind, path_prefix + name)
                 for name in names.split())


SCOPE = (f("competition_code", "TEXT NOT NULL", "@competition_code"),
         f("season_code", "TEXT NOT NULL", "@season_code"))


def table(source, key, *groups, indexes=()):
    fields = SCOPE + tuple(field for group in groups for field in group)
    names = [field.name for field in fields]
    if len(names) != len(set(names)):
        raise ValueError(f"Duplicate columns in {source}: {names}")
    return Table(source, ("competition_code", "season_code") + tuple(key), fields,
                 tuple(tuple(index) for index in indexes))


PERSON_DETAILS = (
    f("alias", "TEXT"), f("alias_raw", "TEXT", "aliasRaw"),
    f("passport_name", "TEXT", "passportName"),
    f("passport_surname", "TEXT", "passportSurname"),
    f("jersey_name", "TEXT", "jerseyName"),
    f("abbreviated_name", "TEXT", "abbreviatedName"),
    f("country_code", "TEXT", "country.code"),
    f("country_name", "TEXT", "country.name"),
    f("height_cm", "INTEGER", "height"),
    f("weight_kg", "INTEGER", "weight"),
    f("birth_at", "TIMESTAMP", "birthDate"),
    f("birth_country_code", "TEXT", "birthCountry.code"),
    f("birth_country_name", "TEXT", "birthCountry.name"),
    f("twitter_account", "TEXT", "twitterAccount"),
    f("instagram_account", "TEXT", "instagramAccount"),
    f("facebook_account", "TEXT", "facebookAccount"),
    f("is_referee", "BOOLEAN", "isReferee"),
)

GAME_STATS = keys(
    "timePlayed valuation fieldGoalsMade2 fieldGoalsAttempted2 fieldGoalsMade3 "
    "fieldGoalsAttempted3 freeThrowsMade freeThrowsAttempted fieldGoalsMadeTotal "
    "fieldGoalsAttemptedTotal accuracyMade accuracyAttempted totalRebounds "
    "defensiveRebounds offensiveRebounds assistances steals turnovers "
    "blocksFavour blocksAgainst foulsCommited foulsReceived plusMinus", "NUMERIC",
)

STATS_IDENTITY = (
    f("phase_code", "TEXT NOT NULL", "@phase_code"),
    f("mode", "TEXT NOT NULL", "@mode"),
    f("entry_ordinal", "INTEGER NOT NULL", "@entry_ordinal"),
    f("person_key", "TEXT NOT NULL", "@person_key"),
    f("club_code", "TEXT", "@club_code"),
    f("player_name", "TEXT", "player.name"),
    f("player_age", "INTEGER", "player.age"),
    f("player_image_url", "TEXT", "player.imageUrl"),
    f("club_name", "TEXT", "player.team.name"),
    f("club_tv_codes", "TEXT", "player.team.tvCodes"),
    f("club_image_url", "TEXT", "player.team.imageUrl"),
    f("player_ranking", "INTEGER", "playerRanking"),
)

STANDINGS_IDENTITY = (
    f("phase_code", "TEXT NOT NULL", "@phase_code"),
    f("round_number", "INTEGER NOT NULL", "@round_number"),
    f("club_code", "TEXT NOT NULL", "@club_code"),
    f("club_name", "TEXT", "club.name"),
    f("club_tv_code", "TEXT", "club.tvCode"),
    f("group_name", "TEXT", "groupName"),
    f("position", "INTEGER", "position"),
    f("position_change", "TEXT", "positionChange"),
    f("games_played", "INTEGER", "gamesPlayed"),
    f("games_won", "INTEGER", "gamesWon"),
    f("games_lost", "INTEGER", "gamesLost"),
    f("qualified", "BOOLEAN", "qualified"),
)


TABLES = {
    "seasons": table("seasons", (), (
        f("name", "TEXT", "@name"), f("start_year", "INTEGER", "@start_year"),
        f("alias", "TEXT"), f("competition_name", "TEXT", "name"),
        f("start_at", "TIMESTAMP", "startDate"),
        f("activation_at", "TIMESTAMP", "activationDate"),
        f("end_at", "TIMESTAMP", "endDate"),
        f("champion_club_code", "TEXT", "@champion_club_code"),
        f("champion_club_name", "TEXT", "winner.name"),
    )),
    "clubs": table("clubs", ("club_code",), (
        f("club_code", "TEXT NOT NULL", "@club_code"), f("name", "TEXT", "@name"),
        f("abbreviated_name", "TEXT", "abbreviatedName"),
        f("editorial_name", "TEXT", "editorialName"),
        f("tv_code", "TEXT", "tvCode"), f("is_virtual", "BOOLEAN", "isVirtual"),
        f("crest_url", "TEXT", "images.crest"), f("sponsor", "TEXT"),
        f("permanent_name", "TEXT", "clubPermanentName"),
        f("permanent_alias", "TEXT", "clubPermanentAlias"),
        f("country_code", "TEXT", "country.code"),
        f("country_name", "TEXT", "country.name"),
        f("address", "TEXT"), f("website", "TEXT"),
        f("tickets_url", "TEXT", "ticketsUrl"),
        f("twitter_account", "TEXT", "twitterAccount"),
        f("venue_code", "TEXT", "venueCode"), f("city", "TEXT"),
        f("president", "TEXT"), f("phone", "TEXT"),
    )),
    "people": table("people", ("person_key",), (
        f("person_key", "TEXT NOT NULL", "@person_key"),
        f("person_code", "TEXT", "@person_code"),
        f("name", "TEXT", "@name"),
    ), PERSON_DETAILS, indexes=(("person_code",),)),
    "registrations": table("registrations", ("registration_key",), (
        f("registration_key", "TEXT NOT NULL", "@registration_key"),
        f("person_key", "TEXT NOT NULL", "@person_key"),
        f("club_code", "TEXT", "@club_code"),
        f("role_code", "TEXT", "@role_code"),
        f("role_name", "TEXT", "typeName"),
        f("active", "BOOLEAN", "@active"),
        f("start_at", "TIMESTAMP", "startDate"),
        f("end_at", "TIMESTAMP", "endDate"),
        f("sort_order", "INTEGER", "order"),
        f("dorsal", "TEXT"), f("dorsal_raw", "TEXT", "dorsalRaw"),
        f("position", "INTEGER"), f("position_name", "TEXT", "positionName"),
        f("last_team", "TEXT", "lastTeam"),
        f("external_id", "INTEGER", "externalId"),
        f("person_name", "TEXT", "person.name"),
        f("club_name", "TEXT", "club.name"),
    ), indexes=(("person_key",), ("club_code",))),
    "rounds": table("rounds", ("round_key",), (
        f("round_key", "TEXT NOT NULL", "@round_key"),
        f("phase_code", "TEXT NOT NULL", "@phase_code"),
        f("round_number", "INTEGER NOT NULL", "@round_number"),
        f("round_index", "INTEGER", "index"),
        f("name", "TEXT", "@name"),
        f("first_game_at", "TIMESTAMP", "minGameStartDate"),
        f("last_game_at", "TIMESTAMP", "maxGameStartDate"),
        f("formatted_dates", "TEXT", "datesFormmated"),
    ), indexes=(("phase_code", "round_number"),)),
    "games": table("games", ("game_code",), (
        f("game_code", "INTEGER NOT NULL", "@game_code"),
        f("source_id", "TEXT", "id"), f("identifier", "TEXT"),
        f("phase_code", "TEXT", "@phase_code"),
        f("phase_name", "TEXT", "phaseType.name"),
        f("phase_alias", "TEXT", "phaseType.alias"),
        f("phase_is_group", "BOOLEAN", "phaseType.isGroupPhase"),
        f("group_id", "TEXT", "group.id"),
        f("group_name", "TEXT", "group.name"),
        f("group_raw_name", "TEXT", "group.rawName"),
        f("group_order", "INTEGER", "group.order"),
        f("round_number", "INTEGER", "@round_number"),
        f("round_name", "TEXT", "roundName"),
        f("round_alias", "TEXT", "roundAlias"),
        f("scheduled_at", "TIMESTAMPTZ", "@scheduled_at"),
        f("source_date", "TEXT", "date"),
        f("local_date", "TIMESTAMP", "localDate"),
        f("local_time_zone_minutes", "INTEGER", "localTimeZone"),
        f("played", "BOOLEAN", "@played"),
        f("game_status", "TEXT", "gameStatus"),
        f("status", "TEXT", "@status"),
        f("status_note", "TEXT", "@status_note"),
        f("confirmed_date", "BOOLEAN", "confirmedDate"),
        f("confirmed_hour", "BOOLEAN", "confirmedHour"),
        f("local_club_code", "TEXT", "@local_club_code"),
        f("local_club_name", "TEXT", "local.club.name"),
        f("local_club_abbreviated_name", "TEXT", "local.club.abbreviatedName"),
        f("local_club_tv_code", "TEXT", "local.club.tvCode"),
        f("road_club_code", "TEXT", "@road_club_code"),
        f("road_club_name", "TEXT", "road.club.name"),
        f("road_club_abbreviated_name", "TEXT", "road.club.abbreviatedName"),
        f("road_club_tv_code", "TEXT", "road.club.tvCode"),
        f("local_score", "INTEGER", "@local_score"),
        f("road_score", "INTEGER", "@road_score"),
        f("local_standings_score", "INTEGER", "@local_standings_score"),
        f("road_standings_score", "INTEGER", "@road_standings_score"),
        f("match_winner_club_code", "TEXT", "@match_winner_club_code"),
        f("champion_club_code", "TEXT", "@champion_club_code"),
        f("champion_club_name", "TEXT", "winner.name"),
        f("audience", "INTEGER", "@audience"), f("audience_note", "TEXT", "@audience_note"),
        f("audience_confirmed", "BOOLEAN", "audienceConfirmed"),
        f("venue_code", "TEXT", "venue.code"),
        f("venue_name", "TEXT", "venue.name"),
        f("venue_capacity", "INTEGER", "venue.capacity"),
        f("venue_address", "TEXT", "venue.address"),
        f("venue_active", "BOOLEAN", "venue.active"),
        f("venue_notes", "TEXT", "venue.notes"),
        f("is_neutral_venue", "BOOLEAN", "isNeutralVenue"),
        f("social_feed", "TEXT", "socialFeed"),
        f("operations_code", "TEXT", "operationsCode"),
    ), indexes=(("scheduled_at",), ("local_club_code",), ("road_club_code",))),
    "game_officials": table("game_officials", ("game_code", "official_number"), (
        f("game_code", "INTEGER NOT NULL", "@game_code"),
        f("official_number", "INTEGER NOT NULL", "@official_number"),
        f("official_code", "TEXT", "@official_code"),
        f("name", "TEXT", "@name"), f("alias", "TEXT"),
        f("country_code", "TEXT", "country.code"),
        f("country_name", "TEXT", "country.name"),
        f("active", "BOOLEAN"),
        f("image_vertical_small", "TEXT", "images.verticalSmall"),
    ), indexes=(("official_code",),)),
    "game_period_scores": table("game_period_scores", ("game_code", "side", "period_number"), (
        f("game_code", "INTEGER NOT NULL", "@game_code"),
        f("side", "TEXT NOT NULL", "@side"),
        f("period_number", "INTEGER NOT NULL", "@period_number"),
        f("score", "INTEGER", "@score"),
    )),
    "game_player_stats": table("game_player_stats", ("game_code", "side", "person_key"), (
        f("game_code", "INTEGER NOT NULL", "@game_code"),
        f("side", "TEXT NOT NULL", "@side"),
        f("person_key", "TEXT NOT NULL", "@person_key"),
        f("club_code", "TEXT", "@club_code"),
        f("person_name", "TEXT", "player.person.name"),
        f("club_name", "TEXT", "player.club.name"),
        f("player_type_code", "TEXT", "player.type"),
        f("registration_active", "BOOLEAN", "player.active"),
        f("registration_start_at", "TIMESTAMP", "player.startDate"),
        f("registration_end_at", "TIMESTAMP", "player.endDate"),
        f("position", "INTEGER", "player.position"),
        f("position_name", "TEXT", "player.positionName"),
        f("dorsal", "TEXT", "player.dorsal"),
        f("external_id", "INTEGER", "player.externalId"),
        f("headshot_url", "TEXT", "player.images.headshot"),
        f("points", "NUMERIC", "@points"),
    ), tuple(f(field.name, field.kind, "stats." + field.path) for field in GAME_STATS), (
        f("started", "BOOLEAN", "stats.startFive"),
        f("started_alt", "BOOLEAN", "stats.startFive2"),
    ), indexes=(("person_key",), ("club_code",))),
    "game_team_stats": table("game_team_stats", ("game_code", "side", "stats_kind"), (
        f("game_code", "INTEGER NOT NULL", "@game_code"),
        f("side", "TEXT NOT NULL", "@side"),
        f("stats_kind", "TEXT NOT NULL", "@stats_kind"),
        f("coach_code", "TEXT", "@coach_code"),
        f("coach_name", "TEXT", "@coach_name"),
        f("points", "NUMERIC"),
    ), tuple(field for field in GAME_STATS if field.name != "points")),
    "game_stat_gaps": table("game_stat_gaps", ("game_code", "stat_name"), (
        f("game_code", "INTEGER NOT NULL", "@game_code"),
        f("stat_name", "TEXT NOT NULL", "@stat_name"),
        f("reason", "TEXT", "@reason"),
    )),
    "play_by_play": table("play_by_play", ("game_code", "period", "event_ordinal"), (
        f("game_code", "INTEGER NOT NULL", "@game_code"),
        f("period", "TEXT NOT NULL", "@period"),
        f("event_ordinal", "INTEGER NOT NULL", "@event_ordinal"),
        f("play_number", "INTEGER", "@play_number"),
        f("club_code", "TEXT", "@club_code"),
        f("player_code", "TEXT", "@player_code"),
        f("person_code", "TEXT", "@person_code"),
        f("person_code_method", "TEXT", "@person_code_method"),
        f("play_type", "TEXT", "@play_type"),
        f("event_type", "INTEGER", "TYPE"),
        f("player_name", "TEXT", "PLAYER"),
        f("team_name", "TEXT", "TEAM"),
        f("dorsal", "TEXT", "DORSAL"),
        f("minute", "INTEGER", "MINUTE"),
        f("marker_time", "TEXT", "MARKERTIME"),
        f("points_a", "INTEGER", "POINTS_A"),
        f("points_b", "INTEGER", "POINTS_B"),
        f("comment", "TEXT", "COMMENT"),
        f("play_info", "TEXT", "PLAYINFO"),
    ), indexes=(("game_code", "play_number"), ("person_code",))),
    "shots": table("shots", ("game_code", "shot_ordinal"), (
        f("game_code", "INTEGER NOT NULL", "@game_code"),
        f("shot_ordinal", "INTEGER NOT NULL", "@shot_ordinal"),
        f("play_number", "INTEGER", "@play_number"),
        f("club_code", "TEXT", "@club_code"),
        f("player_code", "TEXT", "@player_code"),
        f("person_code", "TEXT", "@person_code"),
        f("person_code_method", "TEXT", "@person_code_method"),
        f("player_name", "TEXT", "PLAYER"),
        f("action_code", "TEXT", "ID_ACTION"),
        f("action", "TEXT", "ACTION"),
        f("points", "INTEGER", "@points"),
        f("coord_x", "NUMERIC", "@coord_x"),
        f("coord_y", "NUMERIC", "@coord_y"),
        f("zone", "TEXT", "ZONE"),
        f("fastbreak", "BOOLEAN", "FASTBREAK"),
        f("second_chance", "BOOLEAN", "SECOND_CHANCE"),
        f("points_off_turnover", "BOOLEAN", "POINTS_OFF_TURNOVER"),
        f("minute", "INTEGER", "MINUTE"),
        f("console_time", "TEXT", "CONSOLE"),
        f("points_a", "INTEGER", "POINTS_A"),
        f("points_b", "INTEGER", "POINTS_B"),
        f("shot_at", "TIMESTAMPTZ", "UTC"),
    ), indexes=(("person_code",),)),
}

# Each v3 category/feed has its own table. This avoids large blocks of NULLs
# for metrics that do not exist in other categories or feeds.
PLAYER_METRICS = {
    "traditional": "gamesPlayed gamesStarted minutesPlayed pointsScored twoPointersMade "
                   "twoPointersAttempted twoPointersPercentage threePointersMade "
                   "threePointersAttempted threePointersPercentage freeThrowsMade "
                   "freeThrowsAttempted freeThrowsPercentage offensiveRebounds "
                   "defensiveRebounds totalRebounds assists steals turnovers blocks "
                   "blocksAgainst foulsCommited foulsDrawn pir",
    "advanced": "gamesPlayed minutesPlayed effectiveFieldGoalPercentage "
                "trueShootingPercentage offensiveReboundsPercentage "
                "defensiveReboundsPercentage reboundsPercentage assistsToTurnoversRatio "
                "assistsRatio turnoversRatio twoPointAttemptsRatio threePointAttemptsRatio "
                "freeThrowsRate possesions",
    "scoring": "gamesPlayed gamesStarted twoPointAttemptsShare threePointAttemptsShare "
               "freeThrowsAttemptsShare twoPointersMadeShare threePointersMadeShare "
               "freeThrowsMadeShare twoPointRate threePointRate "
               "pointsFromTwoPointersPercentage pointsFromThreePointersPercentage "
               "pointsFromFreeThrowsPercentage",
    "misc": "gamesPlayed gamesStarted wins losses minutesPlayed doubleDoubles tripleDoubles",
}
for category, metrics in PLAYER_METRICS.items():
    TABLES[f"season_player_stats_{category}"] = table(
        "season_player_stats", ("phase_code", "mode", "entry_ordinal"),
        STATS_IDENTITY, keys(metrics, "NUMERIC"),
        indexes=(("person_key",), ("club_code",)),
    )

# v3 team season statistics: one row per club in each feed, phase and mode. The
# opponents feeds hold what a club's opponents did against it. Reference
# numbers, local only.
TEAM_STATS_IDENTITY = (
    f("phase_code", "TEXT NOT NULL", "@phase_code"),
    f("mode", "TEXT NOT NULL", "@mode"),
    f("club_code", "TEXT NOT NULL", "@club_code"),
    f("club_name", "TEXT", "team.name"),
    f("club_tv_codes", "TEXT", "team.tvCodes"),
    f("club_image_url", "TEXT", "team.imageUrl"),
    f("team_ranking", "INTEGER", "teamRanking"),
)
TEAM_METRICS = {
    "traditional": "gamesPlayed minutesPlayed pointsScored twoPointersMade "
                   "twoPointersAttempted twoPointersPercentage threePointersMade "
                   "threePointersAttempted threePointersPercentage freeThrowsMade "
                   "freeThrowsAttempted freeThrowsPercentage offensiveRebounds "
                   "defensiveRebounds totalRebounds assists steals turnovers blocks "
                   "blocksAgainst foulsCommited foulsDrawn pir",
    "advanced": "gamesPlayed effectiveFieldGoalPercentage trueShootingPercentage "
                "offensiveReboundsPercentage defensiveReboundsPercentage "
                "reboundsPercentage assistsToTurnoversRatio assistsRatio turnoversRatio "
                "twoPointRate threePointRate freeThrowsRate "
                "pointsFromTwoPointersPercentage pointsFromThreePointersPercentage "
                "pointsFromFreeThrowsPercentage",
}
TEAM_STATS_TABLES = tuple(f"season_team_stats_{prefix}{category}"
                          for prefix in ("", "opponents_") for category in TEAM_METRICS)
for name in TEAM_STATS_TABLES:
    TABLES[name] = table(
        "season_team_stats", ("phase_code", "mode", "club_code"),
        TEAM_STATS_IDENTITY, keys(TEAM_METRICS[name.rsplit("_", 1)[1]], "NUMERIC"),
    )

STANDINGS_METRICS = {
    "basicstandings": (
        keys("winPercentage", "NUMERIC"),
        keys("pointsDifference pointsFor pointsAgainst", "INTEGER"),
        keys("homeRecord awayRecord neutralRecord overtimeRecord lastTenRecord", "TEXT"),
    ),
    "calendarstandings": (),
    "streaks": (
        keys("homeRecord awayRecord last10 homeLast5 awayLast5", "TEXT"),
        keys("longestWinsStreakCurrentSeason longestLosesStreakCurrentSeason "
             "longestWinsStreakAnySeason longestLosesStreakAnySeason", "INTEGER"),
    ),
    "aheadbehind": (
        keys("winsPercentage", "NUMERIC"),
        keys("quater1Ahead quater1Behind quater1Tied half1Ahead half1Behind "
             "half1Tied quater3Ahead quater3Behind quater3Tied", "TEXT"),
    ),
    "margins": (
        keys("pointDifference1to5 pointDifference6to10 pointDifference11to15 "
             "pointDifferenceMoreThan15 rebounds assists blocks threePointers "
             "twoPointers freeThrows", "TEXT"),
    ),
}
STANDINGS_NAMES = {
    "basicstandings": "basic", "calendarstandings": "calendar",
    "aheadbehind": "ahead_behind",
}
for feed, groups in STANDINGS_METRICS.items():
    TABLES[f"standings_{STANDINGS_NAMES.get(feed, feed)}"] = table(
        "standings", ("phase_code", "round_number", "club_code"),
        STANDINGS_IDENTITY, *groups, indexes=(("club_code",),),
    )

TABLES["standings_calendar_streaks"] = table(
    "standings", ("phase_code", "round_number", "club_code", "streak_ordinal"), (
        f("phase_code", "TEXT NOT NULL", "@phase_code"),
        f("round_number", "INTEGER NOT NULL", "@round_number"),
        f("club_code", "TEXT NOT NULL", "@club_code"),
        f("streak_ordinal", "INTEGER NOT NULL", "@streak_ordinal"),
        f("start_at", "TIMESTAMP", "startDate"),
        f("end_at", "TIMESTAMP", "endDate"),
        f("win_loss_record", "TEXT", "winLossRecord"),
    ),
)

TABLES["standings_basic_form"] = table(
    "standings", ("phase_code", "round_number", "club_code", "result_ordinal"), (
        f("phase_code", "TEXT NOT NULL", "@phase_code"),
        f("round_number", "INTEGER NOT NULL", "@round_number"),
        f("club_code", "TEXT NOT NULL", "@club_code"),
        f("result_ordinal", "INTEGER NOT NULL", "@result_ordinal"),
        f("result", "TEXT", "@result"),
    ),
)

STANDINGS_FEED_TABLES = (
    "standings_basic", "standings_calendar",
    "standings_streaks", "standings_ahead_behind", "standings_margins",
    "standings_calendar_streaks", "standings_basic_form",
)

PUBLISHED_TABLES = ()


def physical_name(name):
    return name


def create_table_sql(name):
    spec = TABLES[name]
    columns = ", ".join(f'"{field.name}" {field.kind}' for field in spec.fields)
    key = ", ".join(f'"{column}"' for column in spec.key)
    return f'CREATE TABLE IF NOT EXISTS "{physical_name(name)}" ({columns}, PRIMARY KEY ({key}))'


def add_column_sql(name):
    """Safely add columns when a later code version enriches a flat table."""
    for field in TABLES[name].fields:
        yield (f'ALTER TABLE "{physical_name(name)}" '
               f'ADD COLUMN IF NOT EXISTS "{field.name}" {field.kind}')


def create_index_sql(name):
    for index in TABLES[name].indexes:
        columns = ", ".join(f'"{column}"' for column in index)
        suffix = "_".join(index)
        yield (f'CREATE INDEX IF NOT EXISTS "idx_flat_{name}_{suffix}" '
               f'ON "{physical_name(name)}" ({columns})')

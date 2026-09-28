"""The 16 source projections owned by the first Gold build."""

from postgres_etl.flat_schema import (COLUMN_NAMES, Field, SCOPE,
                                       STANDINGS_IDENTITY, TABLES as SILVER_TABLES,
                                       Table, snake)


SOURCE_NAMES = (
    "seasons", "clubs", "people", "registrations", "rounds", "games",
    "game_officials", "game_period_scores", "game_player_stats",
    "game_team_stats", "season_player_stats_traditional",
    "season_player_stats_advanced", "season_player_stats_scoring",
    "season_player_stats_misc", "play_by_play", "shots",
)
PLAYER_STATS = frozenset(name for name in SOURCE_NAMES
                         if name.startswith("season_player_stats_"))
TABLES = {name: SILVER_TABLES[name] for name in SOURCE_NAMES}

STANDINGS_FEEDS = (
    ("standings_basic", "basic"), ("standings_calendar", "calendar"),
    ("standings_streaks", "streaks"),
    ("standings_ahead_behind", "ahead_behind"),
    ("standings_margins", "margins"),
)
STANDINGS_CHILDREN = ("standings_basic_form", "standings_calendar_streaks")
STANDINGS_SHARED = ("position", "position_change", "games_played",
                    "games_won", "games_lost", "qualified")
STANDINGS_RENAMES = {
    "longest_loss_streak_current_season": "longest_lose_streak_current_season",
    "longest_loss_streak_any_season": "longest_lose_streak_any_season",
}


def feed_fields(name):
    """The six shared page fields plus metrics unique to this Silver feed."""
    identity_names = {field.name for field in SCOPE + STANDINGS_IDENTITY}
    metrics = tuple(field for field in SILVER_TABLES[name].fields
                    if field.name not in identity_names)
    shared = tuple(field for field in STANDINGS_IDENTITY
                   if field.name in STANDINGS_SHARED)
    return shared + metrics


STANDINGS_FIELDS = SCOPE + (
    Field("phase_code", "TEXT NOT NULL", "standings_basic.phase_code"),
    Field("round_number", "INTEGER NOT NULL", "standings_basic.round_number"),
    Field("club_code", "TEXT NOT NULL", "standings_basic.club_code"),
    Field("club_name", "TEXT", "standings_basic.club_name"),
    Field("club_tv_code", "TEXT", "standings_basic.club_tv_code"),
    Field("crest_url", "TEXT", "clubs.crest_url"),
    Field("group_name", "TEXT", "standings_basic.group_name"),
) + tuple(
    Field(f'{prefix}_{STANDINGS_RENAMES.get(field.name, field.name)}', field.kind,
          f'{name}.{field.name}')
    for name, prefix in STANDINGS_FEEDS for field in feed_fields(name)
) + (
    Field("form", "JSONB NOT NULL", "standings_basic_form"),
    Field("streak_history", "JSONB NOT NULL", "standings_calendar_streaks"),
)
STANDINGS_TABLE = Table(
    "standings_page",
    ("competition_code", "season_code", "phase_code", "round_number", "club_code"),
    STANDINGS_FIELDS,
)
TEAM_MEASURES = (
    "points", "fieldGoalsMade2", "fieldGoalsAttempted2", "fieldGoalsMade3",
    "fieldGoalsAttempted3", "freeThrowsMade", "freeThrowsAttempted",
    "fieldGoalsMadeTotal", "fieldGoalsAttemptedTotal", "totalRebounds",
    "defensiveRebounds", "offensiveRebounds", "assistances", "steals",
    "turnovers", "blocksFavour", "blocksAgainst", "foulsCommited",
    "foulsReceived", "valuation",
)
TEAM_MEASURE_COLUMNS = tuple((snake(name), COLUMN_NAMES.get(snake(name), snake(name)))
                             for name in TEAM_MEASURES)
TEAM_FIELDS = SCOPE + (
    Field("phase_code", "TEXT NOT NULL", "games.phase_code"),
    Field("club_code", "TEXT NOT NULL", "games.club_code"),
    Field("club_name", "TEXT", "clubs.name"),
    Field("games_played", "INTEGER NOT NULL", "game_team_stats"),
) + tuple(Field(f"{side}_{name}", "NUMERIC", f"game_team_stats.{source}")
          for side in ("own", "opp") for name, source in TEAM_MEASURE_COLUMNS)
TEAM_SEASON_TABLE = Table(
    "team_season_stats", ("competition_code", "season_code", "phase_code", "club_code"),
    TEAM_FIELDS,
)
COVERAGE_SEASON_TABLE = Table(
    "coverage_seasons", ("competition_code", "season_code"),
    SCOPE + (Field("items", "JSONB NOT NULL", "silver"),),
)
COVERAGE_GAME_TABLE = Table(
    "coverage_games", ("competition_code", "season_code", "game_code"),
    SCOPE + (Field("game_code", "INTEGER NOT NULL", "games.game_code"),
             Field("items", "JSONB NOT NULL", "silver")),
)
RECORDS_KEY = ("competition_code", "metric", "rank_ordinal")
RECORDS_BASE = (
    Field("competition_code", "TEXT NOT NULL", "silver"),
    Field("metric", "TEXT NOT NULL", "silver"),
    Field("rank_ordinal", "INTEGER NOT NULL", "silver"),
    Field("season_code", "TEXT NOT NULL", "silver"),
)
RECORDS_TABLES = {
    "app_records_player_seasons": Table("records_player_seasons", RECORDS_KEY,
        RECORDS_BASE + (
            Field("person_key", "TEXT NOT NULL", "season_player_stats_traditional"),
            Field("player_name", "TEXT", "season_player_stats_traditional"),
            Field("club_code", "TEXT", "season_player_stats_traditional"),
            Field("club_name", "TEXT", "season_player_stats_traditional"),
            Field("value", "NUMERIC NOT NULL", "season_player_stats_traditional"),
        )),
    "app_records_single_games": Table("records_single_games", RECORDS_KEY,
        RECORDS_BASE + (
            Field("game_code", "INTEGER NOT NULL", "game_player_stats"),
            Field("scheduled_at", "TIMESTAMPTZ", "games"),
            Field("person_key", "TEXT NOT NULL", "game_player_stats"),
            Field("player_name", "TEXT", "game_player_stats"),
            Field("club_code", "TEXT", "game_player_stats"),
            Field("club_name", "TEXT", "game_player_stats"),
            Field("value", "NUMERIC NOT NULL", "game_player_stats"),
        )),
    "app_records_team_seasons": Table("records_team_seasons", RECORDS_KEY,
        RECORDS_BASE + (
            Field("club_code", "TEXT NOT NULL", "games"),
            Field("club_name", "TEXT", "games"),
            Field("value", "NUMERIC NOT NULL", "game_team_stats"),
        )),
}
SERIES_TABLE = Table("postseason_series",
    ("competition_code", "season_code", "phase_code", "club_a_code", "club_b_code"),
    SCOPE + (
        Field("phase_code", "TEXT NOT NULL", "games"),
        Field("club_a_code", "TEXT NOT NULL", "games"),
        Field("club_b_code", "TEXT NOT NULL", "games"),
        Field("club_a_name", "TEXT", "games"),
        Field("club_b_name", "TEXT", "games"),
        Field("games_played", "INTEGER NOT NULL", "games"),
        Field("club_a_wins", "INTEGER NOT NULL", "games"),
        Field("club_b_wins", "INTEGER NOT NULL", "games"),
        Field("winner_club_code", "TEXT", "games"),
        Field("games", "JSONB NOT NULL", "games"),
    ),
)
AGGREGATE_NAMES = ("app_team_season_stats", "app_coverage_seasons",
                   "app_coverage_games")
DERIVED_NAMES = ("app_standings", *AGGREGATE_NAMES,
                 *RECORDS_TABLES, "app_postseason_series")
GOLD_TABLES = {**TABLES, "app_standings": STANDINGS_TABLE,
               "app_team_season_stats": TEAM_SEASON_TABLE,
               "app_coverage_seasons": COVERAGE_SEASON_TABLE,
               "app_coverage_games": COVERAGE_GAME_TABLE,
               **RECORDS_TABLES, "app_postseason_series": SERIES_TABLE}


def columns(name):
    return tuple(field.name for field in GOLD_TABLES[name].fields)


def create_table_sql(name):
    spec = GOLD_TABLES[name]
    fields = ", ".join(f'"{field.name}" {field.kind}' for field in spec.fields)
    key = ", ".join(f'"{column}"' for column in spec.key)
    return f'CREATE TABLE IF NOT EXISTS gold."{name}" ({fields}, PRIMARY KEY ({key}))'


def scope_predicate(name, alias=None):
    prefix = f'{alias}.' if alias else ""
    predicate = (f'{prefix}"competition_code" = %s AND '
                 f'{prefix}"season_code" = %s')
    if name in PLAYER_STATS:
        predicate += f' AND {prefix}"phase_code" <> \'PS\''
    return predicate


def count_sql(name, schema):
    if schema not in {"silver", "gold"}:
        raise ValueError(f"Unknown schema: {schema}")
    return f'SELECT count(*) FROM {schema}."{name}" WHERE {scope_predicate(name)}'

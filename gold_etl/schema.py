"""The 16 source projections owned by the first Gold build."""

from postgres_etl.flat_schema import (Field, SCOPE, STANDINGS_IDENTITY,
                                       TABLES as SILVER_TABLES, Table)


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
GOLD_TABLES = {**TABLES, "app_standings": STANDINGS_TABLE}


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

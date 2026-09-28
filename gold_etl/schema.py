"""The 16 source projections owned by the first Gold build."""

from postgres_etl.flat_schema import TABLES as SILVER_TABLES


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


def columns(name):
    return tuple(field.name for field in TABLES[name].fields)


def create_table_sql(name):
    spec = TABLES[name]
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

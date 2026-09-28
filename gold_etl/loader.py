"""Replace one Gold table/season slice using registered Silver source columns."""

from gold_etl.schema import (IDENTITY_TABLES, RECORDS_TABLES, SEASON_DERIVED_NAMES, TABLES,
                             columns, create_table_sql, scope_predicate)
from gold_etl.player_rounds import read_rows as read_player_rows
from gold_etl.team_ratings import read_rows as read_rating_rows
from gold_etl.team_splits import read_rows as read_split_rows
from gold_etl.team_rounds import read_rows as read_round_rows
from gold_etl.postseason import TABLES as PS_TABLES, read_rows as read_postseason_rows
from gold_etl.standings import read_rows as read_standings_rows
from gold_etl.team_season import read_rows as read_team_rows
from gold_etl.coverage import read_rows as read_coverage_rows
from gold_etl.records import read_rows as read_record_rows
from gold_etl.identity import read_rows as read_identity_rows
from gold_etl.series import read_rows as read_series_rows


def replace_scope(connection, name, competition_code, season_code):
    """DDL, delete, and copy commit together; a failure restores old Gold rows."""
    if name not in TABLES:
        raise ValueError(f"Unknown Gold source table: {name}")
    with connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS gold")
            cursor.execute(create_table_sql(name))
            cursor.execute(
                f'DELETE FROM gold."{name}" WHERE {scope_predicate(name)}',
                (competition_code, season_code),
            )
            field_list = ", ".join(f'"{column}"' for column in columns(name))
            cursor.execute(
                f'INSERT INTO gold."{name}" ({field_list}) '
                f'SELECT {field_list} FROM silver."{name}" '
                f'WHERE {scope_predicate(name)}',
                (competition_code, season_code),
            )
            return cursor.rowcount


def replace_postseason_scope(connection, name, competition_code, season_code):
    """Replace only derived PS rows; source rows survive and failures roll back."""
    if name not in PS_TABLES:
        raise ValueError(f"No postseason derivation for {name}")
    from psycopg2.extras import execute_values

    with connection:
        with connection.cursor() as cursor:
            rows = read_postseason_rows(cursor, competition_code, season_code)[name]
            cursor.execute(
                f'DELETE FROM gold."{name}" WHERE competition_code = %s '
                "AND season_code = %s AND phase_code = 'PS'",
                (competition_code, season_code),
            )
            if rows:
                fields = columns(name)
                names = ", ".join(f'"{field}"' for field in fields)
                values = [tuple(competition_code if field == "competition_code" else
                                season_code if field == "season_code" else row.get(field)
                                for field in fields) for row in rows]
                execute_values(cursor, f'INSERT INTO gold."{name}" ({names}) VALUES %s',
                               values, page_size=1000)
            return len(rows)


def replace_standings_scope(connection, competition_code, season_code):
    """Replace the page table season slice atomically from seven Silver feeds."""
    from psycopg2.extras import Json, execute_values

    name = "app_standings"
    with connection:
        with connection.cursor() as cursor:
            rows = read_standings_rows(cursor, competition_code, season_code)
            cursor.execute("CREATE SCHEMA IF NOT EXISTS gold")
            cursor.execute(create_table_sql(name))
            cursor.execute(
                'DELETE FROM gold."app_standings" '
                'WHERE competition_code = %s AND season_code = %s',
                (competition_code, season_code),
            )
            if rows:
                fields = columns(name)
                names = ", ".join(f'"{field}"' for field in fields)
                values = [tuple(Json(row[field]) if field in {"form", "streak_history"}
                                else row[field] for field in fields) for row in rows]
                execute_values(cursor, f'INSERT INTO gold."{name}" ({names}) VALUES %s',
                               values, page_size=1000)
            return len(rows)


def read_aggregate_rows(cursor, name, competition_code, season_code):
    if name not in SEASON_DERIVED_NAMES:
        raise ValueError(f"Unknown Gold aggregate table: {name}")
    if name == "player_round_stats":
        return read_player_rows(cursor, competition_code, season_code)
    if name == "team_round_splits":
        return read_split_rows(cursor, competition_code, season_code)
    if name == "team_round_ratings":
        return read_rating_rows(cursor, competition_code, season_code)
    if name == "team_round_stats":
        return read_round_rows(cursor, competition_code, season_code)
    if name == "app_team_season_stats":
        return read_team_rows(cursor, competition_code, season_code)
    return read_coverage_rows(cursor, competition_code, season_code)[name]


def replace_aggregate_scope(connection, name, competition_code, season_code):
    """Replace one registered derived season slice in a single transaction."""
    if name not in SEASON_DERIVED_NAMES:
        raise ValueError(f"Unknown Gold aggregate table: {name}")
    from psycopg2.extras import Json, execute_values

    with connection:
        with connection.cursor() as cursor:
            rows = read_aggregate_rows(cursor, name, competition_code, season_code)
            cursor.execute("CREATE SCHEMA IF NOT EXISTS gold")
            cursor.execute(create_table_sql(name))
            cursor.execute(
                f'DELETE FROM gold."{name}" '
                'WHERE competition_code = %s AND season_code = %s',
                (competition_code, season_code),
            )
            if rows:
                fields = columns(name)
                names = ", ".join(f'"{field}"' for field in fields)
                values = [tuple(competition_code if field == "competition_code" else
                                season_code if field == "season_code" else
                                Json(row[field]) if field == "items" else row.get(field)
                                for field in fields) for row in rows]
                execute_values(cursor, f'INSERT INTO gold."{name}" ({names}) VALUES %s',
                               values, page_size=1000)
            return len(rows)


def replace_records_scope(connection, name, competition_code):
    """Replace one competition's full-history leaderboard atomically."""
    if name not in RECORDS_TABLES:
        raise ValueError(f"Unknown Gold records table: {name}")
    from psycopg2.extras import execute_values

    with connection:
        with connection.cursor() as cursor:
            rows = read_record_rows(cursor, name, competition_code)
            cursor.execute("CREATE SCHEMA IF NOT EXISTS gold")
            cursor.execute(create_table_sql(name))
            cursor.execute(f'DELETE FROM gold."{name}" WHERE competition_code = %s',
                           (competition_code,))
            if rows:
                fields = columns(name)
                names = ", ".join(f'"{field}"' for field in fields)
                values = [tuple(row[field] for field in fields) for row in rows]
                execute_values(cursor, f'INSERT INTO gold."{name}" ({names}) VALUES %s',
                               values, page_size=1000)
            return len(rows)


def replace_identity_scope(connection, name, competition_code):
    """Replace one competition's full-history identities atomically."""
    if name not in IDENTITY_TABLES:
        raise ValueError(f"Unknown Gold identity table: {name}")
    from psycopg2.extras import Json, execute_values

    with connection:
        with connection.cursor() as cursor:
            rows = read_identity_rows(cursor, name, competition_code)
            cursor.execute("CREATE SCHEMA IF NOT EXISTS gold")
            cursor.execute(create_table_sql(name))
            cursor.execute(f'DELETE FROM gold."{name}" WHERE competition_code = %s',
                           (competition_code,))
            if rows:
                fields = columns(name)
                names = ", ".join(f'"{field}"' for field in fields)
                values = [tuple(Json(row[field]) if field == "clubs" else row[field]
                                for field in fields) for row in rows]
                execute_values(cursor, f'INSERT INTO gold."{name}" ({names}) VALUES %s',
                               values, page_size=1000)
            return len(rows)


def replace_series_scope(connection, competition_code, season_code):
    """Replace one postseason season slice without touching other Gold rows."""
    from psycopg2.extras import Json, execute_values

    name = "app_postseason_series"
    with connection:
        with connection.cursor() as cursor:
            rows = read_series_rows(cursor, competition_code, season_code)
            cursor.execute("CREATE SCHEMA IF NOT EXISTS gold")
            cursor.execute(create_table_sql(name))
            cursor.execute(
                f'DELETE FROM gold."{name}" WHERE competition_code = %s '
                'AND season_code = %s', (competition_code, season_code))
            if rows:
                fields = columns(name)
                names = ", ".join(f'"{field}"' for field in fields)
                values = [tuple(competition_code if field == "competition_code" else
                                season_code if field == "season_code" else
                                Json(row[field]) if field == "games" else row[field]
                                for field in fields) for row in rows]
                execute_values(cursor, f'INSERT INTO gold."{name}" ({names}) VALUES %s',
                               values, page_size=1000)
            return len(rows)

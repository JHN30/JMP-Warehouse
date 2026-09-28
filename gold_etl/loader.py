"""Replace one Gold table/season slice using registered Silver source columns."""

from gold_etl.schema import TABLES, columns, create_table_sql, scope_predicate


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

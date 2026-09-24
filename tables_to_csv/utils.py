"""Read-only helpers for exporting the current PostgreSQL ETL tables."""

import os
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.db import Tee, connect, elapsed  # noqa: E402,F401  (re-exported for main)
from common.seasons import COMPETITION_CODES, current_season_year, select_seasons  # noqa: E402,F401
from postgres_etl.flat_schema import TABLES, physical_name  # noqa: E402


def existing_tables(connection, names):
    """Return requested logical names whose physical tables are on the search path."""
    existing = []
    missing = []
    with connection.cursor() as cursor:
        for name in names:
            cursor.execute("SELECT to_regclass(%s)", (physical_name(name),))
            (relation,) = cursor.fetchone()
            (existing if relation is not None else missing).append(name)
    return existing, missing


def available_seasons(connection, competition, names):
    """Discover seasons in the selected database tables, not in the JSON cache."""
    from psycopg2 import sql

    found = set()
    with connection.cursor() as cursor:
        for name in names:
            query = sql.SQL(
                "SELECT DISTINCT season_code FROM {} WHERE competition_code = %s"
            ).format(sql.Identifier(physical_name(name)))
            cursor.execute(query, (COMPETITION_CODES[competition],))
            found.update(row[0] for row in cursor.fetchall())
    return sorted(found)


def count_rows(connection, competition, season_code, name):
    from psycopg2 import sql

    query = sql.SQL(
        "SELECT count(*) FROM {} WHERE competition_code = %s AND season_code = %s"
    ).format(sql.Identifier(physical_name(name)))
    with connection.cursor() as cursor:
        cursor.execute(query, (COMPETITION_CODES[competition], season_code))
        return cursor.fetchone()[0]


def export_table(connection, competition, season_code, name, destination):
    """Stream a deterministic PostgreSQL CSV to a temporary file, then publish it."""
    from psycopg2 import sql

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    order = sql.SQL(", ").join(sql.Identifier(column) for column in TABLES[name].key)
    query = sql.SQL(
        "COPY (SELECT * FROM {} WHERE competition_code = {} AND season_code = {} "
        "ORDER BY {}) TO STDOUT WITH (FORMAT CSV, HEADER TRUE)"
    ).format(
        sql.Identifier(physical_name(name)),
        sql.Literal(COMPETITION_CODES[competition]),
        sql.Literal(season_code),
        order,
    )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False,
            dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp",
        ) as output:
            temporary = Path(output.name)
            with connection.cursor() as cursor:
                cursor.copy_expert(query.as_string(connection), output)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

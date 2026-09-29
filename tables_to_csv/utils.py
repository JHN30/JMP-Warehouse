"""Read-only helpers for exporting every silver and gold table to one CSV file per table."""

import os
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.db import Tee, connect, elapsed  # noqa: E402,F401  (re-exported for main)
from common.seasons import COMPETITION_CODES, current_season_year, select_seasons  # noqa: E402,F401

LAYERS = ("silver", "gold")
# SQL Server Management Studio detects UTF-8 CSV files from the byte order mark.
BOM = b"\xef\xbb\xbf"


def _identifier(name):
    return '"' + name.replace('"', '""') + '"'


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def discover_tables(connection, layers):
    """Base tables of the given schemas: {(schema, table): {"columns": [(name, type)],
    "key": [primary key columns]}}, sorted by schema and table."""
    tables = {}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.table_schema, c.table_name, c.column_name, c.data_type "
            "FROM information_schema.columns c JOIN information_schema.tables t "
            "ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
            "WHERE t.table_type = 'BASE TABLE' AND c.table_schema = ANY(%s) "
            "ORDER BY c.table_schema, c.table_name, c.ordinal_position", (list(layers),))
        for schema, table, column, kind in cursor.fetchall():
            tables.setdefault((schema, table), {"columns": [], "key": []})[
                "columns"].append((column, kind))
        cursor.execute(
            "SELECT n.nspname, c.relname, a.attname FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey::int2[]) "
            "WHERE i.indisprimary AND n.nspname = ANY(%s) "
            "ORDER BY n.nspname, c.relname, array_position(i.indkey::int2[], a.attnum)",
            (list(layers),))
        for schema, table, column in cursor.fetchall():
            if (schema, table) in tables:
                tables[(schema, table)]["key"].append(column)
    return dict(sorted(tables.items()))


def available_seasons(connection, competition):
    """Seasons of the competition in `silver.seasons`."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT DISTINCT season_code FROM silver."seasons" '
                       "WHERE competition_code = %s", (COMPETITION_CODES[competition],))
        return sorted(row[0] for row in cursor.fetchall())


def _where(columns, competition, seasons):
    names = {name for name, _ in columns}
    predicates = []
    if "competition_code" in names:
        predicates.append(f'"competition_code" = {_literal(COMPETITION_CODES[competition])}')
    if seasons is not None and "season_code" in names:
        listed = ", ".join(_literal(season) for season in seasons)
        predicates.append(f'"season_code" IN ({listed})')
    return " WHERE " + " AND ".join(predicates) if predicates else ""


def _select(columns):
    """Booleans become 1 and 0 because SQL Server's bit type does not read `t` and `f`."""
    return ", ".join(f"{_identifier(name)}::integer AS {_identifier(name)}"
                     if kind == "boolean" else _identifier(name) for name, kind in columns)


def count_query(schema, table, spec, competition, seasons):
    return (f"SELECT count(*) FROM {_identifier(schema)}.{_identifier(table)}"
            + _where(spec["columns"], competition, seasons))


def copy_query(schema, table, spec, competition, seasons):
    """COPY statement streaming the whole table as CSV with a header, ordered by its key."""
    order = (" ORDER BY " + ", ".join(_identifier(column) for column in spec["key"])
             if spec["key"] else "")
    return (f"COPY (SELECT {_select(spec['columns'])} FROM "
            f"{_identifier(schema)}.{_identifier(table)}"
            + _where(spec["columns"], competition, seasons) + order
            + ") TO STDOUT WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8')")


def count_rows(connection, schema, table, spec, competition, seasons):
    with connection.cursor() as cursor:
        cursor.execute(count_query(schema, table, spec, competition, seasons))
        return cursor.fetchone()[0]


def export_table(connection, schema, table, spec, competition, seasons, destination):
    """Stream the table to a temporary file, then move it over the destination."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    query = copy_query(schema, table, spec, competition, seasons)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False,
            dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp",
        ) as output:
            temporary = Path(output.name)
            output.write(BOM)
            with connection.cursor() as cursor:
                cursor.copy_expert(query, output)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

"""Read-only, scope-specific equality checks for Gold source projections."""

from gold_etl.schema import TABLES, columns, count_sql, scope_predicate


def check_scope(cursor, name, competition_code, season_code):
    """Return actionable issues; PKs and equal row counts make one-way EXCEPT sufficient."""
    if name not in TABLES:
        raise ValueError(f"Unknown Gold source table: {name}")
    cursor.execute("SELECT to_regclass(%s)", (f"gold.{name}",))
    if cursor.fetchone()[0] is None:
        return [f"gold.{name} is missing"]
    scope = (competition_code, season_code)
    cursor.execute(count_sql(name, "silver"), scope)
    source_count = cursor.fetchone()[0]
    cursor.execute(count_sql(name, "gold"), scope)
    gold_count = cursor.fetchone()[0]
    issues = []
    if source_count != gold_count:
        issues.append(f"gold.{name} {season_code}: {gold_count} rows; "
                      f"silver has {source_count}")
    field_list = ", ".join(f'"{column}"' for column in columns(name))
    cursor.execute(
        f'SELECT EXISTS (SELECT {field_list} FROM silver."{name}" '
        f'WHERE {scope_predicate(name)} EXCEPT '
        f'SELECT {field_list} FROM gold."{name}" '
        f'WHERE {scope_predicate(name)})', scope + scope,
    )
    if cursor.fetchone()[0]:
        issues.append(f"gold.{name} {season_code}: source-column values differ from silver")
    return issues

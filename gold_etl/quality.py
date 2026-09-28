"""Read-only, scope-specific equality checks for Gold source projections."""

from gold_etl.schema import TABLES, columns, count_sql, scope_predicate
from gold_etl.postseason import TABLES as PS_TABLES, _dict_rows, read_rows as read_postseason_rows
from gold_etl.standings import KEY as STANDINGS_KEY, read_rows as read_standings_rows
from gold_etl.schema import GOLD_TABLES, SEASON_DERIVED_NAMES, IDENTITY_TABLES, RECORDS_TABLES
from gold_etl.loader import read_aggregate_rows
from gold_etl.records import read_rows as read_record_rows
from gold_etl.identity import read_rows as read_identity_rows
from gold_etl.series import read_rows as read_series_rows


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


def check_postseason_scope(cursor, name, competition_code, season_code):
    """Compare the complete derived PS slice with fresh Silver calculations."""
    if name not in PS_TABLES:
        raise ValueError(f"No postseason derivation for {name}")
    cursor.execute("SELECT to_regclass(%s)", (f"gold.{name}",))
    if cursor.fetchone()[0] is None:
        return [f"gold.{name} is missing"]
    expected = read_postseason_rows(cursor, competition_code, season_code)[name]
    field_list = ", ".join(f'"{field}"' for field in columns(name))
    cursor.execute(
        f'SELECT {field_list} FROM gold."{name}" '
        "WHERE competition_code = %s AND season_code = %s AND phase_code = 'PS'",
        (competition_code, season_code),
    )
    actual = _dict_rows(cursor)
    for row in expected:
        row["competition_code"] = competition_code
        row["season_code"] = season_code
    if len(actual) != len(expected):
        return [f"gold.{name} PS {season_code}: {len(actual)} rows; "
                f"Silver derivation expects {len(expected)}"]
    by_key = lambda rows: {(row["mode"], row["entry_ordinal"]): row for row in rows}
    if by_key(actual) != by_key(expected):
        return [f"gold.{name} PS {season_code}: derived keys or values differ from Silver"]
    return []


def check_standings_scope(cursor, competition_code, season_code):
    """Compare every page key and field/list value with Silver derivation."""
    name = "app_standings"
    cursor.execute("SELECT to_regclass(%s)", ("gold.app_standings",))
    if cursor.fetchone()[0] is None:
        return ["gold.app_standings is missing"]
    expected = read_standings_rows(cursor, competition_code, season_code)
    fields = ", ".join(f'"{field}"' for field in columns(name))
    cursor.execute(
        f'SELECT {fields} FROM gold."{name}" '
        'WHERE competition_code = %s AND season_code = %s',
        (competition_code, season_code),
    )
    actual = _dict_rows(cursor)
    by_key = lambda rows: {tuple(row[column] for column in STANDINGS_KEY): row
                           for row in rows}
    if by_key(actual).keys() != by_key(expected).keys():
        return [f"gold.app_standings {season_code}: keys differ from silver.standings_basic "
                f"({len(actual)} Gold, {len(expected)} Silver)"]
    if by_key(actual) != by_key(expected):
        return [f"gold.app_standings {season_code}: feed fields or lists differ from Silver"]
    return []


def check_aggregate_scope(cursor, name, competition_code, season_code):
    """Compare every derived key and value with a fresh Silver calculation."""
    if name not in SEASON_DERIVED_NAMES:
        raise ValueError(f"Unknown Gold aggregate table: {name}")
    cursor.execute("SELECT to_regclass(%s)", (f"gold.{name}",))
    if cursor.fetchone()[0] is None:
        return [f"gold.{name} is missing"]
    expected = read_aggregate_rows(cursor, name, competition_code, season_code)
    for row in expected:
        row["competition_code"] = competition_code
        row["season_code"] = season_code
    fields = ", ".join(f'"{field}"' for field in columns(name))
    cursor.execute(
        f'SELECT {fields} FROM gold."{name}" '
        'WHERE competition_code = %s AND season_code = %s',
        (competition_code, season_code),
    )
    actual = _dict_rows(cursor)
    key = GOLD_TABLES[name].key
    by_key = lambda rows: {tuple(row[column] for column in key): row for row in rows}
    if len(actual) != len(expected) or by_key(actual).keys() != by_key(expected).keys():
        return [f"gold.{name} {season_code}: keys differ from Silver derivation "
                f"({len(actual)} Gold, {len(expected)} expected)"]
    if by_key(actual) != by_key(expected):
        return [f"gold.{name} {season_code}: derived values differ from Silver"]
    return []


def check_records_scope(cursor, name, competition_code):
    """Compare every leaderboard key and value with all loaded Silver seasons."""
    if name not in RECORDS_TABLES:
        raise ValueError(f"Unknown Gold records table: {name}")
    cursor.execute("SELECT to_regclass(%s)", (f"gold.{name}",))
    if cursor.fetchone()[0] is None:
        return [f"gold.{name} is missing"]
    expected = read_record_rows(cursor, name, competition_code)
    fields = ", ".join(f'"{field}"' for field in columns(name))
    cursor.execute(f'SELECT {fields} FROM gold."{name}" WHERE competition_code = %s',
                   (competition_code,))
    actual = _dict_rows(cursor)
    key = GOLD_TABLES[name].key
    by_key = lambda rows: {tuple(row[field] for field in key): row for row in rows}
    if len(actual) != len(expected) or by_key(actual).keys() != by_key(expected).keys():
        return [f"gold.{name}: keys differ from Silver derivation "
                f"({len(actual)} Gold, {len(expected)} expected)"]
    if by_key(actual) != by_key(expected):
        return [f"gold.{name}: record values differ from Silver"]
    return []


def check_identity_scope(cursor, name, competition_code):
    """Compare every identity key and value with complete Silver history."""
    if name not in IDENTITY_TABLES:
        raise ValueError(f"Unknown Gold identity table: {name}")
    cursor.execute("SELECT to_regclass(%s)", (f"gold.{name}",))
    if cursor.fetchone()[0] is None:
        return [f"gold.{name} is missing"]
    expected = read_identity_rows(cursor, name, competition_code)
    fields = ", ".join(f'"{field}"' for field in columns(name))
    cursor.execute(f'SELECT {fields} FROM gold."{name}" WHERE competition_code = %s',
                   (competition_code,))
    actual = _dict_rows(cursor)
    key = GOLD_TABLES[name].key
    by_key = lambda rows: {tuple(row[field] for field in key): row for row in rows}
    if len(actual) != len(expected) or by_key(actual).keys() != by_key(expected).keys():
        return [f"gold.{name}: keys differ from Silver derivation "
                f"({len(actual)} Gold, {len(expected)} expected)"]
    if by_key(actual) != by_key(expected):
        return [f"gold.{name}: identity values differ from Silver"]
    return []


def check_series_scope(cursor, competition_code, season_code):
    """Compare pairing keys, counts and ordered game JSON with Silver."""
    name = "app_postseason_series"
    cursor.execute("SELECT to_regclass(%s)", (f"gold.{name}",))
    if cursor.fetchone()[0] is None:
        return [f"gold.{name} is missing"]
    expected = read_series_rows(cursor, competition_code, season_code)
    for row in expected:
        row["competition_code"] = competition_code
        row["season_code"] = season_code
    fields = ", ".join(f'"{field}"' for field in columns(name))
    cursor.execute(f'SELECT {fields} FROM gold."{name}" '
                   'WHERE competition_code = %s AND season_code = %s',
                   (competition_code, season_code))
    actual = _dict_rows(cursor)
    key = GOLD_TABLES[name].key
    by_key = lambda rows: {tuple(row[field] for field in key): row for row in rows}
    if len(actual) != len(expected) or by_key(actual).keys() != by_key(expected).keys():
        return [f"gold.{name} {season_code}: keys differ from Silver derivation "
                f"({len(actual)} Gold, {len(expected)} expected)"]
    if by_key(actual) != by_key(expected):
        return [f"gold.{name} {season_code}: values or games differ from Silver"]
    return []


# Final-round cumulative values against the API's accumulated team feeds. Counting
# stats must match exactly; the API rounds rates to one decimal (percent), so the
# tolerance is a little above half a tenth. The API's turnovers_ratio,
# assists_ratio and free_throws_rate use other definitions and are not compared.
API_COUNTS = (("games_played", "traditional", "games_played"),
              ("points_for", "traditional", "points"),
              ("own_three_pointers_made", "traditional", "three_pointers_made"),
              ("own_free_throws_made", "traditional", "free_throws_made"),
              ("own_free_throws_attempted", "traditional", "free_throws_attempted"),
              ("own_offensive_rebounds", "traditional", "offensive_rebounds"),
              ("own_defensive_rebounds", "traditional", "defensive_rebounds"),
              ("own_turnovers", "traditional", "turnovers"),
              ("own_assists", "traditional", "assists"))
API_RATES = (("efg_pct", "advanced", "effective_field_goal_percentage"),
             ("true_shooting_pct", "advanced", "true_shooting_percentage"),
             ("orb_pct", "advanced", "offensive_rebounds_percentage"),
             ("drb_pct", "advanced", "defensive_rebounds_percentage"))
API_RATE_TOLERANCE = 0.06


def check_round_api_scope(cursor, competition_code, season_code):
    """Warnings where final-round rows differ from the API feeds (scopes without a feed are skipped)."""
    scope = (competition_code, season_code)
    cursor.execute(
        'SELECT DISTINCT ON (scope, club_code) * FROM gold."team_round_stats" '
        'WHERE competition_code = %s AND season_code = %s '
        'ORDER BY scope, club_code, round_number DESC', scope)
    ours = _dict_rows(cursor)
    api = {}
    for kind in ("traditional", "advanced"):
        cursor.execute(
            f'SELECT * FROM silver."season_team_stats_{kind}" WHERE competition_code = %s '
            "AND season_code = %s AND mode = 'accumulated'", scope)
        api[kind] = {(row["phase_code"], row["club_code"]): row for row in _dict_rows(cursor)}
    differences = {}
    for row in ours:
        key = (row["scope"], row["club_code"])
        for column, kind, source in API_COUNTS + API_RATES:
            theirs = api[kind].get(key)
            if theirs is None or theirs.get(source) is None or row[column] is None:
                continue
            scale = 100 if (column, kind, source) in API_RATES else 1
            gap = abs(float(row[column]) * scale - float(theirs[source]))
            if gap > (API_RATE_TOLERANCE if scale == 100 else 0):
                differences.setdefault((row["scope"], column), []).append(
                    f'{row["club_code"]}: {float(row[column]) * scale:g} vs API {float(theirs[source]):g}')
    return [f"gold.team_round_stats {season_code} {scope_name}: {column} differs from the API "
            f"feed for {len(examples)} club(s) (e.g. {examples[0]})"
            for (scope_name, column), examples in sorted(differences.items())]

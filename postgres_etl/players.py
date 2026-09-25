"""Cross-season player identity, computed locally from already-loaded flat
tables.

One row per ``person_code`` (restricted to people who appear as a player,
``role_code = 'J'``, in ``app_registrations`` at least once), so the app can
look a player up without picking a season first. Archives (season-by-season
club history) and head-to-head (shared games) are already fully answerable
from ``app_registrations``/``app_game_player_stats`` via ``person_code``, so
this table only adds the one missing piece: identity plus career span and a
compact club-history summary.

Like ``records.py``, this table is NOT season-scoped: a player's row spans
every season they appeared in, so a rebuild always recomputes the whole
table from current local data and replaces prior contents.
"""

from flat_schema import PLAYER_TABLES, create_index_sql, create_table_sql, physical_name
from shared import COMPETITION_CODES, connect


_COMPETITION_CODE = COMPETITION_CODES["euroleague"]

_INSERT_COLUMNS = (
    "competition_code", "person_code", "name", "country_code", "country_name",
    "height_cm", "weight_kg", "birth_at", "birth_country_code", "birth_country_name",
    "position", "position_name", "first_season_code", "last_season_code",
    "seasons_played", "clubs",
)


def _players_select_sql():
    people = physical_name("people")
    registrations = physical_name("registrations")
    return (
        "WITH latest_person AS ("
        "  SELECT DISTINCT ON (competition_code, person_code) "
        "  competition_code, person_code, name, country_code, country_name, "
        "  height_cm, weight_kg, birth_at, birth_country_code, birth_country_name "
        f'  FROM "{people}" '
        "  WHERE competition_code = %(competition_code)s "
        "  ORDER BY competition_code, person_code, season_code DESC"
        "), latest_position AS ("
        "  SELECT DISTINCT ON (competition_code, person_key) "
        "  competition_code, person_key, position, position_name "
        f'  FROM "{registrations}" '
        "  WHERE competition_code = %(competition_code)s AND role_code = 'J' "
        "  ORDER BY competition_code, person_key, season_code DESC, start_at DESC"
        "), span AS ("
        "  SELECT competition_code, person_key, "
        "  min(season_code) AS first_season_code, max(season_code) AS last_season_code, "
        "  count(DISTINCT season_code) AS seasons_played "
        f'  FROM "{registrations}" '
        "  WHERE competition_code = %(competition_code)s AND role_code = 'J' "
        "  GROUP BY competition_code, person_key"
        "), distinct_clubs AS ("
        "  SELECT DISTINCT competition_code, person_key, season_code, club_code, club_name "
        f'  FROM "{registrations}" '
        "  WHERE competition_code = %(competition_code)s AND role_code = 'J'"
        "), clubs AS ("
        "  SELECT competition_code, person_key, "
        "  jsonb_agg(jsonb_build_object("
        "    'seasonCode', season_code, 'clubCode', club_code, 'clubName', club_name"
        "  ) ORDER BY season_code) AS clubs "
        "  FROM distinct_clubs "
        "  GROUP BY competition_code, person_key"
        ") "
        "SELECT p.competition_code, p.person_code, p.name, p.country_code, p.country_name, "
        "p.height_cm, p.weight_kg, p.birth_at, p.birth_country_code, p.birth_country_name, "
        "pos.position, pos.position_name, "
        "span.first_season_code, span.last_season_code, span.seasons_played, clubs.clubs "
        "FROM latest_person AS p "
        "JOIN span ON span.competition_code = p.competition_code "
        "AND span.person_key = p.person_code "
        "JOIN clubs ON clubs.competition_code = p.competition_code "
        "AND clubs.person_key = p.person_code "
        "LEFT JOIN latest_position AS pos ON pos.competition_code = p.competition_code "
        "AND pos.person_key = p.person_code"
    )


def build_players(config_path, names=PLAYER_TABLES, dry_run=False, log=print):
    """Recompute the requested player tables from current local data.

    Each table is fully replaced (TRUNCATE, then one INSERT) inside its own
    transaction; a run never leaves a table half-written. Not season-scoped:
    always reflects every season currently loaded locally. ``dry_run``
    reports the row count without writing. Returns {name: row_count}.
    """
    unknown = set(names) - set(PLAYER_TABLES)
    if unknown:
        raise ValueError("Unknown player table(s): " + ", ".join(sorted(unknown)))
    params = {"competition_code": _COMPETITION_CODE}
    counts = {}
    connection = connect(config_path)
    try:
        if dry_run:
            connection.set_session(readonly=True)
            with connection.cursor() as cursor:
                for name in names:
                    select_sql = _players_select_sql()
                    physical = physical_name(name)
                    cursor.execute(f"SELECT count(*) FROM ({select_sql}) AS probe", params)
                    counts[name] = cursor.fetchone()[0]
                    log(f"  {physical}: {counts[name]:,} rows would be computed")
            connection.rollback()
            connection.set_session(readonly=False)
        else:
            with connection:
                with connection.cursor() as cursor:
                    for name in names:
                        select_sql = _players_select_sql()
                        physical = physical_name(name)
                        cursor.execute(create_table_sql(name))
                        for statement in create_index_sql(name):
                            cursor.execute(statement)
                        cursor.execute(f'TRUNCATE TABLE "{physical}"')
                        columns = ", ".join(f'"{column}"' for column in _INSERT_COLUMNS)
                        cursor.execute(
                            f'INSERT INTO "{physical}" ({columns}) {select_sql}', params)
                        cursor.execute(f'SELECT count(*) FROM "{physical}"')
                        counts[name] = cursor.fetchone()[0]
                        log(f"  {physical}: {counts[name]:,} rows")
    finally:
        connection.close()
    return counts


def validate_players(config_path, names=PLAYER_TABLES, log=print):
    """Read-only checks: no duplicate person_code, first <= last season,
    seasons_played matches the clubs array's distinct season count, and a
    non-empty clubs array. Returns True when every check passes."""
    passed = True
    connection = connect(config_path)
    try:
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with connection.cursor() as cursor:
            for name in names:
                physical = physical_name(name)
                cursor.execute("SELECT to_regclass(%s)", (physical,))
                if cursor.fetchone()[0] is None:
                    log(f"  ERROR {physical}: missing_table")
                    passed = False
                    continue
                cursor.execute(f'SELECT count(*) FROM "{physical}"')
                total = cursor.fetchone()[0]
                cursor.execute(
                    f'SELECT count(*) FROM (SELECT person_code FROM "{physical}" '
                    "GROUP BY person_code HAVING count(*) > 1) AS dupes"
                )
                duplicates = cursor.fetchone()[0]
                cursor.execute(
                    f'SELECT count(*) FROM "{physical}" '
                    "WHERE first_season_code > last_season_code"
                )
                bad_span = cursor.fetchone()[0]
                cursor.execute(
                    f'SELECT count(*) FROM "{physical}" AS row '
                    "WHERE jsonb_array_length(row.clubs) = 0 OR row.clubs IS NULL "
                    "OR row.seasons_played <> ("
                    "  SELECT count(DISTINCT elem->>'seasonCode') "
                    "  FROM jsonb_array_elements(row.clubs) AS elem"
                    ")"
                )
                bad_clubs = cursor.fetchone()[0]
                errors = duplicates + bad_span + bad_clubs
                if errors:
                    passed = False
                log(f"Quality {physical}: {total:,} rows, {errors} error(s)")
                if duplicates:
                    log(f"  ERROR {physical}: duplicate_person_code ({duplicates:,} row(s))")
                if bad_span:
                    log(f"  ERROR {physical}: first_season_after_last ({bad_span:,} row(s))")
                if bad_clubs:
                    log(f"  ERROR {physical}: clubs_mismatch_or_empty ({bad_clubs:,} row(s))")
        connection.rollback()
    finally:
        connection.close()
    return passed

"""All-time leaderboards, computed locally from already-loaded flat tables.

Mirrors the three ``/records/*`` routes in the jmp-euroleague2 Express backend
(``backend/src/routes/seasons.ts``): the same four metrics per table, the same
source filters (forfeits excluded via ``games.played``), and the same
tie-break order, so the web app can eventually read a precomputed table
instead of aggregating on every request (that cutover is a separate,
coordinated change in the web-app repo, not part of this pipeline).

Unlike every other table here, these three are not season-scoped: a table's
rows span every season already loaded locally (``E2000``-current), so a
rebuild always recomputes the full top 50 per metric from current local data
and replaces prior contents, rather than loading one season's bronze files.
"""

from flat_schema import create_index_sql, create_table_sql, physical_name
from shared import COMPETITION_CODES, connect


RECORDS_TABLES = ("app_records_player_seasons", "app_records_single_games",
                  "app_records_team_seasons")
TOP_N = 50

# metric name -> local column name. Both happen to match for every metric here.
PLAYER_SEASON_METRICS = {"points_scored": "points_scored", "total_rebounds": "total_rebounds",
                         "assists": "assists", "pir": "pir"}
SINGLE_GAME_METRICS = {"points": "points", "valuation": "valuation",
                       "total_rebounds": "total_rebounds", "assistances": "assistances"}
TEAM_SEASON_METRICS = {"points": "points", "valuation": "valuation",
                       "total_rebounds": "total_rebounds", "assistances": "assistances"}

_COMPETITION_CODE = COMPETITION_CODES["euroleague"]

_INSERT_COLUMNS = {
    "app_records_player_seasons": (
        "competition_code", "metric", "rank_ordinal", "season_code", "person_key",
        "player_name", "club_code", "club_name", "value",
    ),
    "app_records_single_games": (
        "competition_code", "metric", "rank_ordinal", "season_code", "game_code",
        "scheduled_at", "person_key", "player_name", "club_code", "club_name", "value",
    ),
    "app_records_team_seasons": (
        "competition_code", "metric", "rank_ordinal", "season_code", "club_code",
        "club_name", "value",
    ),
}


def _ranked_select(parts, columns):
    """Wrap per-metric SELECTs (each already producing ``rank_ordinal``) into
    one UNION ALL, keeping only the top N rows of each metric."""
    ranked = " UNION ALL ".join(parts)
    column_list = ", ".join(columns)
    return f"SELECT {column_list} FROM ({ranked}) AS ranked WHERE rank_ordinal <= {TOP_N}"


def _player_season_select():
    table = physical_name("season_stats_traditional")
    parts = []
    for metric, column in PLAYER_SEASON_METRICS.items():
        parts.append(
            f"SELECT competition_code, '{metric}' AS metric, season_code, person_key, "
            f"player_name, club_code, club_name, \"{column}\" AS value, "
            f"row_number() OVER (ORDER BY \"{column}\" DESC, season_code ASC, "
            f"person_key ASC) AS rank_ordinal "
            f'FROM "{table}" '
            f"WHERE competition_code = %s AND phase_code = 'all' AND mode = 'accumulated' "
            f'AND "{column}" IS NOT NULL'
        )
    select_sql = _ranked_select(parts, _INSERT_COLUMNS["app_records_player_seasons"])
    return select_sql, (_COMPETITION_CODE,) * len(PLAYER_SEASON_METRICS)


def _single_game_select():
    stats = physical_name("game_player_stats")
    games = physical_name("games")
    parts = []
    for metric, column in SINGLE_GAME_METRICS.items():
        parts.append(
            f"SELECT gps.competition_code AS competition_code, '{metric}' AS metric, "
            f"gps.season_code AS season_code, gps.game_code AS game_code, "
            f"g.scheduled_at AS scheduled_at, gps.person_key AS person_key, "
            f"gps.person_name AS player_name, gps.club_code AS club_code, "
            f"gps.club_name AS club_name, gps.\"{column}\" AS value, "
            f"row_number() OVER (ORDER BY gps.\"{column}\" DESC, gps.season_code ASC, "
            f"gps.game_code ASC, gps.person_key ASC) AS rank_ordinal "
            f'FROM "{stats}" AS gps '
            f'JOIN "{games}" AS g ON g.competition_code = gps.competition_code '
            f"AND g.season_code = gps.season_code AND g.game_code = gps.game_code "
            f"WHERE gps.competition_code = %s AND g.played IS TRUE "
            f'AND gps."{column}" IS NOT NULL'
        )
    select_sql = _ranked_select(parts, _INSERT_COLUMNS["app_records_single_games"])
    return select_sql, (_COMPETITION_CODE,) * len(SINGLE_GAME_METRICS)


def _team_season_select():
    stats = physical_name("game_team_stats")
    games = physical_name("games")
    parts = []
    for metric, column in TEAM_SEASON_METRICS.items():
        agg = (
            f"SELECT gts.competition_code AS competition_code, gts.season_code AS season_code, "
            f"CASE WHEN gts.side = 'local' THEN g.local_club_code ELSE g.road_club_code END "
            f"AS club_code, "
            f"CASE WHEN gts.side = 'local' THEN g.local_club_name ELSE g.road_club_name END "
            f"AS club_name, "
            f'sum(gts."{column}") AS value '
            f'FROM "{stats}" AS gts '
            f'JOIN "{games}" AS g ON g.competition_code = gts.competition_code '
            f"AND g.season_code = gts.season_code AND g.game_code = gts.game_code "
            f"WHERE gts.competition_code = %s AND gts.stats_kind = 'total' AND g.played IS TRUE "
            f"GROUP BY gts.competition_code, gts.season_code, club_code, club_name"
        )
        parts.append(
            f"SELECT competition_code, '{metric}' AS metric, season_code, club_code, "
            f"club_name, value, "
            f"row_number() OVER (ORDER BY value DESC, season_code ASC, club_code ASC) "
            f"AS rank_ordinal "
            f"FROM ({agg}) AS totals "
            f"WHERE club_code IS NOT NULL AND value IS NOT NULL"
        )
    select_sql = _ranked_select(parts, _INSERT_COLUMNS["app_records_team_seasons"])
    return select_sql, (_COMPETITION_CODE,) * len(TEAM_SEASON_METRICS)


_SELECTS = {
    "app_records_player_seasons": _player_season_select,
    "app_records_single_games": _single_game_select,
    "app_records_team_seasons": _team_season_select,
}


def build_records(config_path, names=RECORDS_TABLES, dry_run=False, log=print):
    """Recompute the requested records tables from current local data.

    Each table is fully replaced (TRUNCATE, then one ranked INSERT) inside its
    own transaction; a run never leaves a table half-written. Not
    season-scoped: always reflects every season currently loaded locally.
    ``dry_run`` reports the row count each table would have without writing.
    Returns {name: row_count}.
    """
    unknown = set(names) - set(RECORDS_TABLES)
    if unknown:
        raise ValueError("Unknown records table(s): " + ", ".join(sorted(unknown)))
    counts = {}
    connection = connect(config_path)
    try:
        if dry_run:
            # Read-only: counts come straight from the ranking query over the
            # source tables, so the target table need not exist yet.
            connection.set_session(readonly=True)
            with connection.cursor() as cursor:
                for name in names:
                    select_sql, params = _SELECTS[name]()
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
                        select_sql, params = _SELECTS[name]()
                        physical = physical_name(name)
                        cursor.execute(create_table_sql(name))
                        for statement in create_index_sql(name):
                            cursor.execute(statement)
                        cursor.execute(f'TRUNCATE TABLE "{physical}"')
                        columns = ", ".join(f'"{column}"' for column in _INSERT_COLUMNS[name])
                        cursor.execute(
                            f'INSERT INTO "{physical}" ({columns}) {select_sql}', params)
                        cursor.execute(f'SELECT count(*) FROM "{physical}"')
                        counts[name] = cursor.fetchone()[0]
                        log(f"  {physical}: {counts[name]:,} rows")
    finally:
        connection.close()
    return counts


def validate_records(config_path, names=RECORDS_TABLES, log=print):
    """Read-only checks: dense rank_ordinal per metric, non-null/non-negative
    value, and at most TOP_N rows per metric. Returns True when every check
    passes. Prints one line per table plus one line per failing check."""
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
                    f'SELECT count(*) FROM "{physical}" '
                    "WHERE value IS NULL OR value < 0"
                )
                bad_value = cursor.fetchone()[0]
                cursor.execute(
                    f'SELECT count(*) FROM (SELECT metric, count(*) AS rows FROM "{physical}" '
                    f"GROUP BY metric HAVING count(*) > {TOP_N}) AS oversized"
                )
                oversized = cursor.fetchone()[0]
                # rank_ordinal gap/duplicate check: every metric's rank_ordinal values
                # must be exactly {1, ..., N} with no gaps or duplicates.
                cursor.execute(
                    f'SELECT count(*) FROM ('
                    f'  SELECT metric FROM "{physical}" '
                    "  GROUP BY metric "
                    "  HAVING count(*) <> count(DISTINCT rank_ordinal) "
                    "     OR max(rank_ordinal) <> count(*) OR min(rank_ordinal) <> 1"
                    ") AS bad_ranks"
                )
                bad_ranks = cursor.fetchone()[0]
                errors = bad_value + oversized + bad_ranks
                if errors:
                    passed = False
                log(f"Quality {physical}: {total:,} rows, {errors} error(s)")
                if bad_value:
                    log(f"  ERROR {physical}: null_or_negative_value ({bad_value:,} row(s))")
                if oversized:
                    log(f"  ERROR {physical}: metric_over_{TOP_N}_rows ({oversized:,} row(s))")
                if bad_ranks:
                    log(f"  ERROR {physical}: rank_ordinal_not_dense ({bad_ranks:,} metric(s))")
        connection.rollback()
    finally:
        connection.close()
    return passed

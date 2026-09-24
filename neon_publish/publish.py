"""Replace season-scoped web-app tables in Neon with the local PostgreSQL rows.

Every selected table of one season is replaced inside a single Neon
transaction (DELETE that season, COPY the new rows, verify the counts). Readers
keep seeing the previous rows until COMMIT and then the complete new season,
never a half-loaded state. Unlike the old CSV/psql import, running it again is
safe: nothing is appended.
"""

import os
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from postgres_etl.flat_schema import TABLES, create_index_sql, create_table_sql, physical_name  # noqa: E402
from common.seasons import COMPETITION_CODES  # noqa: E402


# The tables the web app reads: the v2/v3 flat tables it uses today, plus the
# page-shaped app_* tables it moves to. Live-API tables and etl_source_payloads
# stay local.
APP_TABLES = (
    "seasons", "clubs", "people", "registrations", "rounds", "games",
    "game_officials", "game_period_scores", "game_player_stats",
    "game_team_stats",
    "season_stats_traditional", "season_stats_advanced",
    "season_stats_scoring", "season_stats_misc",
    "standings_basicstandings", "standings_calendarstandings",
    "standings_streaks", "standings_aheadbehind", "standings_margins",
    "standings_calendar_streaks", "standings_basic_form",
    "app_standings",
)
NEON_URL_ENV = "NEON_DATABASE_URL"
# Publishing is refused when a table would keep less than this share of its
# current Neon rows; a failed or partial local load must not empty the site.
SHRINK_LIMIT = 0.9
SPOOL_BYTES = 32 * 1024 * 1024


def neon_connect(env_var=NEON_URL_ENV):
    url = os.environ.get(env_var)
    if not url:
        raise RuntimeError(
            f"Set the {env_var} environment variable to the Neon direct "
            "(non-pooled) connection URL."
        )
    try:
        import psycopg2
    except ImportError as error:
        raise RuntimeError("Publishing requires psycopg2 (or psycopg2-binary).") from error
    return psycopg2.connect(url)


def shrink_problems(local_counts, remote_counts, limit=SHRINK_LIMIT):
    """Describe tables whose season would lose too many existing Neon rows."""
    problems = []
    for name, local in local_counts.items():
        remote = remote_counts.get(name) or 0
        if remote and local < remote * limit:
            problems.append(f"{physical_name(name)}: {remote:,} -> {local:,} rows")
    return problems


def _columns(name):
    from psycopg2 import sql

    return sql.SQL(", ").join(sql.Identifier(field.name) for field in TABLES[name].fields)


def _season_filter(competition_code, season_code):
    from psycopg2 import sql

    return sql.SQL("competition_code = {} AND season_code = {}").format(
        sql.Literal(competition_code), sql.Literal(season_code)
    )


def _count(cursor, name, competition_code, season_code):
    from psycopg2 import sql

    cursor.execute(sql.SQL("SELECT count(*) FROM {} WHERE {}").format(
        sql.Identifier(physical_name(name)), _season_filter(competition_code, season_code)
    ))
    return cursor.fetchone()[0]


def _existing_columns(cursor, name):
    cursor.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s",
        (physical_name(name),),
    )
    return {row[0] for row in cursor.fetchall()}


def _ensure_table(cursor, name, log):
    """Create a missing table or add missing columns; never drop anything.

    Only statements that are actually needed run, because ALTER TABLE takes an
    exclusive lock that would briefly block the web app's reads.
    """
    existing = _existing_columns(cursor, name)
    if not existing:
        log(f"  {physical_name(name)}: creating table in Neon")
        cursor.execute(create_table_sql(name))
        for statement in create_index_sql(name):
            cursor.execute(statement)
        return
    for field in TABLES[name].fields:
        if field.name not in existing:
            log(f"  {physical_name(name)}: adding column {field.name} {field.kind}")
            cursor.execute(
                f'ALTER TABLE "{physical_name(name)}" ADD COLUMN "{field.name}" {field.kind}'
            )


def export_season(local, competition_code, season_code, names):
    """Read every table from one consistent local snapshot into CSV spools."""
    from psycopg2 import sql

    counts, spools = {}, {}
    local.set_session(readonly=True, isolation_level="REPEATABLE READ")
    try:
        with local.cursor() as cursor:
            for name in names:
                counts[name] = _count(cursor, name, competition_code, season_code)
                order = sql.SQL(", ").join(sql.Identifier(column) for column in TABLES[name].key)
                query = sql.SQL(
                    "COPY (SELECT {} FROM {} WHERE {} ORDER BY {}) TO STDOUT WITH (FORMAT CSV)"
                ).format(_columns(name), sql.Identifier(physical_name(name)),
                         _season_filter(competition_code, season_code), order)
                spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES, mode="w+b")
                spools[name] = spool
                cursor.copy_expert(query.as_string(local), spool)
                spool.seek(0)
    except BaseException:
        for spool in spools.values():
            spool.close()
        raise
    finally:
        local.rollback()
        local.set_session(readonly=False, isolation_level="DEFAULT")
    return counts, spools


def remote_counts(neon, competition_code, season_code, names):
    counts = {}
    with neon.cursor() as cursor:
        for name in names:
            cursor.execute("SELECT to_regclass(%s)", (physical_name(name),))
            if cursor.fetchone()[0] is None:
                counts[name] = None
            else:
                counts[name] = _count(cursor, name, competition_code, season_code)
    neon.rollback()
    return counts


def publish_season(local, neon, competition, season_code, names,
                   dry_run=False, allow_shrink=False, log=print):
    """Replace one season of ``names`` in Neon; return {table: (before, after)}."""
    from psycopg2 import sql

    competition_code = COMPETITION_CODES[competition]
    before = remote_counts(neon, competition_code, season_code, names)
    if dry_run:
        local.set_session(readonly=True)
        with local.cursor() as cursor:
            local_counts = {name: _count(cursor, name, competition_code, season_code)
                            for name in names}
        local.rollback()
        local.set_session(readonly=False)
    else:
        local_counts, spools = export_season(local, competition_code, season_code, names)

    try:
        problems = shrink_problems(local_counts, before)
        if problems and not allow_shrink:
            raise ValueError(
                f"Refusing to publish {season_code}; it would remove existing Neon rows "
                "(check the local load, or pass --allow-shrink if this is intended):\n  "
                + "\n  ".join(problems)
            )
        if dry_run:
            return {name: (before[name], local_counts[name]) for name in names}

        with neon:  # One transaction: COMMIT on success, ROLLBACK on any error.
            with neon.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '15s'")
                for name in names:
                    _ensure_table(cursor, name, log)
                for name in names:
                    table = sql.Identifier(physical_name(name))
                    cursor.execute(sql.SQL("DELETE FROM {} WHERE {}").format(
                        table, _season_filter(competition_code, season_code)
                    ))
                    cursor.copy_expert(
                        sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT CSV)").format(
                            table, _columns(name)
                        ).as_string(neon),
                        spools[name],
                    )
                    published = _count(cursor, name, competition_code, season_code)
                    if published != local_counts[name]:
                        raise RuntimeError(
                            f"{physical_name(name)}: Neon has {published:,} rows after COPY "
                            f"but local PostgreSQL has {local_counts[name]:,}; rolled back."
                        )
        return {name: (before[name], local_counts[name]) for name in names}
    finally:
        if not dry_run:
            for spool in spools.values():
                spool.close()

"""Atomically replace selected Gold scopes in Neon's public app tables."""

import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from psycopg2 import sql

from common.dotenv import read_env_value
from common.seasons import COMPETITION_CODES
from gold_etl.schema import GOLD_TABLES
from neon_publish.contract import (APP_TABLES, GAME_DIFF_TABLES, predicate,
                                   preflight, scope, target_name)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
NEON_URL_ENV = "NEON_DATABASE_URL"
SHRINK_LIMIT = 0.9
SPOOL_BYTES = 32 * 1024 * 1024


def neon_connect(env_var=NEON_URL_ENV):
    url = os.environ.get(env_var) or read_env_value(PROJECT_ROOT / ".env", env_var)
    url = (url or "").strip().strip("\"'")
    if not url:
        raise RuntimeError(f"Set {env_var} to the direct (non-pooled) Neon URL.")
    from pipeline import looks_like_postgres_url
    if not looks_like_postgres_url(url) or "-pooler" in (urlsplit(url).hostname or ""):
        raise RuntimeError(f"{env_var} must be a direct, valid PostgreSQL URL.")
    import psycopg2
    return psycopg2.connect(url)


def shrink_problems(local_counts, remote_counts, limit=SHRINK_LIMIT):
    return [f"{target_name(name)}: {remote:,} -> {local:,} rows"
            for name, local in local_counts.items()
            if (remote := remote_counts.get(name) or 0) and local < remote * limit]


def _relation(name, schema):
    return sql.Identifier(schema, name if schema == "gold" else target_name(name))


def _columns(name):
    return sql.SQL(", ").join(sql.Identifier(field.name)
                            for field in GOLD_TABLES[name].fields)


def _where(name):
    return sql.SQL(predicate(name))


def _count(cursor, name, competition_code, season_code, schema):
    cursor.execute(sql.SQL("SELECT count(*) FROM {} WHERE {}").format(
        _relation(name, schema), _where(name)), scope(name, competition_code, season_code))
    return cursor.fetchone()[0]


def game_checksums(cursor, name, competition_code, season_code, schema):
    cursor.execute("SET LOCAL TimeZone = 'UTC'")
    cursor.execute("SET LOCAL DateStyle = 'ISO'")
    order = sql.SQL(", ").join(sql.Identifier(column) for column in GOLD_TABLES[name].key)
    cursor.execute(sql.SQL(
        "SELECT game_code, count(*), md5(string_agg(ROW({})::text, E'\\n' ORDER BY {})) "
        "FROM {} WHERE {} GROUP BY game_code"
    ).format(_columns(name), order, _relation(name, schema), _where(name)),
        scope(name, competition_code, season_code))
    return {game: (rows, digest) for game, rows, digest in cursor.fetchall()}


def game_rows(cursor, name, competition_code, season_code):
    cursor.execute(sql.SQL("SELECT game_code, count(*) FROM {} WHERE {} GROUP BY game_code")
                   .format(_relation(name, "public"), _where(name)),
                   scope(name, competition_code, season_code))
    return {game: (rows, None) for game, rows in cursor.fetchall()}


def changed_games(local_sums, remote_sums):
    replace = sorted(game for game, value in local_sums.items() if remote_sums.get(game) != value)
    remove = sorted(game for game in remote_sums if game not in local_sums)
    return replace, remove


def _snapshot(local, competition_code, season_code, names, remote_sums, dry_run):
    """Count and optionally spool selected rows from one repeatable-read snapshot."""
    counts, spools, plans = {}, {}, {}
    local.set_session(readonly=True, isolation_level="REPEATABLE READ")
    try:
        with local.cursor() as cursor:
            for name in names:
                cursor.execute("SELECT to_regclass(%s)", (f"gold.{name}",))
                if cursor.fetchone()[0] is None:
                    raise ValueError(f"gold.{name} is missing; build Gold first")
                counts[name] = _count(cursor, name, competition_code, season_code, "gold")
                where = _where(name)
                params = list(scope(name, competition_code, season_code))
                if name in GAME_DIFF_TABLES:
                    sums = game_checksums(cursor, name, competition_code, season_code, "gold")
                    replace, remove = changed_games(sums, remote_sums[name])
                    plans[name] = (replace, remove, len(sums))
                    where = sql.SQL("{} AND game_code = ANY(%s)").format(where)
                    params.append(replace)
                if dry_run:
                    continue
                order = sql.SQL(", ").join(sql.Identifier(column) for column in GOLD_TABLES[name].key)
                query = sql.SQL("COPY (SELECT {} FROM {} WHERE {} ORDER BY {}) TO STDOUT WITH (FORMAT CSV)")
                query = query.format(_columns(name), _relation(name, "gold"), where, order)
                query = cursor.mogrify(query.as_string(local), tuple(params)).decode()
                spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES, mode="w+b")
                spools[name] = spool
                cursor.copy_expert(query, spool)
                spool.seek(0)
    except BaseException:
        for spool in spools.values():
            spool.close()
        raise
    finally:
        local.rollback()
        local.set_session(readonly=False, isolation_level="DEFAULT")
    return counts, spools, plans


def _remote_state(cursor, competition_code, season_code, names, problems):
    counts, sums = {}, {}
    for name in names:
        if problems.get(name) and any("missing table" in issue for issue in problems[name]):
            counts[name] = None
            if name in GAME_DIFF_TABLES:
                sums[name] = {}
            continue
        counts[name] = _count(cursor, name, competition_code, season_code, "public")
        if name in GAME_DIFF_TABLES:
            sums[name] = (game_rows(cursor, name, competition_code, season_code)
                          if problems.get(name) else
                          game_checksums(cursor, name, competition_code, season_code, "public"))
    return counts, sums


def _replace(cursor, name, competition_code, season_code, spool, plan):
    where = _where(name)
    params = list(scope(name, competition_code, season_code))
    if plan is not None:
        replace, remove, _ = plan
        games = replace + remove
        if games:
            cursor.execute(sql.SQL("DELETE FROM {} WHERE {} AND game_code = ANY(%s)")
                           .format(_relation(name, "public"), where), (*params, games))
        if not replace:
            return
    else:
        cursor.execute(sql.SQL("DELETE FROM {} WHERE {}").format(
            _relation(name, "public"), where), params)
    cursor.copy_expert(sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT CSV)").format(
        _relation(name, "public"), _columns(name)).as_string(cursor.connection), spool)


def publish_season(local, neon, competition, season_code, names=APP_TABLES,
                   dry_run=False, allow_shrink=False, log=print):
    """Publish one season plus selected competition-wide tables in one transaction."""
    if competition != "euroleague":
        raise ValueError("Only EuroLeague publishing is supported")
    if not names or any(name not in APP_TABLES for name in names):
        raise ValueError("Select one or more registered Gold tables")
    code = COMPETITION_CODES[competition]
    spools = {}
    if dry_run:
        neon.set_session(readonly=True)
    try:
        with neon:
            with neon.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '15s'")
                problems = preflight(cursor, names)
                for issues in problems.values():
                    for issue in issues:
                        log(f"  Schema: {issue}")
                before, remote_sums = _remote_state(cursor, code, season_code, names, problems)
                counts, spools, plans = _snapshot(local, code, season_code, names,
                                                  remote_sums, dry_run)
                for name, (replace, remove, total) in plans.items():
                    verb = "would be replaced" if dry_run else "replaced"
                    log(f"  {target_name(name)}: {len(replace)} of {total} game(s) {verb}"
                        + (f", {len(remove)} removed" if remove else ""))
                shrinks = shrink_problems(counts, before)
                for issue in shrinks:
                    log(f"  Shrink guard: {issue}")
                if dry_run:
                    return {name: (before[name], counts[name]) for name in names}
                if problems:
                    raise ValueError("Neon schema preflight failed; apply the reviewed migration first")
                if shrinks and not allow_shrink:
                    raise ValueError("Refusing to publish because the row-count shrink guard failed: "
                                     + "; ".join(shrinks))
                for name in names:
                    _replace(cursor, name, code, season_code, spools[name], plans.get(name))
                    after = _count(cursor, name, code, season_code, "public")
                    if after != counts[name]:
                        raise RuntimeError(f"{target_name(name)}: Neon has {after:,} rows, "
                                           f"expected {counts[name]:,}; transaction rolled back")
        return {name: (before[name], counts[name]) for name in names}
    finally:
        for spool in spools.values():
            spool.close()
        if dry_run:
            neon.set_session(readonly=False)

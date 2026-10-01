"""Publish one EuroLeague season and selected global Gold tables to Neon."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.db import connect  # noqa: E402
from gold_etl.main import main as gold_main  # noqa: E402
from neon_publish.contract import (APP_TABLES, GLOBAL_TABLES, MIGRATIONS,  # noqa: E402
                                    migration_sql, target_name)
from neon_publish.publish import neon_connect, publish_season  # noqa: E402
from pipeline import season_code_for  # noqa: E402


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-sc", "--season-code", default="current")
    parser.add_argument("-tb", "--table", nargs="+", default=["all"])
    parser.add_argument("--list-tables", action="store_true")
    parser.add_argument("--print-migration", nargs="?", const="30g", choices=sorted(MIGRATIONS),
                        help="Print the reviewed DDL for the tables added in 30g (default) "
                        "or 30h; no database.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-shrink", action="store_true")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_tables:
        for name in APP_TABLES:
            print(f"gold.{name} -> public.{target_name(name)} "
                  f"({'competition' if name in GLOBAL_TABLES else 'season'})")
        return 0
    if args.print_migration:
        print(migration_sql(MIGRATIONS[args.print_migration], args.print_migration), end="")
        return 0
    if args.table == ["all"]:
        names = APP_TABLES
    else:
        unknown = set(args.table) - set(APP_TABLES)
        if unknown or "all" in args.table:
            parser.error("Unknown or mixed table selection: " + ", ".join(sorted(unknown)))
        names = tuple(dict.fromkeys(args.table))
    try:
        season = season_code_for("euroleague", args.season_code)
    except ValueError as error:
        parser.error(str(error))
    local = neon = None
    try:
        local = connect()
        with local.cursor() as cursor:
            cursor.execute("SELECT 1 FROM silver.seasons WHERE competition_code = %s "
                           "AND season_code = %s", ("E", season))
            if cursor.fetchone() is None:
                raise ValueError(f"{season} is not loaded in Silver")
        local.rollback()
        if not args.dry_run:
            if gold_main(["-sc", season, "-tb", *names, "--quality-only"]):
                raise ValueError("Gold quality failed; Neon unchanged")
        neon = neon_connect()
        results = publish_season(local, neon, "euroleague", season, names,
                                 dry_run=args.dry_run, allow_shrink=args.allow_shrink)
        for name, (before, after) in results.items():
            old = "unavailable" if before is None else f"{before:,}"
            print(f"  {target_name(name)}: {old} -> {after:,} rows")
        print(f"Season {season} {'checked (Neon unchanged)' if args.dry_run else 'committed'}")
        return 0
    except Exception as error:
        # libpq errors may contain the connection string. Show the class only.
        detail = str(error) if isinstance(error, (ValueError, RuntimeError)) else "database operation failed"
        print(f"Publish failed ({type(error).__name__}): {detail}", file=sys.stderr)
        return 1
    finally:
        if neon is not None:
            neon.close()
        if local is not None:
            local.close()


if __name__ == "__main__":
    sys.exit(main())
